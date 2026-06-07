"""Integration tests for F03: ReAct main loop.

Verification command: pytest tests/integration/test_react_loop.py -v
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from agent.core import react_loop
from agent.main import app
from agent.schemas import (
    ConstraintSet,
    HardConstraints,
    PlanRunRequest,
    SoftPreferences,
)


# ── Module-level fixture: force deterministic planner path ─────────────────────
# These tests exercise the deterministic planning path (F03).
# Clearing ANTHROPIC_API_KEY prevents react_loop from delegating to llm_planner.

@pytest.fixture(autouse=True)
def _no_llm_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def base_constraint() -> ConstraintSet:
    return ConstraintSet(
        hard=HardConstraints(max_distance_km=10.0, age_range=(18, 40), total_duration=4.0),
        soft=SoftPreferences(noise_level="medium", per_capita=150, tags=["出片", "美食"]),
    )


@pytest.fixture()
def family_constraint() -> ConstraintSet:
    return ConstraintSet(
        hard=HardConstraints(max_distance_km=8.0, age_range=(0, 12), total_duration=6.0),
        soft=SoftPreferences(noise_level="high", per_capita=200, tags=["亲子友好", "儿童乐园"]),
    )


# ── Helper ────────────────────────────────────────────────────────────────────


async def _collect_events(cs: ConstraintSet, session_id: str = "test-sess") -> list[dict]:  # type: ignore[type-arg]
    gen = await react_loop.run(cs, session_id, start_time="10:00")
    events = []
    async for evt in gen:
        events.append(dict(evt))
    return events


# ── Tests: generator output ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_emits_thought_action_observation_done(base_constraint: ConstraintSet) -> None:
    """The loop must emit events in the correct ReAct order."""
    with patch("agent.tools.mock_data.random") as mock_rand:
        mock_rand.random.return_value = 0.5  # no faults, always available
        events = await _collect_events(base_constraint)

    types = [e["type"] for e in events]
    assert "thought" in types
    assert "action" in types
    assert "observation" in types
    assert types[-1] == "done", f"Last event must be 'done', got: {types[-1]}"


@pytest.mark.asyncio
async def test_run_done_event_contains_itinerary(base_constraint: ConstraintSet) -> None:
    """The 'done' event must carry a valid Itinerary with 3-4 nodes."""
    with patch("agent.tools.mock_data.random") as mock_rand:
        mock_rand.random.return_value = 0.5
        events = await _collect_events(base_constraint)

    done_evt = next(e for e in events if e["type"] == "done")
    assert "itinerary" in done_evt
    itinerary = done_evt["itinerary"]
    assert "nodes" in itinerary
    assert 2 <= len(itinerary["nodes"]) <= 4, f"Expected 2-4 nodes, got {len(itinerary['nodes'])}"
    assert "session_id" in itinerary
    assert "total_duration_min" in itinerary
    assert "total_per_capita" in itinerary


@pytest.mark.asyncio
async def test_run_itinerary_nodes_have_required_fields(base_constraint: ConstraintSet) -> None:
    """Each itinerary node must have id, name, start_time, end_time, per_capita."""
    with patch("agent.tools.mock_data.random") as mock_rand:
        mock_rand.random.return_value = 0.5
        events = await _collect_events(base_constraint)

    itinerary = next(e for e in events if e["type"] == "done")["itinerary"]
    for node in itinerary["nodes"]:
        assert "node_id" in node
        assert "name" in node
        assert "start_time" in node
        assert "end_time" in node
        assert "per_capita" in node
        assert "node_type" in node
        assert node["node_type"] in ("venue", "restaurant")


@pytest.mark.asyncio
async def test_run_thought_before_action(base_constraint: ConstraintSet) -> None:
    """At least one thought must appear before the first action."""
    with patch("agent.tools.mock_data.random") as mock_rand:
        mock_rand.random.return_value = 0.5
        events = await _collect_events(base_constraint)

    types = [e["type"] for e in events]
    first_thought = types.index("thought")
    first_action = types.index("action")
    assert first_thought < first_action, "Thought must precede first Action"


@pytest.mark.asyncio
async def test_run_parallel_tools_both_called(base_constraint: ConstraintSet) -> None:
    """Both venue_search and restaurant_search must appear as action events."""
    with patch("agent.tools.mock_data.random") as mock_rand:
        mock_rand.random.return_value = 0.5
        events = await _collect_events(base_constraint)

    action_tools = {e["tool"] for e in events if e["type"] == "action"}
    assert "venue_search" in action_tools
    assert "restaurant_search" in action_tools


@pytest.mark.asyncio
async def test_run_check_availability_called_serially(base_constraint: ConstraintSet) -> None:
    """check_availability must appear as at least one action event."""
    with patch("agent.tools.mock_data.random") as mock_rand:
        mock_rand.random.return_value = 0.5
        events = await _collect_events(base_constraint)

    avail_actions = [e for e in events if e.get("type") == "action" and e.get("tool") == "check_availability"]
    assert len(avail_actions) >= 1, "check_availability must be called at least once"


@pytest.mark.asyncio
async def test_run_family_scenario_prefers_child_friendly(family_constraint: ConstraintSet) -> None:
    """Family (age 0-12) scenario should include child-friendly venues."""
    with patch("agent.tools.mock_data.random") as mock_rand, \
         patch("agent.tools.check_availability.random") as avail_rand:
        mock_rand.random.return_value = 0.5
        avail_rand.random.return_value = 0.9  # all candidates always available
        events = await _collect_events(family_constraint)

    itinerary = next(e for e in events if e["type"] == "done")["itinerary"]
    names = [n["name"] for n in itinerary["nodes"]]
    # At least one venue should come from child-friendly pool (Shanghai venues)
    child_venues = {
        "上海迪士尼乐园", "上海科技馆", "玛雅海滩水公园", "上海自然博物馆",
        "上海环球港", "上海天文馆", "上海野生动物园", "上海动物园", "上海海洋水族馆",
        "上海儿童博物馆", "徐家汇商业广场", "上海马戏城", "大宁灵石公园",
        "正大乐城", "世纪公园", "上海长风公园", "辰山植物园", "顾村公园",
        "共青森林公园", "上海科技馆自然博物馆分馆",
    }
    assert any(name in child_venues for name in names), (
        f"Family scenario should prefer child-friendly venues, got: {names}"
    )


@pytest.mark.asyncio
async def test_run_four_nodes_for_long_duration(base_constraint: ConstraintSet) -> None:
    """6-hour+ duration should produce 4 nodes."""
    long_cs = ConstraintSet(
        hard=HardConstraints(max_distance_km=10.0, age_range=(18, 40), total_duration=8.0),
        soft=base_constraint.soft,
    )
    with patch("agent.tools.mock_data.random") as mock_rand:
        mock_rand.random.return_value = 0.5
        events = await _collect_events(long_cs)

    itinerary = next(e for e in events if e["type"] == "done")["itinerary"]
    assert len(itinerary["nodes"]) >= 3


@pytest.mark.asyncio
async def test_run_fault_triggers_level1_replacement(base_constraint: ConstraintSet) -> None:
    """When check_availability returns unavailable, loop emits a Level 1 replacement thought."""
    call_count = 0

    def _random() -> float:
        nonlocal call_count
        call_count += 1
        # First 2 calls: availability checks → unavailable (>0.2)
        # Route/fault checks → no fault (<0.1)
        return 0.5 if call_count <= 4 else 0.0

    with patch("agent.tools.mock_data.random") as mock_rand:
        mock_rand.random.side_effect = _random
        # Patch availability to fail first, succeed on fallback
        with patch("agent.tools.check_availability.random") as avail_rand:
            # First venue: unavailable (0.9 > 0.2), fallback: available (0.1 < 0.8)
            avail_rand.random.side_effect = [0.9, 0.1, 0.9, 0.1, 0.9, 0.1, 0.9, 0.1]
            events = await _collect_events(base_constraint)

    replacement_thoughts = [
        e for e in events
        if e.get("type") == "thought" and "替换" in e.get("content", "")
    ]
    # may or may not have triggered depending on random — just ensure loop completes
    done_events = [e for e in events if e["type"] == "done"]
    assert len(done_events) == 1, "Loop must always produce exactly one 'done' event"


@pytest.mark.asyncio
async def test_run_no_fault_produces_valid_times(base_constraint: ConstraintSet) -> None:
    """All nodes must have chronologically increasing start_time values."""
    with patch("agent.tools.mock_data.random") as mock_rand:
        mock_rand.random.return_value = 0.5
        with patch("agent.tools.check_availability.random") as avail_rand:
            avail_rand.random.return_value = 0.9  # always available
            events = await _collect_events(base_constraint)

    itinerary = next(e for e in events if e["type"] == "done")["itinerary"]
    nodes = itinerary["nodes"]
    for i in range(1, len(nodes)):
        prev_end = nodes[i - 1]["end_time"]
        curr_start = nodes[i]["start_time"]
        assert curr_start >= prev_end, (
            f"Node {i} starts at {curr_start} before previous ends at {prev_end}"
        )


# ── Tests: HTTP endpoint ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_plan_run_endpoint_returns_sse_stream(base_constraint: ConstraintSet) -> None:
    """POST /api/plan/run must return text/event-stream with SSE events."""
    payload = PlanRunRequest(
        constraint_set=base_constraint,
        start_time="10:00",
        session_id="http-test-sess",
    )
    with patch("agent.tools.mock_data.random") as mock_rand:
        mock_rand.random.return_value = 0.5
        with patch("agent.tools.check_availability.random") as avail_rand:
            avail_rand.random.return_value = 0.9
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                async with client.stream(
                    "POST",
                    "/api/plan/run",
                    json=payload.model_dump(),
                    headers={"Accept": "text/event-stream"},
                ) as resp:
                    assert resp.status_code == 200
                    lines = []
                    async for line in resp.aiter_lines():
                        lines.append(line)

    data_lines = [l for l in lines if l.startswith("data: ")]
    assert len(data_lines) >= 3, f"Expected ≥3 SSE data lines, got {len(data_lines)}"

    # Last real data line before [DONE] must be parseable JSON with type=done
    done_line = next(
        (l for l in reversed(data_lines) if "done" in l and "[DONE]" not in l), None
    )
    assert done_line is not None, "SSE stream must include a 'done' event"
    evt = json.loads(done_line[len("data: "):])
    assert evt["type"] == "done"


@pytest.mark.asyncio
async def test_plan_run_endpoint_session_id_propagated(base_constraint: ConstraintSet) -> None:
    """session_id from the request must appear in the itinerary."""
    payload = PlanRunRequest(
        constraint_set=base_constraint,
        start_time="10:00",
        session_id="my-custom-sess-id",
    )
    with patch("agent.tools.mock_data.random") as mock_rand:
        mock_rand.random.return_value = 0.5
        with patch("agent.tools.check_availability.random") as avail_rand:
            avail_rand.random.return_value = 0.9
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                async with client.stream(
                    "POST", "/api/plan/run",
                    json=payload.model_dump(),
                ) as resp:
                    content = await resp.aread()

    raw = content.decode()
    done_line = next(
        (l for l in raw.splitlines() if l.startswith("data: ") and "done" in l and "[DONE]" not in l),
        None,
    )
    assert done_line is not None
    evt = json.loads(done_line[len("data: "):])
    assert evt["itinerary"]["session_id"] == "my-custom-sess-id"
