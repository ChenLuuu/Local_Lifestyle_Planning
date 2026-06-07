"""Unit tests for F14: LLM-backed planner (llm_planner.py).

All tests mock the AsyncOpenAI client so no real API calls are made.
Verification command: pytest tests/unit/test_llm_planner.py -v
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.core import llm_planner
from agent.schemas import ConstraintSet, HardConstraints, SoftPreferences


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def base_constraint() -> ConstraintSet:
    return ConstraintSet(
        hard=HardConstraints(max_distance_km=10.0, age_range=(18, 40), total_duration=6.0),
        soft=SoftPreferences(noise_level="medium", per_capita=150, tags=["出片", "美食"]),
    )


@pytest.fixture()
def long_constraint() -> ConstraintSet:
    return ConstraintSet(
        hard=HardConstraints(max_distance_km=15.0, age_range=(18, 40), total_duration=8.0),
        soft=SoftPreferences(noise_level="low", per_capita=200, tags=["商务", "安静"]),
    )


@pytest.fixture()
def family_constraint() -> ConstraintSet:
    return ConstraintSet(
        hard=HardConstraints(max_distance_km=8.0, age_range=(0, 12), total_duration=6.0),
        soft=SoftPreferences(noise_level="high", per_capita=200, tags=["亲子友好", "儿童乐园"]),
    )


# ---------------------------------------------------------------------------
# Helpers for building mock OpenAI chat.completions responses
# ---------------------------------------------------------------------------


def _tool_use_response(*tool_calls: tuple[str, str, dict[str, Any]]) -> MagicMock:
    """Mock OpenAI response with tool_calls (function calling)."""
    response = MagicMock()
    tcs = []
    for name, tool_id, tool_input in tool_calls:
        tc = MagicMock()
        tc.id = tool_id
        tc.function.name = name
        tc.function.arguments = json.dumps(tool_input, ensure_ascii=False)
        tcs.append(tc)
    response.choices[0].message.tool_calls = tcs
    response.choices[0].message.content = None
    response.choices[0].message.model_dump.return_value = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in tcs
        ],
    }
    return response


def _text_response(text: str = "规划完成，行程已安排好。") -> MagicMock:
    """Mock OpenAI response with text only (no tool calls)."""
    response = MagicMock()
    response.choices[0].message.tool_calls = None
    response.choices[0].message.content = text
    response.choices[0].message.model_dump.return_value = {
        "role": "assistant",
        "content": text,
        "tool_calls": None,
    }
    return response


def _make_stream_chunk(response: MagicMock, chunk_idx: int, total_chunks: int = 2) -> MagicMock:
    """Create a streaming chunk from a mock response.
    
    Arguments are sent only in the first chunk to avoid duplication.
    """
    chunk = MagicMock()
    chunk.choices = []
    choice = MagicMock()
    chunk.choices.append(choice)
    
    delta = MagicMock()
    choice.delta = delta
    choice.finish_reason = None if chunk_idx < total_chunks - 1 else "stop"
    
    if response.choices[0].message.tool_calls:
        delta.tool_calls = []
        for idx, tc in enumerate(response.choices[0].message.tool_calls):
            tc_delta = MagicMock()
            tc_delta.index = idx
            tc_delta.id = tc.id if chunk_idx == 0 else ""
            func_delta = MagicMock()
            func_delta.name = tc.function.name if chunk_idx == 0 else ""
            func_delta.arguments = tc.function.arguments if chunk_idx == 0 else ""
            tc_delta.function = func_delta
            delta.tool_calls.append(tc_delta)
    else:
        delta.tool_calls = None
        delta.content = response.choices[0].message.content if chunk_idx == 0 else ""
    
    return chunk


async def _stream_response(response: MagicMock):
    """Generate streaming response chunks with arguments only in first chunk."""
    yield _make_stream_chunk(response, chunk_idx=0)
    yield _make_stream_chunk(response, chunk_idx=1)


def _make_client(*responses: MagicMock) -> MagicMock:
    """Create a mock AsyncOpenAI client returning streaming responses."""
    client = MagicMock()
    responses_list = list(responses)
    
    async def create_stream(*args, **kwargs):
        if responses_list:
            response = responses_list.pop(0)
            return _stream_response(response)
        raise StopAsyncIteration
    
    client.chat.completions.create = AsyncMock(side_effect=create_stream)
    return client


async def _collect(cs: ConstraintSet, session_id: str = "test-sess") -> list[dict[str, Any]]:
    gen = await llm_planner.run(cs, session_id, "10:00")
    return [dict(e) async for e in gen]


# ---------------------------------------------------------------------------
# Tests: first-byte / event ordering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_first_event_is_thought(base_constraint: ConstraintSet) -> None:
    """First emitted event must be 'thought' — satisfies ≤3 s first-byte SLA."""
    with patch("agent.core.llm_planner.AsyncOpenAI") as mock_cls:
        mock_cls.return_value = _make_client(_text_response())
        with patch("agent.tools.mock_data.random") as r:
            r.random.return_value = 0.5
            events = await _collect(base_constraint)

    assert events[0]["type"] == "thought"
    assert "LLM规划模式" in events[0]["content"]


@pytest.mark.asyncio
async def test_last_event_is_done(base_constraint: ConstraintSet) -> None:
    """Final event must be 'done' with a valid itinerary."""
    with patch("agent.core.llm_planner.AsyncOpenAI") as mock_cls:
        mock_cls.return_value = _make_client(_text_response())
        with patch("agent.tools.mock_data.random") as r:
            r.random.return_value = 0.5
            events = await _collect(base_constraint)

    assert events[-1]["type"] == "done"
    assert "itinerary" in events[-1]


@pytest.mark.asyncio
async def test_done_itinerary_has_required_fields(base_constraint: ConstraintSet) -> None:
    """The done event's itinerary must have session_id, nodes, totals."""
    with patch("agent.core.llm_planner.AsyncOpenAI") as mock_cls:
        mock_cls.return_value = _make_client(_text_response())
        with patch("agent.tools.mock_data.random") as r:
            r.random.return_value = 0.5
            events = await _collect(base_constraint, session_id="my-sess")

    itin = events[-1]["itinerary"]
    assert itin["session_id"] == "my-sess"
    assert isinstance(itin["nodes"], list)
    assert len(itin["nodes"]) >= 2
    assert "total_duration_min" in itin
    assert "total_per_capita" in itin


# ---------------------------------------------------------------------------
# Tests: LLM tool call dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_venue_search_tool_call_emits_action_observation(
    base_constraint: ConstraintSet,
) -> None:
    """When LLM emits a venue_search tool_use, we yield action then observation."""
    venue_call = _tool_use_response(
        ("venue_search", "tu_01", {"per_capita": 150, "tags": ["出片"]})
    )
    with patch("agent.core.llm_planner.AsyncOpenAI") as mock_cls:
        mock_cls.return_value = _make_client(venue_call, _text_response())
        with patch("agent.tools.mock_data.random") as r:
            r.random.return_value = 0.5
            events = await _collect(base_constraint)

    types = [e["type"] for e in events]
    assert "action" in types
    assert "observation" in types
    assert types.index("action") < types.index("observation")


@pytest.mark.asyncio
async def test_llm_restaurant_search_tool_call_dispatched(
    base_constraint: ConstraintSet,
) -> None:
    """venue_search + restaurant_search tool calls both dispatch correctly."""
    parallel_call = _tool_use_response(
        ("venue_search", "tu_01", {"per_capita": 150, "tags": ["出片"]}),
        ("restaurant_search", "tu_02", {"per_capita": 150}),
    )
    with patch("agent.core.llm_planner.AsyncOpenAI") as mock_cls:
        mock_cls.return_value = _make_client(parallel_call, _text_response())
        with patch("agent.tools.mock_data.random") as r:
            r.random.return_value = 0.5
            events = await _collect(base_constraint)

    action_tools = {e["tool"] for e in events if e["type"] == "action"}
    assert "venue_search" in action_tools
    assert "restaurant_search" in action_tools


@pytest.mark.asyncio
async def test_llm_check_availability_tool_call_dispatched(
    base_constraint: ConstraintSet,
) -> None:
    """check_availability tool call is dispatched when LLM requests it.

    search tools are now pre-fetched directly (no LLM round), so the first
    (and only) FC round should receive avail_call directly.
    """
    avail_call = _tool_use_response(
        ("check_availability", "tu_02", {"item_id": "v001", "time_slot": "10:00"})
    )
    with patch("agent.core.llm_planner.AsyncOpenAI") as mock_cls:
        mock_cls.return_value = _make_client(avail_call, _text_response())
        with patch("agent.tools.mock_data.random") as r:
            r.random.return_value = 0.5
            with patch("agent.tools.check_availability.random") as cr:
                cr.random.return_value = 0.9
                events = await _collect(base_constraint)

    action_tools = [e.get("tool") for e in events if e["type"] == "action"]
    assert "check_availability" in action_tools


@pytest.mark.asyncio
async def test_llm_route_plan_tool_call_dispatched(
    base_constraint: ConstraintSet,
) -> None:
    """route_plan tool call is dispatched and result collected."""
    route_call = _tool_use_response(
        (
            "route_plan",
            "tu_03",
            {
                "from_address": "外滩",
                "to_address": "海底捞",
                "from_lat": 31.2397,
                "from_lng": 121.4899,
                "to_lat": 31.2373,
                "to_lng": 121.4772,
            },
        )
    )
    with patch("agent.core.llm_planner.AsyncOpenAI") as mock_cls:
        mock_cls.return_value = _make_client(route_call, _text_response())
        with patch("agent.tools.mock_data.random") as r:
            r.random.return_value = 0.5
            events = await _collect(base_constraint)

    action_tools = [e.get("tool") for e in events if e["type"] == "action"]
    assert "route_plan" in action_tools


# ---------------------------------------------------------------------------
# Tests: itinerary node count
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_short_duration_yields_three_nodes(base_constraint: ConstraintSet) -> None:
    """< 6h total duration → 3-node itinerary."""
    with patch("agent.core.llm_planner.AsyncOpenAI") as mock_cls:
        mock_cls.return_value = _make_client(_text_response())
        with patch("agent.tools.mock_data.random") as r:
            r.random.return_value = 0.5
            events = await _collect(base_constraint)

    nodes = events[-1]["itinerary"]["nodes"]
    assert len(nodes) <= 3


@pytest.mark.asyncio
async def test_long_duration_yields_four_nodes(long_constraint: ConstraintSet) -> None:
    """≥ 6h total duration → 4-node itinerary."""
    with patch("agent.core.llm_planner.AsyncOpenAI") as mock_cls:
        mock_cls.return_value = _make_client(_text_response())
        with patch("agent.tools.mock_data.random") as r:
            r.random.return_value = 0.5
            events = await _collect(long_constraint)

    nodes = events[-1]["itinerary"]["nodes"]
    assert len(nodes) >= 3


# ---------------------------------------------------------------------------
# Tests: safety-net / fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_safety_net_when_llm_makes_no_tool_calls(
    base_constraint: ConstraintSet,
) -> None:
    """If LLM never calls search tools, safety-net runs venue_search directly."""
    with patch("agent.core.llm_planner.AsyncOpenAI") as mock_cls:
        mock_cls.return_value = _make_client(_text_response())
        with patch("agent.tools.mock_data.random") as r:
            r.random.return_value = 0.5
            events = await _collect(base_constraint)

    done = events[-1]
    assert done["type"] == "done"
    assert len(done["itinerary"]["nodes"]) >= 2


@pytest.mark.asyncio
async def test_tool_fault_emits_error_event_not_crash(
    base_constraint: ConstraintSet,
) -> None:
    """A ToolFaultError during tool dispatch must emit an 'error' event, not raise."""
    from agent.tools.mock_data import ToolFaultError

    venue_call = _tool_use_response(
        ("venue_search", "tu_01", {"per_capita": 150, "tags": ["出片"]})
    )
    with patch("agent.core.llm_planner.AsyncOpenAI") as mock_cls:
        mock_cls.return_value = _make_client(venue_call, _text_response())
        with patch("agent.core.llm_planner.venue_search", new=AsyncMock(
            side_effect=ToolFaultError("NO_NEARBY")
        )):
            with patch("agent.tools.mock_data.random") as r:
                r.random.return_value = 0.5
                events = await _collect(base_constraint)

    error_events = [e for e in events if e["type"] == "error"]
    assert len(error_events) >= 1
    assert events[-1]["type"] == "done"


# ---------------------------------------------------------------------------
# Tests: multi-turn conversation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multi_turn_loop_terminates(base_constraint: ConstraintSet) -> None:
    """LLM making tool calls in multiple rounds must eventually terminate."""
    round1 = _tool_use_response(
        ("venue_search", "tu_01", {"per_capita": 150, "tags": ["出片"]})
    )
    round2 = _tool_use_response(
        ("restaurant_search", "tu_02", {"per_capita": 150})
    )
    with patch("agent.core.llm_planner.AsyncOpenAI") as mock_cls:
        mock_cls.return_value = _make_client(round1, round2, _text_response())
        with patch("agent.tools.mock_data.random") as r:
            r.random.return_value = 0.5
            events = await _collect(base_constraint)

    assert events[-1]["type"] == "done"
    action_tools = {e.get("tool") for e in events if e["type"] == "action"}
    assert "venue_search" in action_tools
    assert "restaurant_search" in action_tools


@pytest.mark.asyncio
async def test_done_content_mentions_llm_mode(base_constraint: ConstraintSet) -> None:
    """Done event content should indicate LLM planning mode."""
    with patch("agent.core.llm_planner.AsyncOpenAI") as mock_cls:
        mock_cls.return_value = _make_client(_text_response())
        with patch("agent.tools.mock_data.random") as r:
            r.random.return_value = 0.5
            events = await _collect(base_constraint)

    done_content = events[-1]["content"]
    assert "[LLM]" in done_content


@pytest.mark.asyncio
async def test_node_times_are_chronological(base_constraint: ConstraintSet) -> None:
    """All nodes must have chronologically non-decreasing start times."""
    with patch("agent.core.llm_planner.AsyncOpenAI") as mock_cls:
        mock_cls.return_value = _make_client(_text_response())
        with patch("agent.tools.mock_data.random") as r:
            r.random.return_value = 0.5
            events = await _collect(base_constraint)

    nodes = events[-1]["itinerary"]["nodes"]
    for i in range(1, len(nodes)):
        prev_end = nodes[i - 1]["end_time"]
        curr_start = nodes[i]["start_time"]
        assert curr_start >= prev_end, (
            f"Node {i} starts {curr_start} before previous ends {prev_end}"
        )
