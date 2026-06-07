"""Tool: book a single node via Mock API (idempotency key, never cached).

execute_booking results are NEVER cached via CachedLayer (hard constraint 7).
Idempotency is enforced via a module-level store keyed by "{idempotency_key}:{node_id}".
Only successful bookings are stored; failed ones are retried on the next call.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Literal

from agent.schemas import ItineraryNode
from agent.tools.mock_data import maybe_inject_fault


@dataclass
class BookingRecord:
    node_id: str
    name: str
    status: Literal["success", "failed"]
    order_id: str
    message: str


# Keyed by "{idempotency_key}:{node_id}".
# Prevents duplicate orders on retry without going through CachedLayer.
_idempotency_store: dict[str, BookingRecord] = {}


async def book_node(node: ItineraryNode, idempotency_key: str) -> BookingRecord:
    """Book a single itinerary node via Mock API.

    Returns cached BookingRecord for idempotent retries (same key + node_id).
    Raises ToolFaultError at 10% probability — caller must handle; never caught here.
    """
    cache_key = f"{idempotency_key}:{node.node_id}"
    if cache_key in _idempotency_store:
        return _idempotency_store[cache_key]

    await asyncio.sleep(0)
    maybe_inject_fault(f"execute_booking:{node.node_type}")

    order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
    record = BookingRecord(
        node_id=node.node_id,
        name=node.name,
        status="success",
        order_id=order_id,
        message=f"{node.name} 预订成功，订单号 {order_id}",
    )
    _idempotency_store[cache_key] = record
    return record
