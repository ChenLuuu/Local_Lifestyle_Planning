"""Router: POST /api/deals/match — match group-buy deals to an itinerary."""

from __future__ import annotations

from fastapi import APIRouter

from agent.schemas import DealsMatchRequest, DealsMatchResponse
from agent.tools.deal_matcher import match_deals

router = APIRouter(prefix="/api/deals", tags=["deals"])


@router.post("/match", response_model=DealsMatchResponse)
async def deals_match(request: DealsMatchRequest) -> DealsMatchResponse:
    """Return Meituan group-buy deals and coupons matched to each itinerary node."""
    return await match_deals(request)
