"""Router: core planning Agent endpoint — POST /api/plan/run (SSE)."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from agent.core import react_loop
from agent.modules.profile_store import get_profile
from agent.schemas import PlanRunRequest

router = APIRouter(prefix="/api/plan", tags=["plan"])


@router.post("/run")
async def plan_run(body: PlanRunRequest) -> EventSourceResponse:
    """Run the ReAct loop and stream Thought/Action/Observation/Done events."""

    profile_tags: list[str] | None = None
    if body.user_id:
        profile = get_profile(body.user_id)
        if profile.preference_tags:
            profile_tags = profile.preference_tags

    async def _event_gen() -> AsyncGenerator[dict[str, str], None]:
        effective_start = body.constraint_set.raw_labels.start_time or body.start_time
        gen = await react_loop.run(
            body.constraint_set,
            body.session_id,
            effective_start,
            profile_tags,
        )
        async for event in gen:
            yield {"data": json.dumps(event, ensure_ascii=False)}
        yield {"data": "[DONE]"}

    return EventSourceResponse(_event_gen())
