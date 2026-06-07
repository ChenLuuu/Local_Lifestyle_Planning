"""Family profile: per-scene preference memory with Bayesian confidence update.

Rules:
- Scene labels are isolation namespaces: 亲子 / 商务 / 聚会 signals never bleed across.
- Initial confidence for a brand-new preference entry = INITIAL_CONFIDENCE (0.5).
- Positive signals (EXPLICIT_MODIFY, IMPLICIT_APPROVE) raise confidence linearly.
- Negative signals (NEGATIVE_FEEDBACK, DEEP_INQUIRY) lower confidence.
- Confidence is clamped to [0.0, 1.0].
- Entries crossing PROMOTE_THRESHOLD (0.8) emit a "promoted" learning log entry,
  signaling that this preference should be treated as a soft→hard constraint next time.

Public API:
  FamilyProfile.apply_signal(signal)  → LearningLogEntry
  FamilyProfile.apply_signals(list)   → list[LearningLogEntry]
  FamilyProfile.high_confidence_tags(scene) → list[str]
  FamilyProfile.to_constraint_boost(scene)  → {"boost_tags": [...]}
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent.modules.signal_extractor import Signal, SignalType

INITIAL_CONFIDENCE: float = 0.5
PROMOTE_THRESHOLD: float = 0.8
POSITIVE_DELTA: float = 0.1   # per-unit multiplier for positive signals
NEGATIVE_DELTA: float = 0.15  # per-unit multiplier for negative signals

_POSITIVE = {SignalType.EXPLICIT_MODIFY, SignalType.IMPLICIT_APPROVE}


@dataclass
class PreferenceEntry:
    tag: str
    scene: str
    confidence: float = INITIAL_CONFIDENCE
    hit_count: int = 0          # incremented on every positive signal
    last_value: str = ""        # last concrete value that triggered this entry


@dataclass
class LearningLogEntry:
    scene: str
    tag: str
    value: str
    confidence_before: float
    confidence_after: float
    promoted: bool   # True when confidence crosses PROMOTE_THRESHOLD for first time
    message: str     # human-readable explanation shown to the user


@dataclass
class FamilyProfile:
    """Per-user preference memory, isolated by scene label."""

    user_id: str
    # scene_prefs["亲子"]["轻食"] = PreferenceEntry(...)
    scene_prefs: dict[str, dict[str, PreferenceEntry]] = field(default_factory=dict)

    # ── internal helpers ──────────────────────────────────────────────────────

    def _get_or_create(self, scene: str, tag: str) -> PreferenceEntry:
        self.scene_prefs.setdefault(scene, {})
        if tag not in self.scene_prefs[scene]:
            self.scene_prefs[scene][tag] = PreferenceEntry(tag=tag, scene=scene)
        return self.scene_prefs[scene][tag]

    # ── public API ────────────────────────────────────────────────────────────

    def apply_signal(self, signal: Signal) -> LearningLogEntry:
        """Apply one signal and return a single learning log entry."""
        entry = self._get_or_create(signal.scene, signal.tag)
        before = entry.confidence

        if signal.signal_type in _POSITIVE:
            delta = POSITIVE_DELTA * signal.strength
            entry.confidence = min(1.0, entry.confidence + delta)
            entry.hit_count += 1
        else:
            delta = NEGATIVE_DELTA * signal.strength
            entry.confidence = max(0.0, entry.confidence - delta)

        entry.last_value = signal.value

        promoted = before < PROMOTE_THRESHOLD and entry.confidence >= PROMOTE_THRESHOLD

        if promoted:
            msg = (
                f"结合您上次喜欢「{signal.tag}」，"
                f"本次为您首推相关选项（置信度 {entry.confidence:.0%}）"
            )
        elif signal.signal_type in _POSITIVE:
            msg = (
                f"已记录您在「{signal.scene}」场景偏好「{signal.tag}」"
                f"（置信度 {entry.confidence:.0%}）"
            )
        else:
            msg = (
                f"已记录您在「{signal.scene}」场景不偏好「{signal.tag}」"
                f"（置信度 {entry.confidence:.0%}）"
            )

        return LearningLogEntry(
            scene=signal.scene,
            tag=signal.tag,
            value=signal.value,
            confidence_before=round(before, 10),
            confidence_after=round(entry.confidence, 10),
            promoted=promoted,
            message=msg,
        )

    def apply_signals(self, signals: list[Signal]) -> list[LearningLogEntry]:
        """Apply a batch of signals in order and return all log entries."""
        return [self.apply_signal(s) for s in signals]

    def high_confidence_tags(self, scene: str) -> list[str]:
        """Return tags whose confidence >= PROMOTE_THRESHOLD for the given scene."""
        prefs = self.scene_prefs.get(scene, {})
        return sorted(
            tag for tag, e in prefs.items() if e.confidence >= PROMOTE_THRESHOLD
        )

    def to_constraint_boost(self, scene: str) -> dict[str, list[str]]:
        """Produce a constraint-boost hint dict for the planner.

        Returns {"boost_tags": [...]} when there are high-confidence tags,
        or {} when there are none (planner can merge safely with setdefault).
        """
        tags = self.high_confidence_tags(scene)
        if not tags:
            return {}
        return {"boost_tags": tags}
