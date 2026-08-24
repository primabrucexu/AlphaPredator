# F005: MCP 基础接入
> STATUS：完成

## MileStone

| 日期 | 事件 |
|---|---|
| 2026-08-24 | 完成 FastMCP 基础接入，并通过 Hermes 0.17.0 真实客户端验证 |
| 2026-08-24 | 确认 README 只提供手工注册说明，不提供自动注册脚本 |
| 2026-08-24 | 确认通过 `/api/mcp` 挂载到现有 FastAPI，只允许 localhost |
| 2026-08-24 | 确认 F005 不提供 Tool、Resource 或 Prompt，业务 Tool 拆分到 F005.1 |
| 2026-08-24 | 确认首个目标客户端为本机 Hermes，MCP 框架使用独立 FastMCP |
| 2026-08-23 | 立项 |

## Relation

- **Related**: F001–F004（F005 不接入这些 Feature 的业务能力）
- **Enables**: F005.1（在基础 MCP Server 通过真实客户端验证后接入业务 Tool）

## What

### 已确认需求

- 在现有 FastAPI 后端进程中提供一个标准 MCP Server，使本机 Hermes 等 Agent 可以手工注册 AlphaPredator。
- 使用独立的 `fastmcp` 包和 Streamable HTTP 传输。
- MCP ASGI 应用挂载到 `/api/mcp`，注册地址为 `http://127.0.0.1:8000/api/mcp/`。
- F005 只交付连接、初始化和能力发现；Tool、Resource 和 Prompt 列表全部为空。
- F005 不调用任何业务 service，不访问 SQLite、DuckDB、`MarketDataProvider`、`TaskService`、thsdk 或韭研公社。
- 首版不增加认证，安全边界限定为本机 localhost。
- README 只说明本项目作为 MCP Server 的手工注册参数，不提供自动注册脚本。
- 完成自动化协议验证后，必须使用本机 Hermes 完成一次真实注册和空能力发现验证。

### 第一版非目标

- 不提供探针 Tool、业务 Tool、Resource 或 Prompt。
- 不接入行情、自选股、标签、涨停历史、任务或其他业务能力；这些内容统一由 F005.1 或其后续设计处理。
- 不新增数据库表、迁移、REST API 或前端页面。
- 不提供 stdio、旧 SSE 或独立 MCP 进程。
- 不提供 API Key、OAuth、远程 HTTPS、局域网或公网访问。
- 不提供 Hermes 自动注册脚本，不提交 Hermes 用户级配置。

## How

### 1. 架构

```text
本机 Hermes
    │  Streamable HTTP
    ▼
http://127.0.0.1:8000/api/mcp/
    │
    ▼
FastAPI Web 进程
├── 现有 /api REST API
└── /api/mcp → FastMCP ASGI 应用
                    ├── Tools: []
                    ├── Resources: []
                    └── Prompts: []
```

FastMCP 只负责 MCP 协议、Streamable HTTP 和能力发现。F005 没有业务适配层，也不创建第二个服务进程。

### 2. 组件边界

- 新增一个独立 MCP 模块，负责创建 `FastMCP("AlphaPredator")` 实例及其 ASGI 应用。
- MCP 模块不得导入数据库 Session、业务 service、Provider、任务 Handler 或外部数据客户端。
- FastAPI 主应用只负责挂载 MCP ASGI 应用并组合生命周期，不在 `main.py` 中定义 Tool。
- 使用 FastMCP 3.x 兼容范围，具体依赖在 `backend/pyproject.toml` 中限制为同一主版本。
- 不注册任何 `@mcp.tool()`、Resource 或 Prompt，包括连通性探针。

建议的最小文件范围：

```text
backend/app/mcp_server.py
backend/app/main.py
backend/pyproject.toml
backend/tests/test_mcp.py
README.md
docs/feature/F005-mcp-integration.md
docs/integrations/mcp.md
```

### 3. 挂载与生命周期

- FastMCP HTTP 应用的内部路径使用 `/`，FastAPI 挂载前缀使用 `/api/mcp`，避免最终地址变成 `/api/mcp/mcp`。
- Hermes 使用带尾斜杠的完整地址 `/api/mcp/`，避免依赖客户端是否跟随挂载路径重定向。
- FastAPI 顶层 lifespan 组合现有数据库迁移、待处理任务 Worker 启动、Provider 关闭和 FastMCP lifespan。
- 挂载子应用的 lifespan 不会自动替代顶层 lifespan；实现时必须显式保证 FastMCP 会话管理器正常启动和关闭。
- 保持 FastMCP 默认的标准 Streamable HTTP 会话行为，不启用 stdio、旧 SSE 或额外兼容服务。

### 4. 本机安全边界

- 项目标准启动方式继续监听 `127.0.0.1:8000`。
- FastMCP 保留或显式配置 localhost Host/Origin 防护，非本机 Host/Origin 请求不得进入 MCP 服务。
- 无认证是 F005 本机第一版的明确取舍，不得在该状态下改为监听 `0.0.0.0`、局域网地址或公网地址。
- 未来需要远程访问时必须另立需求，确认认证、HTTPS、Origin 和部署边界。

### 5. 错误处理

- FastMCP 初始化或生命周期启动失败时，让后端启动明确失败，不隐藏异常，也不降级成表面可用的空壳。
- F005 没有业务调用，因此不定义业务错误转换、业务重试或数据降级逻辑。
- MCP 失败不得影响既有错误语义，也不得生成伪造的连接成功或能力结果。

### 6. README 与真实注册

README 只记录 MCP Server 名称、Streamable HTTP 类型和完整本机 URL，不补充范围、安全或实现说明，也不提供自动注册脚本。

实现完成后使用本机 Hermes 手工注册，记录 Hermes 版本或标识、验证日期、连接结果和空能力发现结果。Hermes 用户级配置不进入仓库。

### 7. 验证策略

- 使用 FastMCP 客户端完成初始化，并验证 Tool、Resource、Prompt 列表均为空。
- 验证 FastAPI 正确挂载 `/api/mcp`，MCP lifespan 正常运行。
- 验证现有 `/api/health` 等 REST API 和 FastAPI 原有初始化流程不受影响。
- 验证非 localhost 的 MCP Host/Origin 请求被拒绝。
- 在 `backend` 下执行完整 `python -m pytest -q`。
- 自动化测试通过后启动真实后端，用本机 Hermes 完成手工注册验证。

## MCP

F005 负责 MCP 基础连接、传输、安全边界和目标客户端注册验证，本身不暴露业务能力，因此其 `mcp_status` 为“不适用”。所有业务 Tool 由 F005.1 管理；其他业务 Feature 在 F005.1 完成前保持“待确认”，完成后再同步更新。

## Acceptance Criteria

- [x] AC1: AlphaPredator 在现有 FastAPI 进程中通过 `/api/mcp` 提供 Streamable HTTP MCP Server，不启动独立 MCP 进程。
- [x] AC2: 本机 MCP 客户端可以使用 `http://127.0.0.1:8000/api/mcp/` 完成初始化和能力发现。
- [x] AC3: Tool、Resource 和 Prompt 列表全部为空，不提供探针或业务能力。
- [x] AC4: MCP 模块不调用业务 service，不访问 SQLite、DuckDB、Provider、任务框架、thsdk 或韭研公社。
- [x] AC5: FastMCP lifespan 与现有 FastAPI lifespan 正确组合，数据库迁移、待处理任务启动和 Provider 关闭行为不回退。
- [x] AC6: 现有 REST API 保持可用，MCP 接入不改变原有 API 路径和错误语义。
- [x] AC7: MCP 仅允许 localhost；非本机 Host/Origin 请求被拒绝，无认证状态下不监听 `0.0.0.0` 或对外暴露。
- [x] AC8: README 只记录 MCP Server 名称、传输类型和完整 URL。
- [x] AC9: 项目不提供 Hermes 自动注册脚本，也不提交或修改 Hermes 用户级配置。
- [x] AC10: MCP 自动化测试及后端完整测试通过。
- [x] AC11: 本机 Hermes 可以手工注册 AlphaPredator，完成连接和空能力发现；验证日期、客户端标识和结果记录到 `docs/integrations/mcp.md`。

## Risk

| 风险 | 解决 |
|---|---|
| 挂载子应用后 FastMCP lifespan 未运行，首次请求返回错误 | 顶层 FastAPI lifespan 显式组合 FastMCP lifespan，并增加真实协议测试 |
| 挂载前缀与内部路径叠加成错误 URL | FastMCP 内部路径使用 `/`，固定验证 `/api/mcp/` |
| 空 Tool 服务在目标客户端中无法注册或显示异常 | 自动化验证之外，F005 完成前必须使用真实 Hermes 验证 |
| 无认证服务被意外暴露到非本机网络 | 标准启动监听 `127.0.0.1`，同时启用 localhost Host/Origin 防护 |
| MCP 接入破坏现有 FastAPI 初始化 | 生命周期测试同时覆盖原有启动行为和 REST 健康接口 |
