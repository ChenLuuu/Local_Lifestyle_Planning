# docs/api-patterns.md
# API 设计规范
#
# 适用条件：添加或修改 API 端点时必读
# 来源：团队约定 + 硬约束（违反会被 make check 检测）
# ─────────────────────────────────────────────────────────

## 认证（硬约束）

所有 API 端点**必须**经过 **JWT Bearer Token** 认证。

```python
# ✅ 正确：使用 Depends 注入当前用户
from agent.core.auth import get_current_user

@router.post("/api/plan/run")
async def run_plan(
    request: PlanRequest,
    current_user: User = Depends(get_current_user),
) -> EventSourceResponse:
    ...

# ❌ 错误：缺少认证依赖
@router.post("/api/plan/run")
async def run_plan(request: PlanRequest) -> EventSourceResponse:
    ...
```

公开端点必须**显式标注** `tags=["public"]`：

```python
# ✅ 公开端点（无需登录即可访问）
@router.post("/api/auth/login", tags=["public"])
async def login(credentials: LoginRequest) -> TokenResponse: ...

# ✅ 协同确认只读页（持有 share_token 即可，无需账号）
@router.get("/api/collab/{token}", tags=["public"])
async def view_shared_plan(token: str) -> SharedPlanResponse: ...
```

---

## 统一响应格式

**成功响应**：
```json
{
    "data": { "...": "业务数据" },
    "meta": { "timestamp": "2026-05-27T14:00:00Z", "version": "0.1.0" }
}
```

**错误响应**（Agent 友好 — 必须包含修复指导）：
```json
{
    "error": {
        "code": "NO_AVAILABILITY",
        "message": "该餐厅当前时段已无座位",
        "detail": "restaurant_id=r_001, timeslot=18:00-20:00",
        "fix_hint": "trigger partial_replan for level 1 replacement: try adjacent timeslot or same-district alternative"
    }
}
```

> 硬约束：错误消息必须包含 `fix_hint`，指导 Agent 下一步降级动作，而不只是描述错误本身。

---

## 端点命名约定

```
GET    /api/{resource}           列表（分页）
GET    /api/{resource}/{id}      单个资源
POST   /api/{resource}           创建
PUT    /api/{resource}/{id}      全量更新
PATCH  /api/{resource}/{id}      部分更新
DELETE /api/{resource}/{id}      删除
```

---

## SSE 流式端点（ReAct Loop 专用）

`POST /api/plan/run` 是唯一的 SSE 流式端点，**必须**遵守以下数据包格式：

```
event: thought
data: {"step": 1, "content": "用户想带两个小孩下午游玩，时间窗口 14:00-19:00..."}

event: action
data: {"tool": "venue_search", "args": {"tags": ["亲子"], "max_distance_km": 5}}

event: observation
data: {"tool": "venue_search", "result": {"venues": [...], "count": 12}}

event: thought
data: {"step": 2, "content": "venue_search 返回 12 个场馆，筛选亲子友好且距离 ≤5km..."}

... （循环直到完成）

event: done
data: {"itinerary": {...}, "total_nodes": 4, "elapsed_seconds": 18.3}
```

顺序约束：**Thought → Action → Observation**，不允许跳过步骤或乱序。

```python
# ✅ 正确的 SSE 端点实现模板
from sse_starlette.sse import EventSourceResponse

@router.post("/api/plan/run", tags=["plan"])
async def run_plan(
    request: PlanRequest,
    current_user: User = Depends(get_current_user),
) -> EventSourceResponse:
    async def event_generator() -> AsyncIterator[dict[str, str]]:
        async for event in react_loop.run(request.constraints, request.session_id):
            yield {"event": event.type, "data": event.model_dump_json()}
    return EventSourceResponse(event_generator())
```

---

## 核心 API 端点一览

### 规划阶段

| 端点 | 方法 | 描述 | 响应类型 |
|------|------|------|----------|
| `/api/plan/run` | POST | 启动 ReAct 规划循环 | SSE stream |
| `/api/plan/{session_id}` | GET | 获取当前方案快照 | JSON |
| `/api/plan/{session_id}/node/{node_id}/swap` | POST | 触发单节点 partial_replan | SSE stream |

**请求体 `POST /api/plan/run`**：
```json
{
    "session_id": "sess_abc123",
    "constraints": {
        "companions": "family",
        "headcount": 4,
        "age_range": [3, 42],
        "district": "朝阳区",
        "scene": "亲子出游",
        "budget_per_capita": 200,
        "total_duration_hours": 5,
        "start_time": "14:00",
        "tags": ["室内", "不想走路", "美食"],
        "special_requirements": "宠物友好，不吃辣"
    },
    "user_id": "user_001"
}
```

### 执行阶段

| 端点 | 方法 | 描述 | 响应类型 |
|------|------|------|----------|
| `/api/execute` | POST | 批量执行所有已确认节点 | SSE stream |

**请求体 `POST /api/execute`**：
```json
{
    "session_id": "sess_abc123",
    "idempotency_key": "idem_xyz789"
}
```

> 硬约束：`execute_booking` 结果**永不缓存**。`idempotency_key` 由前端生成，防止重复下单。

**执行 SSE 数据包格式**：
```
event: booking_progress
data: {"node_id": "n_001", "type": "restaurant", "status": "booking", "name": "外婆家（望京店）"}

event: booking_done
data: {"node_id": "n_001", "status": "confirmed", "order_id": "mock_ord_001", "elapsed_ms": 1240}

event: booking_failed
data: {"node_id": "n_002", "status": "failed", "reason": "NO_SEAT", "degraded_to": "n_002_alt"}

event: execute_complete
data: {"total": 4, "succeeded": 4, "failed": 0, "share_text": "今天的行程敲定啦！..."}
```

### 协同确认阶段

| 端点 | 方法 | 描述 | 认证 |
|------|------|------|------|
| `/api/collab/create` | POST | 生成只读分享链接（2h有效） | JWT |
| `/api/collab/{token}` | GET | 查看分享方案（任何人） | public |
| `/api/collab/{token}/confirm` | POST | 成员投票/留言 | public |

**协同状态机**：`pending` → `all_confirmed` → `executing` → `done`

### 用户画像

| 端点 | 方法 | 描述 | 认证 |
|------|------|------|------|
| `/api/profile/{user_id}` | GET | 读取用户画像（场景隔离） | JWT |
| `/api/profile/{user_id}/signals` | POST | 写入信号（由 signal_extractor 调用） | JWT |

---

## 分页

所有列表端点支持分页：

```
GET /api/venues?page=1&per_page=20&scene=亲子

响应：
{
    "data": [...],
    "meta": { "page": 1, "per_page": 20, "total": 48, "total_pages": 3, "timestamp": "..." }
}
```

默认值：`per_page=20`，最大值：`per_page=100`

---

## 缓存规则（Redis TTL 分级）

| Tool | TTL | 说明 |
|------|-----|------|
| `venue_search` | 60s | 场馆列表相对稳定 |
| `restaurant_search` | 60s | 餐厅信息相对稳定 |
| `check_availability` | 5s | 库存实时性要求高 |
| `route_plan` | 300s | 路线不频繁变化 |
| `execute_booking` | **永不缓存** | 必须校验幂等键 |

缓存键格式：`{tool_name}:{sha256(args_json)[:16]}`

---

*来源：D005（技术栈选型）、D001（批量执行设计）、D003（三阶段产品架构）*
*最后更新：2026-05-27*
*过期条件：认证方案变更、新增核心端点、缓存 TTL 调整时需更新本文档*
