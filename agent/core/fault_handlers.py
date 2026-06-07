"""Fault router: 3-class fault × 3-level degradation.

Fault classes:
  NO_SEAT       – no seat / no ticket at requested time (most common Mock fault)
  TIME_CONFLICT – a scheduled slot overlaps with another node
  NO_NEARBY     – no same-category POI within 500 m radius

Degradation cascade (tried in order):
  Level 1 SILENT_REPLACE   – find an available replacement; show reason to user
  Level 2 REORDER          – drop the failed node; compress remaining schedule
  Level 3 USER_DECISION    – no viable path; surface the choice to the user

All ToolFaultError exceptions raised by tools must be routed here.
route_fault() never raises — it always returns a FaultResult.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from agent.schemas import ConstraintSet, Itinerary, ItineraryNode
from agent.tools.check_availability import check_availability
from agent.tools.mock_data import (
    MockRestaurantData,
    MockVenueData,
    ToolFaultError,
    get_restaurant_pool,
    get_venue_pool,
)


class FaultClass(StrEnum):
    NO_SEAT = "no_seat"
    TIME_CONFLICT = "time_conflict"
    NO_NEARBY = "no_nearby"


class DegradationLevel(StrEnum):
    LEVEL_1_SILENT = "level_1_silent"
    LEVEL_2_REORDER = "level_2_reorder"
    LEVEL_3_USER_DECISION = "level_3_user_decision"


@dataclass
class FaultContext:
    """All context needed to route a fault to the right handler."""

    failed_node: ItineraryNode
    node_index: int
    itinerary: Itinerary
    constraint_set: ConstraintSet
    original_error: str


@dataclass
class FaultResult:
    """The outcome of fault handling.  Never raises; always populated."""

    level: DegradationLevel
    fault_class: FaultClass
    message: str
    replacement_node: ItineraryNode | None = field(default=None)
    reordered_itinerary: Itinerary | None = field(default=None)
    requires_user_action: bool = field(default=False)


def classify_fault(exc: ToolFaultError) -> FaultClass:
    """Map a ToolFaultError message to one of the three fault classes."""
    msg = str(exc).lower()
    if "时间冲突" in msg or "time_conflict" in msg or "conflict" in msg:
        return FaultClass.TIME_CONFLICT
    if "周边" in msg or "no_nearby" in msg:
        return FaultClass.NO_NEARBY
    return FaultClass.NO_SEAT


async def _try_level1(ctx: FaultContext) -> ItineraryNode | None:
    """Level 1: find an available same-type replacement from the mock pool.

    Filters: same node_type, not already in itinerary, per_capita ≤ budget × 1.5.
    Returns the first available candidate, or None if none found.
    """
    node = ctx.failed_node
    existing_ids = {n.node_id for n in ctx.itinerary.nodes}
    budget_cap = int(ctx.constraint_set.soft.per_capita * 1.5)

    pool: list[MockVenueData | MockRestaurantData] = []
    if node.node_type == "venue":
        pool = [
            v for v in get_venue_pool()
            if v.id not in existing_ids and v.per_capita <= budget_cap
        ]
    elif node.node_type == "restaurant":
        pool = [
            r for r in get_restaurant_pool()
            if r.id not in existing_ids and r.per_capita <= budget_cap
        ]

    for item in pool:
        try:
            result = await check_availability(item.id, node.start_time)
            if result["available"]:
                return ItineraryNode(
                    node_id=item.id,
                    node_type=node.node_type,
                    name=item.name,
                    address=item.address,
                    start_time=node.start_time,
                    end_time=node.end_time,
                    duration_min=node.duration_min,
                    per_capita=item.per_capita,
                    transit_to_next=node.transit_to_next,
                )
        except ToolFaultError:
            continue

    return None


def _try_level2(ctx: FaultContext) -> Itinerary | None:
    """Level 2: drop the failed node and repack the remaining schedule.

    Returns None when the itinerary has only one node (nothing to repack).
    """
    from agent.core.time_allocator import (  # local to avoid circular at module level
        ActivitySlot,
        TimeConflictError,
        TransitSlot,
        allocate,
    )

    remaining = [n for i, n in enumerate(ctx.itinerary.nodes) if i != ctx.node_index]
    if not remaining:
        return None

    activities = [
        ActivitySlot(
            node_id=n.node_id,
            node_type=n.node_type,
            name=n.name,
            address=n.address,
            duration_min=n.duration_min,
            per_capita=n.per_capita,
        )
        for n in remaining
    ]
    transits: list[TransitSlot] = []
    for n in remaining[:-1]:
        if n.transit_to_next:
            transits.append(TransitSlot(
                mode=n.transit_to_next.mode,
                duration_min=n.transit_to_next.duration_min,
                distance_km=n.transit_to_next.distance_km,
            ))
        else:
            transits.append(TransitSlot(mode="地铁", duration_min=15, distance_km=3.0))

    window_start = ctx.itinerary.nodes[0].start_time
    window_min = int(ctx.constraint_set.hard.total_duration * 60)

    try:
        new_nodes = allocate(activities, transits, window_start, window_min)
    except TimeConflictError:
        return None

    return Itinerary(
        session_id=ctx.itinerary.session_id,
        nodes=new_nodes,
        total_duration_min=sum(n.duration_min for n in new_nodes) + sum(
            n.transit_to_next.duration_min for n in new_nodes if n.transit_to_next
        ),
        total_per_capita=sum(n.per_capita for n in new_nodes),
    )


async def route_fault(exc: ToolFaultError, ctx: FaultContext) -> FaultResult:
    """Main fault router.  Never raises — always returns a FaultResult.

    Cascade: Level 1 (silent replace) → Level 2 (reorder) → Level 3 (user decision).
    """
    fault_class = classify_fault(exc)

    # ── Level 1: silent replacement ──────────────────────────────────────────
    try:
        replacement = await _try_level1(ctx)
    except Exception:
        replacement = None

    if replacement is not None:
        return FaultResult(
            level=DegradationLevel.LEVEL_1_SILENT,
            fault_class=fault_class,
            message=(
                f"【Level 1 静默替换】{ctx.failed_node.name} 当前时段不可用，"
                f"已自动替换为 {replacement.name}（同区域同类型）。"
            ),
            replacement_node=replacement,
        )

    # ── Level 2: reorder / compress ──────────────────────────────────────────
    try:
        reordered = _try_level2(ctx)
    except Exception:
        reordered = None

    if reordered is not None:
        return FaultResult(
            level=DegradationLevel.LEVEL_2_REORDER,
            fault_class=fault_class,
            message=(
                f"【Level 2 方案重排】{ctx.failed_node.name} 无可用替换，"
                f"已移除该节点并压缩行程，剩余 {len(reordered.nodes)} 个节点。"
            ),
            reordered_itinerary=reordered,
        )

    # ── Level 3: user decision required ──────────────────────────────────────
    return FaultResult(
        level=DegradationLevel.LEVEL_3_USER_DECISION,
        fault_class=fault_class,
        message=(
            f"【Level 3 暂停执行】{ctx.failed_node.name} 周边 500 米内无同类可用选项，"
            f"请选择：取消该节点 / 重新搜索 / 中止行程。"
        ),
        requires_user_action=True,
    )
