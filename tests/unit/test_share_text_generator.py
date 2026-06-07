"""Unit tests for F13: social share text generation."""

from __future__ import annotations

import asyncio

import pytest

from agent.schemas import (
    Itinerary,
    ItineraryNode,
    ShareTextRequest,
    ShareTextResponse,
    TransitInfo,
)
from agent.tools.generate_share_text import (
    _CLOSINGS,
    _HASHTAGS,
    _OPENINGS,
    _TITLES,
    _build_body,
    _card_line,
    _node_summary,
    generate_share_text,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

_TRANSIT = TransitInfo(mode="地铁", duration_min=15, distance_km=4.5)


def _make_node(
    node_id: str = "v001",
    node_type: str = "venue",
    name: str = "欢乐谷",
    start_time: str = "10:00",
    end_time: str = "14:00",
    duration_min: int = 240,
    per_capita: int = 200,
    transit_to_next: TransitInfo | None = None,
) -> ItineraryNode:
    return ItineraryNode(
        node_id=node_id,
        node_type=node_type,
        name=name,
        address="朝阳区",
        start_time=start_time,
        end_time=end_time,
        duration_min=duration_min,
        per_capita=per_capita,
        transit_to_next=transit_to_next,
    )


def _make_itinerary(nodes: list[ItineraryNode] | None = None) -> Itinerary:
    if nodes is None:
        nodes = [
            _make_node("v001", "venue", "欢乐谷", "10:00", "14:00", 240, 200, _TRANSIT),
            _make_node("r001", "restaurant", "海底捞", "14:30", "16:00", 90, 150),
        ]
    total_min = sum(n.duration_min for n in nodes)
    total_pc = sum(n.per_capita for n in nodes)
    return Itinerary(
        session_id="test-session-001",
        nodes=nodes,
        total_duration_min=total_min,
        total_per_capita=total_pc,
    )


# ── Helper function unit tests ─────────────────────────────────────────────────


def test_card_line_format() -> None:
    node = _make_node(start_time="10:00", name="欢乐谷", node_type="venue")
    line = _card_line(node)
    assert "10:00" in line
    assert "欢乐谷" in line
    assert "venue" in line


def test_card_line_restaurant() -> None:
    node = _make_node(node_type="restaurant", name="海底捞", start_time="14:30")
    line = _card_line(node)
    assert "14:30" in line
    assert "海底捞" in line
    assert "restaurant" in line


def test_node_summary_family_venue() -> None:
    node = _make_node(node_type="venue", name="故宫", per_capita=60)
    summary = _node_summary(node, "family")
    assert "故宫" in summary
    assert "60" in summary
    assert "老人" in summary or "全家" in summary


def test_node_summary_girlfriends_venue() -> None:
    node = _make_node(node_type="venue", name="798艺术区")
    summary = _node_summary(node, "girlfriends")
    assert "798艺术区" in summary
    assert "出片" in summary


def test_node_summary_bros_restaurant() -> None:
    node = _make_node(node_type="restaurant", name="胡大饭馆")
    summary = _node_summary(node, "bros")
    assert "胡大饭馆" in summary
    assert "浪" in summary or "吃" in summary


def test_node_summary_unknown_type_fallback() -> None:
    node = _make_node(node_type="other_type", name="测试地点")
    summary = _node_summary(node, "family")
    assert "测试地点" in summary


def test_build_body_contains_opening(
) -> None:
    itin = _make_itinerary()
    body = _build_body(itin, "family")
    assert _OPENINGS["family"] in body


def test_build_body_contains_all_node_names() -> None:
    itin = _make_itinerary()
    body = _build_body(itin, "girlfriends")
    for node in itin.nodes:
        assert node.name in body


def test_build_body_contains_closing() -> None:
    itin = _make_itinerary()
    body = _build_body(itin, "bros")
    assert _CLOSINGS["bros"] in body


def test_build_body_contains_duration() -> None:
    itin = _make_itinerary()
    body = _build_body(itin, "family")
    assert "小时" in body


def test_build_body_contains_per_capita() -> None:
    itin = _make_itinerary()
    body = _build_body(itin, "family")
    assert str(itin.total_per_capita) in body


# ── generate_share_text async tests ──────────────────────────────────────────


@pytest.mark.parametrize("audience", ["family", "girlfriends", "bros"])
def test_returns_share_text_response(audience: str) -> None:
    itin = _make_itinerary()
    req = ShareTextRequest(itinerary=itin, audience=audience)
    result = asyncio.run(generate_share_text(req))
    assert isinstance(result, ShareTextResponse)


@pytest.mark.parametrize("audience", ["family", "girlfriends", "bros"])
def test_title_matches_audience(audience: str) -> None:
    itin = _make_itinerary()
    req = ShareTextRequest(itinerary=itin, audience=audience)
    result = asyncio.run(generate_share_text(req))
    assert result.title == _TITLES[audience]


@pytest.mark.parametrize("audience", ["family", "girlfriends", "bros"])
def test_hashtags_match_audience(audience: str) -> None:
    itin = _make_itinerary()
    req = ShareTextRequest(itinerary=itin, audience=audience)
    result = asyncio.run(generate_share_text(req))
    assert result.hashtags == _HASHTAGS[audience]


@pytest.mark.parametrize("audience", ["family", "girlfriends", "bros"])
def test_session_id_preserved(audience: str) -> None:
    itin = _make_itinerary()
    req = ShareTextRequest(itinerary=itin, audience=audience)
    result = asyncio.run(generate_share_text(req))
    assert result.session_id == "test-session-001"


@pytest.mark.parametrize("audience", ["family", "girlfriends", "bros"])
def test_audience_field_preserved(audience: str) -> None:
    itin = _make_itinerary()
    req = ShareTextRequest(itinerary=itin, audience=audience)
    result = asyncio.run(generate_share_text(req))
    assert result.audience == audience


def test_card_lines_count_matches_nodes() -> None:
    itin = _make_itinerary()
    req = ShareTextRequest(itinerary=itin, audience="family")
    result = asyncio.run(generate_share_text(req))
    assert len(result.card_lines) == len(itin.nodes)


def test_card_lines_contain_node_names() -> None:
    itin = _make_itinerary()
    req = ShareTextRequest(itinerary=itin, audience="bros")
    result = asyncio.run(generate_share_text(req))
    for i, node in enumerate(itin.nodes):
        assert node.name in result.card_lines[i]


def test_single_node_itinerary() -> None:
    single = [_make_node("v002", "venue", "故宫", "10:00", "13:00", 180, 60)]
    itin = _make_itinerary(single)
    req = ShareTextRequest(itinerary=itin, audience="family")
    result = asyncio.run(generate_share_text(req))
    assert len(result.card_lines) == 1
    assert "故宫" in result.body


def test_body_is_non_empty_string() -> None:
    itin = _make_itinerary()
    req = ShareTextRequest(itinerary=itin, audience="girlfriends")
    result = asyncio.run(generate_share_text(req))
    assert isinstance(result.body, str) and len(result.body) > 50


def test_hashtags_are_non_empty_list() -> None:
    itin = _make_itinerary()
    req = ShareTextRequest(itinerary=itin, audience="bros")
    result = asyncio.run(generate_share_text(req))
    assert isinstance(result.hashtags, list) and len(result.hashtags) >= 1
