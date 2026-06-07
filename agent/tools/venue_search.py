"""Tool: search for activity venues matching a ConstraintSet."""

from __future__ import annotations

import asyncio
import math

from agent.schemas import ConstraintSet, VenueResult
from agent.tools.mock_data import get_venue_pool, maybe_inject_fault

# Reference point for distance filtering — Shanghai city center
_CENTER_LAT = 31.2304
_CENTER_LNG = 121.4737


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


async def venue_search(
    constraint_set: ConstraintSet, limit: int = 10
) -> list[VenueResult]:
    """Return venues passing hard distance constraint, unscored (LLM will score).

    Raises ToolFaultError at 10% probability — must be caught by fault_handlers.
    """
    await asyncio.sleep(0)
    maybe_inject_fault("venue_search")

    max_dist = constraint_set.hard.max_distance_km
    filtered = [
        v for v in get_venue_pool()
        if _haversine_km(_CENTER_LAT, _CENTER_LNG, v.lat, v.lng) <= max_dist
    ]
    return [
        VenueResult(
            id=v.id,
            name=v.name,
            venue_type=v.venue_type,
            address=v.address,
            per_capita=v.per_capita,
            duration_min=v.duration_min,
            tags=v.tags,
            noise_level=v.noise_level,
            lat=v.lat,
            lng=v.lng,
        )
        for v in filtered[:limit]
    ]
