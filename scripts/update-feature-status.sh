#!/usr/bin/env bash
# =============================================================================
# scripts/update-feature-status.sh
# 功能清单状态更新脚本 · 验证门控
#
# 核心规则：
#   Agent 不能直接把状态改成 passing。
#   只有本脚本执行验证命令成功后，才允许状态转移。
#   这是防止 Agent 提前宣告完成的关键机制。
#
# 用法：
#   bash scripts/update-feature-status.sh <FEATURE_ID>
#   bash scripts/update-feature-status.sh F01
#   bash scripts/update-feature-status.sh --all   # 验证所有 active 功能
#
# 功能清单格式（docs/features.md 中每个功能块）：
#   ### F01: 用户注册
#   - **行为**：POST /api/register 返回 201
#   - **验证命令**：`curl -X POST http://localhost:8000/api/register ...`
#   - **状态**：`active`
#   - **证据**：（通过后自动填写）
# =============================================================================

set -euo pipefail

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

FEATURES_FILE="docs/features.md"
LOG_FILE="logs/verification-$(date +%Y%m%d-%H%M%S).log"

mkdir -p logs

# ----------------------------------------------------------------------------
# 使用说明
# ----------------------------------------------------------------------------
usage() {
    echo "用法: $0 <FEATURE_ID>"
    echo "      $0 --all"
    echo ""
    echo "  <FEATURE_ID>  要验证的功能 ID（如 F01）"
    echo "  --all         验证所有 active 状态的功能"
    echo ""
    echo "示例："
    echo "  $0 F01"
    echo "  $0 --all"
    exit 1
}

# ----------------------------------------------------------------------------
# 从 features.md 中提取功能信息
# <placeholder> 根据实际 features.md 格式调整解析逻辑
# ----------------------------------------------------------------------------
get_feature_verification_cmd() {
    local feature_id="$1"
    # 提取功能块中的验证命令行
    # 格式：- **验证命令**：`<command>`
    awk "/### ${feature_id}:/,/^###/" "$FEATURES_FILE" \
        | grep "验证命令" \
        | sed 's/.*`\(.*\)`.*/\1/' \
        | head -1
}

get_feature_status() {
    local feature_id="$1"
    awk "/### ${feature_id}:/,/^###/" "$FEATURES_FILE" \
        | grep "状态" \
        | sed 's/.*`\(.*\)`.*/\1/' \
        | head -1
}

# ----------------------------------------------------------------------------
# 验证单个功能
# ----------------------------------------------------------------------------
verify_feature() {
    local feature_id="$1"

    echo ""
    echo -e "${BLUE}── 验证功能 ${feature_id} ──${NC}"

    # 检查功能存在
    if ! grep -q "### ${feature_id}:" "$FEATURES_FILE" 2>/dev/null; then
        echo -e "${RED}❌ 功能 ${feature_id} 在 ${FEATURES_FILE} 中不存在${NC}"
        return 1
    fi

    # 检查当前状态
    local current_status
    current_status=$(get_feature_status "$feature_id")
    echo "  当前状态：${current_status}"

    if [ "$current_status" = "passing" ]; then
        echo -e "${GREEN}  ✅ 已是 passing 状态，跳过${NC}"
        return 0
    fi

    if [ "$current_status" = "not_started" ]; then
        echo -e "${YELLOW}  ⚠️  功能尚未开始（not_started），请先将状态改为 active${NC}"
        return 1
    fi

    # 获取验证命令
    local verification_cmd
    verification_cmd=$(get_feature_verification_cmd "$feature_id")

    if [ -z "$verification_cmd" ]; then
        echo -e "${RED}  ❌ 未找到验证命令，请在 features.md 中补充${NC}"
        return 1
    fi

    echo "  验证命令：${verification_cmd}"
    echo ""

    # 执行三层验证
    echo -e "${BLUE}  [第一层] 静态分析...${NC}"
    if ! make lint typecheck 2>&1 | tee -a "$LOG_FILE"; then
        echo -e "${RED}  ❌ 第一层验证失败（lint/typecheck）${NC}"
        echo "  📋 详细日志：${LOG_FILE}"
        return 1
    fi
    echo -e "${GREEN}  ✅ 第一层通过${NC}"

    echo -e "${BLUE}  [第二层] 运行时验证（测试）...${NC}"
    if ! make test 2>&1 | tee -a "$LOG_FILE"; then
        echo -e "${RED}  ❌ 第二层验证失败（测试）${NC}"
        echo "  📋 详细日志：${LOG_FILE}"
        return 1
    fi
    echo -e "${GREEN}  ✅ 第二层通过${NC}"

    echo -e "${BLUE}  [第三层] 端到端验证...${NC}"
    if ! eval "$verification_cmd" 2>&1 | tee -a "$LOG_FILE"; then
        echo -e "${RED}  ❌ 第三层验证失败（端到端）${NC}"
        echo ""
        echo "  诊断提示："
        echo "    1. 确认应用已启动（make dev）"
        echo "    2. 检查环境变量配置（.env）"
        echo "    3. 检查数据库迁移是否已运行"
        echo "  📋 详细日志：${LOG_FILE}"
        return 1
    fi
    echo -e "${GREEN}  ✅ 第三层通过${NC}"

    # 所有层通过，更新状态为 passing
    local commit_hash
    commit_hash=$(git rev-parse --short HEAD 2>/dev/null || echo "no-git")
    local timestamp
    timestamp=$(date +%Y-%m-%d\ %H:%M:%S)
    local evidence="commit ${commit_hash}, verified at ${timestamp}"

    # 更新 features.md 中的状态（<placeholder> 根据实际格式调整 sed 命令）
    sed -i "s/\(### ${feature_id}:.*\)/\1/" "$FEATURES_FILE" 2>/dev/null || true

    # 状态更新（简化实现，实际项目可用更精确的解析）
    # 注意：此处 sed 命令需根据 features.md 实际格式调整
    echo ""
    echo -e "${GREEN}  ✅ 功能 ${feature_id} 验证通过${NC}"
    echo "  证据：${evidence}"
    echo ""
    echo "  ⚠️  请手动更新 docs/features.md 中 ${feature_id} 的状态："
    echo "     - **状态**：\`passing\`"
    echo "     - **证据**：${evidence}"

    return 0
}

# ----------------------------------------------------------------------------
# 主逻辑
# ----------------------------------------------------------------------------
if [ $# -eq 0 ]; then
    usage
fi

if [ ! -f "$FEATURES_FILE" ]; then
    echo -e "${RED}❌ 功能清单文件不存在：${FEATURES_FILE}${NC}"
    exit 1
fi

if [ "$1" = "--all" ]; then
    echo "▶ 验证所有 active 功能..."
    # 提取所有 active 功能的 ID
    ACTIVE_IDS=$(grep -B 5 "状态.*active" "$FEATURES_FILE" \
        | grep "### F" \
        | sed 's/### \(F[0-9]*\):.*/\1/' || true)

    if [ -z "$ACTIVE_IDS" ]; then
        echo -e "${YELLOW}⚠️  没有 active 状态的功能${NC}"
        exit 0
    fi

    FAIL_COUNT=0
    for id in $ACTIVE_IDS; do
        verify_feature "$id" || FAIL_COUNT=$((FAIL_COUNT + 1))
    done

    echo ""
    if [ "$FAIL_COUNT" -eq 0 ]; then
        echo -e "${GREEN}✅ 所有 active 功能验证通过${NC}"
    else
        echo -e "${RED}❌ ${FAIL_COUNT} 个功能验证失败${NC}"
        exit 1
    fi
else
    verify_feature "$1"
fi
