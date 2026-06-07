"""Router: user authentication — fixed demo login as 小团."""

from fastapi import APIRouter

from agent.modules.profile_store import XIAOTUAN_ID, get_profile
from agent.schemas import LoginResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login() -> LoginResponse:
    """Return 小团's profile. Demo: no credentials required."""
    profile = get_profile(XIAOTUAN_ID)
    return LoginResponse(
        user_id=profile.user_id,
        name=profile.name,
        avatar=profile.avatar,
        preference_tags=profile.preference_tags,
        preference_summary=profile.preference_summary,
        is_returning=bool(profile.preference_tags),
    )
