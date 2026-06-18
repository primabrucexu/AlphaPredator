# F05：MCP 基础接入服务

## 背景

- 项目需要先接入 MCP（Model Context Protocol），让 OpenAI Codex、Hermes 等 Agent 客户端可以连接 AlphaPredator 后端。
- 当前阶段的目标是先打通 MCP 连接链路，不通过 MCP 暴露交易复盘、行情查询、联动套利等业务能力。
- 后续确认客户端兼容性和本机连接稳定性后，再逐步增加业务 Tool。

## 目标

- 以 Streamable HTTP 协议提供 MCP 服务端点。
- 集成到现有 FastAPI 后端，复用同一个后端进程，不引入独立 MCP 进程。
- 挂载 MCP ASGI app 到 `/api/mcp`。
- 保留现有 SQLite / DuckDB 初始化逻辑，同时正确初始化 FastMCP Streamable HTTP session manager。
- 允许 MCP 客户端完成连接、初始化和基础工具发现。

## 不做什么

- 第一阶段不暴露交易复盘 CRUD、月度统计或 OCR 能力。
- 第一阶段不暴露行情查询、短线情绪、联动套利等能力。
- 第一阶段不新建或修改数据库表。
- 第一阶段不做 stdio 传输，仅做 Streamable HTTP。
- 第一阶段不加认证；安全边界限定为本机使用，只允许绑定 `127.0.0.1` / `localhost`，不允许暴露到 `0.0.0.0` 或公网。

## 分阶段设计

### F05a：MCP 基础接入

当前阶段。

- 新增 `fastmcp>=3.0` 依赖。
- 新增 MCP route 模块，创建 `FastMCP("AlphaPredator")` 实例。
- 使用 `mcp_server.http_app(path="/")` 创建 MCP ASGI app。
- 在 FastAPI 主 app 上挂载：

```python
app.mount("/api/mcp", mcp_app)
```

- 组合现有 FastAPI lifespan 与 `mcp_app.lifespan`。
- 不接入业务 service。
- 不读写业务数据库。

### F05b：交易复盘只读 Tool

后续阶段。

- `list_trade_reviews`
- `get_trade_review_detail`
- `get_monthly_trade_stats`

### F05c：交易复盘写入 Tool

后续阶段。

- `create_trade_review`
- `update_trade_review`
- `delete_trade_review`

写入 Tool 需要补充调用前确认语义和 `ToolAnnotations`，其中删除 Tool 必须标注 destructive。

### F05d：OCR Tool

后续阶段。

- `parse_trade_screenshot`
- 验证 Codex / Hermes 是否能把粘贴图片自动转换为 base64。
- 如果客户端不支持自动编码，则继续通过 Web 前端上传截图做 OCR。

## 目标平台

- **OpenAI Codex**（Windows 客户端）
- **Hermes**（新 Agent 客户端）

两个平台均按 Streamable HTTP 方式接入。当前阶段只验证连接和协议链路，不验证业务 Tool 能力。

## 技术选型

| 项目 | 选择 |
|------|------|
| MCP 库 | `fastmcp>=3.0`（PrefectHQ/fastmcp） |
| 传输协议 | Streamable HTTP（单端点 POST/GET/DELETE） |
| 集成方式 | `fastmcp.http_app(path="/")` 挂载到现有 FastAPI `app.mount("/api/mcp", mcp_app)` |
| 端点路径 | `/api/mcp` |
| 认证 | 第一阶段无认证；仅允许本机访问 |

## 架构

```text
Agent (Codex / Hermes)
    │  POST /api/mcp  (JSON-RPC 请求)
    │  GET  /api/mcp  (SSE 服务器推送)
    │  DELETE /api/mcp (结束会话)
    ▼
┌─────────────────────────────┐
│  FastAPI                    │
│                              │
│  app.mount("/api/mcp")       │
│  ┌─────────────────────────┐│
│  │ FastMCP 实例 (新增)      ││
│  │ • JSON-RPC 解析          ││
│  │ • Session 管理            ││
│  │ • SSE 流推送             ││
│  │ • 工具发现               ││
│  └─────────────────────────┘│
│                              │
│  第一阶段不连接业务 service  │
└─────────────────────────────┘
```

**原则**：第一阶段只做 MCP 协议接入，不做业务能力适配。

## MCP Tool 策略

第一阶段默认不暴露业务 Tool。

为了验证客户端是否能完成工具发现和工具调用，可选保留一个无业务含义、无副作用的探针 Tool：

### 可选 Tool：get_alpha_predator_info

| 属性 | 内容 |
|------|------|
| 名称 | `get_alpha_predator_info` |
| 只读 | ✓ |
| 说明 | 返回 AlphaPredator MCP 服务的基础信息，用于验证 MCP Tool 调用链路 |

**参数**：无。

**返回**：

```json
{
  "name": "AlphaPredator",
  "mcp_status": "ok",
  "capabilities_stage": "F05a-basic-mcp"
}
```

说明：

- 该 Tool 不读取业务数据库。
- 该 Tool 不调用交易复盘、行情、联动套利等 service。
- 如果用户希望严格“空服务”，可以不实现该 Tool，仅验证 MCP 初始化和工具列表为空的表现。

## 挂载与生命周期

- MCP ASGI app 使用 `mcp_server.http_app(path="/")` 创建。
- 现有 FastAPI app 直接挂载到 `/api/mcp`：

```python
app.mount("/api/mcp", mcp_app)
```

- 不能用 `mcp_app.lifespan` 直接替换现有 FastAPI lifespan。
- 实现时必须组合现有 lifespan 与 MCP lifespan，确保两件事都发生：
  - 现有 SQLite / DuckDB schema 初始化仍正常执行。
  - FastMCP Streamable HTTP session manager 正常初始化。

## 本机安全边界

第一阶段 MCP 服务没有认证，因此安全边界必须写死在部署约束里：

- 后端 MCP 服务仅面向本机 Agent 客户端。
- 开发启动时应绑定 `127.0.0.1` 或 `localhost`。
- 不允许在无认证状态下绑定 `0.0.0.0` 或暴露到局域网 / 公网。
- 如后续需要远程访问，必须先补充认证方案（API Key 或 OAuth）后再开放。
- 如 MCP 客户端通过浏览器或 Inspector 直连，需要单独验证 `Origin` / CORS 行为，避免本地 MCP 服务被网页跨源滥用。

## 新增 / 修改文件

### 新增

- `backend/app/api/routes/mcp.py`：FastMCP 实例创建；可选定义 `get_alpha_predator_info` 探针 Tool。

### 修改

- `backend/app/main.py`：调用 `mcp.http_app(path="/")` 并 `app.mount("/api/mcp", mcp_app)`；组合现有 FastAPI lifespan 与 `mcp_app.lifespan`。
- `backend/pyproject.toml`：新增 `fastmcp>=3.0` 依赖。

## 核心代码结构预览

```python
# backend/app/api/routes/mcp.py

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

mcp = FastMCP(
    "AlphaPredator",
    instructions=(
        "A股智能选股工作台。当前 MCP 阶段仅提供基础连接能力，"
        "暂不暴露交易复盘、行情查询或联动套利等业务工具。"
    ),
)

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_alpha_predator_info() -> dict:
    """返回 MCP 服务基础信息，用于验证工具调用链路。"""
    return {
        "name": "AlphaPredator",
        "mcp_status": "ok",
        "capabilities_stage": "F05a-basic-mcp",
    }
```

如果选择严格空服务，则 `backend/app/api/routes/mcp.py` 只创建 `FastMCP` 实例，不定义任何 `@mcp.tool`。

```python
# backend/app/main.py （新增挂载代码）

from app.api.routes.mcp import mcp as mcp_server

mcp_app = mcp_server.http_app(path="/")

# 需要组合现有 lifespan 和 mcp_app.lifespan，不能直接替换数据库初始化 lifespan。
@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_sqlite_parent()
    ensure_sqlite_schema()
    ensure_duckdb_parent()
    ensure_duckdb_schema()
    async with mcp_app.lifespan(app):
        yield

app = FastAPI(lifespan=lifespan, ...)
app.mount("/api/mcp", mcp_app)
```

## 验收标准

- 后端能正常启动，现有 SQLite / DuckDB schema 初始化不回退。
- MCP 端点可通过 `http://127.0.0.1:<port>/api/mcp` 访问。
- MCP Inspector、Codex 或 Hermes 至少一个客户端可以完成连接初始化。
- 如果实现探针 Tool，客户端可以发现并调用 `get_alpha_predator_info`，返回 `mcp_status = "ok"`。
- 如果选择严格空服务，客户端可以连接，并能正确处理工具列表为空的情况。
- MCP 服务未暴露到非本机地址。

## 待验证项

- Streamable HTTP 连接在 Windows 环境下的稳定性。
- `app.mount("/api/mcp", mcp_app)` 与组合 lifespan 在本项目现有 FastAPI 初始化流程下是否能正常启动和完成 MCP session 初始化。
- 在本机访问限制下，MCP Inspector / Codex / Hermes 的连接地址是否统一使用 `http://127.0.0.1:<port>/api/mcp`。
- 严格空服务时，不同客户端对“无 Tool”的展示和交互体验是否清晰；如体验不佳，则启用 `get_alpha_predator_info` 探针 Tool。

## 后续规划

- 第二阶段：交易复盘只读 Tool。
- 第三阶段：交易复盘写入 Tool。
- 第四阶段：OCR Tool。
- 后续按需暴露行情查询、短线情绪和联动套利 Tool。
- 如需要远程访问，先补充认证（API Key 或 OAuth）。
