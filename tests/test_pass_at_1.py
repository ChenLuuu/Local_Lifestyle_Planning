"""F10: Pass@1 Automated Evaluation Framework.

20 test cases covering 亲子出行 / 商务宴请 / 生日聚会.
4 weighted dimensions:
  D1 约束满足率 (0.30) — node count, node types, budget alignment
  D2 时间合法性 (0.25) — format, start<end, no gaps/overlaps, chronology
  D3 执行完成率 (0.25) — booking success rate with fault injection disabled
  D4 降级触发率 (0.20) — fault_handlers.route_fault returns valid FaultResult

Per-case pass threshold: overall ≥ 0.70.
Target: Pass@1 ≥ 85% (≥ 17/20 cases).

Verification: pytest tests/test_pass_at_1.py -v --tb=short
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from unittest.mock import patch

import pytest

from agent.core import react_loop
from agent.core.fault_handlers import DegradationLevel, FaultContext, route_fault
from agent.schemas import ConstraintSet, HardConstraints, Itinerary, SoftPreferences
from agent.tools import execute_booking as _eb_mod
from agent.tools.execute_booking import book_node
from agent.tools.mock_data import ToolFaultError

# ── Constants ─────────────────────────────────────────────────────────────────

PASS_THRESHOLD = 0.70
TARGET_PASS_RATE = 0.85

WEIGHTS = {
    "d1": 0.30,  # constraint satisfaction
    "d2": 0.25,  # time validity
    "d3": 0.25,  # execution completion
    "d4": 0.20,  # fault degradation
}

# ── Data models ────────────────────────────────────────────────────────────────


@dataclass
class EvalCase:
    id: str
    scenario: str
    constraint_set: ConstraintSet
    start_time: str = "10:00"


@dataclass
class ScoreResult:
    case_id: str
    scenario: str
    d1: float
    d2: float
    d3: float
    d4: float

    @property
    def overall(self) -> float:
        return (
            self.d1 * WEIGHTS["d1"]
            + self.d2 * WEIGHTS["d2"]
            + self.d3 * WEIGHTS["d3"]
            + self.d4 * WEIGHTS["d4"]
        )

    @property
    def passed(self) -> bool:
        return self.overall >= PASS_THRESHOLD


# ── Helpers ────────────────────────────────────────────────────────────────────


def _cs(
    budget: int,
    duration: float,
    noise: str,
    tags: list[str],
    age_range: tuple[int, int] = (18, 45),
    max_dist: float = 10.0,
) -> ConstraintSet:
    return ConstraintSet(
        hard=HardConstraints(
            max_distance_km=max_dist,
            age_range=age_range,
            total_duration=duration,
        ),
        soft=SoftPreferences(noise_level=noise, per_capita=budget, tags=tags),
    )


def _no_faults():
    """Disable fault injection: patches mock_data.random so random() returns 0.9.

    0.9 > FAULT_RATE (0.10) → no ToolFaultError raised.
    """
    return patch("agent.tools.mock_data.random.random", return_value=0.9)


def _hhmm_to_min(t: str) -> int:
    h, m = map(int, t.split(":"))
    return h * 60 + m


# ── Test case definitions (20 cases) ─────────────────────────────────────────

TEST_CASES: list[EvalCase] = [
    # ── 亲子出行 (7 cases) ────────────────────────────────────────────────────
    EvalCase("PC01", "亲子出行", _cs(100, 3.0, "low", ["亲子友好", "安全设施"], (0, 10))),
    EvalCase("PC02", "亲子出行", _cs(80, 4.0, "low", ["涨知识", "文化探索"], (5, 12))),
    EvalCase("PC03", "亲子出行", _cs(200, 5.0, "high", ["儿童乐园", "亲子友好"], (3, 8))),
    EvalCase("PC04", "亲子出行", _cs(120, 3.0, "medium", ["购物", "室内", "亲子友好"], (2, 10))),
    EvalCase("PC05", "亲子出行", _cs(250, 6.0, "high", ["亲子友好", "安全设施", "不费脑"], (4, 10))),
    EvalCase("PC06", "亲子出行", _cs(80, 4.0, "low", ["悠闲放松", "户外", "亲子友好"], (2, 8))),
    EvalCase("PC07", "亲子出行", _cs(100, 3.0, "medium", ["出片", "艺术", "亲子友好"], (5, 12))),
    # ── 商务宴请 (7 cases) ────────────────────────────────────────────────────
    EvalCase("BZ01", "商务宴请", _cs(300, 2.0, "low", ["高端大气", "私密包间", "有面子"])),
    EvalCase("BZ02", "商务宴请", _cs(150, 2.0, "medium", ["地道口味", "高性价比"])),
    EvalCase("BZ03", "商务宴请", _cs(200, 3.0, "low", ["本地特色", "必吃清单", "有面子"])),
    EvalCase("BZ04", "商务宴请", _cs(250, 2.5, "low", ["高端大气", "商务接待"]), "18:00"),
    EvalCase("BZ05", "商务宴请", _cs(100, 2.0, "low", ["安静环境", "慢节奏"])),
    EvalCase("BZ06", "商务宴请", _cs(200, 4.0, "high", ["氛围感", "户外", "喝酒撸串"])),
    EvalCase("BZ07", "商务宴请", _cs(350, 3.0, "low", ["高端大气", "有面子"]), "19:00"),
    # ── 生日聚会 (6 cases) ────────────────────────────────────────────────────
    EvalCase("BD01", "生日聚会", _cs(150, 4.0, "high", ["必吃清单", "排队也值"])),
    EvalCase("BD02", "生日聚会", _cs(250, 2.0, "low", ["精致体验", "仪式感", "氛围感"])),
    EvalCase("BD03", "生日聚会", _cs(180, 5.0, "medium", ["出片", "网红地标", "艺术"])),
    EvalCase("BD04", "生日聚会", _cs(150, 3.0, "high", ["亲子友好", "儿童乐园"], (5, 10))),
    EvalCase("BD05", "生日聚会", _cs(200, 6.0, "high", ["不费脑", "出片"])),
    EvalCase("BD06", "生日聚会", _cs(100, 3.0, "medium", ["高性价比", "地道口味"])),
]

assert len(TEST_CASES) == 20  # noqa: S101


# ── Evaluation engine ─────────────────────────────────────────────────────────


async def _run_plan(case: EvalCase) -> Itinerary | None:
    """Run the ReAct loop with fault injection disabled; return the itinerary."""
    session_id = str(uuid.uuid4())
    itinerary: Itinerary | None = None
    with _no_faults():
        gen = await react_loop.run(case.constraint_set, session_id, case.start_time)
        async for event in gen:
            if event.get("type") == "done" and "itinerary" in event:
                itinerary = Itinerary(**event["itinerary"])
    return itinerary


def _score_d1(case: EvalCase, itin: Itinerary) -> float:
    """D1 约束满足率: node count, types, and per-capita budget alignment."""
    checks: list[bool] = []
    # 1. Node count is 3 or 4
    checks.append(3 <= len(itin.nodes) <= 4)
    # 2. Matches duration rule: < 6 h → 3 nodes, ≥ 6 h → 4 nodes
    expected = 3 if case.constraint_set.hard.total_duration < 6.0 else 4
    checks.append(len(itin.nodes) == expected)
    # 3. All node types are valid strings
    checks.append(all(n.node_type in ("restaurant", "venue") for n in itin.nodes))
    # 4. Mixed itinerary: at least one restaurant and one venue
    node_types = {n.node_type for n in itin.nodes}
    checks.append("restaurant" in node_types and "venue" in node_types)
    # 5. Budget: majority of nodes have per_capita within 2× soft cap
    cap = case.constraint_set.soft.per_capita * 2
    within = sum(1 for n in itin.nodes if n.per_capita <= cap)
    checks.append(within > len(itin.nodes) // 2)
    return sum(checks) / len(checks)


def _score_d2(itin: Itinerary) -> float:
    """D2 时间合法性: format, start<end, duration consistency, no timeline gaps."""
    checks: list[bool] = []
    for node in itin.nodes:
        try:
            s = _hhmm_to_min(node.start_time)
            e = _hhmm_to_min(node.end_time)
        except (ValueError, AttributeError):
            checks.extend([False, False])
            continue
        checks.append(s < e)  # start strictly before end
        checks.append(abs((e - s) - node.duration_min) <= 5)  # ±5 min rounding
    # Chronological: end + transit == next start (allow 2 min rounding)
    for i in range(len(itin.nodes) - 1):
        curr, nxt = itin.nodes[i], itin.nodes[i + 1]
        end_min = _hhmm_to_min(curr.end_time)
        next_start = _hhmm_to_min(nxt.start_time)
        transit = curr.transit_to_next.duration_min if curr.transit_to_next else 0
        checks.append(abs(end_min + transit - next_start) <= 2)
    return sum(checks) / len(checks) if checks else 0.0


async def _score_d3(itin: Itinerary) -> float:
    """D3 执行完成率: call book_node for each node with no fault injection."""
    if not itin.nodes:
        return 0.0
    _eb_mod._idempotency_store.clear()
    key = str(uuid.uuid4())
    successes = 0
    with _no_faults():
        for node in itin.nodes:
            try:
                rec = await book_node(node, key)
                if rec.status == "success":
                    successes += 1
            except Exception:  # noqa: BLE001
                pass
    return successes / len(itin.nodes)


async def _score_d4(case: EvalCase, itin: Itinerary) -> float:
    """D4 降级触发率: route_fault must return a valid FaultResult, never raise."""
    if not itin.nodes:
        return 0.0
    exc = ToolFaultError(
        "无座/无票: trigger partial_replan for level 1 replacement"
    )
    ctx = FaultContext(
        failed_node=itin.nodes[0],
        node_index=0,
        itinerary=itin,
        constraint_set=case.constraint_set,
        original_error=str(exc),
    )
    try:
        with _no_faults():
            result = await route_fault(exc, ctx)
        if result.level not in set(DegradationLevel):
            return 0.0
        return 1.0 if result.message else 0.0
    except Exception:  # noqa: BLE001
        return 0.0


async def _evaluate(case: EvalCase) -> ScoreResult:
    """Run all 4 dimensions for one test case."""
    itin = await _run_plan(case)
    if itin is None:
        return ScoreResult(case_id=case.id, scenario=case.scenario,
                           d1=0.0, d2=0.0, d3=0.0, d4=0.0)
    return ScoreResult(
        case_id=case.id,
        scenario=case.scenario,
        d1=_score_d1(case, itin),
        d2=_score_d2(itin),
        d3=await _score_d3(itin),
        d4=await _score_d4(case, itin),
    )


# ── 20 parametrized test cases ────────────────────────────────────────────────


@pytest.mark.parametrize("case", TEST_CASES, ids=[c.id for c in TEST_CASES])
async def test_pass_at_1(case: EvalCase) -> None:
    """Each scenario must score ≥ 0.70 on the weighted 4-dimension rubric."""
    score = await _evaluate(case)
    assert score.overall >= PASS_THRESHOLD, (
        f"[{case.id}] {case.scenario}: overall={score.overall:.2f} < {PASS_THRESHOLD} | "
        f"D1={score.d1:.2f} D2={score.d2:.2f} D3={score.d3:.2f} D4={score.d4:.2f}"
    )


# ── Overall Pass@1 rate + report ──────────────────────────────────────────────


async def test_pass_at_1_overall_rate() -> None:
    """Assert overall Pass@1 ≥ 85% and print the full evaluation report."""
    results = [await _evaluate(c) for c in TEST_CASES]

    by_scenario: dict[str, list[ScoreResult]] = {}
    for r in results:
        by_scenario.setdefault(r.scenario, []).append(r)

    passed = sum(1 for r in results if r.passed)
    rate = passed / len(results)

    print(f"\n{'═' * 60}")
    print("  Pass@1 自动化评测报告（F10）")
    print(f"{'═' * 60}")
    for scenario, rs in sorted(by_scenario.items()):
        sc_n = sum(1 for r in rs if r.passed)
        print(f"\n  【{scenario}】{sc_n}/{len(rs)} 通过")
        for r in rs:
            flag = "✅" if r.passed else "❌"
            print(
                f"    {flag} [{r.case_id}] {r.overall:.2f} | "
                f"D1={r.d1:.2f} D2={r.d2:.2f} "
                f"D3={r.d3:.2f} D4={r.d4:.2f}"
            )
    print(f"\n{'─' * 60}")
    print(f"  总体 Pass@1 = {rate:.1%}  ({passed}/{len(results)})")
    target_str = f"{TARGET_PASS_RATE:.1%}"
    status = "✅ 达标" if rate >= TARGET_PASS_RATE else "❌ 未达标"
    print(f"  目标 ≥ {target_str}  {status}")
    print(f"{'═' * 60}\n")

    assert rate >= TARGET_PASS_RATE, (
        f"Pass@1 = {rate:.1%} ({passed}/{len(results)}) 低于目标 {TARGET_PASS_RATE:.1%}"
    )
