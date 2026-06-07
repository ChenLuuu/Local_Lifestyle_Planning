#!/usr/bin/env bash
# =============================================================================
# scripts/session-handoff.sh
# 会话交接脚本 · 每次会话结束前运行
#
# 用途：
#   自动执行会话退出检查清单，确保仓库处于清洁状态。
#   防止「以后再清理」的心理陷阱——熵增是默认状态。
#
# 清洁状态五个条件：
#   [1] 构建通过
#   [2] 测试通过
#   [3] 进度已记录（PROGRESS.md 最近已更新）
#   [4] 无过时工件（无调试代码残留）
#   [5] 启动路径可用
#
# 运行方式：
#   bash scripts/session-handoff.sh
#   make update-progress
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PASS="${GREEN}✅${NC}"
FAIL="${RED}❌${NC}"
WARN="${YELLOW}⚠️ ${NC}"

ERRORS=0
WARNINGS=0

pass()  { echo -e "  ${PASS} $1"; }
fail()  { echo -e "  ${FAIL} $1"; ERRORS=$((ERRORS + 1)); }
warn()  { echo -e "  ${WARN} $1"; WARNINGS=$((WARNINGS + 1)); }

echo ""
echo -e "${BLUE}════════════════════════════════════════${NC}"
echo -e "${BLUE}  会话交接检查 · 确保清洁状态${NC}"
echo -e "${BLUE}════════════════════════════════════════${NC}"

# ----------------------------------------------------------------------------
# [1] 构建检查
# ----------------------------------------------------------------------------
echo ""
echo -e "${BLUE}── [1/5] 构建检查 ──${NC}"
if make build 2>&1 | tail -5; then
    pass "构建通过"
else
    fail "构建失败 — 请先修复后再退出会话"
fi

# ----------------------------------------------------------------------------
# [2] 测试检查
# ----------------------------------------------------------------------------
echo ""
echo -e "${BLUE}── [2/5] 测试检查 ──${NC}"
if make test 2>&1 | tail -10; then
    pass "所有测试通过"
else
    fail "测试失败 — 不允许带着红色测试退出会话"
fi

# ----------------------------------------------------------------------------
# [3] 进度文件检查
# ----------------------------------------------------------------------------
echo ""
echo -e "${BLUE}── [3/5] 进度文件检查 ──${NC}"

if [ ! -f "PROGRESS.md" ]; then
    fail "PROGRESS.md 不存在"
else
    # 检查文件最近是否更新（24小时内）
    if [ "$(find PROGRESS.md -mmin -1440 2>/dev/null | wc -l)" -gt 0 ]; then
        pass "PROGRESS.md 已在 24 小时内更新"
    else
        warn "PROGRESS.md 超过 24 小时未更新，请确认进度信息是最新的"
    fi

    # 检查必要章节
    for section in "当前状态" "已完成" "下一步"; do
        if grep -q "## ${section}" PROGRESS.md; then
            pass "PROGRESS.md 包含「${section}」章节"
        else
            warn "PROGRESS.md 缺少「${section}」章节"
        fi
    done
fi

# 检查功能清单
if [ -f "docs/features.md" ]; then
    ACTIVE_COUNT=$(grep -c "state.*active" docs/features.md 2>/dev/null || echo 0)
    if [ "$ACTIVE_COUNT" -gt 1 ]; then
        warn "功能清单有 ${ACTIVE_COUNT} 个 active 功能（WIP > 1，建议保持 WIP=1）"
    else
        pass "功能清单 WIP 状态正常"
    fi
else
    warn "docs/features.md 不存在"
fi

# ----------------------------------------------------------------------------
# [4] 调试代码检查
# ----------------------------------------------------------------------------
echo ""
echo -e "${BLUE}── [4/5] 调试代码检查 ──${NC}"

# 检查常见调试代码残留
DEBUG_PATTERNS=(
    "console\.log"
    "debugger"
    "pdb\.set_trace"
    "print(\"DEBUG"
    "TODO.*临时"
    "FIXME.*临时"
)

FOUND_DEBUG=0
for pattern in "${DEBUG_PATTERNS[@]}"; do
    MATCHES=$(grep -rn "$pattern" agent/ frontend/src/ 2>/dev/null | grep -v ".pyc" || true)
    if [ -n "$MATCHES" ]; then
        warn "发现可能的调试代码：${pattern}"
        echo "$MATCHES" | head -3 | while read -r line; do
            echo "         $line"
        done
        FOUND_DEBUG=$((FOUND_DEBUG + 1))
    fi
done

if [ "$FOUND_DEBUG" -eq 0 ]; then
    pass "无调试代码残留"
fi

# 检查临时文件
TEMP_FILES=$(find . -name "*.tmp" -o -name "debug-*.log" -o -name "test-output-*.txt" \
    2>/dev/null | grep -v ".git" | grep -v "node_modules" || true)
if [ -n "$TEMP_FILES" ]; then
    warn "发现临时文件："
    echo "$TEMP_FILES" | while read -r f; do echo "         $f"; done
else
    pass "无临时文件残留"
fi

# ----------------------------------------------------------------------------
# [5] 启动路径检查
# ----------------------------------------------------------------------------
echo ""
echo -e "${BLUE}── [5/5] 启动路径检查 ──${NC}"

# 检查 make dev 目标存在
if grep -q "^dev:" Makefile 2>/dev/null; then
    pass "make dev 已定义"
else
    fail "make dev 未定义，启动路径不可用"
fi

# 检查 git 状态
if command -v git &>/dev/null && git rev-parse --git-dir &>/dev/null; then
    UNCOMMITTED=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')
    if [ "$UNCOMMITTED" -eq 0 ]; then
        pass "Git 工作区干净，所有变更已提交"
    else
        warn "有 ${UNCOMMITTED} 个未提交的文件，请确认是否需要提交"
        git status --short | head -10
    fi
fi

# ----------------------------------------------------------------------------
# 汇总报告
# ----------------------------------------------------------------------------
echo ""
echo -e "${BLUE}════════════════════════════════════════${NC}"
echo -e "  错误：${RED}${ERRORS}${NC}  警告：${YELLOW}${WARNINGS}${NC}"
echo ""

if [ "$ERRORS" -eq 0 ]; then
    echo -e "${GREEN}  ✅ 仓库处于清洁状态，可以安全结束会话${NC}"
    echo ""
    echo "  📝 建议在退出前运行："
    echo "     git add -A && git commit -m 'chore: session handoff - update progress'"
else
    echo -e "${RED}  ❌ 存在 ${ERRORS} 个错误，请修复后再结束会话${NC}"
    echo ""
    echo "  长期可靠性取决于操作纪律，不仅仅是单次运行的成功。"
    echo "  每个会话结束时的状态质量，直接决定下一个会话的效率。"
fi
echo -e "${BLUE}════════════════════════════════════════${NC}"
echo ""

exit $ERRORS
