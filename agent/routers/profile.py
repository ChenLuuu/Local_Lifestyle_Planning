"""Router: user profile management."""

from fastapi import APIRouter, HTTPException

from agent.modules.preference_extractor import extract_preferences
from agent.modules.profile_store import get_profile, merge_tags
from agent.schemas import (
    ExtractPreferencesRequest,
    ExtractPreferencesResponse,
    UserProfile,
)

router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.get("/{user_id}", response_model=UserProfile)
async def get_user_profile(user_id: str) -> UserProfile:
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    return get_profile(user_id)


@router.post("/extract", response_model=ExtractPreferencesResponse)
async def extract_and_save(
    body: ExtractPreferencesRequest,
) -> ExtractPreferencesResponse:
    """Extract preferences from free text and merge into user profile."""
    tags, summary = await extract_preferences(body.free_text)
    profile = merge_tags(body.user_id, tags, note=body.free_text)
    return ExtractPreferencesResponse(
        extracted_tags=tags,
        summary=summary,
        profile=profile,
    )
