"""Integration tests for F05: node-swap partial replanning.

Verification command: pytest tests/integration/test_node_swap.py -v
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from agent.core import partial_replan
from agent.core.time_allocator import TimeConflictError
from agent.main import app
from agent.schemas import (
    ConstraintSet,
    HardConstraints,
    Itinerary,
    ItineraryNode,
    SoftPreferences,
    SwapAcceptRequest,
    SwapCandidatesRequest,
    TransitInfo,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def base_constraint() -> ConstraintSet:
    return ConstraintSet(
        hard=HardConstraints(max_distance_km=10.0, age_range=(18, 40), total_duration=6.0),
        soft=SoftPreferences(noise_level="medium", per_capita=150, tags=["出片", "美食"]),
    )


@pytest.fixture()
def sample_itinerary() -> Itinerary:
    """Two-node itinerary: venue (120 min) + restaurant (75 min) + 15 min transit.

    Total: 210 min, well within the 6h (360 min) window.
    Uses v003 and r003 so the full pool of alternates is available.
    """
    return Itinerary(
        session_id="test-swap-sess",
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
                node_id="r003",
                node_type="restaurant",
                name="外婆家（悠唐店）",
                address="朝阳区工人体育场北路6号悠唐购物中心4F",
                start_time="12:15",
                end_time="13:30",
                duration_min=75,
                per_capita=100,
                transit_to_next=None,
            ),
        ],
        total_duration_min=210,
        total_per_capita=100,
    )


def _no_fault_no_avail_patch() -> tuple[object, object]:
    """Returns (mock_fault, mock_avail) context managers for fully deterministic tests."""
    from unittest.mock import patch as _patch

    fault_p = _patch("agent.tools.mock_data.random")
    avail_p = _patch("agent.tools.check_availability.random")
    return fault_p, avail_p


# ── find_replacement_candidates ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_find_candidates_returns_three_for_venue(
    sample_itinerary: Itinerary, base_constraint: ConstraintSet
) -> None:
    """find_replacement_candidates must return exactly 3 venues when pool is large enough."""
    with patch("agent.tools.mock_data.random") as mock_fault, \
         patch("agent.tools.check_availability.random") as mock_avail:
        mock_fault.random.return_value = 0.5   # no fault
        mock_avail.random.return_value = 0.9   # always available
        candidates = await partial_replan.find_replacement_candidates(
            itinerary=sample_itinerary,
            node_index=0,  # venue node
            constraint_set=base_constraint,
        )

    assert len(candidates) == 3, f"Expected 3 candidates, got {len(candidates)}"


@pytest.mark.asyncio
async def test_find_candidates_returns_three_for_restaurant(
    sample_itinerary: Itinerary, base_constraint: ConstraintSet
) -> None:
    """find_replacement_candidates must return 3 restaurants when pool allows."""
    with patch("agent.tools.mock_data.random") as mock_fault, \
         patch("agent.tools.check_availability.random") as mock_avail:
        mock_fault.random.return_value = 0.5
        mock_avail.random.return_value = 0.9
        candidates = await partial_replan.find_replacement_candidates(
            itinerary=sample_itinerary,
            node_index=1,  # restaurant node
            constraint_set=base_constraint,
        )

    assert len(candidates) == 3, f"Expected 3 candidates, got {len(candidates)}"


@pytest.mark.asyncio
async def test_candidates_exclude_existing_node_ids(
    sample_itinerary: Itinerary, base_constraint: ConstraintSet
) -> None:
    """No candidate may duplicate a node already in the itinerary."""
    existing_ids = {n.node_id for n in sample_itinerary.nodes}

    with patch("agent.tools.mock_data.random") as mock_fault, \
         patch("agent.tools.check_availability.random") as mock_avail:
        mock_fault.random.return_value = 0.5
        mock_avail.random.return_value = 0.9
        candidates = await partial_replan.find_replacement_candidates(
            itinerary=sample_itinerary,
            node_index=0,
            constraint_set=base_constraint,
        )

    for c in candidates:
        assert c.node_id not in existing_ids, (
            f"Candidate {c.node_id} is already in the itinerary"
        )


@pytest.mark.asyncio
async def test_venue_candidates_have_venue_type(
    sample_itinerary: Itinerary, base_constraint: ConstraintSet
) -> None:
    """When swapping a venue node, all candidates must be venues."""
    with patch("agent.tools.mock_data.random") as mock_fault, \
         patch("agent.tools.check_availability.random") as mock_avail:
        mock_fault.random.return_value = 0.5
        mock_avail.random.return_value = 0.9
        candidates = await partial_replan.find_replacement_candidates(
            itinerary=sample_itinerary,
            node_index=0,
            constraint_set=base_constraint,
        )

    for c in candidates:
        assert c.node_type == "venue", f"Expected venue, got {c.node_type}"


@pytest.mark.asyncio
async def test_restaurant_candidates_have_restaurant_type(
    sample_itinerary: Itinerary, base_constraint: ConstraintSet
) -> None:
    """When swapping a restaurant node, all candidates must be restaurants."""
    with patch("agent.tools.mock_data.random") as mock_fault, \
         patch("agent.tools.check_availability.random") as mock_avail:
        mock_fault.random.return_value = 0.5
        mock_avail.random.return_value = 0.9
        candidates = await partial_replan.find_replacement_candidates(
            itinerary=sample_itinerary,
            node_index=1,
            constraint_set=base_constraint,
        )

    for c in candidates:
        assert c.node_type == "restaurant", f"Expected restaurant, got {c.node_type}"


@pytest.mark.asyncio
async def test_candidates_inherit_time_slot(
    sample_itinerary: Itinerary, base_constraint: ConstraintSet
) -> None:
    """Candidates must inherit the start/end times of the original node."""
    original = sample_itinerary.nodes[0]

    with patch("agent.tools.mock_data.random") as mock_fault, \
         patch("agent.tools.check_availability.random") as mock_avail:
        mock_fault.random.return_value = 0.5
        mock_avail.random.return_value = 0.9
        candidates = await partial_replan.find_replacement_candidates(
            itinerary=sample_itinerary,
            node_index=0,
            constraint_set=base_constraint,
        )

    for c in candidates:
        assert c.start_time == original.start_time
        assert c.end_time == original.end_time
        assert c.duration_min == original.duration_min


@pytest.mark.asyncio
async def test_candidates_unavailable_filtered_out(
    sample_itinerary: Itinerary, base_constraint: ConstraintSet
) -> None:
    """Candidates that fail availability check are excluded from results."""
    with patch("agent.tools.mock_data.random") as mock_fault, \
         patch("agent.tools.check_availability.random") as mock_avail:
        mock_fault.random.return_value = 0.5
        mock_avail.random.return_value = 0.0  # always unavailable (0.0 < 0.2 threshold)
        candidates = await partial_replan.find_replacement_candidates(
            itinerary=sample_itinerary,
            node_index=0,
            constraint_set=base_constraint,
        )

    assert candidates == [], f"Expected 0 candidates when all unavailable, got {len(candidates)}"


# ── apply_swap ────────────────────────────────────────────────────────────────


def test_apply_swap_replaces_correct_node(sample_itinerary: Itinerary) -> None:
    """After apply_swap, the node at the given index has the replacement's id and name."""
    replacement = ItineraryNode(
        node_id="v005",
        node_type="venue",
        name="颐和园",
        address="海淀区新建宫门路19号",
        start_time="10:00",
        end_time="12:00",
        duration_min=120,
        per_capita=30,
        transit_to_next=TransitInfo(mode="地铁", duration_min=15, distance_km=3.0),
    )
    new_itin = partial_replan.apply_swap(
        itinerary=sample_itinerary,
        node_index=0,
        replacement=replacement,
        window_start="10:00",
        window_duration_min=360,
    )

    assert new_itin.nodes[0].node_id == "v005"
    assert new_itin.nodes[0].name == "颐和园"


def test_apply_swap_preserves_session_id(sample_itinerary: Itinerary) -> None:
    """apply_swap must preserve the original session_id."""
    replacement = ItineraryNode(
        node_id="v005",
        node_type="venue",
        name="颐和园",
        address="海淀区新建宫门路19号",
        start_time="10:00",
        end_time="12:00",
        duration_min=120,
        per_capita=30,
        transit_to_next=None,
    )
    new_itin = partial_replan.apply_swap(
        itinerary=sample_itinerary,
        node_index=0,
        replacement=replacement,
        window_start="10:00",
        window_duration_min=360,
    )

    assert new_itin.session_id == sample_itinerary.session_id


def test_apply_swap_timeline_no_overlaps(sample_itinerary: Itinerary) -> None:
    """After apply_swap, node start times must be strictly non-decreasing."""
    replacement = ItineraryNode(
        node_id="v005",
        node_type="venue",
        name="颐和园",
        address="海淀区新建宫门路19号",
        start_time="10:00",
        end_time="12:00",
        duration_min=120,
        per_capita=30,
        transit_to_next=TransitInfo(mode="地铁", duration_min=15, distance_km=3.0),
    )
    new_itin = partial_replan.apply_swap(
        itinerary=sample_itinerary,
        node_index=0,
        replacement=replacement,
        window_start="10:00",
        window_duration_min=360,
    )

    nodes = new_itin.nodes
    for i in range(1, len(nodes)):
        prev = nodes[i - 1]
        boundary = (
            prev.end_time
            if prev.transit_to_next is None
            else _add_minutes(prev.end_time, prev.transit_to_next.duration_min)
        )
        assert nodes[i].start_time >= boundary, (
            f"Overlap: node {i} starts {nodes[i].start_time} before boundary {boundary}"
        )


def test_apply_swap_last_node(sample_itinerary: Itinerary) -> None:
    """apply_swap works when replacing the last node."""
    replacement = ItineraryNode(
        node_id="r007",
        node_type="restaurant",
        name="胡大饭馆（簋街总店）",
        address="东城区簋街119号",
        start_time="12:15",
        end_time="13:30",
        duration_min=75,
        per_capita=100,
        transit_to_next=None,
    )
    new_itin = partial_replan.apply_swap(
        itinerary=sample_itinerary,
        node_index=1,
        replacement=replacement,
        window_start="10:00",
        window_duration_min=360,
    )

    assert new_itin.nodes[-1].node_id == "r007"
    assert len(new_itin.nodes) == len(sample_itinerary.nodes)


def test_apply_swap_recalculates_total_per_capita(sample_itinerary: Itinerary) -> None:
    """total_per_capita in the new itinerary sums the per_capita of all nodes."""
    replacement = ItineraryNode(
        node_id="v002",
        node_type="venue",
        name="故宫博物院",
        address="东城区景山前街4号",
        start_time="10:00",
        end_time="12:00",
        duration_min=120,
        per_capita=60,
        transit_to_next=TransitInfo(mode="地铁", duration_min=15, distance_km=3.0),
    )
    new_itin = partial_replan.apply_swap(
        itinerary=sample_itinerary,
        node_index=0,
        replacement=replacement,
        window_start="10:00",
        window_duration_min=360,
    )

    expected = sum(n.per_capita for n in new_itin.nodes)
    assert new_itin.total_per_capita == expected


def test_apply_swap_repeated_on_same_index(sample_itinerary: Itinerary) -> None:
    """Calling apply_swap multiple times on the same index produces valid itineraries."""
    replacements = [
        ItineraryNode(
            node_id=nid, node_type="venue", name=name,
            address="北京市", start_time="10:00", end_time="12:00",
            duration_min=120, per_capita=50,
            transit_to_next=TransitInfo(mode="地铁", duration_min=15, distance_km=3.0),
        )
        for nid, name in [("v005", "颐和园"), ("v006", "国家博物馆"), ("v007", "朝阳公园")]
    ]

    current = sample_itinerary
    for repl in replacements:
        current = partial_replan.apply_swap(
            itinerary=current,
            node_index=0,
            replacement=repl,
            window_start="10:00",
            window_duration_min=360,
        )
        assert current.nodes[0].node_id == repl.node_id


# ── HTTP endpoints ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_candidates_endpoint_returns_200(
    sample_itinerary: Itinerary, base_constraint: ConstraintSet
) -> None:
    """POST /api/plan/swap/candidates must return 200 with a list of candidates."""
    payload = SwapCandidatesRequest(
        session_id="http-test",
        node_index=0,
        itinerary=sample_itinerary,
        constraint_set=base_constraint,
    )
    with patch("agent.tools.mock_data.random") as mock_fault, \
         patch("agent.tools.check_availability.random") as mock_avail:
        mock_fault.random.return_value = 0.5
        mock_avail.random.return_value = 0.9
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/plan/swap/candidates",
                json=payload.model_dump(),
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == "http-test"
    assert body["node_index"] == 0
    assert isinstance(body["candidates"], list)
    assert len(body["candidates"]) == 3


@pytest.mark.asyncio
async def test_candidates_endpoint_invalid_index(
    sample_itinerary: Itinerary, base_constraint: ConstraintSet
) -> None:
    """POST /api/plan/swap/candidates with out-of-range index must return 422."""
    payload = SwapCandidatesRequest(
        session_id="http-test",
        node_index=99,
        itinerary=sample_itinerary,
        constraint_set=base_constraint,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/plan/swap/candidates",
            json=payload.model_dump(),
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_accept_endpoint_returns_valid_itinerary(
    sample_itinerary: Itinerary, base_constraint: ConstraintSet
) -> None:
    """POST /api/plan/swap/accept must return 200 with a recalculated itinerary."""
    candidate = ItineraryNode(
        node_id="v005",
        node_type="venue",
        name="颐和园",
        address="海淀区新建宫门路19号",
        start_time="10:00",
        end_time="12:00",
        duration_min=120,
        per_capita=30,
        transit_to_next=TransitInfo(mode="地铁", duration_min=15, distance_km=3.0),
    )
    payload = SwapAcceptRequest(
        session_id="http-accept-test",
        node_index=0,
        candidate=candidate,
        itinerary=sample_itinerary,
        constraint_set=base_constraint,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/plan/swap/accept",
            json=payload.model_dump(),
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == "http-accept-test"
    assert body["itinerary"]["nodes"][0]["node_id"] == "v005"
    assert len(body["itinerary"]["nodes"]) == len(sample_itinerary.nodes)


@pytest.mark.asyncio
async def test_accept_endpoint_timeline_chronological(
    sample_itinerary: Itinerary, base_constraint: ConstraintSet
) -> None:
    """Accepted swap itinerary must have strictly non-decreasing start times."""
    candidate = ItineraryNode(
        node_id="v005",
        node_type="venue",
        name="颐和园",
        address="海淀区新建宫门路19号",
        start_time="10:00",
        end_time="12:00",
        duration_min=120,
        per_capita=30,
        transit_to_next=TransitInfo(mode="地铁", duration_min=15, distance_km=3.0),
    )
    payload = SwapAcceptRequest(
        session_id="http-timeline-test",
        node_index=0,
        candidate=candidate,
        itinerary=sample_itinerary,
        constraint_set=base_constraint,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/api/plan/swap/accept", json=payload.model_dump())

    assert resp.status_code == 200
    nodes = resp.json()["itinerary"]["nodes"]
    for i in range(1, len(nodes)):
        assert nodes[i]["start_time"] >= nodes[i - 1]["end_time"], (
            f"Node {i} starts before previous ends"
        )


# ── Helper ────────────────────────────────────────────────────────────────────


def _add_minutes(hhmm: str, minutes: int) -> str:
    from datetime import datetime, timedelta
    t = datetime.strptime(hhmm, "%H:%M") + timedelta(minutes=minutes)
    return t.strftime("%H:%M")
