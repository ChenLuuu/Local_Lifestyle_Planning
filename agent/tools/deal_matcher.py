"""Tool: match Meituan group-buy deals and coupons to itinerary nodes.

Matching priority per node:
  1. Exact match by node_id in deal.node_ids (venue/restaurant-specific deal)
  2. Fallback: category-level deal (deal.node_ids == [] acts as wildcard for
     all nodes of that category)

At most 2 deals are attached per node to keep the UI tidy.
No fault injection — deal matching is a read-only catalogue lookup.
"""

from __future__ import annotations

import asyncio

from agent.schemas import (
    DealItem,
    DealsMatchRequest,
    DealsMatchResponse,
    NodeDeal,
)
from agent.tools.mock_data import MockDealData, get_deal_pool

_CATEGORY_FOR_NODE_TYPE: dict[str, str] = {
    "restaurant": "餐饮",
    "venue": "景点",
}


def _to_deal_item(d: MockDealData) -> DealItem:
    return DealItem(
        id=d.id,
        title=d.title,
        original_price=d.original_price,
        deal_price=d.deal_price,
        savings=d.savings,
        category=d.category,
        coupon_type=d.coupon_type,
        valid_days=d.valid_days,
    )


def _find_deals_for_node(
    node_id: str, node_type: str, pool: list[MockDealData]
) -> list[DealItem]:
    category = _CATEGORY_FOR_NODE_TYPE.get(node_type, "景点")
    exact: list[DealItem] = []
    fallback: list[DealItem] = []
    for d in pool:
        if node_id in d.node_ids:
            exact.append(_to_deal_item(d))
        elif not d.node_ids and d.category == category:
            fallback.append(_to_deal_item(d))
    return (exact + fallback)[:2]


async def match_deals(request: DealsMatchRequest) -> DealsMatchResponse:
    """Return deals matched to each itinerary node."""
    await asyncio.sleep(0)
    pool = get_deal_pool()
    node_deals: list[NodeDeal] = []
    for node in request.itinerary.nodes:
        deals = _find_deals_for_node(node.node_id, node.node_type, pool)
        node_deals.append(NodeDeal(
            node_id=node.node_id,
            node_name=node.name,
            deals=deals,
            total_savings=sum(d.savings for d in deals),
        ))
    total = sum(nd.total_savings for nd in node_deals)
    return DealsMatchResponse(
        session_id=request.itinerary.session_id,
        node_deals=node_deals,
        total_savings=total,
        summary=f"已为您节省 {total} 元" if total > 0 else "暂无可用优惠券",
    )
