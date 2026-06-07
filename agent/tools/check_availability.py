"""Tool: check seat/ticket availability for a venue or restaurant (serial calls)."""

from __future__ import annotations

import asyncio
import random

from agent.schemas import AvailabilityResult
from agent.tools.mock_data import maybe_inject_fault

_TIME_SLOTS = [
    "10:00", "11:00", "13:00", "14:00",
    "15:00", "16:00", "17:00", "18:00", "19:00",
]


async def check_availability(item_id: str, time_slot: str) -> AvailabilityResult:
    """Check whether a venue/restaurant has availability at the given time_slot.

    Serial — called one-by-one in the ReAct loop.
    Raises ToolFaultError at 10% probability — never caught here.
    """
    await asyncio.sleep(0)
    maybe_inject_fault("check_availability")

    available = random.random() > 0.2  # noqa: S311 — intentional mock simulation
    next_slot: str | None = None
    if not available:
        candidates = [s for s in _TIME_SLOTS if s > time_slot]
        next_slot = candidates[0] if candidates else None

    return AvailabilityResult(
        item_id=item_id,
        available=available,
        next_slot=next_slot,
    )
