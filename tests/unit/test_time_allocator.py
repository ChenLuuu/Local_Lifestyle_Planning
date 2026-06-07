"""Unit tests for F04: dynamic time allocator (hard validate → elastic fill → conflict check)."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from agent.core.time_allocator import (
    ActivitySlot,
    TimeConflictError,
    TransitSlot,
    allocate,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _slot(
    name: str,
    duration: int,
    priority: int = 5,
    extendable: bool = True,
    node_type: str = "venue",
) -> ActivitySlot:
    return ActivitySlot(
        node_id=f"id_{name}",
        node_type=node_type,
        name=name,
        address=f"{name}_addr",
        duration_min=duration,
        per_capita=100,
        priority=priority,
        extendable=extendable,
    )


def _transit(mode: str = "地铁", duration: int = 15, dist: float = 3.0) -> TransitSlot:
    return TransitSlot(mode=mode, duration_min=duration, distance_km=dist)


def _hhmm_to_min(hhmm: str) -> int:
    t = datetime.strptime(hhmm, "%H:%M")
    return t.hour * 60 + t.minute


# ── Hard Validation ───────────────────────────────────────────────────────────


class TestHardValidation:
    def test_fits_exactly(self) -> None:
        """When min duration == window, no pruning occurs."""
        nodes = allocate(
            [_slot("A", 60), _slot("B", 60)],
            [_transit(duration=30)],
            "10:00",
            150,
        )
        assert len(nodes) == 2

    def test_prune_lowest_priority(self) -> None:
        """Activity with highest priority number is pruned first."""
        acts = [_slot("Keep", 120, priority=1), _slot("Drop", 120, priority=5)]
        nodes = allocate(acts, [_transit(duration=30)], "10:00", 150)
        assert len(nodes) == 1
        assert nodes[0].name == "Keep"

    def test_prune_multiple_until_fits(self) -> None:
        """Multiple activities are pruned in priority order until window fits."""
        acts = [
            _slot("Keep", 60, priority=1),
            _slot("Drop1", 60, priority=3),
            _slot("Drop2", 60, priority=5),
        ]
        trns = [_transit(duration=30), _transit(duration=30)]
        nodes = allocate(acts, trns, "10:00", 70)
        assert len(nodes) == 1
        assert nodes[0].name == "Keep"

    def test_single_too_long_raises(self) -> None:
        """Single activity exceeding window raises TimeConflictError."""
        with pytest.raises(TimeConflictError, match="trigger partial_replan"):
            allocate([_slot("Giant", 120, priority=1)], [], "10:00", 60)

    def test_empty_activities_returns_empty(self) -> None:
        assert allocate([], [], "10:00", 240) == []

    def test_equal_priority_removes_last(self) -> None:
        """Among same-priority ties, last (highest index) activity is pruned first."""
        acts = [_slot("First", 60, priority=5), _slot("Last", 60, priority=5)]
        nodes = allocate(acts, [_transit(duration=30)], "10:00", 70)
        assert len(nodes) == 1
        assert nodes[0].name == "First"

    def test_error_message_has_recovery_hint(self) -> None:
        """Error messages include recovery guidance per fault_handlers contract."""
        with pytest.raises(TimeConflictError) as exc_info:
            allocate([_slot("Big", 300, priority=1)], [], "10:00", 60)
        assert "partial_replan" in str(exc_info.value)

    def test_prune_middle_activity(self) -> None:
        """Pruning a middle activity correctly removes its incoming transit."""
        acts = [
            _slot("A", 60, priority=1),
            _slot("B", 60, priority=5),  # middle, lowest priority
            _slot("C", 60, priority=2),
        ]
        trns = [_transit(duration=10), _transit(duration=10)]
        # min = 60+60+60+10+10 = 200 > 150
        nodes = allocate(acts, trns, "10:00", 150)
        assert len(nodes) == 2
        names = {n.name for n in nodes}
        assert "B" not in names


# ── Elastic Allocation ────────────────────────────────────────────────────────


class TestElasticAllocation:
    def test_slack_fully_consumed(self) -> None:
        """All slack time is distributed when activities are extendable."""
        acts = [_slot("A", 60), _slot("B", 60)]
        nodes = allocate(acts, [], "10:00", 180)
        assert sum(n.duration_min for n in nodes) == 180

    def test_non_extendable_unchanged(self) -> None:
        """Non-extendable activities do not receive slack time."""
        acts = [_slot("Fixed", 60, extendable=False), _slot("Flex", 60)]
        nodes = allocate(acts, [], "10:00", 180)
        fixed = next(n for n in nodes if n.name == "Fixed")
        flex = next(n for n in nodes if n.name == "Flex")
        assert fixed.duration_min == 60
        assert flex.duration_min == 120

    def test_all_non_extendable_no_growth(self) -> None:
        """No slack distribution when all activities are non-extendable."""
        acts = [_slot("A", 60, extendable=False), _slot("B", 60, extendable=False)]
        nodes = allocate(acts, [], "10:00", 240)
        assert nodes[0].duration_min == 60
        assert nodes[1].duration_min == 60

    def test_zero_slack_no_change(self) -> None:
        """When min duration equals window, activity durations are unchanged."""
        acts = [_slot("A", 60), _slot("B", 60)]
        nodes = allocate(acts, [_transit(duration=30)], "10:00", 150)
        assert nodes[0].duration_min == 60
        assert nodes[1].duration_min == 60

    def test_proportional_distribution_total(self) -> None:
        """Total activity duration after allocation equals window minus transits."""
        acts = [_slot("Short", 30), _slot("Long", 60)]
        nodes = allocate(acts, [], "10:00", 180)
        assert sum(n.duration_min for n in nodes) == 180

    def test_proportional_ratio_preserved(self) -> None:
        """Larger base duration gets proportionally more slack."""
        acts = [_slot("Short", 30), _slot("Long", 60)]
        nodes = allocate(acts, [], "10:00", 180)
        short = next(n for n in nodes if n.name == "Short")
        long_ = next(n for n in nodes if n.name == "Long")
        # short: int(90 * 30/90)=30 extra → 60; long: 90-30=60 extra → 120
        assert long_.duration_min >= short.duration_min

    def test_original_activities_not_mutated(self) -> None:
        """allocate() must not mutate the caller's input list."""
        acts = [_slot("A", 60), _slot("B", 60)]
        orig_durations = [a.duration_min for a in acts]
        allocate(acts, [], "10:00", 200)
        assert [a.duration_min for a in acts] == orig_durations

    def test_single_extendable_gets_all_slack(self) -> None:
        """When only one activity is extendable, it absorbs all slack."""
        acts = [_slot("Fixed", 60, extendable=False), _slot("Flex", 60, extendable=True)]
        nodes = allocate(acts, [_transit(duration=10)], "10:00", 200)
        flex = next(n for n in nodes if n.name == "Flex")
        # slack = 200 - (60+60+10) = 70; all goes to Flex
        assert flex.duration_min == 130


# ── Timeline Construction ─────────────────────────────────────────────────────


class TestTimelineConstruction:
    def test_start_time_propagates(self) -> None:
        """Start/end times are computed correctly with transit gaps."""
        acts = [_slot("A", 60), _slot("B", 60)]
        nodes = allocate(acts, [_transit(duration=15)], "09:00", 135)
        assert nodes[0].start_time == "09:00"
        assert nodes[0].end_time == "10:00"
        assert nodes[1].start_time == "10:15"
        assert nodes[1].end_time == "11:15"

    def test_transit_data_preserved(self) -> None:
        """Transit mode, duration, and distance are passed through unchanged."""
        trns = [_transit(mode="公交", duration=20, dist=5.0)]
        nodes = allocate([_slot("A", 60), _slot("B", 60)], trns, "10:00", 140)
        t = nodes[0].transit_to_next
        assert t is not None
        assert t.mode == "公交"
        assert t.duration_min == 20
        assert t.distance_km == 5.0

    def test_last_node_has_no_transit(self) -> None:
        """The final node never has a transit_to_next."""
        nodes = allocate(
            [_slot("A", 60), _slot("B", 60)],
            [_transit(duration=15)],
            "10:00",
            135,
        )
        assert nodes[-1].transit_to_next is None

    def test_single_activity(self) -> None:
        """Single-activity timeline has correct start/end and no transit."""
        nodes = allocate([_slot("Solo", 90, extendable=False)], [], "14:00", 120)
        assert len(nodes) == 1
        assert nodes[0].start_time == "14:00"
        assert nodes[0].end_time == "15:30"
        assert nodes[0].transit_to_next is None

    def test_four_node_itinerary(self) -> None:
        """Four-node itinerary with correct node count and ordering."""
        acts = [
            _slot("A", 60, priority=1),
            _slot("B", 45, priority=2),
            _slot("C", 60, priority=3),
            _slot("D", 45, priority=4),
        ]
        trns = [_transit(duration=15), _transit(duration=20), _transit(duration=15)]
        # min = 60+45+60+45+15+20+15 = 260
        nodes = allocate(acts, trns, "10:00", 260)
        assert len(nodes) == 4
        assert nodes[0].name == "A"
        assert nodes[3].name == "D"

    def test_node_fields_match_input(self) -> None:
        """All ActivitySlot fields are faithfully copied to ItineraryNode."""
        act = ActivitySlot(
            node_id="test-id",
            node_type="restaurant",
            name="TestRestaurant",
            address="123 Main St",
            duration_min=60,
            per_capita=150,
        )
        nodes = allocate([act], [], "12:00", 90)
        n = nodes[0]
        assert n.node_id == "test-id"
        assert n.node_type == "restaurant"
        assert n.name == "TestRestaurant"
        assert n.address == "123 Main St"
        assert n.per_capita == 150

    def test_timeline_ends_within_window(self) -> None:
        """Final node end_time does not exceed window_start + window_duration_min."""
        acts = [_slot("A", 60), _slot("B", 60)]
        window_min = 200
        nodes = allocate(acts, [_transit(duration=15)], "10:00", window_min)
        window_end = (
            datetime.strptime("10:00", "%H:%M") + timedelta(minutes=window_min)
        ).strftime("%H:%M")
        assert nodes[-1].end_time <= window_end

    def test_different_start_times(self) -> None:
        """Window can start at any HH:MM, not just 10:00."""
        nodes = allocate([_slot("Dinner", 90, extendable=False)], [], "18:30", 120)
        assert nodes[0].start_time == "18:30"
        assert nodes[0].end_time == "20:00"


# ── Conflict Detection ────────────────────────────────────────────────────────


class TestConflictDetection:
    def test_valid_timeline_no_raise(self) -> None:
        """A properly constructed timeline passes conflict check silently."""
        acts = [_slot("A", 60), _slot("B", 60)]
        nodes = allocate(acts, [_transit(duration=15)], "10:00", 150)
        assert len(nodes) == 2

    def test_consecutive_nodes_non_overlapping(self) -> None:
        """Consecutive nodes never start before the previous node + transit ends."""
        acts = [_slot("A", 45), _slot("B", 60), _slot("C", 30)]
        trns = [_transit(duration=20), _transit(duration=10)]
        nodes = allocate(acts, trns, "09:00", 165)
        for i in range(len(nodes) - 1):
            curr = nodes[i]
            nxt = nodes[i + 1]
            transit_end_min = _hhmm_to_min(curr.end_time)
            if curr.transit_to_next:
                transit_end_min += curr.transit_to_next.duration_min
            assert transit_end_min <= _hhmm_to_min(nxt.start_time)
