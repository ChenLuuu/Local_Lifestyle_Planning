"""Signal extractor: 4 user feedback signal types → profile update.

Signal types:
  EXPLICIT_MODIFY   – user swapped a node (strongest signal of preference change)
  DEEP_INQUIRY      – user requested more candidates (curious / unsatisfied)
  IMPLICIT_APPROVE  – user accepted a node without modification (weak positive)
  NEGATIVE_FEEDBACK – user rejected a node or all candidates

Event schema accepted by extract_signals():
  {
    "event_type": "node_swap" | "candidate_request" | "node_accept" | "node_reject_all",
    "scene":      "亲子" | "商务" | "聚会" | str  (default "通用"),
    "old_node":   {name, tags, ...}  # for node_swap
    "new_node":   {name, tags, ...}  # for node_swap / node_accept
    "node":       {name, tags, ...}  # for node_accept
    "tags":       list[str]          # explicit preference tags (optional fallback)
  }
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class SignalType(StrEnum):
    EXPLICIT_MODIFY = "explicit_modify"
    DEEP_INQUIRY = "deep_inquiry"
    IMPLICIT_APPROVE = "implicit_approve"
    NEGATIVE_FEEDBACK = "negative_feedback"


@dataclass
class Signal:
    signal_type: SignalType
    tag: str
    value: str    # concrete value that triggered the signal (e.g. node name)
    scene: str    # scene label for isolation
    strength: float  # 0.0–1.0; scales the confidence delta applied to FamilyProfile


def _tags_from_node(node: dict[str, Any]) -> list[str]:
    raw = node.get("tags", [])
    return list(raw) if isinstance(raw, list) else []


def extract_signals(event: dict[str, Any]) -> list[Signal]:
    """Extract feedback signals from a single user interaction event."""
    event_type: str = str(event.get("event_type", ""))
    scene: str = str(event.get("scene", "通用"))
    explicit_tags: list[str] = list(event.get("tags", []))

    signals: list[Signal] = []

    if event_type == "node_swap":
        old_node: dict[str, Any] = dict(event.get("old_node") or {})
        new_node: dict[str, Any] = dict(event.get("new_node") or {})
        old_tags = _tags_from_node(old_node)
        new_tags = _tags_from_node(new_node)

        for tag in old_tags:
            signals.append(
                Signal(
                    signal_type=SignalType.NEGATIVE_FEEDBACK,
                    tag=tag,
                    value=str(old_node.get("name", "")),
                    scene=scene,
                    strength=0.6,
                )
            )
        for tag in new_tags:
            signals.append(
                Signal(
                    signal_type=SignalType.EXPLICIT_MODIFY,
                    tag=tag,
                    value=str(new_node.get("name", "")),
                    scene=scene,
                    strength=0.8,
                )
            )

    elif event_type == "candidate_request":
        tags = explicit_tags or ["探索"]
        for tag in tags:
            signals.append(
                Signal(
                    signal_type=SignalType.DEEP_INQUIRY,
                    tag=tag,
                    value="requested_more",
                    scene=scene,
                    strength=0.5 if explicit_tags else 0.3,
                )
            )

    elif event_type == "node_accept":
        node: dict[str, Any] = dict(event.get("node") or {})
        accept_tags = _tags_from_node(node) or explicit_tags
        for tag in accept_tags:
            signals.append(
                Signal(
                    signal_type=SignalType.IMPLICIT_APPROVE,
                    tag=tag,
                    value=str(node.get("name", "")),
                    scene=scene,
                    strength=0.4,
                )
            )

    elif event_type == "node_reject_all":
        for tag in explicit_tags:
            signals.append(
                Signal(
                    signal_type=SignalType.NEGATIVE_FEEDBACK,
                    tag=tag,
                    value="rejected_all",
                    scene=scene,
                    strength=0.7,
                )
            )

    return signals
