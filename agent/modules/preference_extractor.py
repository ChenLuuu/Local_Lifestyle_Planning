"""LLM-powered preference extractor: free text → structured preference tags.

Flow:
1. Try LLM (DashScope qwen-plus) with a tight JSON extraction prompt.
2. On any failure (timeout / API key missing / parse error), fall back to
   deterministic keyword matching so the feature always works.

Output: list[str] of preference tags and a human-readable summary.
"""

from __future__ import annotations

import asyncio
import json
import os
import re

# keyword → tags mapping for deterministic fallback
_KEYWORD_TAGS: list[tuple[str, list[str]]] = [
    ("停车", ["有车", "停车方便"]),
    ("开车", ["有车", "驾车出行"]),
    ("有车", ["有车", "停车方便"]),
    ("驾车", ["有车", "驾车出行"]),
    ("不辣", ["不辣"]),
    ("忌辣", ["不辣", "忌辣"]),
    ("不吃辣", ["不辣"]),
    ("宠物", ["宠物友好"]),
    ("带狗", ["宠物友好"]),
    ("带猫", ["宠物友好"]),
    ("老人", ["老人友好", "无障碍"]),
    ("老年", ["老人友好", "无障碍"]),
    ("爸妈", ["老人友好", "家庭"]),
    ("父母", ["老人友好", "家庭"]),
    ("学生", ["学生", "平价"]),
    ("穷", ["平价"]),
    ("省钱", ["平价"]),
    ("儿童", ["亲子友好", "儿童设施"]),
    ("小孩", ["亲子友好", "儿童设施"]),
    ("宝宝", ["亲子友好", "儿童设施"]),
    ("轮椅", ["无障碍", "无障碍设施"]),
    ("素食", ["素食", "健康餐"]),
    ("清真", ["清真"]),
    ("安静", ["安静", "低噪音"]),
    ("不想走路", ["轻松", "少步行"]),
    ("懒", ["轻松", "少步行"]),
    ("出片", ["出片", "网红"]),
    ("拍照", ["出片"]),
    ("女友", ["约会", "浪漫"]),
    ("另一半", ["约会", "浪漫"]),
    ("纪念", ["仪式感", "浪漫"]),
    ("生日", ["仪式感", "生日庆典"]),
]

_EXTRACTION_PROMPT = """\
你是用户偏好提取助手。从用户的自由文本需求中，提取结构化的偏好标签。

## 用户需求
{text}

## 任务
将上述需求提炼为简短的偏好标签（中文，每个标签2-6个字）和一句简洁的偏好摘要。

## 输出格式（严格JSON，不要其他内容）
{{"tags": ["有车", "停车方便", "不辣"], "summary": "您有车，偏好停车方便，且不吃辣"}}

如果没有可提取的偏好，返回：{{"tags": [], "summary": ""}}"""


def _keyword_extract(text: str) -> list[str]:
    tags: set[str] = set()
    for keyword, tag_list in _KEYWORD_TAGS:
        if keyword in text:
            tags.update(tag_list)
    return sorted(tags)


async def extract_preferences(free_text: str) -> tuple[list[str], str]:
    """Return (tags, summary) from free_text.

    Tries LLM first; falls back to keyword matching on any error.
    """
    if not free_text.strip():
        return [], ""

    api_key = os.getenv("LLM_API_KEY", "")
    if api_key:
        try:
            tags, summary = await _llm_extract(free_text, api_key)
            if tags:
                return tags, summary
        except Exception:  # noqa: S110
            pass  # fall through to keyword fallback

    # Deterministic fallback
    tags = _keyword_extract(free_text)
    summary = ("已记录：" + "、".join(tags)) if tags else ""
    return tags, summary


async def _llm_extract(free_text: str, api_key: str) -> tuple[list[str], str]:
    from openai import AsyncOpenAI

    base_url = os.getenv(
        "LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    model = os.getenv("LLM_MODEL", "qwen-plus")
    client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=8.0)

    response = await asyncio.wait_for(
        client.chat.completions.create(
            model=model,
            max_tokens=256,
            messages=[
                {
                    "role": "user",
                    "content": _EXTRACTION_PROMPT.format(text=free_text),
                }
            ],
        ),
        timeout=7.0,
    )
    raw = (response.choices[0].message.content or "").strip()
    # Strip markdown fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    data: dict[str, object] = json.loads(raw)
    raw_tags = data.get("tags", [])
    tags = [str(t) for t in (raw_tags if isinstance(raw_tags, list) else [])]
    summary = str(data.get("summary", ""))
    return tags, summary
