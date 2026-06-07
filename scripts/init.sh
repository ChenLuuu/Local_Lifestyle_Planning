#!/usr/bin/env bash
# =============================================================================
# scripts/init.sh
# 初始化阶段脚本 · 验证自举契约
#
# 用途：
#   在项目第一次启动或新 Agent 会话开始时运行。
#   只做初始化，不写任何业务功能代码。
#   输出是基础设施，不是功能代码。
#
# 自举契约四条件（缺一不可）：
#   [1] 环境能启动
#   [2] 测试框架可用（至少一个示例测试通过）
#   [3] 能看进度（PROGRESS.md 存在）
#   [4] 能接手下一步（features.md 存在且有 not_started 条目）
#
# 运行方式：
#   bash scripts/init.sh
#   make init
# =============================================================================

set -euo pipefail

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

PASS="${GREEN}✅${NC}"
FAIL="${RED}❌${NC}"
WARN="${YELLOW}⚠️ ${NC}"

echo ""
echo -e "${BLUE}════════════════════════════════════════${NC}"
echo -e "${BLUE}  初始化阶段 · 验证自举契约${NC}"
echo -e "${BLUE}════════════════════════════════════════${NC}"
echo ""

ERRORS=0

# ----------------------------------------------------------------------------
# 辅助函数
# ----------------------------------------------------------------------------
check_pass() { echo -e "  ${PASS} $1"; }
check_fail() { echo -e "  ${FAIL} $1"; ERRORS=$((ERRORS + 1)); }
check_warn() { echo -e "  ${WARN} $1"; }
section()    { echo ""; echo -e "${BLUE}── $1 ──${NC}"; }

# ----------------------------------------------------------------------------
# [1] 检查运行时环境
# ----------------------------------------------------------------------------
section "检查运行时环境"

# <placeholder> 根据项目类型选择 Python 或 Node.js 检查

# Python 环境检查
if command -v python3 &>/dev/null; then
    PYTHON_VER=$(python3 --version 2>&1)
    check_pass "Python 可用：${PYTHON_VER}"
else
    check_fail "Python 3 未找到，请安装 Python"
fi

# 检查 .python-version 文件（如存在）
if [ -f ".python-version" ]; then
    REQUIRED_VER=$(cat .python-version)
    check_pass ".python-version 存在：${REQUIRED_VER}"
else
    check_warn ".python-version 不存在（建议创建以锁定版本）"
fi

# Node.js 检查（如使用，取消注释）
# if command -v node &>/dev/null; then
#     NODE_VER=$(node --version)
#     check_pass "Node.js 可用：${NODE_VER}"
#     if [ -f ".nvmrc" ]; then
#         REQUIRED_NODE=$(cat .nvmrc)
#         check_pass ".nvmrc 存在：${REQUIRED_NODE}"
#     else
#         check_warn ".nvmrc 不存在（建议创建以锁定版本）"
#     fi
# else
#     check_fail "Node.js 未找到，请安装或使用 nvm"
# fi

# ----------------------------------------------------------------------------
# [2] 检查依赖配置文件
# ----------------------------------------------------------------------------
section "检查依赖配置（环境子系统）"

if [ -f "pyproject.toml" ]; then
    check_pass "pyproject.toml 存在"
elif [ -f "package.json" ]; then
    check_pass "package.json 存在"
else
    check_fail "依赖配置文件缺失（需要 pyproject.toml 或 package.json）"
fi

# ----------------------------------------------------------------------------
# [3] 检查 Harness 核心文件
# ----------------------------------------------------------------------------
section "检查指令子系统（菜谱架）"

for f in AGENTS.md CLAUDE.md; do
    if [ -f "$f" ]; then
        check_pass "$f 存在"
        # 检查关键章节是否存在
        if grep -q "make check" "$f" 2>/dev/null; then
            check_pass "  └─ 包含 make check 验证命令"
        else
            check_warn "  └─ 未找到 make check 命令，建议补充"
        fi
    else
        check_warn "$f 不存在（AGENTS.md 是必需的，CLAUDE.md 可选）"
    fi
done

# ----------------------------------------------------------------------------
# [4] 检查状态子系统
# ----------------------------------------------------------------------------
section "检查状态子系统（备菜台）"

if [ -f "PROGRESS.md" ]; then
    check_pass "PROGRESS.md 存在"
else
    check_fail "PROGRESS.md 不存在"
    echo "         正在创建空模板..."
    cat > PROGRESS.md << 'EOF'
# 项目进度

## 当前状态
- 最新 commit: （待填写）
- 测试状态：（待填写）
- Lint：（待填写）

## 已完成
（暂无）

## 进行中
（暂无）

## 已知问题 / 阻塞
（暂无）

## 下一步
1. 完成初始化阶段
2. 从 docs/features.md 选择第一个功能开始
EOF
    check_pass "PROGRESS.md 空模板已创建"
fi

if [ -f "DECISIONS.md" ]; then
    check_pass "DECISIONS.md 存在"
else
    check_warn "DECISIONS.md 不存在（建议创建以记录技术决策）"
fi

# ----------------------------------------------------------------------------
# [5] 检查功能清单
# ----------------------------------------------------------------------------
section "检查功能清单"

if [ -f "docs/features.md" ]; then
    check_pass "docs/features.md 存在"
    NOT_STARTED_COUNT=$(grep -c "not_started" docs/features.md 2>/dev/null || echo 0)
    if [ "$NOT_STARTED_COUNT" -gt 0 ]; then
        check_pass "有 ${NOT_STARTED_COUNT} 个待开始的功能"
    else
        check_warn "没有 not_started 的功能，请检查功能清单"
    fi
else
    check_fail "docs/features.md 不存在"
fi

# ----------------------------------------------------------------------------
# [6] 检查 Makefile 验证命令
# ----------------------------------------------------------------------------
section "检查反馈子系统（出菜检查口）"

if [ -f "Makefile" ]; then
    check_pass "Makefile 存在"
    for target in setup test lint check; do
        if grep -q "^${target}:" Makefile 2>/dev/null; then
            check_pass "  └─ make ${target} 已定义"
        else
            check_fail "  └─ make ${target} 未定义"
        fi
    done
else
    check_fail "Makefile 不存在"
fi

# ----------------------------------------------------------------------------
# 汇总
# ----------------------------------------------------------------------------
echo ""
echo -e "${BLUE}════════════════════════════════════════${NC}"
if [ "$ERRORS" -eq 0 ]; then
    echo -e "${GREEN}  ✅ 自举契约验证通过（${ERRORS} 个错误）${NC}"
    echo -e "${GREEN}  可以开始功能实现阶段${NC}"
else
    echo -e "${RED}  ❌ 自举契约验证失败（${ERRORS} 个错误）${NC}"
    echo -e "${RED}  请修复以上问题后再开始功能实现${NC}"
fi
echo -e "${BLUE}════════════════════════════════════════${NC}"
echo ""

exit $ERRORS
