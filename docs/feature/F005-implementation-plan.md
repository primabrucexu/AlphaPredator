# F005 MCP Basic Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 FastAPI 进程中挂载一个无 Tool、Resource、Prompt 的 FastMCP Streamable HTTP Server，并通过本机 Hermes 完成真实注册验证。

**Architecture:** `backend/app/mcp_server.py` 只创建空 FastMCP Server 和 ASGI 应用；`backend/app/main.py` 使用 `combine_lifespans()` 组合现有 FastAPI 与 FastMCP 生命周期，并挂载到 `/api/mcp`。F005 不导入业务 service、Provider、任务框架或数据库。

**Tech Stack:** Python 3.11、FastAPI、FastMCP 3.x、pytest、Uvicorn、Streamable HTTP

---

## 文件范围

| 文件 | 职责 |
|---|---|
| `backend/app/mcp_server.py` | 创建空 FastMCP Server 和 `path="/"` 的 ASGI 应用 |
| `backend/app/main.py` | 组合 lifespan 并把 MCP 应用挂载到 `/api/mcp` |
| `backend/pyproject.toml` | 增加 `fastmcp>=3,<4` 依赖 |
| `backend/tests/test_mcp.py` | 验证空能力、挂载、生命周期和 localhost Host 防护 |
| `docs/feature/F005-mcp-integration.md` | 记录实现里程碑和验收结果 |
| `docs/feature/index.json` | 更新 F005 状态 |
| `docs/integrations/mcp.md` | 汇总实现与 Hermes 验证状态 |

README 已包含注册参数，实现阶段不再扩写。

### Task 1: 用失败测试定义空 MCP Server

**Files:**
- Create: `backend/tests/test_mcp.py`
- Create: `backend/app/mcp_server.py`
- Modify: `backend/pyproject.toml:5-15`

- [ ] **Step 1: 先写空能力测试**

在 `backend/tests/test_mcp.py` 写入：

```python
from __future__ import annotations

import asyncio

from fastmcp import Client

from app.mcp_server import mcp


def test_mcp_server_exposes_no_capabilities() -> None:
    async def verify() -> None:
        async with Client(mcp) as client:
            assert await client.list_tools() == []
            assert await client.list_resources() == []
            assert await client.list_prompts() == []

    asyncio.run(verify())
```

- [ ] **Step 2: 运行测试并确认失败原因正确**

Run：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_mcp.py -q
```

Expected：测试收集失败，错误为缺少 `fastmcp` 或 `app.mcp_server`，证明当前项目尚未提供 MCP Server。

- [ ] **Step 3: 增加 FastMCP 依赖**

在 `backend/pyproject.toml` 的 `dependencies` 中加入：

```toml
  "fastmcp>=3,<4",
```

然后安装当前项目依赖：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Expected：安装成功，`fastmcp` 解析到 3.x。

- [ ] **Step 4: 实现最小空 Server**

创建 `backend/app/mcp_server.py`：

```python
from __future__ import annotations

from fastmcp import FastMCP


mcp = FastMCP("AlphaPredator")
mcp_app = mcp.http_app(path="/")
```

不得在该文件导入任何 AlphaPredator 业务模块。

- [ ] **Step 5: 运行空能力测试**

Run：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_mcp.py -q
```

Expected：`1 passed`，Tool、Resource、Prompt 均为空。

### Task 2: 挂载到现有 FastAPI 并组合生命周期

**Files:**
- Modify: `backend/tests/test_mcp.py`
- Modify: `backend/app/main.py:3-46`

- [ ] **Step 1: 先写挂载与 HTTP 初始化测试**

向 `backend/tests/test_mcp.py` 增加：

```python
from contextlib import contextmanager

from fastapi.testclient import TestClient
from starlette.routing import Mount


INITIALIZE_REQUEST = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "AlphaPredatorTest", "version": "1.0"},
    },
}


def _patch_main_startup(monkeypatch, main_module) -> list[str]:
    events: list[str] = []
    for name in (
        "migrate_legacy_watchlists",
        "migrate_legacy_tags",
        "migrate_stock_tag_order",
        "migrate_task_tables",
        "sync_tagged_stocks_to_watchlist",
    ):
        monkeypatch.setattr(main_module, name, lambda *_args, _name=name: events.append(_name))
    monkeypatch.setattr(
        main_module.Base.metadata,
        "create_all",
        lambda *_args: events.append("create_all"),
    )

    @contextmanager
    def session_factory():
        events.append("session")
        yield object()

    monkeypatch.setattr(main_module, "SessionLocal", session_factory)
    monkeypatch.setattr(main_module, "next_pending_task", lambda _session: None)
    monkeypatch.setattr(
        main_module,
        "close_process_market_provider",
        lambda: events.append("provider_closed"),
    )
    return events


def test_main_mounts_mcp_and_preserves_lifespan(monkeypatch) -> None:
    import app.main as main

    events = _patch_main_startup(monkeypatch, main)
    mounted_paths = [route.path for route in main.app.routes if isinstance(route, Mount)]
    assert "/api/mcp" in mounted_paths

    with TestClient(main.app) as client:
        assert client.get("/api/health").json() == {"status": "ok"}
        response = client.post(
            "/api/mcp/",
            headers={"Accept": "application/json, text/event-stream"},
            json=INITIALIZE_REQUEST,
        )
        assert response.status_code == 200
        assert "AlphaPredator" in response.text

    assert events == [
        "migrate_legacy_watchlists",
        "migrate_legacy_tags",
        "migrate_stock_tag_order",
        "migrate_task_tables",
        "create_all",
        "sync_tagged_stocks_to_watchlist",
        "session",
        "provider_closed",
    ]
```

- [ ] **Step 2: 运行新增测试并确认挂载断言失败**

Run：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_mcp.py::test_main_mounts_mcp_and_preserves_lifespan -q
```

Expected：FAIL，`mounted_paths` 不包含 `/api/mcp`。

- [ ] **Step 3: 最小修改 FastAPI 主应用**

在 `backend/app/main.py` 增加导入：

```python
from fastmcp.utilities.lifespan import combine_lifespans

from app.mcp_server import mcp_app
```

将 FastAPI 创建语句修改为：

```python
app = FastAPI(
    title="AlphaPredator",
    version="0.1.0",
    lifespan=combine_lifespans(lifespan, mcp_app.lifespan),
)
```

在现有 `app.include_router(api_router)` 后增加：

```python
app.mount("/api/mcp", mcp_app)
```

不要改变现有 `lifespan()` 函数内部的迁移、Worker 和 Provider 逻辑。

- [ ] **Step 4: 运行 MCP 测试**

Run：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_mcp.py -q
```

Expected：空能力与挂载生命周期测试全部通过。

### Task 3: 固化 localhost Host 防护

**Files:**
- Modify: `backend/tests/test_mcp.py`

- [ ] **Step 1: 增加非本机 Host 拒绝测试**

向 `backend/tests/test_mcp.py` 增加：

```python
def test_mcp_rejects_non_local_host(monkeypatch) -> None:
    import app.main as main

    _patch_main_startup(monkeypatch, main)
    with TestClient(main.app, base_url="http://malicious.example") as client:
        response = client.post(
            "/api/mcp/",
            headers={"Accept": "application/json, text/event-stream"},
            json=INITIALIZE_REQUEST,
        )

    assert response.status_code == 421
```

- [ ] **Step 2: 运行安全测试**

Run：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_mcp.py::test_mcp_rejects_non_local_host -q
```

Expected：PASS。FastMCP 在 localhost 构造时默认启用 DNS rebinding 防护并拒绝非本机 Host。

- [ ] **Step 3: 运行后端完整测试**

Run：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

Expected：全部测试通过，无既有 API、任务或行情测试回退。

### Task 4: 真实进程与 FastMCP HTTP 冒烟验证

**Files:**
- Modify only if verification finds a scoped F005 defect.

- [ ] **Step 1: 启动真实后端**

Run：

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Expected：后端启动完成，无 FastMCP lifespan 异常。

- [ ] **Step 2: 使用 FastMCP CLI 验证 HTTP 地址**

在另一终端运行：

```powershell
cd backend
.\.venv\Scripts\fastmcp.exe list http://127.0.0.1:8000/api/mcp/ --resources --prompts --json
```

Expected：连接成功，输出中 tools、resources、prompts 均为空。

- [ ] **Step 3: 验证原有健康接口**

Run：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

Expected：返回 `status = ok`。

### Task 5: 本机 Hermes 手工注册与文档收尾

**Files:**
- Modify: `docs/feature/F005-mcp-integration.md`
- Modify: `docs/feature/index.json`
- Modify: `docs/integrations/mcp.md`

- [ ] **Step 1: 按 README 手工注册**

在本机 Hermes 的 MCP Server 设置中填写：

```text
Name: AlphaPredator
Transport: Streamable HTTP
URL: http://127.0.0.1:8000/api/mcp/
```

Expected：Hermes 显示 AlphaPredator 已连接，能力发现完成，且没有 Tool、Resource 或 Prompt。

- [ ] **Step 2: 记录真实验证证据**

在 `docs/integrations/mcp.md` 把 F005 状态更新为“已实现”，把 Hermes 状态更新为“客户端已验证”，并记录界面中实际看到的 Hermes 版本、2026-08-24 和“注册成功，空能力发现通过”。如果界面不显示版本，则明确记录“版本未显示”，不得猜测。F005.1 继续保持“待确认”。

- [ ] **Step 3: 更新 Feature 验收状态**

在 `docs/feature/F005-mcp-integration.md`：

- 增加 2026-08-24 实现与 Hermes 验证里程碑。
- 将 `STATUS` 改为“完成”。
- 只勾选有测试或真实验证证据支持的 AC1–AC11。

在 `docs/feature/index.json` 将 F005 的 `status` 改为“完成”；F005 的 `mcp_status` 仍保持“不适用”，F005.1 和其他 Feature 的 `mcp_status` 仍保持“待确认”。

- [ ] **Step 4: 最终验证工作区**

Run：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
cd ..
git diff --check
git status --short
```

Expected：后端完整测试全部通过，`git diff --check` 无错误；变更范围只包含 F005 实现、测试和已确认文档。
