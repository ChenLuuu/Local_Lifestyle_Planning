"""Unit tests for F12: 商业化触点植入 — deal_matcher."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from agent.schemas import (
    DealsMatchRequest,
    DealsMatchResponse,
    Itinerary,
    ItineraryNode,
)
from agent.tools.deal_matcher import _find_deals_for_node, match_deals
from agent.tools.mock_data import get_deal_pool


# ── Helpers ───────────────────────────────────────────────────────────────────

def _node(node_id: str, node_type: str, name: str = "测试地点") -> ItineraryNode:
    return ItineraryNode(
        node_id=node_id,
        node_type=node_type,
        name=name,
        address="北京市朝阳区",
        start_time="10:00",
        end_time="12:00",
        duration_min=120,
        per_capita=100,
    )


def _itinerary(*nodes: ItineraryNode) -> Itinerary:
    return Itinerary(
        session_id=str(uuid4()),
        nodes=list(nodes),
        total_duration_min=sum(n.duration_min for n in nodes),
        total_per_capita=sum(n.per_capita for n in nodes),
    )


# ── Mock data pool tests ───────────────────────────────────────────────────────

def test_deal_pool_not_empty() -> None:
    assert len(get_deal_pool()) > 0


def test_deal_pool_has_venue_specific_deals() -> None:
    pool = get_deal_pool()
    assert any("v001" in d.node_ids for d in pool)


def test_deal_pool_has_restaurant_specific_deals() -> None:
    pool = get_deal_pool()
    assert any("r001" in d.node_ids for d in pool)


def test_deal_pool_has_wildcard_deals() -> None:
    pool = get_deal_pool()
    assert any(not d.node_ids for d in pool)


def test_deal_savings_positive() -> None:
    for d in get_deal_pool():
        assert d.savings > 0
        assert d.savings == d.original_price - d.deal_price


# ── _find_deals_for_node unit tests ───────────────────────────────────────────

def test_exact_match_venue_v001() -> None:
    pool = get_deal_pool()
    deals = _find_deals_for_node("v001", "venue", pool)
    assert len(deals) >= 1
    assert any("迪士尼" in d.title for d in deals)


def test_exact_match_restaurant_r001() -> None:
    pool = get_deal_pool()
    deals = _find_deals_for_node("r001", "restaurant", pool)
    assert len(deals) >= 1
    assert any("海底捞" in d.title for d in deals)


def test_exact_match_restaurant_r002() -> None:
    pool = get_deal_pool()
    deals = _find_deals_for_node("r002", "restaurant", pool)
    assert len(deals) >= 1
    assert any("南京大牌档" in d.title for d in deals)


def test_max_2_deals_per_node() -> None:
    pool = get_deal_pool()
    # v001 has an exact deal + a wildcard fallback
    deals = _find_deals_for_node("v001", "venue", pool)
    assert len(deals) <= 2


def test_wildcard_fallback_for_unknown_venue() -> None:
    pool = get_deal_pool()
    deals = _find_deals_for_node("v999", "venue", pool)
    # No exact match — should fall back to wildcard 景点 deals
    assert len(deals) >= 1
    assert all(d.category == "景点" for d in deals)


def test_wildcard_fallback_for_unknown_restaurant() -> None:
    pool = get_deal_pool()
    deals = _find_deals_for_node("r999", "restaurant", pool)
    assert len(deals) >= 1
    assert all(d.category == "餐饮" for d in deals)


def test_deal_item_fields_populated() -> None:
    pool = get_deal_pool()
    deals = _find_deals_for_node("r001", "restaurant", pool)
    d = deals[0]
    assert d.id
    assert d.title
    assert d.original_price > 0
    assert d.deal_price > 0
    assert d.savings > 0
    assert d.coupon_type
    assert d.valid_days > 0


# ── match_deals integration tests ─────────────────────────────────────────────

def test_match_deals_single_venue_node() -> None:
    req = DealsMatchRequest(itinerary=_itinerary(_node("v001", "venue", "欢乐谷")))
    resp: DealsMatchResponse = asyncio.new_event_loop().run_until_complete(match_deals(req))
    assert resp.total_savings > 0
    assert len(resp.node_deals) == 1
    assert resp.node_deals[0].node_id == "v001"


def test_match_deals_single_restaurant_node() -> None:
    req = DealsMatchRequest(itinerary=_itinerary(_node("r008", "restaurant", "本味鲜森")))
    resp = asyncio.new_event_loop().run_until_complete(match_deals(req))
    assert resp.total_savings > 0
    assert any("本味鲜森" in d.title or d.savings > 0 for d in resp.node_deals[0].deals)


def test_match_deals_multiple_nodes_accumulates_savings() -> None:
    itin = _itinerary(
        _node("v001", "venue", "欢乐谷"),
        _node("r001", "restaurant", "海底捞"),
    )
    req = DealsMatchRequest(itinerary=itin)
    resp = asyncio.new_event_loop().run_until_complete(match_deals(req))
    assert len(resp.node_deals) == 2
    # Total savings == sum of per-node savings
    assert resp.total_savings == sum(nd.total_savings for nd in resp.node_deals)


def test_match_deals_summary_text_with_savings() -> None:
    req = DealsMatchRequest(itinerary=_itinerary(_node("r001", "restaurant", "海底捞")))
    resp = asyncio.new_event_loop().run_until_complete(match_deals(req))
    assert "节省" in resp.summary
    assert str(resp.total_savings) in resp.summary


def test_match_deals_preserves_session_id() -> None:
    itin = _itinerary(_node("v002", "venue", "故宫"))
    req = DealsMatchRequest(itinerary=itin)
    resp = asyncio.new_event_loop().run_until_complete(match_deals(req))
    assert resp.session_id == itin.session_id


def test_match_deals_empty_itinerary() -> None:
    itin = Itinerary(
        session_id=str(uuid4()), nodes=[], total_duration_min=0, total_per_capita=0
    )
    req = DealsMatchRequest(itinerary=itin)
    resp = asyncio.new_event_loop().run_until_complete(match_deals(req))
    assert resp.total_savings == 0
    assert resp.node_deals == []
    assert "暂无" in resp.summary


def test_match_deals_business_dinner_scenario() -> None:
    """商务宴请: 蟹天下应匹配高端套餐."""
    req = DealsMatchRequest(itinerary=_itinerary(_node("r006", "restaurant", "蟹天下")))
    resp = asyncio.new_event_loop().run_until_complete(match_deals(req))
    assert resp.total_savings >= 302   # d012 savings


def test_match_deals_family_outing_scenario() -> None:
    """亲子出行: 欢乐水魔方家庭票应匹配."""
    req = DealsMatchRequest(itinerary=_itinerary(_node("v009", "venue", "欢乐水魔方")))
    resp = asyncio.new_event_loop().run_until_complete(match_deals(req))
    assert resp.total_savings >= 160   # d006 savings
