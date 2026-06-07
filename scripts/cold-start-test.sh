#!/usr/bin/env bash
# =============================================================================
# scripts/cold-start-test.sh
# 冷启动测试 · 检验仓库质量
#
# 用途：
#   检验仓库质量的方法：模拟一个全新的 Agent 会话，
#   只看仓库内容，检验它能否回答五个基本问题。
#
#   如果它答不上来，说明地图上有空白——知识可见性缺口存在。
#
# 五个基本问题：
#   [1] 这是什么系统？         → AGENTS.md / README
#   [2] 怎么组织的？           → ARCHITECTURE.md / 模块文档
#   [3] 怎么跑？               → Makefile / init.sh
#   [4] 怎么验证？             → make check 命令
#   [5] 现在做到哪了？         → PROGRESS.md / 功能清单
#
# 运行方式：
#   bash scripts/cold-start-test.sh
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

GAPS=0

pass() { echo -e "  ${PASS} $1"; }
fail() { echo -e "  ${FAIL} $1"; GAPS=$((GAPS + 1)); }
warn() { echo -e "  ${WARN} $1"; }

echo ""
echo -e "${BLUE}════════════════════════════════════════${NC}"
echo -e "${BLUE}  冷启动测试 · 检验知识可见性${NC}"
echo -e "${BLUE}════════════════════════════════════════${NC}"
echo ""
echo "  模拟全新 Agent 会话：只看仓库内容，能否回答五个基本问题？"
echo ""

# ----------------------------------------------------------------------------
# Q1: 这是什么系统？
# ----------------------------------------------------------------------------
echo -e "${BLUE}── [Q1] 这是什么系统？（AGENTS.md / README）──${NC}"

if [ -f "AGENTS.md" ]; then
    pass "AGENTS.md 存在"
    # 检查是否有项目概览
    if grep -q "项目概览\|Project Overview\|## 概述" AGENTS.md 2>/dev/null; then
        pass "AGENTS.md 包含项目概览"
    else
        warn "AGENTS.md 缺少项目概览章节"
    fi
else
    fail "AGENTS.md 不存在 — 新 Agent 无法了解这是什么系统"
fi

if [ -f "README.md" ]; then
    pass "README.md 存在"
else
    warn "README.md 不存在（建议创建面向人类开发者的 README）"
fi

# ----------------------------------------------------------------------------
# Q2: 怎么组织的？
# ----------------------------------------------------------------------------
echo ""
echo -e "${BLUE}── [Q2] 怎么组织的？（ARCHITECTURE.md / 模块文档）──${NC}"

if [ -f "ARCHITECTURE.md" ]; then
    pass "ARCHITECTURE.md 存在"
else
    warn "ARCHITECTURE.md 不存在 — 建议创建架构总览文档"
fi

# 检查核心模块目录
for dir in agent/ agent/core agent/tools agent/modules; do
    if [ -d "$dir" ]; then
        pass "${dir} 存在"
    else
        warn "${dir} 不存在（待实现）"
    fi
done

# ----------------------------------------------------------------------------
# Q3: 怎么跑？
# ----------------------------------------------------------------------------
echo ""
echo -e "${BLUE}── [Q3] 怎么跑？（Makefile / init.sh）──${NC}"

if [ -f "Makefile" ]; then
    pass "Makefile 存在"
    for target in setup dev test check; do
        if grep -q "^${target}:" Makefile 2>/dev/null; then
            pass "  make ${target} 已定义"
        else
            fail "  make ${target} 未定义"
        fi
    done
else
    fail "Makefile 不存在 — 新 Agent 不知道怎么启动项目"
fi

if [ -f "scripts/init.sh" ]; then
    pass "scripts/init.sh 存在"
else
    warn "scripts/init.sh 不存在（建议创建初始化脚本）"
fi

# ----------------------------------------------------------------------------
# Q4: 怎么验证？
# ----------------------------------------------------------------------------
echo ""
echo -e "${BLUE}── [Q4] 怎么验证？（make check / 测试命令）──${NC}"

if [ -f "AGENTS.md" ] && grep -q "make check" AGENTS.md 2>/dev/null; then
    pass "AGENTS.md 中包含验证命令（make check）"
else
    fail "AGENTS.md 中未找到验证命令 — 新 Agent 不知道怎么验证自己的工作"
fi

# 检查测试目录（tests/ 为约定路径，对应 features.md 中的验证命令）
if [ -d "tests/" ]; then
    TEST_COUNT=$(find tests/ -name "test_*.py" 2>/dev/null | wc -l | tr -d ' ')
    pass "tests/ 存在（${TEST_COUNT} 个测试文件）"
else
    warn "tests/ 目录不存在（待创建，功能开发阶段补充）"
fi

# ----------------------------------------------------------------------------
# Q5: 现在做到哪了？
# ----------------------------------------------------------------------------
echo ""
echo -e "${BLUE}── [Q5] 现在做到哪了？（PROGRESS.md / 功能清单）──${NC}"

if [ -f "PROGRESS.md" ]; then
    pass "PROGRESS.md 存在"
    if grep -q "## 当前状态\|## Current Status" PROGRESS.md 2>/dev/null; then
        pass "PROGRESS.md 包含当前状态"
    else
        warn "PROGRESS.md 缺少当前状态章节"
    fi
    if grep -q "## 下一步\|## Next Steps" PROGRESS.md 2>/dev/null; then
        pass "PROGRESS.md 包含下一步"
    else
        warn "PROGRESS.md 缺少下一步章节"
    fi
else
    fail "PROGRESS.md 不存在 — 新 Agent 无法了解当前进度"
fi

if [ -f "docs/features.md" ]; then
    TOTAL=$(grep -c "^### F" docs/features.md 2>/dev/null || echo 0)
    PASSING=$(grep -c "passing" docs/features.md 2>/dev/null || echo 0)
    NOT_STARTED=$(grep -c "not_started" docs/features.md 2>/dev/null || echo 0)
    pass "docs/features.md 存在（共 ${TOTAL} 个功能，${PASSING} 个完成，${NOT_STARTED} 个待开始）"
else
    fail "docs/features.md 不存在 — 新 Agent 不知道该做什么"
fi

# ----------------------------------------------------------------------------
# 汇总
# ----------------------------------------------------------------------------
echo ""
echo -e "${BLUE}════════════════════════════════════════${NC}"
echo ""

if [ "$GAPS" -eq 0 ]; then
    echo -e "${GREEN}  ✅ 冷启动测试通过 · 知识可见性良好${NC}"
    echo ""
    echo "  全新 Agent 会话能够回答所有 5 个基本问题。"
    echo "  地图上没有空白。"
else
    echo -e "${RED}  ❌ 发现 ${GAPS} 个知识可见性缺口${NC}"
    echo ""
    echo "  缺口越大，Agent 失败的概率越高。"
    echo "  不在仓库里的知识，对 Agent 来说等于不存在。"
    echo ""
    echo "  建议：按照上面的 ❌ 项逐一补充文档。"
fi

echo -e "${BLUE}════════════════════════════════════════${NC}"
echo ""

exit $GAPS
