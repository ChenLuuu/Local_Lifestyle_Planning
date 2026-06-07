"""Unit tests for F09: signal_extractor — 4 signal types from user interaction events.

Verification command: pytest tests/unit/test_signal_extractor.py -v
"""

from __future__ import annotations

import pytest

from agent.modules.signal_extractor import Signal, SignalType, extract_signals


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_node(name: str, tags: list[str]) -> dict:
    return {"name": name, "tags": tags, "node_type": "venue"}


# ── node_swap events ──────────────────────────────────────────────────────────


class TestNodeSwap:
    def test_swap_produces_negative_for_old_tags(self):
        event = {
            "event_type": "node_swap",
            "scene": "亲子",
            "old_node": _make_node("喧闹餐厅", ["嘈杂", "商务"]),
            "new_node": _make_node("安静咖啡馆", ["安静", "轻食"]),
        }
        signals = extract_signals(event)
        neg = [s for s in signals if s.signal_type == SignalType.NEGATIVE_FEEDBACK]
        assert len(neg) == 2
        neg_tags = {s.tag for s in neg}
        assert neg_tags == {"嘈杂", "商务"}

    def test_swap_produces_explicit_modify_for_new_tags(self):
        event = {
            "event_type": "node_swap",
            "scene": "亲子",
            "old_node": _make_node("老店", ["传统"]),
            "new_node": _make_node("新店", ["出片", "网红"]),
        }
        signals = extract_signals(event)
        pos = [s for s in signals if s.signal_type == SignalType.EXPLICIT_MODIFY]
        assert len(pos) == 2
        pos_tags = {s.tag for s in pos}
        assert pos_tags == {"出片", "网红"}

    def test_swap_signal_scene_propagated(self):
        event = {
            "event_type": "node_swap",
            "scene": "商务",
            "old_node": _make_node("A", ["x"]),
            "new_node": _make_node("B", ["y"]),
        }
        signals = extract_signals(event)
        assert all(s.scene == "商务" for s in signals)

    def test_swap_negative_strength_is_06(self):
        event = {
            "event_type": "node_swap",
            "scene": "聚会",
            "old_node": _make_node("旧", ["tag1"]),
            "new_node": {},
        }
        signals = extract_signals(event)
        neg = [s for s in signals if s.signal_type == SignalType.NEGATIVE_FEEDBACK]
        assert all(s.strength == pytest.approx(0.6) for s in neg)

    def test_swap_explicit_modify_strength_is_08(self):
        event = {
            "event_type": "node_swap",
            "scene": "亲子",
            "old_node": {},
            "new_node": _make_node("新", ["新标签"]),
        }
        signals = extract_signals(event)
        pos = [s for s in signals if s.signal_type == SignalType.EXPLICIT_MODIFY]
        assert all(s.strength == pytest.approx(0.8) for s in pos)

    def test_swap_explicit_modify_stronger_than_negative(self):
        event = {
            "event_type": "node_swap",
            "scene": "亲子",
            "old_node": _make_node("旧", ["旧标签"]),
            "new_node": _make_node("新", ["新标签"]),
        }
        signals = extract_signals(event)
        neg = next(s for s in signals if s.signal_type == SignalType.NEGATIVE_FEEDBACK)
        pos = next(s for s in signals if s.signal_type == SignalType.EXPLICIT_MODIFY)
        assert pos.strength > neg.strength

    def test_swap_empty_old_node_no_negative(self):
        event = {
            "event_type": "node_swap",
            "scene": "亲子",
            "old_node": {},
            "new_node": _make_node("新", ["美食"]),
        }
        signals = extract_signals(event)
        assert not any(s.signal_type == SignalType.NEGATIVE_FEEDBACK for s in signals)

    def test_swap_empty_new_node_no_positive(self):
        event = {
            "event_type": "node_swap",
            "scene": "亲子",
            "old_node": _make_node("旧", ["旧"]),
            "new_node": {},
        }
        signals = extract_signals(event)
        assert not any(s.signal_type == SignalType.EXPLICIT_MODIFY for s in signals)

    def test_swap_value_is_node_name(self):
        event = {
            "event_type": "node_swap",
            "scene": "亲子",
            "old_node": _make_node("旧店名", ["tag"]),
            "new_node": _make_node("新店名", ["tag2"]),
        }
        signals = extract_signals(event)
        neg = next(s for s in signals if s.signal_type == SignalType.NEGATIVE_FEEDBACK)
        pos = next(s for s in signals if s.signal_type == SignalType.EXPLICIT_MODIFY)
        assert neg.value == "旧店名"
        assert pos.value == "新店名"


# ── candidate_request events ──────────────────────────────────────────────────


class TestCandidateRequest:
    def test_request_with_tags_produces_deep_inquiry(self):
        event = {
            "event_type": "candidate_request",
            "scene": "商务",
            "tags": ["安静", "高档"],
        }
        signals = extract_signals(event)
        assert len(signals) == 2
        assert all(s.signal_type == SignalType.DEEP_INQUIRY for s in signals)

    def test_request_without_tags_uses_default_explore_tag(self):
        event = {"event_type": "candidate_request", "scene": "聚会"}
        signals = extract_signals(event)
        assert len(signals) == 1
        assert signals[0].tag == "探索"
        assert signals[0].signal_type == SignalType.DEEP_INQUIRY

    def test_request_with_tags_strength_is_05(self):
        event = {"event_type": "candidate_request", "scene": "亲子", "tags": ["美食"]}
        signals = extract_signals(event)
        assert signals[0].strength == pytest.approx(0.5)

    def test_request_without_tags_strength_is_03(self):
        event = {"event_type": "candidate_request", "scene": "亲子"}
        signals = extract_signals(event)
        assert signals[0].strength == pytest.approx(0.3)

    def test_request_value_is_requested_more(self):
        event = {"event_type": "candidate_request", "scene": "商务", "tags": ["高档"]}
        signals = extract_signals(event)
        assert all(s.value == "requested_more" for s in signals)


# ── node_accept events ────────────────────────────────────────────────────────


class TestNodeAccept:
    def test_accept_tagged_node_produces_implicit_approve(self):
        event = {
            "event_type": "node_accept",
            "scene": "亲子",
            "node": _make_node("欢乐谷", ["亲子", "户外"]),
        }
        signals = extract_signals(event)
        assert len(signals) == 2
        assert all(s.signal_type == SignalType.IMPLICIT_APPROVE for s in signals)

    def test_accept_strength_is_04(self):
        event = {
            "event_type": "node_accept",
            "scene": "亲子",
            "node": _make_node("X", ["tag"]),
        }
        signals = extract_signals(event)
        assert all(s.strength == pytest.approx(0.4) for s in signals)

    def test_accept_falls_back_to_explicit_tags_when_node_has_none(self):
        event = {
            "event_type": "node_accept",
            "scene": "聚会",
            "node": {"name": "无标签场所"},
            "tags": ["热闹"],
        }
        signals = extract_signals(event)
        assert len(signals) == 1
        assert signals[0].tag == "热闹"

    def test_accept_no_tags_anywhere_returns_empty(self):
        event = {
            "event_type": "node_accept",
            "scene": "聚会",
            "node": {"name": "无标签"},
        }
        signals = extract_signals(event)
        assert signals == []


# ── node_reject_all events ────────────────────────────────────────────────────


class TestNodeRejectAll:
    def test_reject_all_produces_negative_feedback_per_tag(self):
        event = {
            "event_type": "node_reject_all",
            "scene": "聚会",
            "tags": ["嘈杂", "贵"],
        }
        signals = extract_signals(event)
        assert len(signals) == 2
        assert all(s.signal_type == SignalType.NEGATIVE_FEEDBACK for s in signals)

    def test_reject_all_strength_is_07(self):
        event = {
            "event_type": "node_reject_all",
            "scene": "亲子",
            "tags": ["不适合儿童"],
        }
        signals = extract_signals(event)
        assert signals[0].strength == pytest.approx(0.7)

    def test_reject_all_value_is_rejected_all(self):
        event = {
            "event_type": "node_reject_all",
            "scene": "商务",
            "tags": ["嘈杂"],
        }
        signals = extract_signals(event)
        assert signals[0].value == "rejected_all"

    def test_reject_all_no_tags_returns_empty(self):
        event = {"event_type": "node_reject_all", "scene": "亲子"}
        signals = extract_signals(event)
        assert signals == []


# ── general / edge cases ──────────────────────────────────────────────────────


class TestGeneral:
    def test_unknown_event_type_returns_empty(self):
        event = {"event_type": "something_weird", "scene": "亲子"}
        assert extract_signals(event) == []

    def test_missing_event_type_returns_empty(self):
        event = {"scene": "亲子"}
        assert extract_signals(event) == []

    def test_default_scene_is_general(self):
        event = {"event_type": "candidate_request"}
        signals = extract_signals(event)
        assert signals[0].scene == "通用"

    def test_all_signal_strengths_in_range(self):
        events = [
            {"event_type": "node_swap", "old_node": _make_node("A", ["t"]), "new_node": _make_node("B", ["t2"])},
            {"event_type": "candidate_request", "tags": ["t"]},
            {"event_type": "node_accept", "node": _make_node("C", ["t"])},
            {"event_type": "node_reject_all", "tags": ["t"]},
        ]
        for ev in events:
            for sig in extract_signals(ev):
                assert 0.0 <= sig.strength <= 1.0, f"Strength {sig.strength} out of range for {sig}"

    def test_signal_is_dataclass(self):
        s = Signal(
            signal_type=SignalType.EXPLICIT_MODIFY,
            tag="安静",
            value="某店",
            scene="亲子",
            strength=0.8,
        )
        assert s.signal_type == SignalType.EXPLICIT_MODIFY
        assert s.strength == 0.8
