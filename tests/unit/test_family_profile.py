"""Unit tests for F09: family_profile — Bayesian confidence + scene isolation.

Verification command: pytest tests/unit/test_family_profile.py -v
"""

from __future__ import annotations

import pytest

from agent.modules.family_profile import (
    INITIAL_CONFIDENCE,
    NEGATIVE_DELTA,
    POSITIVE_DELTA,
    PROMOTE_THRESHOLD,
    FamilyProfile,
    LearningLogEntry,
    PreferenceEntry,
)
from agent.modules.signal_extractor import Signal, SignalType


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def profile() -> FamilyProfile:
    return FamilyProfile(user_id="u001")


def _pos(tag: str, scene: str = "亲子", strength: float = 1.0) -> Signal:
    return Signal(
        signal_type=SignalType.EXPLICIT_MODIFY,
        tag=tag,
        value="test_value",
        scene=scene,
        strength=strength,
    )


def _implicit(tag: str, scene: str = "亲子", strength: float = 1.0) -> Signal:
    return Signal(
        signal_type=SignalType.IMPLICIT_APPROVE,
        tag=tag,
        value="test_value",
        scene=scene,
        strength=strength,
    )


def _neg(tag: str, scene: str = "亲子", strength: float = 1.0) -> Signal:
    return Signal(
        signal_type=SignalType.NEGATIVE_FEEDBACK,
        tag=tag,
        value="test_value",
        scene=scene,
        strength=strength,
    )


# ── initial state ─────────────────────────────────────────────────────────────


class TestInitialState:
    def test_new_profile_has_empty_scene_prefs(self, profile):
        assert profile.scene_prefs == {}

    def test_first_signal_creates_entry_at_initial_confidence(self, profile):
        profile.apply_signal(_pos("安静"))
        entry = profile.scene_prefs["亲子"]["安静"]
        # confidence should be > INITIAL (positive delta applied)
        assert entry.confidence > INITIAL_CONFIDENCE

    def test_first_signal_starts_from_05(self, profile):
        profile.apply_signal(_pos("轻食", strength=0.8))
        entry = profile.scene_prefs["亲子"]["轻食"]
        expected = min(1.0, INITIAL_CONFIDENCE + POSITIVE_DELTA * 0.8)
        assert entry.confidence == pytest.approx(expected)

    def test_preference_entry_fields(self, profile):
        profile.apply_signal(_pos("美食"))
        entry = profile.scene_prefs["亲子"]["美食"]
        assert isinstance(entry, PreferenceEntry)
        assert entry.tag == "美食"
        assert entry.scene == "亲子"


# ── positive signal confidence increase ──────────────────────────────────────


class TestPositiveSignals:
    def test_explicit_modify_raises_confidence(self, profile):
        before = INITIAL_CONFIDENCE
        log = profile.apply_signal(_pos("户外", strength=1.0))
        assert log.confidence_after > before

    def test_implicit_approve_raises_confidence(self, profile):
        log = profile.apply_signal(_implicit("安静", strength=1.0))
        assert log.confidence_after > INITIAL_CONFIDENCE

    def test_consecutive_positives_keep_increasing(self, profile):
        confs = []
        for _ in range(5):
            log = profile.apply_signal(_pos("户外", strength=1.0))
            confs.append(log.confidence_after)
        assert confs == sorted(confs)

    def test_confidence_capped_at_1(self, profile):
        for _ in range(100):
            profile.apply_signal(_pos("安静", strength=1.0))
        entry = profile.scene_prefs["亲子"]["安静"]
        assert entry.confidence <= 1.0

    def test_hit_count_increments_on_positive(self, profile):
        profile.apply_signal(_pos("安静"))
        profile.apply_signal(_pos("安静"))
        entry = profile.scene_prefs["亲子"]["安静"]
        assert entry.hit_count == 2

    def test_hit_count_not_incremented_on_negative(self, profile):
        profile.apply_signal(_pos("安静"))
        profile.apply_signal(_neg("安静"))
        entry = profile.scene_prefs["亲子"]["安静"]
        assert entry.hit_count == 1

    def test_partial_strength_smaller_delta(self, profile):
        log_half = profile.apply_signal(_pos("tag_a", strength=0.5))
        profile2 = FamilyProfile(user_id="u002")
        log_full = profile2.apply_signal(_pos("tag_a", strength=1.0))
        assert log_full.confidence_after > log_half.confidence_after


# ── negative signal confidence decrease ──────────────────────────────────────


class TestNegativeSignals:
    def test_negative_lowers_confidence(self, profile):
        log = profile.apply_signal(_neg("嘈杂", strength=1.0))
        assert log.confidence_after < INITIAL_CONFIDENCE

    def test_confidence_floored_at_zero(self, profile):
        for _ in range(100):
            profile.apply_signal(_neg("嘈杂", strength=1.0))
        entry = profile.scene_prefs["亲子"]["嘈杂"]
        assert entry.confidence >= 0.0

    def test_negative_delta_larger_than_positive_delta(self):
        assert NEGATIVE_DELTA > POSITIVE_DELTA


# ── scene isolation ───────────────────────────────────────────────────────────


class TestSceneIsolation:
    def test_signals_in_different_scenes_do_not_bleed(self, profile):
        profile.apply_signal(_pos("轻食", scene="亲子"))
        profile.apply_signal(_neg("轻食", scene="商务"))
        # 亲子 entry should be higher than 商务 entry
        child_conf = profile.scene_prefs["亲子"]["轻食"].confidence
        biz_conf = profile.scene_prefs["商务"]["轻食"].confidence
        assert child_conf > biz_conf

    def test_scenes_are_separate_namespaces(self, profile):
        profile.apply_signal(_pos("美食", scene="亲子"))
        # 商务 namespace should not have this tag at all
        assert "美食" not in profile.scene_prefs.get("商务", {})

    def test_three_scenes_independent(self, profile):
        for scene in ["亲子", "商务", "聚会"]:
            profile.apply_signal(_pos("安静", scene=scene, strength=0.5))
        # each scene has its own entry with independent confidence
        entries = [
            profile.scene_prefs[scene]["安静"] for scene in ["亲子", "商务", "聚会"]
        ]
        confidences = [e.confidence for e in entries]
        assert all(c == pytest.approx(confidences[0]) for c in confidences)
        # but they ARE separate objects
        assert entries[0] is not entries[1]


# ── promotion to hard constraint ─────────────────────────────────────────────


class TestPromotion:
    def test_high_confidence_tags_returns_promoted_tags(self, profile):
        # push confidence above threshold with many signals
        for _ in range(10):
            profile.apply_signal(_pos("安静", strength=1.0))
        tags = profile.high_confidence_tags("亲子")
        assert "安静" in tags

    def test_low_confidence_tags_not_returned(self, profile):
        profile.apply_signal(_pos("噪杂", strength=0.1))
        tags = profile.high_confidence_tags("亲子")
        assert "噪杂" not in tags

    def test_to_constraint_boost_empty_when_no_high_conf(self, profile):
        profile.apply_signal(_pos("安静", strength=0.1))
        result = profile.to_constraint_boost("亲子")
        assert result == {}

    def test_to_constraint_boost_returns_boost_tags(self, profile):
        for _ in range(10):
            profile.apply_signal(_pos("轻食", strength=1.0))
        result = profile.to_constraint_boost("亲子")
        assert "boost_tags" in result
        assert "轻食" in result["boost_tags"]

    def test_promoted_flag_in_log_when_crossing_threshold(self, profile):
        promoted_logs = []
        for _ in range(50):
            log = profile.apply_signal(_pos("轻食", strength=1.0))
            if log.promoted:
                promoted_logs.append(log)
        assert len(promoted_logs) == 1  # fires exactly once at crossing

    def test_promoted_message_contains_首推(self, profile):
        for _ in range(50):
            log = profile.apply_signal(_pos("轻食", strength=1.0))
            if log.promoted:
                assert "首推" in log.message
                break


# ── learning log ──────────────────────────────────────────────────────────────


class TestLearningLog:
    def test_log_fields_populated(self, profile):
        log = profile.apply_signal(_pos("安静", scene="亲子"))
        assert isinstance(log, LearningLogEntry)
        assert log.scene == "亲子"
        assert log.tag == "安静"
        assert 0.0 <= log.confidence_before <= 1.0
        assert 0.0 <= log.confidence_after <= 1.0

    def test_positive_log_confidence_increases(self, profile):
        log = profile.apply_signal(_pos("安静"))
        assert log.confidence_after > log.confidence_before

    def test_negative_log_confidence_decreases(self, profile):
        log = profile.apply_signal(_neg("嘈杂"))
        assert log.confidence_after < log.confidence_before

    def test_log_message_mentions_scene_and_tag(self, profile):
        log = profile.apply_signal(_pos("轻食", scene="商务"))
        assert "轻食" in log.message
        assert "商务" in log.message

    def test_apply_signals_returns_list_same_length(self, profile):
        signals = [_pos("安静"), _neg("嘈杂"), _implicit("户外")]
        logs = profile.apply_signals(signals)
        assert len(logs) == 3

    def test_apply_signals_order_preserved(self, profile):
        signals = [_pos("A"), _pos("B"), _pos("C")]
        logs = profile.apply_signals(signals)
        assert [log.tag for log in logs] == ["A", "B", "C"]


# ── independent user profiles ─────────────────────────────────────────────────


class TestUserIndependence:
    def test_two_users_have_separate_profiles(self):
        p1 = FamilyProfile(user_id="alice")
        p2 = FamilyProfile(user_id="bob")
        for _ in range(10):
            p1.apply_signal(_pos("安静", strength=1.0))
        # bob should not be affected
        assert "亲子" not in p2.scene_prefs
