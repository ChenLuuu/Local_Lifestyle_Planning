"""F05: partial replanning — swap a single itinerary node.

find_replacement_candidates: search pool for up to 3 available replacements.
apply_swap: replace node at a given index and recalculate the full timeline.
"""

from __future__ import annotations

from agent.core.time_allocator import ActivitySlot, TransitSlot, allocate
from agent.schemas import (
    ConstraintSet,
    Itinerary,
    ItineraryNode,
)
from agent.tools.check_availability import check_availability
from agent.tools.mock_data import ToolFaultError, get_restaurant_pool, get_venue_pool


async def find_replacement_candidates(
    itinerary: Itinerary,
    node_index: int,
    constraint_set: ConstraintSet,
    count: int = 3,
) -> list[ItineraryNode]:
    """Return up to `count` available replacement candidates for the node at node_index.

    Rules:
    - Candidates must not already appear in the itinerary (by node_id)
    - Candidates must match the original node_type
    - per_capita must be ≤ constraint_set budget × 1.5
    - Each candidate is availability-checked; faults are silently skipped
    - Candidates inherit the original node's time slot and transit_to_next
    """
    original = itinerary.nodes[node_index]
    existing_ids = {n.node_id for n in itinerary.nodes}
    budget_cap = int(constraint_set.soft.per_capita * 1.5)
    time_slot = original.start_time

    candidates: list[ItineraryNode] = []

    if original.node_type == "venue":
        for v in get_venue_pool():
            if len(candidates) >= count:
                break
            if v.id in existing_ids:
                continue
            if v.per_capita > budget_cap:
                continue
            try:
                result = await check_availability(v.id, time_slot)
                if not result["available"]:
                    continue
            except ToolFaultError:
                continue
            candidates.append(ItineraryNode(
                node_id=v.id,
                node_type="venue",
                name=v.name,
                address=v.address,
                start_time=original.start_time,
                end_time=original.end_time,
                duration_min=original.duration_min,
                per_capita=v.per_capita,
                transit_to_next=original.transit_to_next,
            ))

    elif original.node_type == "restaurant":
        for r in get_restaurant_pool():
            if len(candidates) >= count:
                break
            if r.id in existing_ids:
                continue
            if r.per_capita > budget_cap:
                continue
            try:
                result = await check_availability(r.id, time_slot)
                if not result["available"]:
                    continue
            except ToolFaultError:
                continue
            candidates.append(ItineraryNode(
                node_id=r.id,
                node_type="restaurant",
                name=r.name,
                address=r.address,
                start_time=original.start_time,
                end_time=original.end_time,
                duration_min=original.duration_min,
                per_capita=r.per_capita,
                transit_to_next=original.transit_to_next,
            ))

    return candidates


def apply_swap(
    itinerary: Itinerary,
    node_index: int,
    replacement: ItineraryNode,
    window_start: str,
    window_duration_min: int,
) -> Itinerary:
    """Replace node at node_index with `replacement` and recalculate the timeline.

    Transit segments are preserved from the original itinerary.
    Raises TimeConflictError if the new timeline cannot fit in the window.
    """
    nodes = list(itinerary.nodes)

    activities: list[ActivitySlot] = []
    for i, node in enumerate(nodes):
        src = replacement if i == node_index else node
        activities.append(ActivitySlot(
            node_id=src.node_id,
            node_type=src.node_type,
            name=src.name,
            address=src.address,
            duration_min=src.duration_min,
            per_capita=src.per_capita,
        ))

    transits: list[TransitSlot] = []
    for node in nodes[:-1]:
        if node.transit_to_next:
            transits.append(TransitSlot(
                mode=node.transit_to_next.mode,
                duration_min=node.transit_to_next.duration_min,
                distance_km=node.transit_to_next.distance_km,
            ))
        else:
            transits.append(TransitSlot(mode="地铁", duration_min=15, distance_km=3.0))

    new_nodes = allocate(activities, transits, window_start, window_duration_min)

    return Itinerary(
        session_id=itinerary.session_id,
        nodes=new_nodes,
        total_duration_min=sum(n.duration_min for n in new_nodes) + sum(
            n.transit_to_next.duration_min for n in new_nodes if n.transit_to_next
        ),
        total_per_capita=sum(n.per_capita for n in new_nodes),
    )
