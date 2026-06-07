"""Router: POST /api/share/text — generate social share copy for an itinerary."""

from __future__ import annotations

from fastapi import APIRouter

from agent.schemas import ShareTextRequest, ShareTextResponse
from agent.tools.generate_share_text import generate_share_text

router = APIRouter(prefix="/api/share", tags=["share"])


@router.post("/text", response_model=ShareTextResponse)
async def share_text(request: ShareTextRequest) -> ShareTextResponse:
    """Return audience-adapted social share copy for a confirmed itinerary."""
    return await generate_share_text(request)
