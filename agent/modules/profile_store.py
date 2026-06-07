"""In-memory user profile store keyed by user_id.

Persists for the lifetime of the server process. Fine for demo purposes.
"""

from __future__ import annotations

from agent.schemas import UserProfile

_store: dict[str, UserProfile] = {}

XIAOTUAN_ID = "xiaotuan_001"

# Seed the hardcoded demo user
_store[XIAOTUAN_ID] = UserProfile(
    user_id=XIAOTUAN_ID,
    name="小团",
    avatar="🐻",
)


def get_profile(user_id: str) -> UserProfile:
    if user_id not in _store:
        _store[user_id] = UserProfile(user_id=user_id)
    return _store[user_id]


def save_profile(profile: UserProfile) -> None:
    _store[profile.user_id] = profile


def merge_tags(user_id: str, new_tags: list[str], note: str = "") -> UserProfile:
    """Add new preference tags to a user profile (deduplicating) and save."""
    profile = get_profile(user_id)
    existing = set(profile.preference_tags)
    for tag in new_tags:
        existing.add(tag)
    profile.preference_tags = sorted(existing)
    if note and note not in profile.raw_notes:
        profile.raw_notes = [*profile.raw_notes, note]
    if profile.preference_tags:
        profile.preference_summary = "偏好：" + "、".join(profile.preference_tags)
    save_profile(profile)
    return profile
