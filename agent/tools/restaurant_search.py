"""Tool: search for restaurants matching a ConstraintSet."""

from __future__ import annotations

import asyncio
import math

from agent.schemas import ConstraintSet, RestaurantResult
from agent.tools.mock_data import get_restaurant_pool, maybe_inject_fault

# Reference point for distance filtering — Shanghai city center
_CENTER_LAT = 31.2304
_CENTER_LNG = 121.4737


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


async def restaurant_search(
    constraint_set: ConstraintSet, limit: int = 8
) -> list[RestaurantResult]:
    """Return restaurants passing hard distance constraint, unscored (LLM will score).

    Raises ToolFaultError at 10% probability — never caught here.
    """
    await asyncio.sleep(0)
    maybe_inject_fault("restaurant_search")

    max_dist = constraint_set.hard.max_distance_km
    filtered = [
        r for r in get_restaurant_pool()
        if _haversine_km(_CENTER_LAT, _CENTER_LNG, r.lat, r.lng) <= max_dist
    ]
    return [
        RestaurantResult(
            id=r.id,
            name=r.name,
            cuisine=r.cuisine,
            address=r.address,
            per_capita=r.per_capita,
            duration_min=r.duration_min,
            tags=r.tags,
            noise_level=r.noise_level,
            lat=r.lat,
            lng=r.lng,
        )
        for r in filtered[:limit]
    ]
