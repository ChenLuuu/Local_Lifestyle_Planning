"""LLM-backed planner using DashScope qwen-plus Function Calling (F14).

Replaces the deterministic scoring in react_loop with generative planning:
1. Emit first Thought immediately (satisfies ≤3 s first-byte SLA).
2. Run multi-turn OpenAI-compatible Function Calling loop via DashScope.
   Max 3 rounds × 8 s timeout = 24 s; scoring pass adds ≤5 s → total ≤29 s.
3. Collect tool results, assemble the final Itinerary with:
   - Meal-time-aware ordering (restaurant at lunch/dinner window)
   - Per-segment haversine route calculation for all adjacent pairs
4. Yield ReactEventData events throughout (SSE-compatible).
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

from openai import AsyncOpenAI

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
from agent.tools.route_plan import route_plan
from agent.tools.venue_search import venue_search

# ---------------------------------------------------------------------------
# Meal-time helpers (mirrored from react_loop to avoid circular import)
# ---------------------------------------------------------------------------

_MEAL_WINDOWS = [
    (11 * 60 + 30, 13 * 60 + 30),  # lunch
    (17 * 60 + 30, 20 * 60),        # dinner
]


def _to_min(hhmm: str) -> int:
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m


def _add_minutes(hhmm: str, minutes: int) -> str:
    t = datetime.strptime(hhmm, "%H:%M") + timedelta(minutes=minutes)
    return t.strftime("%H:%M")


def _in_meal_window(minutes: int) -> bool:
    return any(lo <= minutes <= hi for lo, hi in _MEAL_WINDOWS)


def _meal_insert_index(venue_durs: list[int], start_min: int, avg_transit: int = 15) -> int:
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
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    )
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


def _assemble_nodes_from_stops(stops: list[_Stop], start_time: str, window_min: int = 24 * 60) -> list[ItineraryNode]:
    """Build ItineraryNode list, pruning activities to fit within window_min."""
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
        if acts:
            acts[0].duration_min = min(acts[0].duration_min, window_min)
            return _ta_allocate(acts[:1], [], start_time, window_min)
        return []


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_PROFILE_HINT_TEMPLATE = "\n\n## 用户历史偏好（来自个人画像，请优先满足）\n{tags}"

SYSTEM_PROMPT = """你是美团本地生活的行程规划助手。

## 工具调用策略（仅需 1 轮，禁止多轮）
用户消息中已内嵌候选场馆和餐厅列表（含坐标）。你只需在**同一轮**内同时发出：
- check_availability × 3：场馆列表前 2 个 id + 餐厅列表前 1 个 id，time_slot 使用出发时间
- route_plan × 1：场馆[0] → 场馆[1]，坐标直接使用列表中的 lat/lng
所有工具结果返回后，用一句话说明规划完成，不输出其他内容，不再调用任何工具。

## 规划原则
- 餐厅安排在午饭（11:30-13:30）或晚饭（17:30-20:00）时间窗口
- 优先选评分高、与标签匹配的场馆

## 异常处理
- 若工具返回 error 字段，跳过该结果继续规划
"""

# ---------------------------------------------------------------------------
# Tool schema definitions for LLM Function Calling
# ---------------------------------------------------------------------------

_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "venue_search",
            "description": "搜索符合约束条件的活动场馆（景点/乐园/公园等）",
            "parameters": {
                "type": "object",
                "properties": {
                    "per_capita": {"type": "integer", "description": "人均预算（元）"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "偏好标签，如 ['出片', '亲子友好', '室内']",
                    },
                },
                "required": ["per_capita", "tags"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "restaurant_search",
            "description": "搜索符合约束条件的餐厅",
            "parameters": {
                "type": "object",
                "properties": {
                    "per_capita": {"type": "integer", "description": "人均预算（元）"},
                },
                "required": ["per_capita"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": "检查场馆或餐厅在指定时间段的座位/票务可用性",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "string", "description": "场馆或餐厅的唯一ID"},
                    "time_slot": {
                        "type": "string",
                        "description": "时间段，格式 HH:MM，如 '10:00'",
                    },
                },
                "required": ["item_id", "time_slot"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "route_plan",
            "description": "计算两地之间的交通路线（步行/地铁/打车）",
            "parameters": {
                "type": "object",
                "properties": {
                    "from_address": {"type": "string", "description": "出发地地址"},
                    "to_address": {"type": "string", "description": "目的地地址"},
                    "from_lat": {"type": "number", "description": "出发地纬度"},
                    "from_lng": {"type": "number", "description": "出发地经度"},
                    "to_lat": {"type": "number", "description": "目的地纬度"},
                    "to_lng": {"type": "number", "description": "目的地经度"},
                },
                "required": [
                    "from_address", "to_address",
                    "from_lat", "from_lng",
                    "to_lat", "to_lng",
                ],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_user_message_with_data(
    cs: ConstraintSet,
    start_time: str,
    venues: list[VenueResult],
    restaurants: list[RestaurantResult],
) -> str:
    node_count = 3 if cs.hard.total_duration < 6 else 4
    rl = cs.raw_labels

    parts: list[str] = []
    if rl.location:
        parts.append(f"地点：{rl.location}")
    if rl.companion:
        parts.append(f"同行人：{rl.companion}")
    if rl.scene:
        parts.append(f"场景：{rl.scene}")
    if rl.budget:
        parts.append(f"预算：{rl.budget}元/人")
    if cs.soft.tags:
        parts.append(f"偏好：{'、'.join(cs.soft.tags)}")
    context = "，".join(parts) if parts else f"人均 ¥{cs.soft.per_capita}，偏好 {cs.soft.tags}"

    v_slim = [
        {
            "id": v["id"], "name": v["name"], "per_capita": v["per_capita"],
            "lat": v["lat"], "lng": v["lng"], "address": v["address"], "tags": v["tags"],
        }
        for v in venues[:6]
    ]
    r_slim = [
        {
            "id": r["id"], "name": r["name"], "per_capita": r["per_capita"],
            "lat": r["lat"], "lng": r["lng"], "address": r["address"],
        }
        for r in restaurants[:3]
    ]

    return (
        f"出发时间 {start_time}，{context}。行程含 {node_count} 个节点。\n\n"
        f"**候选场馆**（已预取，含坐标）：\n{json.dumps(v_slim, ensure_ascii=False)}\n\n"
        f"**候选餐厅**（已预取，含坐标）：\n{json.dumps(r_slim, ensure_ascii=False)}\n\n"
        f"请在同一轮内同时发出以下 4 个工具调用：\n"
        f"- check_availability：id={v_slim[0]['id'] if v_slim else '?'}, time_slot=\"{start_time}\"\n"
        f"- check_availability：id={v_slim[1]['id'] if len(v_slim) > 1 else (v_slim[0]['id'] if v_slim else '?')}, time_slot=\"{start_time}\"\n"
        f"- check_availability：id={r_slim[0]['id'] if r_slim else '?'}, time_slot=\"{start_time}\"\n"
        f"- route_plan：from={v_slim[0]['address'] if v_slim else '?'}（lat={v_slim[0]['lat'] if v_slim else 0}, lng={v_slim[0]['lng'] if v_slim else 0}）→ to={v_slim[1]['address'] if len(v_slim) > 1 else (r_slim[0]['address'] if r_slim else '?')}（lat={v_slim[1]['lat'] if len(v_slim) > 1 else (r_slim[0]['lat'] if r_slim else 0)}, lng={v_slim[1]['lng'] if len(v_slim) > 1 else (r_slim[0]['lng'] if r_slim else 0)}）\n"
        f"完成后回复一句话说明规划完成。"
    )


async def _dispatch_tool(
    tool_name: str,
    tool_input: dict[str, Any],
    constraint_set: ConstraintSet,
) -> dict[str, Any] | list[dict[str, Any]]:
    if tool_name == "venue_search":
        venue_results = await venue_search(constraint_set)
        return [dict(r) for r in venue_results]
    if tool_name == "restaurant_search":
        rest_results = await restaurant_search(constraint_set)
        return [dict(r) for r in rest_results]
    if tool_name == "check_availability":
        avail_result = await check_availability(
            str(tool_input["item_id"]), str(tool_input["time_slot"])
        )
        return dict(avail_result)
    if tool_name == "route_plan":
        route_result = await route_plan(
            from_lat=float(tool_input["from_lat"]),
            from_lng=float(tool_input["from_lng"]),
            from_address=str(tool_input["from_address"]),
            to_lat=float(tool_input["to_lat"]),
            to_lng=float(tool_input["to_lng"]),
            to_address=str(tool_input["to_address"]),
        )
        return dict(route_result)
    raise ValueError(f"Unknown tool: {tool_name}")


def _assemble_itinerary(
    venues: list[VenueResult],
    restaurants: list[RestaurantResult],
    node_count: int,
    session_id: str,
    start_time: str,
    window_min: int = 24 * 60,
) -> Itinerary:
    """Build a structured Itinerary using meal-time ordering and per-segment routes."""
    stops = _build_ordered_stops(venues, restaurants, node_count, start_time)
    nodes = _assemble_nodes_from_stops(stops, start_time, window_min)

    total_dur = sum(n.duration_min for n in nodes) + sum(
        n.transit_to_next.duration_min for n in nodes if n.transit_to_next
    )
    return Itinerary(
        session_id=session_id,
        nodes=nodes,
        total_duration_min=total_dur,
        total_per_capita=sum(n.per_capita for n in nodes),
    )


# ---------------------------------------------------------------------------
# LLM-based candidate scoring
# ---------------------------------------------------------------------------

_SCORING_RULES = """\
- **儿童友好度**：同行有儿童（年龄0-12岁）时，有"亲子友好""安全设施""儿童乐园"标签的场所 +2~+3；不适合儿童或纯成人场所 -2~-3
- **老人友好度**：同行有老人（60岁以上）时，有"老人友好""无障碍设施"标签加分 +2；需长时间站立/步行/排队的场所 -1~-2
- **预算匹配**：人均价格 ≤ 用户预算 +2；超出10%~30% 轻微扣分 -1；超出30%以上 -2~-3；免费或远低于预算 +1
- **标签偏好**：与用户偏好标签每匹配一个 +1，最多累计 +3
- **噪音偏好**：用户选安静/低噪音场景时，low噪音 +2、high噪音 -2；用户选热闹时反之；medium不扣不加
- **场景契合**：悠闲放松 +2 / 元气打卡 +2 / 文化探索 +2 / 美食之旅 +2 / 特别纪念 +2 / 商务接待 +2
- **同行适配**：一个人独处 +2 / 另一半浪漫 +2 / 闺蜜出片 +2 / 兄弟户外 +2 / 带娃亲子 +2 / 家庭聚会 +2 / 商务接待 +2"""


def _build_scoring_context(cs: ConstraintSet, profile_tags: list[str] | None = None) -> str:
    rl = cs.raw_labels
    parts: list[str] = []
    if rl.companion:
        parts.append(f"同行人：{rl.companion}")
    if rl.location:
        parts.append(f"活动区域：{rl.location}")
    if rl.scene:
        parts.append(f"出行场景：{rl.scene}")
    if rl.budget:
        parts.append(f"人均预算：{rl.budget}元")
    if cs.soft.tags:
        parts.append(f"偏好标签：{'、'.join(cs.soft.tags)}")
    age_min, age_max = cs.hard.age_range
    if age_min <= 12:
        parts.append("行程中有儿童")
    if age_max >= 60:
        parts.append("行程中有老人")
    if profile_tags:
        parts.append(f"用户历史偏好：{'、'.join(profile_tags)}")
    if not parts:
        parts = [
            f"人均预算 ¥{cs.soft.per_capita}",
            f"噪音偏好 {cs.soft.noise_level}",
            f"偏好标签 {cs.soft.tags}",
        ]
    return "；".join(parts)


def _build_scoring_prompt(
    venues: list[Any],
    restaurants: list[Any],
    cs: ConstraintSet,
    profile_tags: list[str] | None = None,
) -> str:
    context = _build_scoring_context(cs, profile_tags)
    v_slim = [
        {"id": v["id"], "name": v["name"], "per_capita": v["per_capita"],
         "tags": v["tags"], "noise_level": v["noise_level"]}
        for v in venues
    ]
    r_slim = [
        {"id": r["id"], "name": r["name"], "per_capita": r["per_capita"],
         "tags": r["tags"], "noise_level": r["noise_level"]}
        for r in restaurants
    ]
    return (
        "你是行程规划助手，请根据用户情况为以下候选项评分（整数0-10）。\n\n"
        f"## 用户情况\n{context}\n\n"
        f"## 评分规则\n{_SCORING_RULES}\n\n"
        f"## 候选场馆\n{json.dumps(v_slim, ensure_ascii=False)}\n\n"
        f"## 候选餐厅\n{json.dumps(r_slim, ensure_ascii=False)}\n\n"
        '严格按以下 JSON 格式返回，不要有其他内容：\n'
        '{"venues": [{"id": "v001", "score": 8}, ...], "restaurants": [{"id": "r001", "score": 7}, ...]}'
    )


async def _llm_score_candidates(
    client: AsyncOpenAI,
    model: str,
    venues: list[Any],
    restaurants: list[Any],
    cs: ConstraintSet,
    profile_tags: list[str] | None = None,
) -> tuple[list[Any], list[Any]]:
    """Re-rank candidates by LLM scores. Falls back to original order on any error."""
    if not venues and not restaurants:
        return venues, restaurants
    prompt = _build_scoring_prompt(venues, restaurants, cs, profile_tags)
    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(                model=model,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            ),
            timeout=5.0,  # tight budget: scoring is best-effort
        )
        raw_text: str = response.choices[0].message.content or ""
        data: dict[str, Any] = json.loads(raw_text)
        venue_scores = {item["id"]: item["score"] for item in data.get("venues", [])}
        rest_scores = {item["id"]: item["score"] for item in data.get("restaurants", [])}
        sorted_venues = sorted(venues, key=lambda v: venue_scores.get(v["id"], 0), reverse=True)
        sorted_rests = sorted(restaurants, key=lambda r: rest_scores.get(r["id"], 0), reverse=True)
        return sorted_venues, sorted_rests
    except Exception:
        return venues, restaurants


# ---------------------------------------------------------------------------
# Streaming Function-Calling helper
# ---------------------------------------------------------------------------


async def _stream_fc_round(
    client: AsyncOpenAI,
    model: str,
    messages: list[dict[str, Any]],
    connect_timeout: float = 10.0,
    idle_timeout: float = 4.0,
) -> tuple[list[dict[str, Any]], str | None]:
    """Stream one FC round with two-stage timeout.

    connect_timeout: seconds to receive the stream object (TCP + DashScope queue).
    idle_timeout: max seconds between consecutive SSE chunks; catches stalled streams.
    Together they bound wall-clock time to connect_timeout + N_chunks*idle_timeout,
    in practice ~12-14 s per round for DashScope function-calling responses.
    Raises TimeoutError on either stage.
    """
    acc: dict[int, dict[str, Any]] = {}
    finish: list[str | None] = [None]

    stream = await asyncio.wait_for(
        client.chat.completions.create(  # type: ignore[call-overload]
            model=model,
            max_tokens=512,
            tools=_TOOL_SCHEMAS,
            tool_choice="auto",
            messages=messages,
            stream=True,
        ),
        timeout=connect_timeout,
    )

    it = stream.__aiter__()
    while True:
        try:
            chunk = await asyncio.wait_for(it.__anext__(), timeout=idle_timeout)
        except StopAsyncIteration:
            break
        if not chunk.choices:
            continue
        ch = chunk.choices[0]
        if ch.delta.tool_calls:
            for tc_delta in ch.delta.tool_calls:
                idx = tc_delta.index
                if idx not in acc:
                    acc[idx] = {"id": "", "name": "", "arguments": ""}
                if tc_delta.id:
                    acc[idx]["id"] = tc_delta.id
                if tc_delta.function:
                    if tc_delta.function.name:
                        acc[idx]["name"] += tc_delta.function.name
                    if tc_delta.function.arguments:
                        acc[idx]["arguments"] += tc_delta.function.arguments
        if ch.finish_reason:
            finish[0] = ch.finish_reason

    return [acc[i] for i in sorted(acc)], finish[0]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def run(
    constraint_set: ConstraintSet,
    session_id: str,
    start_time: str = "10:00",
    profile_tags: list[str] | None = None,
) -> AsyncIterator[ReactEventData]:
    """Return an async generator of SSE-compatible ReactEventData events.

    Stage 1 — pre-fetch: venue_search + restaurant_search called directly in Python
    (mock tools, ~0.1 s), eliminating one full LLM FC round.
    Stage 2 — parallel: LLM FC (avail + route, 1 round) runs concurrently with
    LLM scoring, so the slower of the two (~12-14 s FC) hides scoring (~5 s).
    Total wall-clock budget: 0.1 s pre-fetch + ~14 s parallel stage ≈ ≤15 s typical.
    """

    async def _impl() -> AsyncIterator[ReactEventData]:
        api_key = os.getenv("LLM_API_KEY", "")
        base_url = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        model = os.getenv("LLM_MODEL", "qwen-plus")

        yield ReactEventData(
            type="thought",
            content=(
                f"[LLM规划模式] 预算 ¥{constraint_set.soft.per_capita}/人，"
                f"时长 {constraint_set.hard.total_duration}h，"
                f"偏好 {constraint_set.soft.tags}。预取候选数据…"
            ),
        )

        # ── Stage 1: pre-fetch search directly (fast mock, ~0.1 s) ──────────
        yield ReactEventData(type="action", tool="venue_search",
                             params={"per_capita": constraint_set.soft.per_capita,
                                     "tags": constraint_set.soft.tags})
        yield ReactEventData(type="action", tool="restaurant_search",
                             params={"per_capita": constraint_set.soft.per_capita})
        try:
            raw_venues, raw_restaurants = await asyncio.gather(
                venue_search(constraint_set),
                restaurant_search(constraint_set),
            )
        except ToolFaultError as exc:
            yield ReactEventData(type="error", error=str(exc), content="搜索故障，重试")
            try:
                raw_venues = list(await venue_search(constraint_set))
            except (ToolFaultError, Exception) as retry_exc:
                yield ReactEventData(type="error", error=str(retry_exc), content="场地搜索重试失败")
                raw_venues = []
            try:
                raw_restaurants = list(await restaurant_search(constraint_set))
            except (ToolFaultError, Exception) as retry_exc:
                yield ReactEventData(type="error", error=str(retry_exc), content="餐厅搜索重试失败")
                raw_restaurants = []

        collected_venues: list[VenueResult] = list(raw_venues)
        collected_restaurants: list[RestaurantResult] = list(raw_restaurants)
        yield ReactEventData(type="observation", tool="venue_search",
                             result={"count": len(collected_venues),
                                     "top": collected_venues[0]["name"] if collected_venues else "-"})
        yield ReactEventData(type="observation", tool="restaurant_search",
                             result={"count": len(collected_restaurants),
                                     "top": collected_restaurants[0]["name"] if collected_restaurants else "-"})

        # ── Stage 2: LLM FC (avail+route, 1 round) ∥ LLM scoring ───────────
        yield ReactEventData(
            type="thought",
            content="并行执行：LLM 智能评分 ∥ 可用性+路线检查（单轮 FC）",
        )

        client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=30.0)

        score_task: asyncio.Task[
            tuple[list[VenueResult], list[RestaurantResult]]
        ] = asyncio.create_task(
            _llm_score_candidates(
                client, model, collected_venues, collected_restaurants,
                constraint_set, profile_tags,
            )
        )

        system_content = SYSTEM_PROMPT
        if profile_tags:
            system_content += _PROFILE_HINT_TEMPLATE.format(
                tags="、".join(profile_tags)
            )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": _build_user_message_with_data(
                constraint_set, start_time, collected_venues, collected_restaurants,
            )},
        ]

        for _ in range(1):  # single FC round: avail + route only
            try:
                tool_calls, _finish = await _stream_fc_round(client, model, messages)
            except TimeoutError:
                yield ReactEventData(
                    type="error",
                    error="LLM 响应超时",
                    content="DashScope 超时（连接>10s 或 chunk 间隔>4s），切换确定性规划",
                )
                break
            except Exception as exc:
                yield ReactEventData(
                    type="error",
                    error=str(exc),
                    content=f"LLM 调用失败：{exc}，切换确定性规划",
                )
                break

            if not tool_calls:
                break

            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]},
                    }
                    for tc in tool_calls
                ],
            })

            for tc in tool_calls:
                tc_name = tc["name"]
                tc_input: dict[str, Any] = json.loads(tc["arguments"])
                yield ReactEventData(type="action", tool=tc_name, params=tc_input)
                try:
                    result: Any = await _dispatch_tool(tc_name, tc_input, constraint_set)
                    obs: dict[str, Any] = (
                        {"count": len(result), "top": result[0]["name"] if result else "-"}
                        if isinstance(result, list)
                        else dict(result)
                    )
                    yield ReactEventData(type="observation", tool=tc_name, result=obs)
                except (ToolFaultError, Exception) as exc:
                    result = {"error": str(exc)}
                    yield ReactEventData(
                        type="error", tool=tc_name, error=str(exc),
                        content=f"工具异常: {exc}，继续规划",
                    )
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result, ensure_ascii=False),
                })

        # Await scoring (likely already done while FC was running)
        try:
            collected_venues, collected_restaurants = await score_task
        except Exception as score_exc:
            yield ReactEventData(type="error", error=str(score_exc), content="评分失败，保留原始顺序")

        node_count = 3 if constraint_set.hard.total_duration < 6.0 else 4
        window_min = int(constraint_set.hard.total_duration * 60)
        itinerary = _assemble_itinerary(
            collected_venues,
            collected_restaurants,
            node_count,
            session_id,
            start_time,
            window_min,
        )

        yield ReactEventData(
            type="done",
            content=(
                f"[LLM] 规划完成：{len(itinerary.nodes)} 节点，"
                f"人均 ¥{itinerary.total_per_capita}"
            ),
            itinerary=json.loads(itinerary.model_dump_json()),
        )

    return _impl()
