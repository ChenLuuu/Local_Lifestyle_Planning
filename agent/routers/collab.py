"""F08: FastAPI router for collaborative confirmation."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from agent.modules.collab_confirm import (
    PlanState,
    SharedPlan,
    advance_state,
    cast_vote,
    create_share_link,
    get_shared_plan,
    mark_confirmed,
    resolve_conflicts,
)
from agent.schemas import (
    CollabAdvanceRequest,
    CollabConfirmRequest,
    CollabCreateRequest,
    CollabCreateResponse,
    CollabPlanResponse,
    CollabResolveRequest,
    CollabVoteRequest,
)

router = APIRouter(prefix="/api/collab", tags=["collab"])


@router.post("/share", response_model=CollabCreateResponse)
async def create_share(req: CollabCreateRequest) -> CollabCreateResponse:
    plan = create_share_link(req.itinerary, req.owner_id, req.member_ids)
    return CollabCreateResponse(
        token=plan.token,
        expires_at=plan.expires_at.isoformat(),
        share_url=f"/collab/view/{plan.token}",
        state=plan.state,
    )


@router.get("/plan/{token}", response_model=CollabPlanResponse)
async def get_plan(token: str) -> CollabPlanResponse:
    plan = get_shared_plan(token)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found or expired")
    return _to_response(plan)


@router.post("/vote", response_model=CollabPlanResponse)
async def vote(req: CollabVoteRequest) -> CollabPlanResponse:
    try:
        plan = cast_vote(
            req.token, req.user_id, req.node_index, req.approved, req.comment
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_response(plan)


@router.post("/resolve", response_model=CollabPlanResponse)
async def resolve(req: CollabResolveRequest) -> CollabPlanResponse:
    try:
        plan = resolve_conflicts(req.token, dict(req.replacement_map))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_response(plan)


@router.post("/confirm", response_model=CollabPlanResponse)
async def confirm(req: CollabConfirmRequest) -> CollabPlanResponse:
    try:
        plan = mark_confirmed(req.token, req.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_response(plan)


@router.post("/advance", response_model=CollabPlanResponse)
async def advance(req: CollabAdvanceRequest) -> CollabPlanResponse:
    try:
        plan = advance_state(req.token, PlanState(req.new_state))
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_response(plan)


def _to_response(plan: SharedPlan) -> CollabPlanResponse:
    return CollabPlanResponse(
        token=plan.token,
        itinerary=plan.itinerary,
        owner_id=plan.owner_id,
        member_ids=plan.member_ids,
        contested_nodes=plan.contested_nodes(),
        confirmed_users=sorted(plan.confirmed_users),
        state=plan.state,
        expires_at=plan.expires_at.isoformat(),
    )
