"""Tool: generate social share copy adapted to audience relationship type.

Audience styles:
  family      — warm, practical, kid/elder-friendly highlights
  girlfriends — playful, photo-spot emphasis, vibe-first
  bros        — terse, budget/food/fun focus
"""

from __future__ import annotations

import asyncio

from agent.schemas import (
    Itinerary,
    ItineraryNode,
    ShareTextRequest,
    ShareTextResponse,
)

_TITLES: dict[str, str] = {
    "family":      "家人相聚 · 今日行程",
    "girlfriends": "姐妹出游 · 种草清单",
    "bros":        "兄弟出行 · 今日战报",
}

_OPENINGS: dict[str, str] = {
    "family":      "今天和家人来了一场说走就走的踏青，每一站都安排得明明白白！",
    "girlfriends": "姐妹们！今天的行程简直绝了，每一站都超出预期，强烈种草！",
    "bros":        "今天和兄弟们出动，行程已给你们安排好，直接抄作业！",
}

_NODE_LABELS: dict[str, dict[str, str]] = {
    "family": {
        "venue":      "老人小孩都能玩，全家都开心",
        "restaurant": "家庭聚餐首选，口味全家都爱",
    },
    "girlfriends": {
        "venue":      "超级出片的地方，妆容准备好再去！",
        "restaurant": "颜值和口味双在线，姐妹必去",
    },
    "bros": {
        "venue":      "爽！直接去",
        "restaurant": "吃饱了才有力气继续浪",
    },
}

_CLOSINGS: dict[str, str] = {
    "family":      "今天出行顺顺利利，大家都玩得很开心。这样的时光，值得珍藏。",
    "girlfriends": "下次还要一起出来！今天满分，姐妹们冲就完了！",
    "bros":        "完美收官。下次继续，谁报名谁是好兄弟！",
}

_HASHTAGS: dict[str, list[str]] = {
    "family":      ["#亲子出行", "#家庭日", "#北京遛娃", "#周末好去处"],
    "girlfriends": ["#姐妹出游", "#打卡北京", "#出片必去", "#闺蜜游"],
    "bros":        ["#兄弟出行", "#北京吃喝玩乐", "#穷游攻略", "#这波稳了"],
}


def _node_summary(node: ItineraryNode, audience: str) -> str:
    label = _NODE_LABELS[audience].get(node.node_type, "值得去")
    time_range = f"【{node.start_time}-{node.end_time}】"
    cost = f"（人均约 {node.per_capita} 元）"
    return f"{time_range}{node.name} — {label}{cost}"


def _card_line(node: ItineraryNode) -> str:
    return f"{node.start_time} {node.name} ({node.node_type})"


def _build_body(itinerary: Itinerary, audience: str) -> str:
    opening = _OPENINGS[audience]
    node_texts = "\n".join(
        _node_summary(n, audience) for n in itinerary.nodes
    )
    total_per_capita = itinerary.total_per_capita
    duration_h = round(itinerary.total_duration_min / 60, 1)
    stats = f"全程约 {duration_h} 小时，人均消费约 {total_per_capita} 元。"
    closing = _CLOSINGS[audience]
    return f"{opening}\n\n{node_texts}\n\n{stats}{closing}"


async def generate_share_text(request: ShareTextRequest) -> ShareTextResponse:
    """Return audience-adapted social share copy for a confirmed itinerary."""
    await asyncio.sleep(0)
    audience = request.audience
    itinerary = request.itinerary
    return ShareTextResponse(
        session_id=itinerary.session_id,
        audience=audience,
        title=_TITLES[audience],
        body=_build_body(itinerary, audience),
        hashtags=_HASHTAGS[audience],
        card_lines=[_card_line(n) for n in itinerary.nodes],
    )
