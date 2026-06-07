"""Constraint parser: translates collection-step answers into partial ConstraintSet."""

import re

from agent.schemas import (
    CollectAllRequest,
    ConstraintSet,
    HardConstraints,
    RawLabels,
    SoftPreferences,
    TagsRequest,
    TagsResponse,
)

_COMPANION_TAGS: dict[str, list[str]] = {
    "一个人": ["独处充电", "咖啡馆", "美术馆", "书店", "不想说话", "安静环境"],
    "另一半": ["氛围感", "仪式感", "浪漫约会", "打卡拍照", "私密空间", "精致体验"],
    "闺蜜": ["出片", "美食", "艺术", "美甲", "购物", "不想走路", "室内"],
    "兄弟": ["户外", "运动", "喝酒撸串", "不走寻常路", "高性价比", "男生聚集地"],
    "带娃": ["亲子友好", "安全设施", "儿童乐园", "教育意义", "有儿童餐", "不费脑"],
    "家庭聚会": ["停车方便", "包厢", "老人友好", "儿童友好", "本地特色", "够排场"],
    "商务接待": ["高端大气", "有面子", "私密包间", "商务氛围", "交通便利", "代客泊车"],
}

_SCENE_TAGS: dict[str, list[str]] = {
    "悠闲放松": ["慢节奏", "不赶时间", "舒适座位"],
    "元气打卡": ["网红地标", "光线好", "出片角度"],
    "文化探索": ["涨知识", "历史感", "小众冷门"],
    "美食之旅": ["必吃清单", "排队也值", "地道口味"],
    "特别纪念": ["仪式感", "纪念拍照", "专属定制"],
    "商务接待": ["专业服务", "稳定可靠", "有格调"],
}


def get_suggested_tags(request: TagsRequest) -> TagsResponse:
    """Return word-cloud tag suggestions based on companion type and scene."""
    companion_tags: list[str] = _COMPANION_TAGS.get(request.companion, [])
    scene_tags: list[str] = _SCENE_TAGS.get(request.scene, [])
    merged = list(dict.fromkeys(companion_tags + scene_tags))
    return TagsResponse(tags=merged)


# ── F02: ConstraintSet parsing ────────────────────────────────────────────────

_LOCATION_DISTANCE: dict[str, float] = {
    "市中心": 10.0,
    "我家附近": 5.0,
    "目的地周边": 3.0,
    "随便": 20.0,
}

_COMPANION_AGE_RANGE: dict[str, tuple[int, int]] = {
    "带娃": (0, 12),
    "家庭聚会": (0, 80),
    "商务接待": (25, 65),
    "一个人": (18, 40),
    "另一半": (18, 40),
    "闺蜜": (18, 40),
    "兄弟": (18, 40),
}

_COMPANION_NOISE: dict[str, str] = {
    "一个人": "low",
    "商务接待": "low",
    "兄弟": "high",
    "家庭聚会": "high",
}

_BUDGET_PER_CAPITA: dict[str, int] = {
    "人均<50": 50,
    "50-100": 75,
    "100-200": 150,
    "200-500": 350,
    "500+": 600,
}

# Maps substrings in step3 text to extra tags
_TEXT_TAG_MAP: dict[str, str] = {
    "宠物友好": "宠物友好",
    "宠物": "宠物友好",
    "不吃辣": "不辣",
    "学生": "高性价比",
    "薅羊毛": "高性价比",
    "无障碍": "无障碍设施",
    "轮椅": "无障碍设施",
    "老人": "老人友好",
    "儿童": "儿童友好",
}

_DURATION_RE = re.compile(r"(\d+(?:\.\d+)?)\s*小时")
_HALF_DAY_RE = re.compile(r"半天")
_FULL_DAY_RE = re.compile(r"全天|一天")

_DURATION_CHOICES: dict[str, float] = {
    "2小时": 2.0,
    "半天（4小时）": 4.0,
    "大半天（6小时）": 6.0,
    "全天（8小时）": 8.0,
}

_START_TIME_MAP: dict[str, str] = {
    "上午 10:00": "10:00",
    "上午 11:00": "11:00",
    "下午 14:00": "14:00",
    "傍晚 17:00": "17:00",
}


def _parse_duration(text: str) -> float | None:
    """Extract duration in hours from free text, or return None."""
    if _FULL_DAY_RE.search(text):
        return 8.0
    if _HALF_DAY_RE.search(text):
        return 4.0
    m = _DURATION_RE.search(text)
    if m:
        return float(m.group(1))
    return None


def _parse_noise_level(text: str, companion: str) -> str:
    """Derive noise level: step3 text overrides companion default."""
    if "安静" in text:
        return "low"
    if "热闹" in text:
        return "high"
    return _COMPANION_NOISE.get(companion, "medium")


def _parse_extra_tags(text: str) -> list[str]:
    """Extract extra tags from step3 free text (order-preserving, deduplicated)."""
    seen: set[str] = set()
    result: list[str] = []
    for keyword, tag in _TEXT_TAG_MAP.items():
        if keyword in text and tag not in seen:
            seen.add(tag)
            result.append(tag)
    return result


def parse_constraint_set(request: CollectAllRequest) -> ConstraintSet:
    """Build a complete ConstraintSet from all three collection steps."""
    s1 = request.step1
    s2 = request.step2
    text = request.step3.special_requirements

    max_distance_km = _LOCATION_DISTANCE.get(s1.location, 10.0)
    age_range = _COMPANION_AGE_RANGE.get(s1.companion, (18, 60))
    total_duration = _DURATION_CHOICES.get(s1.duration) or _parse_duration(text) or 4.0

    noise_level = _parse_noise_level(text, s1.companion)
    per_capita = _BUDGET_PER_CAPITA.get(s1.budget, 150)

    extra_tags = _parse_extra_tags(text)
    tags = list(dict.fromkeys(s2.tags + extra_tags))

    return ConstraintSet(
        hard=HardConstraints(
            max_distance_km=max_distance_km,
            age_range=age_range,
            total_duration=total_duration,
        ),
        soft=SoftPreferences(
            noise_level=noise_level,
            per_capita=per_capita,
            tags=tags,
        ),
        raw_labels=RawLabels(
            location=s1.location,
            companion=s1.companion,
            budget=s1.budget,
            scene=s1.scene,
            duration_text=text,
            start_time=_START_TIME_MAP.get(s1.start_time, ""),
        ),
    )
