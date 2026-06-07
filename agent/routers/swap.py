"""Router: node-swap endpoints — F05 partial replanning.

POST /api/plan/swap/candidates  → find 3 replacement candidates for a node
POST /api/plan/swap/accept      → accept a candidate and recalculate timeline
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from agent.core.partial_replan import apply_swap, find_replacement_candidates
from agent.core.time_allocator import TimeConflictError
from agent.schemas import (
    SwapAcceptRequest,
    SwapAcceptResponse,
    SwapCandidatesRequest,
    SwapCandidatesResponse,
)

router = APIRouter(prefix="/api/plan/swap", tags=["swap"])


@router.post("/candidates", response_model=SwapCandidatesResponse)
async def get_swap_candidates(body: SwapCandidatesRequest) -> SwapCandidatesResponse:
    """Return up to 3 replacement candidates for the node at body.node_index."""
    if body.node_index >= len(body.itinerary.nodes):
        raise HTTPException(
            status_code=422,
            detail=f"node_index {body.node_index} out of range "
                   f"(itinerary has {len(body.itinerary.nodes)} nodes)",
        )
    candidates = await find_replacement_candidates(
        itinerary=body.itinerary,
        node_index=body.node_index,
        constraint_set=body.constraint_set,
    )
    return SwapCandidatesResponse(
        session_id=body.session_id,
        node_index=body.node_index,
        candidates=candidates,
    )


@router.post("/accept", response_model=SwapAcceptResponse)
async def accept_swap(body: SwapAcceptRequest) -> SwapAcceptResponse:
    """Accept a swap candidate and return the recalculated itinerary."""
    if body.node_index >= len(body.itinerary.nodes):
        raise HTTPException(
            status_code=422,
            detail=f"node_index {body.node_index} out of range "
                   f"(itinerary has {len(body.itinerary.nodes)} nodes)",
        )
    window_start = body.itinerary.nodes[0].start_time
    window_duration_min = int(body.constraint_set.hard.total_duration * 60)

    try:
        new_itinerary = apply_swap(
            itinerary=body.itinerary,
            node_index=body.node_index,
            replacement=body.candidate,
            window_start=window_start,
            window_duration_min=window_duration_min,
        )
    except TimeConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return SwapAcceptResponse(session_id=body.session_id, itinerary=new_itinerary)
