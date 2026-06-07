# =============================================================================
# Harness Engineering · 标准 Makefile
# 反馈子系统（出菜检查口）的核心入口
#
# 用法速查：
#   make setup    安装依赖，初始化环境
#   make dev      启动开发服务器
#   make test     运行测试
#   make check    ★ 完整验证（测试 + lint + 类型检查 + 构建）
#   make clean    清理临时文件
#   make init     初始化阶段：验证自举契约
# =============================================================================

# ----------------------------------------------------------------------------
# 项目配置
# ----------------------------------------------------------------------------
PROJECT_NAME   := meituan-local-agent
PYTHON_VERSION := 3.11             # 与 .python-version 保持一致
NODE_VERSION   := 20               # 与 .nvmrc 保持一致

# Python 相关路径
SRC_DIR        := agent
TEST_DIR       := tests
VENV_DIR       := .venv
PYTHON         := $(VENV_DIR)/bin/python
PIP            := $(VENV_DIR)/bin/pip

# Node.js 相关（前端）
PKG_MANAGER    := npm
FRONTEND_DIR   := frontend

# CI 环境检测
CI             ?= false

.DEFAULT_GOAL  := help
.PHONY: help setup dev test lint typecheck build check clean init verify-bootstrap \
        update-progress harness-audit test-unit test-integration test-e2e \
        test-coverage test-pass-at-1 lint-fix shell

# ----------------------------------------------------------------------------
# help · 打印所有可用目标
# ----------------------------------------------------------------------------
help:
	@echo ""
	@echo "$(PROJECT_NAME) · Makefile 命令速查"
	@echo "============================================"
	@echo ""
	@echo "  环境管理："
	@echo "    make setup               安装所有依赖（Python + Node），初始化开发环境"
	@echo "    make clean               清理构建产物和临时文件"
	@echo ""
	@echo "  开发："
	@echo "    make dev                 启动后端开发服务器（port 8000，热重载）"
	@echo "    make shell               进入 Python 虚拟环境 shell"
	@echo ""
	@echo "  验证（反馈子系统）："
	@echo "    make test                运行完整测试套件（unit + integration）"
	@echo "    make test-unit           只运行单元测试"
	@echo "    make test-integration    只运行集成测试"
	@echo "    make test-e2e            只运行端到端测试"
	@echo "    make test-pass-at-1      运行 Pass@1 自动化评测框架（F10）"
	@echo "    make lint                运行 Lint 检查（ruff）"
	@echo "    make lint-fix            自动修复 Lint 问题"
	@echo "    make typecheck           运行类型检查（mypy --strict）"
	@echo "    make build               构建前端产物"
	@echo "    make check               ★ 完整验证（lint + typecheck + test + build）"
	@echo ""
	@echo "  Harness 维护："
	@echo "    make init                初始化阶段：验证自举契约"
	@echo "    make harness-audit       审计 harness 各子系统健康状态"
	@echo "    make update-progress     运行会话退出检查"
	@echo ""

# ----------------------------------------------------------------------------
# setup · 环境子系统（灶台）
# 安装依赖，锁定版本，确保环境可重现
# ----------------------------------------------------------------------------
setup:
	@echo "▶ [环境子系统] 安装依赖..."
	@python$(PYTHON_VERSION) -m venv $(VENV_DIR)
	@$(PIP) install --upgrade pip
	@$(PIP) install -e ".[dev]"
	@echo "✅ Python 环境初始化完成"
	@if command -v node >/dev/null 2>&1 && [ -d $(FRONTEND_DIR) ]; then \
		echo "▶ 安装前端依赖..."; \
		cd $(FRONTEND_DIR) && $(PKG_MANAGER) ci; \
		echo "✅ Node.js 环境初始化完成"; \
	fi
	@cp -n .env.example .env 2>/dev/null || true
	@echo ""
	@echo "✅ setup 完成。运行 'make check' 验证环境。"

# ----------------------------------------------------------------------------
# dev · 启动开发服务器
# ----------------------------------------------------------------------------
dev:
	@echo "▶ 启动后端开发服务器 (http://localhost:8000)..."
	@echo "   前端：cd $(FRONTEND_DIR) && $(PKG_MANAGER) run dev"
	@echo "   API 文档：http://localhost:8000/docs"
	@$(PYTHON) -m uvicorn agent.main:app --reload --port 8000

shell:
	@$(VENV_DIR)/bin/python

# ----------------------------------------------------------------------------
# test · 测试套件（分层）
# ----------------------------------------------------------------------------
test: test-unit test-integration
	@echo "✅ 所有测试通过"

test-unit:
	@echo "▶ [第二层] 运行单元测试..."
	@$(PYTHON) -m pytest $(TEST_DIR)/unit/ -x -v --tb=short

test-integration:
	@echo "▶ [第二层] 运行集成测试..."
	@$(PYTHON) -m pytest $(TEST_DIR)/integration/ -x -v --tb=short

test-e2e:
	@echo "▶ [第三层] 运行端到端测试..."
	@$(PYTHON) -m pytest $(TEST_DIR)/e2e/ -x -v --tb=long

test-pass-at-1:
	@echo "▶ [F10] Pass@1 自动化评测框架（20 条测例，目标 ≥85%）..."
	@$(PYTHON) -m pytest $(TEST_DIR)/test_pass_at_1.py -v --tb=short

test-coverage:
	@echo "▶ 生成测试覆盖率报告..."
	@$(PYTHON) -m pytest $(TEST_DIR)/ --cov=$(SRC_DIR) --cov-report=html --cov-report=term-missing

# ----------------------------------------------------------------------------
# lint · Lint 检查（第一层）
# ----------------------------------------------------------------------------
lint:
	@echo "▶ [第一层] 运行 Lint 检查..."
	@$(VENV_DIR)/bin/ruff check $(SRC_DIR)/

lint-fix:
	@echo "▶ 自动修复 Lint 问题..."
	@$(VENV_DIR)/bin/ruff check --fix $(SRC_DIR)/
	@$(VENV_DIR)/bin/ruff format $(SRC_DIR)/

# ----------------------------------------------------------------------------
# typecheck · 类型检查（第一层）
# ----------------------------------------------------------------------------
typecheck:
	@echo "▶ [第一层] 运行类型检查..."
	@$(VENV_DIR)/bin/mypy $(SRC_DIR)/ --strict

# ----------------------------------------------------------------------------
# build · 构建
# ----------------------------------------------------------------------------
build:
	@echo "▶ 构建产物..."
	@if [ -d $(FRONTEND_DIR) ]; then \
		echo "▶ 构建前端..."; \
		cd $(FRONTEND_DIR) && $(PKG_MANAGER) run build && echo "✅ 前端构建完成"; \
	else \
		echo "⚠️  frontend/ 目录不存在，跳过前端构建（F11 完成后解锁）"; \
	fi
	@echo "✅ 构建完成"

# ----------------------------------------------------------------------------
# ★ check · 完整验证（反馈子系统的核心命令）
# 顺序：第一层（静态分析）→ 第二层（运行时）→ 第三层（系统级）
# 任何一层失败，立即停止
# ----------------------------------------------------------------------------
check:
	@echo ""
	@echo "════════════════════════════════════════"
	@echo "  ★ make check · 完整验证流水线"
	@echo "════════════════════════════════════════"
	@echo ""
	@echo "── 第一层：静态分析 ──"
	@$(MAKE) lint
	@$(MAKE) typecheck
	@echo ""
	@echo "── 第二层：运行时行为 ──"
	@$(MAKE) test
	@echo ""
	@echo "── 第三层：系统级确认 ──"
	@$(MAKE) test-e2e
	@echo ""
	@echo "── 构建验证 ──"
	@$(MAKE) build
	@echo ""
	@echo "════════════════════════════════════════"
	@echo "  ✅ make check 全部通过 · 仓库处于一致状态"
	@echo "════════════════════════════════════════"
	@echo ""

# ----------------------------------------------------------------------------
# init · 初始化阶段
# 验证自举契约：能启动、能测试、能看进度、能接手下一步
# 只做初始化，不写任何业务功能代码
# ----------------------------------------------------------------------------
init:
	@echo "▶ [初始化阶段] 验证自举契约..."
	@bash scripts/init.sh
	@echo ""
	@echo "自举契约验证："
	@echo "  [1/4] 环境能启动？"
	@$(MAKE) setup
	@echo "  [2/4] 测试框架可用？"
	@$(MAKE) test-unit 2>/dev/null || (echo "❌ 测试框架未就绪，请先配置" && exit 1)
	@echo "  [3/4] 进度文件存在？"
	@test -f PROGRESS.md || (echo "❌ PROGRESS.md 不存在" && exit 1)
	@echo "  [4/4] 功能清单存在？"
	@test -f docs/features.md || (echo "❌ docs/features.md 不存在" && exit 1)
	@echo ""
	@echo "✅ 自举契约验证通过 · 可以开始功能实现阶段"

# ----------------------------------------------------------------------------
# clean · 清理临时文件（幂等操作）
# ----------------------------------------------------------------------------
clean:
	@echo "▶ 清理临时文件..."
	@find . -type f -name "*.pyc" -delete
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.log" -path "*/logs/*" -delete 2>/dev/null || true
	@rm -rf dist/ build/ htmlcov/ .coverage logs/ 2>/dev/null || true
	@if [ -d $(FRONTEND_DIR)/dist ]; then rm -rf $(FRONTEND_DIR)/dist; fi
	@echo "✅ 清理完成"

# ----------------------------------------------------------------------------
# harness-audit · Harness 健康审计
# 检查五子系统是否齐备，定期运行以防止 harness 腐化
# ----------------------------------------------------------------------------
harness-audit:
	@echo ""
	@echo "▶ Harness 健康审计"
	@echo "────────────────────────────────────────"
	@echo "子系统检查："
	@echo ""
	@echo "[1] 指令子系统（菜谱架）"
	@test -f AGENTS.md    && echo "  ✅ AGENTS.md" || echo "  ❌ AGENTS.md 缺失"
	@test -f CLAUDE.md    && echo "  ✅ CLAUDE.md" || echo "  ⚠️  CLAUDE.md 缺失（可选）"
	@echo ""
	@echo "[2] 状态子系统（备菜台）"
	@test -f PROGRESS.md      && echo "  ✅ PROGRESS.md" || echo "  ❌ PROGRESS.md 缺失"
	@test -f DECISIONS.md     && echo "  ✅ DECISIONS.md" || echo "  ❌ DECISIONS.md 缺失"
	@test -f docs/features.md && echo "  ✅ docs/features.md" || echo "  ❌ docs/features.md 缺失"
	@echo ""
	@echo "[3] 环境子系统（灶台）"
	@test -f pyproject.toml  && echo "  ✅ pyproject.toml" || echo "  ❌ pyproject.toml 缺失"
	@test -f .python-version && echo "  ✅ .python-version ($(shell cat .python-version 2>/dev/null))" || echo "  ⚠️  .python-version 缺失"
	@test -f .nvmrc          && echo "  ✅ .nvmrc ($(shell cat .nvmrc 2>/dev/null))" || echo "  ⚠️  .nvmrc 缺失"
	@echo ""
	@echo "[4] 反馈子系统（出菜检查口）"
	@test -f Makefile && grep -q "make check" Makefile && echo "  ✅ make check 已定义" || echo "  ❌ make check 未定义"
	@echo ""
	@echo "[5] 工具子系统（刀具架）"
	@test -d scripts/ && echo "  ✅ scripts/ 目录存在" || echo "  ⚠️  scripts/ 目录缺失"
	@echo ""
	@echo "[6] 源码结构"
	@test -d $(SRC_DIR)/      && echo "  ✅ $(SRC_DIR)/ 目录存在" || echo "  ⚠️  $(SRC_DIR)/ 目录待创建"
	@test -d $(TEST_DIR)/     && echo "  ✅ $(TEST_DIR)/ 目录存在" || echo "  ⚠️  $(TEST_DIR)/ 目录待创建"
	@test -d $(FRONTEND_DIR)/ && echo "  ✅ $(FRONTEND_DIR)/ 目录存在" || echo "  ⚠️  $(FRONTEND_DIR)/ 目录待创建（F11）"
	@echo ""
	@echo "────────────────────────────────────────"

# ----------------------------------------------------------------------------
# update-progress · 会话退出辅助
# 提示 Agent 在退出前执行的检查项
# ----------------------------------------------------------------------------
update-progress:
	@echo ""
	@echo "▶ 会话退出检查清单"
	@echo "────────────────────────────────────────"
	@$(MAKE) check && echo "✅ make check 通过" || echo "❌ make check 失败，请先修复"
	@echo ""
	@echo "请手动确认："
	@echo "  [ ] PROGRESS.md 已更新（当前状态/已知问题/下一步）"
	@echo "  [ ] docs/features.md 功能清单已更新"
	@echo "  [ ] 无调试代码残留（console.log / debugger / 临时 TODO）"
	@echo "  [ ] git status 干净，所有工作已提交"
	@echo ""
