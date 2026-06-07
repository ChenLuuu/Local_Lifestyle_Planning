# 本地生活规划 Agent

基于 ReAct 架构的美团本地场景短时活动规划与执行 Agent。用户输入偏好后，Agent 自动调用 8 个工具（并行搜索场地 + 餐厅、路线规划、可用性检查），通过 SSE 实时输出思考过程，生成 3-4 节点行程，支持滑卡微调、多人协同确认、批量预订执行。

---

## 功能一览

| 功能 | 描述 |
| --- | --- |
| F01-02 渐进式需求收集 | 单选卡片 → 词云标签 → 自由文本，3 步收集约束集 |
| F03 ReAct 规划 Agent | Thought → Action → Observation 循环，SSE 实时流式输出 |
| F04 动态时间分配 | 三步算法：硬性校验 → 弹性分配 → 冲突检测 |
| F05 滑卡微调 | Framer Motion 滑动卡片替换行程节点，自动重算时间线 |
| F06 批量执行 | 幂等键防重复，SSE 进度条，asyncio 并发预订 |
| F07 异常降级 | 三级降级：静默替换 → 重排压缩 → 用户决策 |
| F08 多人协同 | 分享链接 + 投票确认，状态机管理 pending→done |
| F09 用户画像 | 贝叶斯置信度更新，Learning Log 沉淀偏好 |
| F10 Pass@1 评测 | 20 条测例，四维断言，目标 ≥85%（当前 100%） |
| F12 商业化触点 | 17 条 Mock 券池，精准匹配 + 品类兜底 |
| F13 社交分享文案 | 三种受众风格（家庭/闺蜜/兄弟）× 四类输出 |
| F14 LLM 规划（可选） | 在 `.env` 中配置 `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` 后自动切换为 LLM Function Calling |

---

## 技术栈

- **后端**：Python 3.11 + FastAPI + SSE-Starlette + SQLite
- **前端**：React 18 + TypeScript + TailwindCSS + Framer Motion + Vite
- **测试**：pytest（349 tests）+ ruff + mypy --strict

---

## 前置条件

| 工具 | 版本 | 检查命令 |
| --- | --- | --- |
| Python | 3.11.x | `python3.11 --version` |
| Node.js | 20.x | `node --version` |
| npm | 9+ | `npm --version` |

> Redis 可选。若未启动 Redis，缓存层自动降级为内存缓存，不影响 demo 运行。

---

## 快速启动（本地 Demo）

### 第一步：激活 Python 虚拟环境

```bash
# 进入项目目录
cd /Users/chenlu/Desktop/本地生活规划

# 激活已有的虚拟环境（首次使用 make setup 创建）
source .venv/bin/activate
```

验证激活成功：

```bash
which python   # 应输出 .../本地生活规划/.venv/bin/python
python --version   # 应输出 Python 3.11.x
```

### 第二步：（首次）安装依赖

如果是第一次运行，或 `.venv/` 目录不存在：

```bash
# 创建虚拟环境并安装所有依赖
make setup
```

`make setup` 会自动：

1. 创建 `.venv/` Python 虚拟环境
2. 安装后端 Python 依赖（`pip install -e ".[dev]"`）
3. 安装前端 Node 依赖（`npm ci`）
4. 从 `.env.example` 复制 `.env` 模板

### 第三步：配置环境变量

将模板复制为实际配置文件：

```bash
cp .env.example .env
```

编辑 `.env`，填入以下三项 LLM 配置（其余项保持默认即可）：

```bash
# LLM API 密钥（支持 DashScope 或其他 OpenAI 兼容中转服务）
LLM_API_KEY=your-api-key-here

# OpenAI 兼容端点
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

# 使用的模型名称
LLM_MODEL=qwen-plus
```

> 未填写有效 `LLM_API_KEY` 时，Agent 自动使用确定性 Mock 规划，不消耗 LLM 额度，所有功能均可正常体验。

### 第四步：启动后端服务

**新开一个终端窗口**，激活虚拟环境后启动：

```bash
source .venv/bin/activate
python -m uvicorn agent.main:app --reload --port 8000
```

看到以下输出说明启动成功：

```text
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000
```

验证后端正常：

```bash
curl http://localhost:8000/health
# 返回: {"status":"ok"}
```

### 第五步：启动前端开发服务器

**另开一个终端窗口**：

```bash
cd /Users/chenlu/Desktop/本地生活规划/frontend
npm run dev
```

看到以下输出说明启动成功：

```text
  VITE v5.x  ready in xxx ms

  ➜  Local:   http://localhost:3000/
```

### 第六步：打开浏览器体验 Demo

访问 [http://localhost:3000](http://localhost:3000)

---

## 完整体验流程

```text
需求收集 → 智能规划 → 方案确认 → 协同确认 → 一键执行 → 完成
```

1. **需求收集**：回答 5 道单选题（同伴、人数、地点、场景、预算），选择词云标签，填写特殊要求
2. **智能规划**：实时看到 Agent 的 ReAct 循环（思考→行动→观察），最终生成 3-4 节点行程
3. **方案确认**：查看时间线，对不满意的节点点击「换一个」，左右滑动替补方案卡片
4. **协同确认**：生成分享链接，模拟多人投票确认
5. **一键执行**：SSE 进度条实时显示各节点预订状态（含 10% 随机故障演示）
6. **完成**：查看 Learning Log，了解 Agent 记录了哪些用户偏好

---

## API 文档

后端启动后访问 Swagger UI：[http://localhost:8000/docs](http://localhost:8000/docs)

主要端点：

| 端点 | 方法 | 描述 |
| --- | --- | --- |
| `/health` | GET | 健康检查 |
| `/api/collect/questions` | GET | 获取步骤1问题列表 |
| `/api/collect/tags` | POST | 根据答案生成词云标签 |
| `/api/collect/complete` | POST | 提交三步约束，获取 ConstraintSet |
| `/api/plan/run` | POST | **SSE** ReAct 规划主循环 |
| `/api/plan/swap/candidates` | POST | 获取节点替补方案 |
| `/api/plan/swap/accept` | POST | 接受替换，重算时间线 |
| `/api/execute` | POST | **SSE** 批量执行预订 |
| `/api/collab/share` | POST | 创建协同分享链接 |
| `/api/deals/match` | POST | 匹配优惠券 |
| `/api/share/text` | POST | 生成社交分享文案 |

---

## 运行测试

```bash
source .venv/bin/activate

# 完整验证（lint + 类型检查 + 全量测试 + 前端构建）
make check

# 只跑单元测试
make test-unit

# 只跑集成测试
make test-integration

# Pass@1 评测框架（20 条场景化测例）
make test-pass-at-1
```

---

## 常用 Make 命令

```bash
make setup     # 首次：安装所有依赖
make dev       # 启动后端（等价于 uvicorn 命令）
make check     # 完整验证流水线
make test      # 只跑测试
make lint      # ruff 代码风格检查
make typecheck # mypy --strict 类型检查
make build     # 构建前端生产包
make clean     # 清理缓存和构建产物
```

---

## 目录结构

```text
.
├── agent/                   # 后端
│   ├── main.py              # FastAPI 入口
│   ├── schemas.py           # 所有 Pydantic 模型
│   ├── core/
│   │   ├── react_loop.py    # ReAct 主循环（唯一大脑）
│   │   ├── llm_planner.py   # LLM Function Calling（F14）
│   │   ├── fault_handlers.py # 三级异常降级
│   │   ├── time_allocator.py # 动态时间分配
│   │   └── partial_replan.py # 滑卡替换逻辑
│   ├── tools/               # 8 个工具（严禁互相调用）
│   │   ├── venue_search.py
│   │   ├── restaurant_search.py
│   │   ├── check_availability.py
│   │   ├── route_plan.py
│   │   ├── execute_booking.py
│   │   ├── deal_matcher.py
│   │   ├── generate_share_text.py
│   │   └── mock_data/       # Mock 数据 + 10% 随机故障注入
│   ├── modules/
│   │   ├── collab_confirm.py # 多人协同状态机
│   │   ├── family_profile.py # 用户画像（贝叶斯更新）
│   │   └── signal_extractor.py # 偏好信号提取
│   └── routers/             # FastAPI 路由层
├── frontend/                # 前端
│   └── src/
│       ├── App.tsx           # 主应用 + 流程状态机
│       ├── api.ts            # API 客户端
│       ├── types.ts          # TypeScript 类型定义
│       └── components/      # 各阶段页面组件
├── tests/                   # 分层测试（349 tests）
│   ├── unit/
│   ├── integration/
│   ├── e2e/
│   └── test_pass_at_1.py
├── docs/
│   └── features.md          # 功能状态清单（14/14 passing）
├── Makefile                 # 工程化入口
├── pyproject.toml           # Python 项目配置
└── .env                     # 环境变量（含 API Key 配置）
```

---

## 架构约束

- **单向调用**：`core/react_loop.py` 是唯一调度中心，`tools/` 下各工具严禁互相调用
- **执行刚性**：必须等所有节点确认后统一批量执行（`execute_booking`），规划阶段不发起真实预订
- **Mock 隔离**：不调用真实美团 API，所有数据来自 `tools/mock_data/`，含 10% 随机故障注入
- **缓存边界**：`execute_booking` 结果永不缓存（幂等键防重），其余工具结果走 `cached_layer.py`
