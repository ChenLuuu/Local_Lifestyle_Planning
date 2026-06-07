"""E2E tests for F06: batch-execute bookings.

Verification command: pytest tests/e2e/test_execute_booking.py -v
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from agent.main import app
from agent.schemas import (
    ExecuteRequest,
    Itinerary,
    ItineraryNode,
    TransitInfo,
)
from agent.tools import execute_booking as _eb_mod


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def two_node_itinerary() -> Itinerary:
    return Itinerary(
        session_id="e2e-exec-sess",
        nodes=[
            ItineraryNode(
                node_id="v003",
                node_type="venue",
                name="798艺术区",
                address="朝阳区酒仙桥路4号",
                start_time="10:00",
                end_time="12:00",
                duration_min=120,
                per_capita=0,
                transit_to_next=TransitInfo(mode="地铁", duration_min=15, distance_km=3.0),
            ),
            ItineraryNode(
                node_id="r004",
                node_type="restaurant",
                name="云海肴（三里屯店）",
                address="朝阳区三里屯太古里南区S3-03",
                start_time="12:15",
                end_time="13:30",
                duration_min=75,
                per_capita=120,
                transit_to_next=None,
            ),
        ],
        total_duration_min=210,
        total_per_capita=120,
    )


@pytest.fixture(autouse=True)
def _clear_idempotency_store() -> None:
    """Reset the module-level idempotency store before each test."""
    _eb_mod._idempotency_store.clear()


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _post_execute_sse(payload: dict) -> list[dict]:  # type: ignore[type-arg]
    """POST /api/execute and collect all non-DONE SSE data lines as parsed dicts."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        async with client.stream(
            "POST",
            "/api/execute",
            json=payload,
            headers={"Accept": "text/event-stream"},
        ) as resp:
            events = []
            async for line in resp.aiter_lines():
                if line.startswith("data: ") and line != "data: [DONE]":
                    events.append(json.loads(line[len("data: "):]))
    return events


# ── Unit-level: book_node ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_book_node_success_returns_success_status(
    two_node_itinerary: Itinerary,
) -> None:
    """book_node without faults must return a record with status='success'."""
    node = two_node_itinerary.nodes[0]
    with patch("agent.tools.mock_data.random") as mock_rand:
        mock_rand.random.return_value = 0.5  # no fault
        record = await _eb_mod.book_node(node, f"key-{uuid.uuid4()}")
    assert record.status == "success"
    assert record.node_id == node.node_id
    assert record.name == node.name


@pytest.mark.asyncio
async def test_book_node_success_has_non_empty_order_id(
    two_node_itinerary: Itinerary,
) -> None:
    """A successful booking must produce a non-empty order_id."""
    node = two_node_itinerary.nodes[0]
    with patch("agent.tools.mock_data.random") as mock_rand:
        mock_rand.random.return_value = 0.5
        record = await _eb_mod.book_node(node, f"key-{uuid.uuid4()}")
    assert record.order_id != ""
    assert record.order_id.startswith("ORD-")


@pytest.mark.asyncio
async def test_book_node_fault_raises_tool_fault_error(
    two_node_itinerary: Itinerary,
) -> None:
    """book_node must propagate ToolFaultError when fault is injected — never swallowed."""
    from agent.tools.mock_data import ToolFaultError

    node = two_node_itinerary.nodes[0]
    with patch("agent.tools.mock_data.random") as mock_rand:
        mock_rand.random.return_value = 0.0  # always fault
        with pytest.raises(ToolFaultError):
            await _eb_mod.book_node(node, f"key-{uuid.uuid4()}")


@pytest.mark.asyncio
async def test_book_node_idempotency_same_key_same_order_id(
    two_node_itinerary: Itinerary,
) -> None:
    """Calling book_node twice with the same idempotency_key must return the same order_id."""
    node = two_node_itinerary.nodes[0]
    key = f"idem-{uuid.uuid4()}"
    with patch("agent.tools.mock_data.random") as mock_rand:
        mock_rand.random.return_value = 0.5
        r1 = await _eb_mod.book_node(node, key)
        r2 = await _eb_mod.book_node(node, key)
    assert r1.order_id == r2.order_id
    assert r1.status == r2.status == "success"


@pytest.mark.asyncio
async def test_book_node_different_keys_produce_different_order_ids(
    two_node_itinerary: Itinerary,
) -> None:
    """Different idempotency keys must each produce a fresh order_id."""
    node = two_node_itinerary.nodes[0]
    with patch("agent.tools.mock_data.random") as mock_rand:
        mock_rand.random.return_value = 0.5
        r1 = await _eb_mod.book_node(node, f"key-a-{uuid.uuid4()}")
        r2 = await _eb_mod.book_node(node, f"key-b-{uuid.uuid4()}")
    assert r1.order_id != r2.order_id


# ── HTTP endpoint: SSE structure ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_endpoint_returns_200(two_node_itinerary: Itinerary) -> None:
    """POST /api/execute must return HTTP 200."""
    payload = ExecuteRequest(
        session_id="e2e-200-test",
        itinerary=two_node_itinerary,
    )
    with patch("agent.tools.mock_data.random") as mock_rand:
        mock_rand.random.return_value = 0.5
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            async with client.stream("POST", "/api/execute", json=payload.model_dump()) as resp:
                assert resp.status_code == 200
                await resp.aread()


@pytest.mark.asyncio
async def test_execute_emits_start_event(two_node_itinerary: Itinerary) -> None:
    """First SSE event must be type='start' with total equal to node count."""
    payload = ExecuteRequest(
        session_id="e2e-start-test",
        itinerary=two_node_itinerary,
    )
    with patch("agent.tools.mock_data.random") as mock_rand:
        mock_rand.random.return_value = 0.5
        events = await _post_execute_sse(payload.model_dump())

    assert events[0]["type"] == "start"
    assert events[0]["total"] == len(two_node_itinerary.nodes)
    assert events[0]["session_id"] == "e2e-start-test"


@pytest.mark.asyncio
async def test_execute_emits_booking_event_per_node(two_node_itinerary: Itinerary) -> None:
    """There must be exactly N booking events, one per itinerary node."""
    payload = ExecuteRequest(
        session_id="e2e-booking-count",
        itinerary=two_node_itinerary,
    )
    with patch("agent.tools.mock_data.random") as mock_rand:
        mock_rand.random.return_value = 0.5
        events = await _post_execute_sse(payload.model_dump())

    booking_events = [e for e in events if e["type"] == "booking"]
    assert len(booking_events) == len(two_node_itinerary.nodes)


@pytest.mark.asyncio
async def test_execute_emits_complete_event(two_node_itinerary: Itinerary) -> None:
    """Last SSE event must be type='complete'."""
    payload = ExecuteRequest(
        session_id="e2e-complete-test",
        itinerary=two_node_itinerary,
    )
    with patch("agent.tools.mock_data.random") as mock_rand:
        mock_rand.random.return_value = 0.5
        events = await _post_execute_sse(payload.model_dump())

    assert events[-1]["type"] == "complete"


@pytest.mark.asyncio
async def test_execute_booking_events_have_required_fields(
    two_node_itinerary: Itinerary,
) -> None:
    """Each booking event must include index, node_id, name, status, order_id, message."""
    payload = ExecuteRequest(
        session_id="e2e-fields-test",
        itinerary=two_node_itinerary,
    )
    with patch("agent.tools.mock_data.random") as mock_rand:
        mock_rand.random.return_value = 0.5
        events = await _post_execute_sse(payload.model_dump())

    booking_events = [e for e in events if e["type"] == "booking"]
    for evt in booking_events:
        for field in ("index", "node_id", "name", "status", "order_id", "message"):
            assert field in evt, f"Missing field '{field}' in booking event"
        assert evt["status"] in ("success", "failed")


@pytest.mark.asyncio
async def test_execute_all_succeed_correct_counts(two_node_itinerary: Itinerary) -> None:
    """When no faults, success_count must equal total and failed_count must be 0."""
    payload = ExecuteRequest(
        session_id="e2e-all-success",
        itinerary=two_node_itinerary,
    )
    with patch("agent.tools.mock_data.random") as mock_rand:
        mock_rand.random.return_value = 0.5
        events = await _post_execute_sse(payload.model_dump())

    complete = next(e for e in events if e["type"] == "complete")
    assert complete["success_count"] == len(two_node_itinerary.nodes)
    assert complete["failed_count"] == 0


@pytest.mark.asyncio
async def test_execute_confirmation_text_nonempty(two_node_itinerary: Itinerary) -> None:
    """complete event must carry a non-empty confirmation_text."""
    payload = ExecuteRequest(
        session_id="e2e-confirm-text",
        itinerary=two_node_itinerary,
    )
    with patch("agent.tools.mock_data.random") as mock_rand:
        mock_rand.random.return_value = 0.5
        events = await _post_execute_sse(payload.model_dump())

    complete = next(e for e in events if e["type"] == "complete")
    assert complete["confirmation_text"] != ""


@pytest.mark.asyncio
async def test_execute_counts_sum_to_total(two_node_itinerary: Itinerary) -> None:
    """success_count + failed_count must always equal the number of itinerary nodes."""
    payload = ExecuteRequest(
        session_id="e2e-count-sum",
        itinerary=two_node_itinerary,
    )
    with patch("agent.tools.mock_data.random") as mock_rand:
        mock_rand.random.return_value = 0.5
        events = await _post_execute_sse(payload.model_dump())

    complete = next(e for e in events if e["type"] == "complete")
    total = len(two_node_itinerary.nodes)
    assert complete["success_count"] + complete["failed_count"] == total


@pytest.mark.asyncio
async def test_execute_partial_failure_failed_count_nonzero(
    two_node_itinerary: Itinerary,
) -> None:
    """When faults are always injected, failed_count must equal total."""
    payload = ExecuteRequest(
        session_id="e2e-all-fail",
        itinerary=two_node_itinerary,
    )
    with patch("agent.tools.mock_data.random") as mock_rand:
        mock_rand.random.return_value = 0.0  # always fault
        events = await _post_execute_sse(payload.model_dump())

    complete = next(e for e in events if e["type"] == "complete")
    assert complete["failed_count"] == len(two_node_itinerary.nodes)
    assert complete["success_count"] == 0


@pytest.mark.asyncio
async def test_execute_failed_booking_message_has_recovery_hint(
    two_node_itinerary: Itinerary,
) -> None:
    """Failed booking message must include a recovery hint (CLAUDE.md rule)."""
    payload = ExecuteRequest(
        session_id="e2e-recovery-hint",
        itinerary=two_node_itinerary,
    )
    with patch("agent.tools.mock_data.random") as mock_rand:
        mock_rand.random.return_value = 0.0  # always fault
        events = await _post_execute_sse(payload.model_dump())

    failed_events = [e for e in events if e["type"] == "booking" and e["status"] == "failed"]
    assert failed_events, "Expected at least one failed booking event"
    for evt in failed_events:
        assert "trigger partial_replan" in evt["message"], (
            f"Missing recovery hint in: {evt['message']}"
        )


@pytest.mark.asyncio
async def test_execute_idempotency_same_key_same_order_ids(
    two_node_itinerary: Itinerary,
) -> None:
    """Calling /api/execute twice with the same idempotency_key must yield identical order IDs."""
    fixed_key = f"idem-http-{uuid.uuid4()}"
    payload = ExecuteRequest(
        session_id="e2e-idem",
        itinerary=two_node_itinerary,
        idempotency_key=fixed_key,
    ).model_dump()

    with patch("agent.tools.mock_data.random") as mock_rand:
        mock_rand.random.return_value = 0.5
        events1 = await _post_execute_sse(payload)
        events2 = await _post_execute_sse(payload)

    order_ids_1 = {
        (e["node_id"], e["order_id"])
        for e in events1 if e["type"] == "booking" and e["status"] == "success"
    }
    order_ids_2 = {
        (e["node_id"], e["order_id"])
        for e in events2 if e["type"] == "booking" and e["status"] == "success"
    }
    assert order_ids_1 == order_ids_2, (
        f"Idempotency broken: first={order_ids_1}, second={order_ids_2}"
    )


@pytest.mark.asyncio
async def test_execute_empty_itinerary_completes_immediately() -> None:
    """An empty itinerary must produce start + complete events with total=0."""
    empty_itin = Itinerary(
        session_id="e2e-empty",
        nodes=[],
        total_duration_min=0,
        total_per_capita=0,
    )
    payload = ExecuteRequest(session_id="e2e-empty", itinerary=empty_itin).model_dump()

    with patch("agent.tools.mock_data.random") as mock_rand:
        mock_rand.random.return_value = 0.5
        events = await _post_execute_sse(payload)

    assert events[0]["type"] == "start"
    assert events[0]["total"] == 0
    complete = next(e for e in events if e["type"] == "complete")
    assert complete["success_count"] == 0
    assert complete["failed_count"] == 0


@pytest.mark.asyncio
async def test_execute_all_booking_node_ids_covered(two_node_itinerary: Itinerary) -> None:
    """booking events must cover every node_id in the itinerary — no node skipped."""
    payload = ExecuteRequest(
        session_id="e2e-all-covered",
        itinerary=two_node_itinerary,
    )
    with patch("agent.tools.mock_data.random") as mock_rand:
        mock_rand.random.return_value = 0.5
        events = await _post_execute_sse(payload.model_dump())

    expected_ids = {n.node_id for n in two_node_itinerary.nodes}
    booked_ids = {e["node_id"] for e in events if e["type"] == "booking"}
    assert booked_ids == expected_ids


@pytest.mark.asyncio
async def test_execute_session_id_propagated_to_complete(two_node_itinerary: Itinerary) -> None:
    """complete event must echo back the original session_id."""
    payload = ExecuteRequest(
        session_id="my-custom-exec-session",
        itinerary=two_node_itinerary,
    )
    with patch("agent.tools.mock_data.random") as mock_rand:
        mock_rand.random.return_value = 0.5
        events = await _post_execute_sse(payload.model_dump())

    complete = next(e for e in events if e["type"] == "complete")
    assert complete["session_id"] == "my-custom-exec-session"
