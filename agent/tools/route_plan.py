"""Tool: estimate transit route between two addresses."""

from __future__ import annotations

import asyncio
import math

from agent.schemas import RouteResult
from agent.tools.mock_data import make_route, maybe_inject_fault


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Approximate great-circle distance in km."""
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(
        math.radians(lat2)
    ) * math.sin(dlng / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


async def route_plan(
    from_lat: float,
    from_lng: float,
    from_address: str,
    to_lat: float,
    to_lng: float,
    to_address: str,
) -> RouteResult:
    """Estimate transit mode and duration between two geo points.

    Raises ToolFaultError at 10% probability — never caught here.
    """
    await asyncio.sleep(0)
    maybe_inject_fault("route_plan")

    distance_km = _haversine(from_lat, from_lng, to_lat, to_lng)
    route = make_route(from_address, to_address, distance_km)
    return RouteResult(
        from_address=route.from_address,
        to_address=route.to_address,
        distance_km=route.distance_km,
        duration_min=route.duration_min,
        transit_mode=route.transit_mode,
    )
