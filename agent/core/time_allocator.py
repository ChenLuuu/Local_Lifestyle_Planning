"""Time allocator: hard validate → elastic fill → conflict check. F04."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from agent.schemas import ItineraryNode, TransitInfo


@dataclass
class ActivitySlot:
    node_id: str
    node_type: str
    name: str
    address: str
    duration_min: int
    per_capita: int
    priority: int = field(default=5)
    extendable: bool = field(default=True)


@dataclass
class TransitSlot:
    mode: str
    duration_min: int
    distance_km: float


class TimeConflictError(Exception):
    """Timeline cannot fit in the given window; trigger partial_replan."""


def _hhmm_add(base: str, minutes: int) -> str:
    t = datetime.strptime(base, "%H:%M") + timedelta(minutes=minutes)
    return t.strftime("%H:%M")


def _min_duration(acts: list[ActivitySlot], trns: list[TransitSlot]) -> int:
    return sum(a.duration_min for a in acts) + sum(t.duration_min for t in trns)


def _hard_validate(
    activities: list[ActivitySlot],
    transits: list[TransitSlot],
    window: int,
) -> tuple[list[ActivitySlot], list[TransitSlot]]:
    """Prune lowest-priority activities until minimum duration fits in window."""
    acts: list[ActivitySlot] = [dataclasses.replace(a) for a in activities]
    trns: list[TransitSlot] = list(transits)

    while len(acts) > 1 and _min_duration(acts, trns) > window:
        n = len(acts)
        worst_idx = max(range(n), key=lambda i: (acts[i].priority, i))
        # Determine which transit segment to remove:
        # - removing first activity → drop transit[0]
        # - removing last activity  → drop transit[-1]
        # - removing middle activity → drop incoming transit[worst_idx-1],
        #   keep outgoing transit as proxy for the new neighbour pair
        if worst_idx == 0:
            t_remove = 0
        elif worst_idx == n - 1:
            t_remove = len(trns) - 1
        else:
            t_remove = worst_idx - 1
        acts.pop(worst_idx)
        if trns:
            trns.pop(t_remove)

    min_dur = _min_duration(acts, trns)
    if min_dur > window:
        raise TimeConflictError(
            f"minimum duration {min_dur}min exceeds window {window}min; "
            "trigger partial_replan for level 2 replacement"
        )
    return acts, trns


def _elastic_allocate(
    acts: list[ActivitySlot],
    trns: list[TransitSlot],
    window: int,
) -> None:
    """Distribute slack time proportionally to extendable activities."""
    slack = window - _min_duration(acts, trns)
    if slack <= 0:
        return
    extendable = [a for a in acts if a.extendable]
    if not extendable:
        return
    base_total = sum(a.duration_min for a in extendable)
    distributed = 0
    for a in extendable[:-1]:
        extra = int(slack * a.duration_min / base_total)
        a.duration_min += extra
        distributed += extra
    extendable[-1].duration_min += slack - distributed


def _build_timeline(
    acts: list[ActivitySlot],
    trns: list[TransitSlot],
    window_start: str,
) -> list[ItineraryNode]:
    nodes: list[ItineraryNode] = []
    cursor = window_start
    for i, act in enumerate(acts):
        start = cursor
        end = _hhmm_add(start, act.duration_min)
        transit: TransitInfo | None = None
        if i < len(trns):
            t = trns[i]
            transit = TransitInfo(
                mode=t.mode,
                duration_min=t.duration_min,
                distance_km=t.distance_km,
            )
            cursor = _hhmm_add(end, t.duration_min)
        else:
            cursor = end
        nodes.append(ItineraryNode(
            node_id=act.node_id,
            node_type=act.node_type,
            name=act.name,
            address=act.address,
            start_time=start,
            end_time=end,
            duration_min=act.duration_min,
            per_capita=act.per_capita,
            transit_to_next=transit,
        ))
    return nodes


def _check_conflicts(
    nodes: list[ItineraryNode],
    window_start: str,
    window_duration_min: int,
) -> None:
    """Verify timeline fits in window and has no overlapping segments."""
    if not nodes:
        return
    window_end = _hhmm_add(window_start, window_duration_min)
    if nodes[-1].end_time > window_end:
        raise TimeConflictError(
            f"timeline end {nodes[-1].end_time} exceeds window end {window_end}; "
            "trigger partial_replan for level 1 replacement"
        )
    for i in range(len(nodes) - 1):
        curr, nxt = nodes[i], nodes[i + 1]
        boundary = (
            _hhmm_add(curr.end_time, curr.transit_to_next.duration_min)
            if curr.transit_to_next
            else curr.end_time
        )
        if boundary > nxt.start_time:
            raise TimeConflictError(
                f"overlap: {curr.name} boundary {boundary} > "
                f"{nxt.name} start {nxt.start_time}; "
                "trigger partial_replan for level 1 replacement"
            )


def allocate(
    activities: list[ActivitySlot],
    transits: list[TransitSlot],
    window_start: str,
    window_duration_min: int,
) -> list[ItineraryNode]:
    """Three-step time allocation algorithm.

    1. Hard validate: prune lowest-priority activities until minimum fits window.
    2. Elastic allocate: distribute slack proportionally to extendable activities.
    3. Conflict check: verify no overlaps and timeline fits within window.

    Returns a list of ItineraryNode with non-overlapping times.
    Raises TimeConflictError if even a single activity cannot fit.
    """
    if not activities:
        return []
    acts, trns = _hard_validate(activities, transits, window_duration_min)
    _elastic_allocate(acts, trns, window_duration_min)
    nodes = _build_timeline(acts, trns, window_start)
    _check_conflicts(nodes, window_start, window_duration_min)
    return nodes
