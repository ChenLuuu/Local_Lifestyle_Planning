"""F08: multi-user collaborative confirmation.

SharedPlan state machine: pending → all_confirmed → executing → done.

create_share_link  → SharedPlan (token valid 2 hours)
get_shared_plan    → SharedPlan | None (None if not found or expired)
cast_vote          → SharedPlan
resolve_conflicts  → SharedPlan (apply replacements for contested nodes)
mark_confirmed     → SharedPlan (all confirmed → state = all_confirmed)
advance_state      → SharedPlan (all_confirmed → executing → done)
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from agent.schemas import Itinerary, ItineraryNode


class PlanState(StrEnum):
    pending = "pending"
    all_confirmed = "all_confirmed"
    executing = "executing"
    done = "done"


@dataclass
class MemberVote:
    user_id: str
    node_index: int
    approved: bool
    comment: str = ""


@dataclass
class SharedPlan:
    token: str
    itinerary: Itinerary
    owner_id: str
    member_ids: list[str]
    votes: list[MemberVote] = field(default_factory=list)
    confirmed_users: set[str] = field(default_factory=set)
    state: PlanState = PlanState.pending
    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )
    expires_at: datetime = field(
        default_factory=lambda: datetime.now(UTC) + timedelta(hours=2)
    )

    def is_expired(self) -> bool:
        return datetime.now(UTC) > self.expires_at

    def all_participants(self) -> set[str]:
        return {self.owner_id} | set(self.member_ids)

    def contested_nodes(self) -> list[int]:
        """Indices of nodes that received at least one rejection vote."""
        rejected: set[int] = set()
        for v in self.votes:
            if not v.approved:
                rejected.add(v.node_index)
        return sorted(rejected)

    def is_all_confirmed(self) -> bool:
        return self.all_participants() <= self.confirmed_users


# Module-level in-memory store (mirrors execute_booking's idempotency store pattern)
_store: dict[str, SharedPlan] = {}


def create_share_link(
    itinerary: Itinerary,
    owner_id: str,
    member_ids: list[str],
) -> SharedPlan:
    """Create a SharedPlan with a secure token. Valid for 2 hours."""
    token = secrets.token_urlsafe(16)
    plan = SharedPlan(
        token=token,
        itinerary=itinerary,
        owner_id=owner_id,
        member_ids=list(member_ids),
    )
    _store[token] = plan
    return plan


def get_shared_plan(token: str) -> SharedPlan | None:
    """Return the SharedPlan, or None if not found or expired."""
    plan = _store.get(token)
    if plan is None or plan.is_expired():
        return None
    return plan


def cast_vote(
    token: str,
    user_id: str,
    node_index: int,
    approved: bool,
    comment: str = "",
) -> SharedPlan:
    """Cast or update a vote for a node. Raises ValueError for invalid inputs."""
    plan = get_shared_plan(token)
    if plan is None:
        raise ValueError(f"Plan not found or expired: {token}")
    if plan.state != PlanState.pending:
        raise ValueError(f"Plan is not in pending state: {plan.state}")
    if user_id not in plan.all_participants():
        raise ValueError(f"User {user_id!r} is not a participant")
    if not (0 <= node_index < len(plan.itinerary.nodes)):
        raise ValueError(f"node_index {node_index} out of range")

    # Replace existing vote for this user+node combination
    plan.votes = [
        v for v in plan.votes
        if not (v.user_id == user_id and v.node_index == node_index)
    ]
    plan.votes.append(MemberVote(
        user_id=user_id,
        node_index=node_index,
        approved=approved,
        comment=comment,
    ))
    return plan


def resolve_conflicts(
    token: str,
    replacement_map: dict[int, ItineraryNode],
) -> SharedPlan:
    """Replace contested nodes and recalculate totals.

    replacement_map: {node_index: replacement_ItineraryNode}
    Caller is responsible for sourcing candidates (via find_replacement_candidates).
    Rejection votes for resolved nodes are cleared after replacement.
    """
    plan = get_shared_plan(token)
    if plan is None:
        raise ValueError(f"Plan not found or expired: {token}")
    if plan.state != PlanState.pending:
        raise ValueError(f"Plan is not in pending state: {plan.state}")

    nodes = list(plan.itinerary.nodes)
    for idx, replacement in replacement_map.items():
        if 0 <= idx < len(nodes):
            nodes[idx] = replacement

    plan.itinerary = Itinerary(
        session_id=plan.itinerary.session_id,
        nodes=nodes,
        total_duration_min=sum(n.duration_min for n in nodes) + sum(
            n.transit_to_next.duration_min for n in nodes if n.transit_to_next
        ),
        total_per_capita=sum(n.per_capita for n in nodes),
    )
    # Clear rejection votes for replaced nodes so they are no longer contested
    resolved = set(replacement_map.keys())
    plan.votes = [v for v in plan.votes if v.node_index not in resolved or v.approved]
    return plan


def mark_confirmed(token: str, user_id: str) -> SharedPlan:
    """Mark a participant as confirmed.

    When all participants confirm, state transitions to all_confirmed.
    """
    plan = get_shared_plan(token)
    if plan is None:
        raise ValueError(f"Plan not found or expired: {token}")
    if plan.state != PlanState.pending:
        raise ValueError(f"Cannot confirm in state: {plan.state}")
    if user_id not in plan.all_participants():
        raise ValueError(f"User {user_id!r} is not a participant")

    plan.confirmed_users.add(user_id)
    if plan.is_all_confirmed():
        plan.state = PlanState.all_confirmed
    return plan


_VALID_TRANSITIONS: dict[PlanState, PlanState] = {
    PlanState.all_confirmed: PlanState.executing,
    PlanState.executing: PlanState.done,
}


def advance_state(token: str, new_state: PlanState) -> SharedPlan:
    """Advance the plan through: all_confirmed → executing → done."""
    plan = _store.get(token)
    if plan is None:
        raise ValueError(f"Plan not found: {token}")
    if _VALID_TRANSITIONS.get(plan.state) != new_state:
        raise ValueError(f"Invalid transition: {plan.state} → {new_state}")
    plan.state = new_state
    return plan


def clear_store() -> None:
    """Reset the in-memory store. For testing only."""
    _store.clear()
