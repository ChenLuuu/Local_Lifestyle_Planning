"""ReAct main loop: Thought → Action → Observation → Itinerary.

Design (D004): hand-written asyncio loop.
- Parallel:  venue_search + restaurant_search
- Serial:    check_availability per candidate
- Ordering:  restaurant inserted at nearest lunch/dinner window
- Routes:    computed for every adjacent node pair (not just first two)
- Streams:   ReactEventData via async generator (SSE-ready)
"""

from __future__ import annotations

import asyncio
import json
import math
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from agent.core.time_allocator import ActivitySlot, TimeConflictError, TransitSlot
from agent.core.time_allocator import allocate as _ta_allocate
from agent.schemas import (
    ConstraintSet,
    Itinerary,
    ItineraryNode,
    ReactEventData,
    RestaurantResult,
    VenueResult,
)
from agent.tools.check_availability import check_availability
from agent.tools.mock_data import ToolFaultError, make_route
from agent.tools.restaurant_search import restaurant_search
from agent.tools.venue_search import venue_search

# Lunch: 11:30-13:30, Dinner: 17:30-20:00
_MEAL_WINDOWS = [
    (11 * 60 + 30, 13 * 60 + 30),
    (17 * 60 + 30, 20 * 60),
]


def _to_min(hhmm: str) -> int:
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m


def _add_minutes(hhmm: str, minutes: int) -> str:
    t = datetime.strptime(hhmm, "%H:%M") + timedelta(minutes=minutes)
    return t.strftime("%H:%M")


def _in_meal_window(minutes: int) -> bool:
    return any(lo <= minutes <= hi for lo, hi in _MEAL_WINDOWS)


def _meal_insert_index(
    venue_durs: list[int], start_min: int, avg_transit: int = 15
) -> int:
    """Return index at which to insert the restaurant.

    0 = before venue[0] (start time already in a meal window).
    k = after venue[k-1] (cursor lands in a meal window after visiting venue[k-1]).
    len(venue_durs) = no meal window hit; fall back to middle.
    """
    cursor = start_min
    if _in_meal_window(cursor):
        return 0
    for i, dur in enumerate(venue_durs):
        cursor += dur
        if _in_meal_window(cursor):
            return i + 1
        cursor += avg_transit
    return max(1, len(venue_durs) // 2)


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    cos_lat = math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
    a = math.sin(dlat / 2) ** 2 + cos_lat * math.sin(dlng / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


@dataclass
class _Stop:
    node_id: str
    name: str
    node_type: str
    address: str
    lat: float
    lng: float
    duration_min: int
    per_capita: int


def _venue_stop(v: VenueResult) -> _Stop:
    return _Stop(
        v["id"], v["name"], "venue", v["address"],
        v["lat"], v["lng"], v["duration_min"], v["per_capita"],
    )


def _rest_stop(r: RestaurantResult) -> _Stop:
    return _Stop(
        r["id"], r["name"], "restaurant", r["address"],
        r["lat"], r["lng"], r["duration_min"], r["per_capita"],
    )


def _build_ordered_stops(
    venues: list[VenueResult],
    restaurants: list[RestaurantResult],
    node_count: int,
    start_time: str,
) -> list[_Stop]:
    """Build stop list with restaurant placed at the nearest meal-time window."""
    cand_v = venues[: node_count - 1]
    cand_r = restaurants[:1]

    if not cand_v:
        return [_rest_stop(r) for r in cand_r]
    if not cand_r:
        return [_venue_stop(v) for v in cand_v]

    venue_durs = [v["duration_min"] for v in cand_v]
    insert_at = _meal_insert_index(venue_durs, _to_min(start_time))

    stops: list[_Stop] = []
    rest_placed = False
    for i, v in enumerate(cand_v):
        if i == insert_at and not rest_placed:
            stops.append(_rest_stop(cand_r[0]))
            rest_placed = True
        stops.append(_venue_stop(v))
    if not rest_placed:
        stops.append(_rest_stop(cand_r[0]))

    return stops


def _assemble_nodes(
    stops: list[_Stop], start_time: str, window_min: int = 24 * 60
) -> list[ItineraryNode]:
    """Build ItineraryNode list, pruning activities to fit within window_min.

    Computes per-segment haversine routes, then delegates to time_allocator
    which enforces the time budget via hard-validate → elastic-fill → conflict-check.
    """
    acts: list[ActivitySlot] = []
    trns: list[TransitSlot] = []
    for i, stop in enumerate(stops):
        acts.append(ActivitySlot(
            node_id=stop.node_id,
            node_type=stop.node_type,
            name=stop.name,
            address=stop.address,
            duration_min=stop.duration_min,
            per_capita=stop.per_capita,
        ))
        if i < len(stops) - 1:
            nxt = stops[i + 1]
            dist = _haversine(stop.lat, stop.lng, nxt.lat, nxt.lng)
            rt = make_route(stop.address, nxt.address, dist)
            trns.append(TransitSlot(
                mode=rt.transit_mode,
                duration_min=rt.duration_min,
                distance_km=rt.distance_km,
            ))
    try:
        return _ta_allocate(acts, trns, start_time, window_min)
    except TimeConflictError:
        # Even a single activity can't fit; return it capped at the window
        if acts:
            acts[0].duration_min = min(acts[0].duration_min, window_min)
            return _ta_allocate(acts[:1], [], start_time, window_min)
        return []


def _t(content: str) -> ReactEventData:
    return ReactEventData(type="thought", content=content)


def _a(tool: str, params: dict[str, Any]) -> ReactEventData:
    return ReactEventData(type="action", tool=tool, params=params)


def _o(tool: str, result: dict[str, Any]) -> ReactEventData:
    return ReactEventData(type="observation", tool=tool, result=result)


async def _avail(item_id: str, time_slot: str) -> bool:
    try:
        r = await check_availability(item_id, time_slot)
        return r["available"]
    except ToolFaultError:
        return False


async def run(
    constraint_set: ConstraintSet,
    session_id: str,
    start_time: str = "10:00",
    profile_tags: list[str] | None = None,
) -> AsyncIterator[ReactEventData]:
    """Return an async generator of SSE-compatible ReactEventData.

    When LLM_API_KEY is set, delegates to llm_planner (F14).
    Falls back to deterministic planning when the key is absent.
    """
    if os.getenv("LLM_API_KEY"):
        from agent.core import llm_planner  # lazy import avoids circular deps

        return await llm_planner.run(
            constraint_set, session_id, start_time, profile_tags
        )

    async def _impl() -> AsyncIterator[ReactEventData]:
        # ── Round 1: parallel search ──────────────────────────────────────
        yield _t(
            f"分析约束：预算 ¥{constraint_set.soft.per_capita}/人，"
            f"时长 {constraint_set.hard.total_duration}h，"
            f"偏好 {constraint_set.soft.tags}。并行搜索场地与餐厅。"
        )
        budget = constraint_set.soft.per_capita
        yield _a("venue_search", {
            "per_capita": budget, "tags": constraint_set.soft.tags
        })
        yield _a("restaurant_search", {"per_capita": budget})

        venues: list[VenueResult]
        restaurants: list[RestaurantResult]
        try:
            venues, restaurants = await asyncio.gather(
                venue_search(constraint_set),
                restaurant_search(constraint_set),
            )
        except ToolFaultError as exc:
            yield ReactEventData(type="error", error=str(exc), content="搜索故障，重试")
            venues = await venue_search(constraint_set)
            restaurants = await restaurant_search(constraint_set)

        v_top = venues[0]["name"] if venues else "-"
        r_top = restaurants[0]["name"] if restaurants else "-"
        yield _o("venue_search", {"count": len(venues), "top": v_top})
        yield _o("restaurant_search", {"count": len(restaurants), "top": r_top})

        # ── Round 2: tag re-rank + determine node count ───────────────────
        node_count = 3 if constraint_set.hard.total_duration < 6.0 else 4
        pref_tags = set(constraint_set.soft.tags)
        venues = sorted(
            venues, key=lambda v: len(pref_tags & set(v["tags"])), reverse=True
        )

        yield _t(
            f"按偏好标签重排候选，出发时间 {start_time}，"
            f"将根据午/晚餐时间窗口智能插入餐厅，计划 {node_count} 个节点。"
        )

        cand_venues = venues[: node_count - 1]
        cand_rest = restaurants[:1]

        # ── Round 3: serial availability check ───────────────────────────
        yield _t("逐一检查座位/票务可用性（串行）。")

        confirmed_venues: list[VenueResult] = []
        for v_cand in cand_venues:
            yield _a("check_availability", {
                "item_id": v_cand["id"], "time_slot": start_time
            })
            ok = await _avail(v_cand["id"], start_time)
            yield _o("check_availability", {"item_id": v_cand["id"], "available": ok})
            if ok:
                confirmed_venues.append(v_cand)
            else:
                for v_fb in venues[node_count:]:
                    if await _avail(v_fb["id"], start_time):
                        confirmed_venues.append(v_fb)
                        yield _t(f"Level 1 替换：{v_cand['name']} → {v_fb['name']}")
                        break

        confirmed_rest: list[RestaurantResult] = []
        for r_cand in cand_rest:
            ok = await _avail(r_cand["id"], start_time)
            if ok:
                confirmed_rest.append(r_cand)
            else:
                for r_fb in restaurants[1:]:
                    if await _avail(r_fb["id"], start_time):
                        confirmed_rest.append(r_fb)
                        yield _t(f"Level 1 替换餐厅：{r_cand['name']} → {r_fb['name']}")
                        break

        # ── Round 4: order + all-pairs routes + assemble ─────────────────
        yield _t("按用餐时机排序节点，逐段计算精确路线，组装时间轴。")

        final_venues = confirmed_venues or list(cand_venues)
        final_rest = confirmed_rest or list(cand_rest)

        window_min = int(constraint_set.hard.total_duration * 60)
        stops = _build_ordered_stops(final_venues, final_rest, node_count, start_time)
        nodes = _assemble_nodes(stops, start_time, window_min)

        total_dur = sum(n.duration_min for n in nodes) + sum(
            n.transit_to_next.duration_min for n in nodes if n.transit_to_next
        )
        itinerary = Itinerary(
            session_id=session_id,
            nodes=nodes,
            total_duration_min=total_dur,
            total_per_capita=sum(n.per_capita for n in nodes),
        )
        yield ReactEventData(
            type="done",
            content=f"规划完成：{len(nodes)} 节点，人均 ¥{itinerary.total_per_capita}",
            itinerary=json.loads(itinerary.model_dump_json()),
        )

    return _impl()
