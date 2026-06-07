"""Router: batch-execute bookings — POST /api/execute (SSE).

All confirmed itinerary nodes are booked concurrently via asyncio.
Progress is streamed as Server-Sent Events: start → booking (×N) → complete.
Fault handling: ToolFaultError caught here (not inside the tool) per CLAUDE.md rule.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from agent.schemas import ExecuteRequest, ItineraryNode
from agent.tools.execute_booking import BookingRecord, book_node
from agent.tools.mock_data import ToolFaultError

router = APIRouter(prefix="/api", tags=["execute"])


@router.post("/execute")
async def execute_bookings(body: ExecuteRequest) -> EventSourceResponse:
    """Book all confirmed nodes concurrently; stream per-node status via SSE."""

    async def _event_gen() -> AsyncGenerator[dict[str, str], None]:
        nodes = body.itinerary.nodes
        idem_key = body.idempotency_key

        yield {"data": json.dumps(
            {"type": "start", "session_id": body.session_id, "total": len(nodes)},
            ensure_ascii=False,
        )}

        async def _book_with_index(
            node: ItineraryNode, idx: int
        ) -> tuple[int, BookingRecord]:
            try:
                record = await book_node(node, idem_key)
            except ToolFaultError as exc:
                record = BookingRecord(
                    node_id=node.node_id,
                    name=node.name,
                    status="failed",
                    order_id="",
                    message=(
                        f"{node.name} 预订失败：{exc}；"
                        "trigger partial_replan for level 1 replacement"
                    ),
                )
            return idx, record

        tasks = [
            asyncio.create_task(_book_with_index(n, i))
            for i, n in enumerate(nodes)
        ]

        results: dict[int, BookingRecord] = {}
        for fut in asyncio.as_completed(tasks):
            idx, record = await fut
            results[idx] = record
            yield {"data": json.dumps(
                {
                    "type": "booking",
                    "index": idx,
                    "node_id": record.node_id,
                    "name": record.name,
                    "status": record.status,
                    "order_id": record.order_id,
                    "message": record.message,
                },
                ensure_ascii=False,
            )}

        all_records = [results[i] for i in range(len(nodes))]
        successes = [r for r in all_records if r.status == "success"]
        failures = [r for r in all_records if r.status == "failed"]

        if successes:
            items = "、".join(r.name for r in successes)
            text = f"行程确认！已为您成功预订 {len(successes)} 项：{items}。"
            if failures:
                failed_names = "、".join(r.name for r in failures)
                text += f"以下 {len(failures)} 项预订失败，建议手动确认：{failed_names}"
        else:
            text = "所有预订均失败，请检查网络后重试。"

        yield {"data": json.dumps(
            {
                "type": "complete",
                "session_id": body.session_id,
                "success_count": len(successes),
                "failed_count": len(failures),
                "confirmation_text": text,
            },
            ensure_ascii=False,
        )}
        yield {"data": "[DONE]"}

    return EventSourceResponse(_event_gen())
