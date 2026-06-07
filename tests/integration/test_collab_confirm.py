"""Integration tests for F08: multi-user collaborative confirmation.

Verification command: pytest tests/integration/test_collab_confirm.py -v
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from agent.main import app
from agent.modules import collab_confirm
from agent.modules.collab_confirm import (
    PlanState,
    advance_state,
    cast_vote,
    clear_store,
    create_share_link,
    get_shared_plan,
    mark_confirmed,
    resolve_conflicts,
)
from agent.schemas import (
    CollabAdvanceRequest,
    CollabConfirmRequest,
    CollabCreateRequest,
    CollabVoteRequest,
    Itinerary,
    ItineraryNode,
    TransitInfo,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_store() -> None:
    """Clear the collab store before every test for isolation."""
    clear_store()


@pytest.fixture()
def sample_itinerary() -> Itinerary:
    return Itinerary(
        session_id="collab-test-sess",
        nodes=[
            ItineraryNode(
                node_id="v001",
                node_type="venue",
                name="国家博物馆",
                address="东城区天安门广场东侧",
                start_time="10:00",
                end_time="12:00",
                duration_min=120,
                per_capita=30,
                transit_to_next=TransitInfo(mode="地铁", duration_min=20, distance_km=5.0),
            ),
            ItineraryNode(
                node_id="r001",
                node_type="restaurant",
                name="全聚德（前门店）",
                address="前门大街30号",
                start_time="12:20",
                end_time="13:30",
                duration_min=70,
                per_capita=150,
                transit_to_next=None,
            ),
        ],
        total_duration_min=210,
        total_per_capita=180,
    )


@pytest.fixture()
def replacement_node() -> ItineraryNode:
    return ItineraryNode(
        node_id="v099",
        node_type="venue",
        name="颐和园",
        address="海淀区新建宫门路19号",
        start_time="10:00",
        end_time="12:00",
        duration_min=120,
        per_capita=50,
        transit_to_next=TransitInfo(mode="地铁", duration_min=20, distance_km=5.0),
    )


# ── create_share_link ─────────────────────────────────────────────────────────


def test_create_share_link_returns_plan(sample_itinerary: Itinerary) -> None:
    """create_share_link returns a SharedPlan with a non-empty token."""
    plan = create_share_link(sample_itinerary, owner_id="u_alice", member_ids=["u_bob"])
    assert plan.token
    assert len(plan.token) > 8


def test_create_share_link_state_is_pending(sample_itinerary: Itinerary) -> None:
    plan = create_share_link(sample_itinerary, owner_id="u_alice", member_ids=["u_bob"])
    assert plan.state == PlanState.pending


def test_create_share_link_expires_in_two_hours(sample_itinerary: Itinerary) -> None:
    plan = create_share_link(sample_itinerary, owner_id="u_alice", member_ids=[])
    delta = plan.expires_at - plan.created_at
    assert timedelta(hours=1, minutes=59) < delta <= timedelta(hours=2, seconds=5)


def test_create_share_link_preserves_itinerary(sample_itinerary: Itinerary) -> None:
    plan = create_share_link(sample_itinerary, owner_id="u_alice", member_ids=[])
    assert plan.itinerary.session_id == sample_itinerary.session_id
    assert len(plan.itinerary.nodes) == len(sample_itinerary.nodes)


# ── get_shared_plan ────────────────────────────────────────────────────────────


def test_get_shared_plan_returns_plan(sample_itinerary: Itinerary) -> None:
    plan = create_share_link(sample_itinerary, owner_id="u_alice", member_ids=[])
    retrieved = get_shared_plan(plan.token)
    assert retrieved is not None
    assert retrieved.token == plan.token


def test_get_shared_plan_unknown_token() -> None:
    assert get_shared_plan("no-such-token") is None


def test_get_shared_plan_expired_returns_none(sample_itinerary: Itinerary) -> None:
    plan = create_share_link(sample_itinerary, owner_id="u_alice", member_ids=[])
    plan.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert get_shared_plan(plan.token) is None


# ── cast_vote ─────────────────────────────────────────────────────────────────


def test_cast_vote_approve_marks_no_contest(sample_itinerary: Itinerary) -> None:
    plan = create_share_link(sample_itinerary, owner_id="u_alice", member_ids=["u_bob"])
    plan = cast_vote(plan.token, "u_bob", node_index=0, approved=True)
    assert plan.contested_nodes() == []


def test_cast_vote_reject_marks_node_contested(sample_itinerary: Itinerary) -> None:
    plan = create_share_link(sample_itinerary, owner_id="u_alice", member_ids=["u_bob"])
    plan = cast_vote(plan.token, "u_bob", node_index=0, approved=False)
    assert 0 in plan.contested_nodes()


def test_cast_vote_update_overrides_previous(sample_itinerary: Itinerary) -> None:
    plan = create_share_link(sample_itinerary, owner_id="u_alice", member_ids=["u_bob"])
    cast_vote(plan.token, "u_bob", node_index=0, approved=False)
    plan = cast_vote(plan.token, "u_bob", node_index=0, approved=True)
    assert plan.contested_nodes() == []
    assert sum(1 for v in plan.votes if v.user_id == "u_bob" and v.node_index == 0) == 1


def test_cast_vote_stores_comment(sample_itinerary: Itinerary) -> None:
    plan = create_share_link(sample_itinerary, owner_id="u_alice", member_ids=["u_bob"])
    plan = cast_vote(plan.token, "u_alice", node_index=1, approved=False, comment="太贵了")
    assert any(v.comment == "太贵了" for v in plan.votes)


def test_cast_vote_invalid_user_raises(sample_itinerary: Itinerary) -> None:
    plan = create_share_link(sample_itinerary, owner_id="u_alice", member_ids=["u_bob"])
    with pytest.raises(ValueError, match="not a participant"):
        cast_vote(plan.token, "u_stranger", node_index=0, approved=True)


def test_cast_vote_out_of_range_index_raises(sample_itinerary: Itinerary) -> None:
    plan = create_share_link(sample_itinerary, owner_id="u_alice", member_ids=[])
    with pytest.raises(ValueError, match="out of range"):
        cast_vote(plan.token, "u_alice", node_index=99, approved=True)


def test_cast_vote_expired_plan_raises(sample_itinerary: Itinerary) -> None:
    plan = create_share_link(sample_itinerary, owner_id="u_alice", member_ids=[])
    plan.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    with pytest.raises(ValueError, match="expired"):
        cast_vote(plan.token, "u_alice", node_index=0, approved=True)


# ── resolve_conflicts ─────────────────────────────────────────────────────────


def test_resolve_conflicts_replaces_node(
    sample_itinerary: Itinerary, replacement_node: ItineraryNode
) -> None:
    plan = create_share_link(sample_itinerary, owner_id="u_alice", member_ids=["u_bob"])
    cast_vote(plan.token, "u_bob", node_index=0, approved=False)
    plan = resolve_conflicts(plan.token, {0: replacement_node})
    assert plan.itinerary.nodes[0].node_id == "v099"


def test_resolve_conflicts_clears_rejection_votes(
    sample_itinerary: Itinerary, replacement_node: ItineraryNode
) -> None:
    plan = create_share_link(sample_itinerary, owner_id="u_alice", member_ids=["u_bob"])
    cast_vote(plan.token, "u_bob", node_index=0, approved=False)
    plan = resolve_conflicts(plan.token, {0: replacement_node})
    assert plan.contested_nodes() == []


def test_resolve_conflicts_recalculates_totals(
    sample_itinerary: Itinerary, replacement_node: ItineraryNode
) -> None:
    plan = create_share_link(sample_itinerary, owner_id="u_alice", member_ids=[])
    plan = resolve_conflicts(plan.token, {0: replacement_node})
    expected_per_capita = sum(n.per_capita for n in plan.itinerary.nodes)
    assert plan.itinerary.total_per_capita == expected_per_capita


def test_resolve_conflicts_invalid_token_raises() -> None:
    with pytest.raises(ValueError, match="not found"):
        resolve_conflicts("bad-token", {})


# ── mark_confirmed ────────────────────────────────────────────────────────────


def test_mark_confirmed_partial_stays_pending(sample_itinerary: Itinerary) -> None:
    plan = create_share_link(sample_itinerary, owner_id="u_alice", member_ids=["u_bob"])
    plan = mark_confirmed(plan.token, "u_alice")
    assert plan.state == PlanState.pending
    assert "u_alice" in plan.confirmed_users


def test_mark_confirmed_all_transitions_to_all_confirmed(sample_itinerary: Itinerary) -> None:
    plan = create_share_link(sample_itinerary, owner_id="u_alice", member_ids=["u_bob"])
    mark_confirmed(plan.token, "u_alice")
    plan = mark_confirmed(plan.token, "u_bob")
    assert plan.state == PlanState.all_confirmed


def test_mark_confirmed_no_members_owner_only(sample_itinerary: Itinerary) -> None:
    plan = create_share_link(sample_itinerary, owner_id="u_alice", member_ids=[])
    plan = mark_confirmed(plan.token, "u_alice")
    assert plan.state == PlanState.all_confirmed


def test_mark_confirmed_invalid_user_raises(sample_itinerary: Itinerary) -> None:
    plan = create_share_link(sample_itinerary, owner_id="u_alice", member_ids=[])
    with pytest.raises(ValueError, match="not a participant"):
        mark_confirmed(plan.token, "u_stranger")


def test_mark_confirmed_wrong_state_raises(sample_itinerary: Itinerary) -> None:
    plan = create_share_link(sample_itinerary, owner_id="u_alice", member_ids=[])
    mark_confirmed(plan.token, "u_alice")
    assert plan.state == PlanState.all_confirmed
    with pytest.raises(ValueError, match="Cannot confirm"):
        mark_confirmed(plan.token, "u_alice")


# ── advance_state ─────────────────────────────────────────────────────────────


def test_advance_state_all_confirmed_to_executing(sample_itinerary: Itinerary) -> None:
    plan = create_share_link(sample_itinerary, owner_id="u_alice", member_ids=[])
    mark_confirmed(plan.token, "u_alice")
    plan = advance_state(plan.token, PlanState.executing)
    assert plan.state == PlanState.executing


def test_advance_state_executing_to_done(sample_itinerary: Itinerary) -> None:
    plan = create_share_link(sample_itinerary, owner_id="u_alice", member_ids=[])
    mark_confirmed(plan.token, "u_alice")
    advance_state(plan.token, PlanState.executing)
    plan = advance_state(plan.token, PlanState.done)
    assert plan.state == PlanState.done


def test_advance_state_invalid_transition_raises(sample_itinerary: Itinerary) -> None:
    plan = create_share_link(sample_itinerary, owner_id="u_alice", member_ids=[])
    with pytest.raises(ValueError, match="Invalid transition"):
        advance_state(plan.token, PlanState.done)


def test_advance_state_unknown_token_raises() -> None:
    with pytest.raises(ValueError, match="not found"):
        advance_state("bad-token", PlanState.executing)


# ── HTTP endpoints ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_http_share_returns_token(sample_itinerary: Itinerary) -> None:
    payload = CollabCreateRequest(
        itinerary=sample_itinerary, owner_id="u_alice", member_ids=["u_bob"]
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/api/collab/share", json=payload.model_dump())
    assert resp.status_code == 200
    body = resp.json()
    assert body["token"]
    assert body["state"] == "pending"
    assert body["share_url"].startswith("/collab/view/")


@pytest.mark.asyncio
async def test_http_get_plan_returns_itinerary(sample_itinerary: Itinerary) -> None:
    plan = create_share_link(sample_itinerary, owner_id="u_alice", member_ids=[])
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(f"/api/collab/plan/{plan.token}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["token"] == plan.token
    assert len(body["itinerary"]["nodes"]) == 2


@pytest.mark.asyncio
async def test_http_get_plan_unknown_returns_404() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/collab/plan/no-such-token")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_http_vote_and_contest(sample_itinerary: Itinerary) -> None:
    plan = create_share_link(sample_itinerary, owner_id="u_alice", member_ids=["u_bob"])
    payload = CollabVoteRequest(
        token=plan.token, user_id="u_bob", node_index=0, approved=False, comment="想换个"
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/api/collab/vote", json=payload.model_dump())
    assert resp.status_code == 200
    body = resp.json()
    assert 0 in body["contested_nodes"]


@pytest.mark.asyncio
async def test_http_confirm_unlocks_execute(sample_itinerary: Itinerary) -> None:
    plan = create_share_link(sample_itinerary, owner_id="u_alice", member_ids=["u_bob"])
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        for user in ("u_alice", "u_bob"):
            req = CollabConfirmRequest(token=plan.token, user_id=user)
            resp = await client.post("/api/collab/confirm", json=req.model_dump())
            assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "all_confirmed"


@pytest.mark.asyncio
async def test_http_advance_to_executing(sample_itinerary: Itinerary) -> None:
    plan = create_share_link(sample_itinerary, owner_id="u_alice", member_ids=[])
    mark_confirmed(plan.token, "u_alice")
    payload = CollabAdvanceRequest(token=plan.token, new_state="executing")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/api/collab/advance", json=payload.model_dump())
    assert resp.status_code == 200
    assert resp.json()["state"] == "executing"


# ── Full flow end-to-end ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_full_collab_flow(
    sample_itinerary: Itinerary, replacement_node: ItineraryNode
) -> None:
    """End-to-end: create → vote (reject node 0) → resolve → confirm all → all_confirmed."""
    # 1. Create share link
    plan = create_share_link(sample_itinerary, owner_id="u_alice", member_ids=["u_bob"])
    token = plan.token

    # 2. Bob rejects node 0
    cast_vote(token, "u_bob", node_index=0, approved=False, comment="不想去博物馆")
    assert 0 in get_shared_plan(token).contested_nodes()  # type: ignore[union-attr]

    # 3. Resolve conflict: replace node 0 with颐和园
    plan = resolve_conflicts(token, {0: replacement_node})
    assert plan.itinerary.nodes[0].node_id == "v099"
    assert plan.contested_nodes() == []

    # 4. Both confirm
    mark_confirmed(token, "u_alice")
    plan = mark_confirmed(token, "u_bob")
    assert plan.state == PlanState.all_confirmed

    # 5. Advance to executing
    plan = advance_state(token, PlanState.executing)
    assert plan.state == PlanState.executing

    # 6. Mark done
    plan = advance_state(token, PlanState.done)
    assert plan.state == PlanState.done
