"""Unit tests for F07: fault_handlers — 3-class fault × 3-level degradation.

Verification command: pytest tests/unit/test_fault_handlers.py -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agent.core.fault_handlers import (
    DegradationLevel,
    FaultClass,
    FaultContext,
    FaultResult,
    classify_fault,
    route_fault,
)
from agent.schemas import (
    ConstraintSet,
    HardConstraints,
    Itinerary,
    ItineraryNode,
    SoftPreferences,
    TransitInfo,
)
from agent.tools.mock_data import ToolFaultError


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def constraint() -> ConstraintSet:
    return ConstraintSet(
        hard=HardConstraints(max_distance_km=10.0, age_range=(18, 40), total_duration=6.0),
        soft=SoftPreferences(noise_level="medium", per_capita=150, tags=["出片"]),
    )


@pytest.fixture()
def transit() -> TransitInfo:
    return TransitInfo(mode="地铁", duration_min=15, distance_km=3.0)


@pytest.fixture()
def venue_node(transit: TransitInfo) -> ItineraryNode:
    return ItineraryNode(
        node_id="v001",
        node_type="venue",
        name="欢乐谷主题乐园",
        address="朝阳区东四环小武基北路",
        start_time="10:00",
        end_time="14:00",
        duration_min=240,
        per_capita=200,
        transit_to_next=transit,
    )


@pytest.fixture()
def restaurant_node() -> ItineraryNode:
    return ItineraryNode(
        node_id="r001",
        node_type="restaurant",
        name="海底捞火锅（三里屯店）",
        address="朝阳区三里屯路19号",
        start_time="14:15",
        end_time="15:45",
        duration_min=90,
        per_capita=150,
        transit_to_next=None,
    )


@pytest.fixture()
def two_node_itinerary(
    venue_node: ItineraryNode, restaurant_node: ItineraryNode
) -> Itinerary:
    return Itinerary(
        session_id="sess-001",
        nodes=[venue_node, restaurant_node],
        total_duration_min=345,
        total_per_capita=350,
    )


@pytest.fixture()
def single_node_itinerary(venue_node: ItineraryNode) -> Itinerary:
    return Itinerary(
        session_id="sess-002",
        nodes=[venue_node],
        total_duration_min=240,
        total_per_capita=200,
    )


def _make_replacement(node_type: str = "venue") -> ItineraryNode:
    if node_type == "venue":
        return ItineraryNode(
            node_id="v002",
            node_type="venue",
            name="故宫博物院",
            address="东城区景山前街4号",
            start_time="10:00",
            end_time="13:00",
            duration_min=180,
            per_capita=60,
            transit_to_next=None,
        )
    return ItineraryNode(
        node_id="r002",
        node_type="restaurant",
        name="大董烤鸭店",
        address="朝阳区工人体育场北路8号",
        start_time="14:15",
        end_time="15:45",
        duration_min=90,
        per_capita=280,
        transit_to_next=None,
    )


# ── classify_fault ────────────────────────────────────────────────────────────


class TestClassifyFault:
    def test_no_seat_default(self) -> None:
        exc = ToolFaultError("无座/无票 in venue_search: trigger partial_replan")
        assert classify_fault(exc) == FaultClass.NO_SEAT

    def test_time_conflict_chinese(self) -> None:
        exc = ToolFaultError("时间冲突: slot 10:00 overlaps existing node")
        assert classify_fault(exc) == FaultClass.TIME_CONFLICT

    def test_time_conflict_english_keyword(self) -> None:
        exc = ToolFaultError("time_conflict detected in check_availability")
        assert classify_fault(exc) == FaultClass.TIME_CONFLICT

    def test_time_conflict_bare_keyword(self) -> None:
        exc = ToolFaultError("conflict at slot 14:00")
        assert classify_fault(exc) == FaultClass.TIME_CONFLICT

    def test_no_nearby_chinese(self) -> None:
        exc = ToolFaultError("周边 500 米内无同类选项")
        assert classify_fault(exc) == FaultClass.NO_NEARBY

    def test_no_nearby_english_keyword(self) -> None:
        exc = ToolFaultError("no_nearby: 0 alternatives found")
        assert classify_fault(exc) == FaultClass.NO_NEARBY

    def test_empty_message_defaults_to_no_seat(self) -> None:
        exc = ToolFaultError("")
        assert classify_fault(exc) == FaultClass.NO_SEAT


# ── Level 1: silent replace ───────────────────────────────────────────────────


class TestLevel1SilentReplace:
    async def test_venue_fault_finds_replacement(
        self,
        two_node_itinerary: Itinerary,
        constraint: ConstraintSet,
        venue_node: ItineraryNode,
    ) -> None:
        ctx = FaultContext(
            failed_node=venue_node,
            node_index=0,
            itinerary=two_node_itinerary,
            constraint_set=constraint,
            original_error="无座/无票",
        )
        exc = ToolFaultError("无座/无票")

        with patch(
            "agent.core.fault_handlers._try_level1",
            new_callable=AsyncMock,
            return_value=_make_replacement("venue"),
        ):
            result = await route_fault(exc, ctx)

        assert result.level == DegradationLevel.LEVEL_1_SILENT
        assert result.replacement_node is not None
        assert result.replacement_node.node_id == "v002"
        assert result.requires_user_action is False

    async def test_restaurant_fault_finds_replacement(
        self,
        two_node_itinerary: Itinerary,
        constraint: ConstraintSet,
        restaurant_node: ItineraryNode,
    ) -> None:
        ctx = FaultContext(
            failed_node=restaurant_node,
            node_index=1,
            itinerary=two_node_itinerary,
            constraint_set=constraint,
            original_error="无座/无票",
        )
        exc = ToolFaultError("无座/无票")

        with patch(
            "agent.core.fault_handlers._try_level1",
            new_callable=AsyncMock,
            return_value=_make_replacement("restaurant"),
        ):
            result = await route_fault(exc, ctx)

        assert result.level == DegradationLevel.LEVEL_1_SILENT
        assert result.replacement_node is not None
        assert result.replacement_node.name == "大董烤鸭店"

    async def test_level1_message_names_both_nodes(
        self,
        two_node_itinerary: Itinerary,
        constraint: ConstraintSet,
        venue_node: ItineraryNode,
    ) -> None:
        ctx = FaultContext(
            failed_node=venue_node,
            node_index=0,
            itinerary=two_node_itinerary,
            constraint_set=constraint,
            original_error="无座/无票",
        )
        exc = ToolFaultError("无座/无票")
        replacement = _make_replacement("venue")

        with patch(
            "agent.core.fault_handlers._try_level1",
            new_callable=AsyncMock,
            return_value=replacement,
        ):
            result = await route_fault(exc, ctx)

        assert venue_node.name in result.message
        assert replacement.name in result.message
        assert "Level 1" in result.message

    async def test_level1_no_reordered_itinerary(
        self,
        two_node_itinerary: Itinerary,
        constraint: ConstraintSet,
        venue_node: ItineraryNode,
    ) -> None:
        ctx = FaultContext(
            failed_node=venue_node,
            node_index=0,
            itinerary=two_node_itinerary,
            constraint_set=constraint,
            original_error="无座/无票",
        )
        exc = ToolFaultError("无座/无票")

        with patch(
            "agent.core.fault_handlers._try_level1",
            new_callable=AsyncMock,
            return_value=_make_replacement("venue"),
        ):
            result = await route_fault(exc, ctx)

        assert result.reordered_itinerary is None


# ── Level 2: reorder ──────────────────────────────────────────────────────────


class TestLevel2Reorder:
    async def test_falls_back_when_level1_returns_none(
        self,
        two_node_itinerary: Itinerary,
        constraint: ConstraintSet,
        venue_node: ItineraryNode,
    ) -> None:
        ctx = FaultContext(
            failed_node=venue_node,
            node_index=0,
            itinerary=two_node_itinerary,
            constraint_set=constraint,
            original_error="无座/无票",
        )
        exc = ToolFaultError("无座/无票")

        with patch(
            "agent.core.fault_handlers._try_level1",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await route_fault(exc, ctx)

        assert result.level == DegradationLevel.LEVEL_2_REORDER
        assert result.reordered_itinerary is not None
        assert result.requires_user_action is False

    async def test_reordered_itinerary_excludes_failed_node(
        self,
        two_node_itinerary: Itinerary,
        constraint: ConstraintSet,
        venue_node: ItineraryNode,
    ) -> None:
        ctx = FaultContext(
            failed_node=venue_node,
            node_index=0,
            itinerary=two_node_itinerary,
            constraint_set=constraint,
            original_error="无座/无票",
        )
        exc = ToolFaultError("无座/无票")

        with patch(
            "agent.core.fault_handlers._try_level1",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await route_fault(exc, ctx)

        assert result.reordered_itinerary is not None
        node_ids = {n.node_id for n in result.reordered_itinerary.nodes}
        assert "v001" not in node_ids

    async def test_level2_message_mentions_removed_and_remaining(
        self,
        two_node_itinerary: Itinerary,
        constraint: ConstraintSet,
        venue_node: ItineraryNode,
    ) -> None:
        ctx = FaultContext(
            failed_node=venue_node,
            node_index=0,
            itinerary=two_node_itinerary,
            constraint_set=constraint,
            original_error="无座/无票",
        )
        exc = ToolFaultError("无座/无票")

        with patch(
            "agent.core.fault_handlers._try_level1",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await route_fault(exc, ctx)

        assert venue_node.name in result.message
        assert "Level 2" in result.message
        assert "移除" in result.message

    async def test_level2_no_replacement_node(
        self,
        two_node_itinerary: Itinerary,
        constraint: ConstraintSet,
        venue_node: ItineraryNode,
    ) -> None:
        ctx = FaultContext(
            failed_node=venue_node,
            node_index=0,
            itinerary=two_node_itinerary,
            constraint_set=constraint,
            original_error="无座/无票",
        )
        exc = ToolFaultError("无座/无票")

        with patch(
            "agent.core.fault_handlers._try_level1",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await route_fault(exc, ctx)

        if result.level == DegradationLevel.LEVEL_2_REORDER:
            assert result.replacement_node is None


# ── Level 3: user decision ────────────────────────────────────────────────────


class TestLevel3UserDecision:
    async def test_single_node_itinerary_triggers_level3(
        self,
        single_node_itinerary: Itinerary,
        constraint: ConstraintSet,
        venue_node: ItineraryNode,
    ) -> None:
        ctx = FaultContext(
            failed_node=venue_node,
            node_index=0,
            itinerary=single_node_itinerary,
            constraint_set=constraint,
            original_error="无座/无票",
        )
        exc = ToolFaultError("无座/无票")

        with patch(
            "agent.core.fault_handlers._try_level1",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await route_fault(exc, ctx)

        assert result.level == DegradationLevel.LEVEL_3_USER_DECISION
        assert result.requires_user_action is True

    async def test_no_nearby_fault_class_preserved(
        self,
        single_node_itinerary: Itinerary,
        constraint: ConstraintSet,
        venue_node: ItineraryNode,
    ) -> None:
        ctx = FaultContext(
            failed_node=venue_node,
            node_index=0,
            itinerary=single_node_itinerary,
            constraint_set=constraint,
            original_error="周边 500 米内无同类",
        )
        exc = ToolFaultError("周边 500 米内无同类")

        with patch(
            "agent.core.fault_handlers._try_level1",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await route_fault(exc, ctx)

        assert result.fault_class == FaultClass.NO_NEARBY
        assert result.level == DegradationLevel.LEVEL_3_USER_DECISION

    async def test_level3_message_guides_user(
        self,
        single_node_itinerary: Itinerary,
        constraint: ConstraintSet,
        venue_node: ItineraryNode,
    ) -> None:
        ctx = FaultContext(
            failed_node=venue_node,
            node_index=0,
            itinerary=single_node_itinerary,
            constraint_set=constraint,
            original_error="无法替换",
        )
        exc = ToolFaultError("无法替换")

        with patch(
            "agent.core.fault_handlers._try_level1",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await route_fault(exc, ctx)

        assert "Level 3" in result.message
        assert "选择" in result.message or "取消" in result.message

    async def test_level3_no_replacement_or_reorder(
        self,
        single_node_itinerary: Itinerary,
        constraint: ConstraintSet,
        venue_node: ItineraryNode,
    ) -> None:
        ctx = FaultContext(
            failed_node=venue_node,
            node_index=0,
            itinerary=single_node_itinerary,
            constraint_set=constraint,
            original_error="无座/无票",
        )
        exc = ToolFaultError("无座/无票")

        with patch(
            "agent.core.fault_handlers._try_level1",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await route_fault(exc, ctx)

        if result.level == DegradationLevel.LEVEL_3_USER_DECISION:
            assert result.replacement_node is None
            assert result.reordered_itinerary is None


# ── Never raises ──────────────────────────────────────────────────────────────


class TestNeverRaises:
    async def test_survives_exception_in_level1_path(
        self,
        two_node_itinerary: Itinerary,
        constraint: ConstraintSet,
        venue_node: ItineraryNode,
    ) -> None:
        ctx = FaultContext(
            failed_node=venue_node,
            node_index=0,
            itinerary=two_node_itinerary,
            constraint_set=constraint,
            original_error="unexpected",
        )
        exc = ToolFaultError("unexpected")

        with patch(
            "agent.core.fault_handlers._try_level1",
            new_callable=AsyncMock,
            side_effect=RuntimeError("unexpected internal error"),
        ):
            result = await route_fault(exc, ctx)

        assert isinstance(result, FaultResult)
        assert result.level in {
            DegradationLevel.LEVEL_2_REORDER,
            DegradationLevel.LEVEL_3_USER_DECISION,
        }

    async def test_survives_time_conflict_fault(
        self,
        two_node_itinerary: Itinerary,
        constraint: ConstraintSet,
        venue_node: ItineraryNode,
    ) -> None:
        ctx = FaultContext(
            failed_node=venue_node,
            node_index=0,
            itinerary=two_node_itinerary,
            constraint_set=constraint,
            original_error="时间冲突",
        )
        exc = ToolFaultError("时间冲突")

        with patch(
            "agent.core.fault_handlers._try_level1",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await route_fault(exc, ctx)

        assert isinstance(result, FaultResult)
        assert result.fault_class == FaultClass.TIME_CONFLICT

    async def test_tool_fault_error_never_propagates(
        self,
        single_node_itinerary: Itinerary,
        constraint: ConstraintSet,
        venue_node: ItineraryNode,
    ) -> None:
        ctx = FaultContext(
            failed_node=venue_node,
            node_index=0,
            itinerary=single_node_itinerary,
            constraint_set=constraint,
            original_error="任意错误",
        )
        exc = ToolFaultError("任意错误")

        with patch(
            "agent.core.fault_handlers._try_level1",
            new_callable=AsyncMock,
            return_value=None,
        ):
            try:
                result = await route_fault(exc, ctx)
                assert isinstance(result, FaultResult)
            except Exception as err:  # noqa: BLE001
                pytest.fail(f"route_fault raised unexpectedly: {err}")


# ── _try_level1 internals ─────────────────────────────────────────────────────


class TestTryLevel1Internals:
    async def test_returns_none_when_all_unavailable(
        self,
        two_node_itinerary: Itinerary,
        constraint: ConstraintSet,
        venue_node: ItineraryNode,
    ) -> None:
        from agent.core.fault_handlers import _try_level1

        ctx = FaultContext(
            failed_node=venue_node,
            node_index=0,
            itinerary=two_node_itinerary,
            constraint_set=constraint,
            original_error="无座/无票",
        )

        with patch(
            "agent.core.fault_handlers.check_availability",
            new_callable=AsyncMock,
            return_value={"item_id": "v002", "available": False, "next_slot": None},
        ):
            result = await _try_level1(ctx)

        assert result is None

    async def test_returns_replacement_when_first_available(
        self,
        single_node_itinerary: Itinerary,
        constraint: ConstraintSet,
        venue_node: ItineraryNode,
    ) -> None:
        from agent.core.fault_handlers import _try_level1

        ctx = FaultContext(
            failed_node=venue_node,
            node_index=0,
            itinerary=single_node_itinerary,
            constraint_set=constraint,
            original_error="无座/无票",
        )

        with patch(
            "agent.core.fault_handlers.check_availability",
            new_callable=AsyncMock,
            return_value={"item_id": "v002", "available": True, "next_slot": None},
        ):
            result = await _try_level1(ctx)

        assert result is not None
        assert result.node_type == "venue"
        assert result.node_id != "v001"

    async def test_skips_fault_prone_candidates(
        self,
        single_node_itinerary: Itinerary,
        constraint: ConstraintSet,
        venue_node: ItineraryNode,
    ) -> None:
        from agent.core.fault_handlers import _try_level1

        ctx = FaultContext(
            failed_node=venue_node,
            node_index=0,
            itinerary=single_node_itinerary,
            constraint_set=constraint,
            original_error="无座/无票",
        )

        with patch(
            "agent.core.fault_handlers.check_availability",
            new_callable=AsyncMock,
            side_effect=ToolFaultError("injected fault"),
        ):
            result = await _try_level1(ctx)

        assert result is None

    async def test_inherits_original_time_slot(
        self,
        single_node_itinerary: Itinerary,
        constraint: ConstraintSet,
        venue_node: ItineraryNode,
    ) -> None:
        from agent.core.fault_handlers import _try_level1

        ctx = FaultContext(
            failed_node=venue_node,
            node_index=0,
            itinerary=single_node_itinerary,
            constraint_set=constraint,
            original_error="无座/无票",
        )

        with patch(
            "agent.core.fault_handlers.check_availability",
            new_callable=AsyncMock,
            return_value={"item_id": "v002", "available": True, "next_slot": None},
        ):
            result = await _try_level1(ctx)

        assert result is not None
        assert result.start_time == venue_node.start_time
        assert result.end_time == venue_node.end_time
        assert result.duration_min == venue_node.duration_min
