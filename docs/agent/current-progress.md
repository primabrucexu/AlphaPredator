# 当前执行进度

> **用途**：记录当前活跃需求的进度、下一步和阻塞点。不保留历史需求。
> **维护规则**：每次会话结束时由 agent 更新。
>
> 本文件只放当前一个活跃需求。当需求不再活跃时，agent 必须：
> 1. 检查是否有阻塞或待人工决策内容
> 2. 如有 → 同步写入对应 `docs/agent/Fxx-*.md` 文件
> 3. 将本文件中该需求分区整体移除
>
> 更多操作日志见 [最近操作](recent-actions.md)。

---

## 当前活跃需求

- [F05：MCP 基础接入服务](F05-mcp-service.md)

---

### 完成情况

- [x] 设计文档：第一阶段改为 MCP 基础接入服务，仅打通 Streamable HTTP、`/api/mcp` 挂载、lifespan 组合和本机安全边界；交易复盘、OCR、行情和联动套利 Tool 后移
- [x] 编码实现：
  - [x] 添加 `fastmcp>=3.0` 依赖到 `pyproject.toml`
  - [x] 创建 `backend/app/api/routes/mcp.py`，创建 `FastMCP("AlphaPredator")` 实例，并定义只读探针 Tool `get_alpha_predator_info`
  - [x] 在 `backend/app/main.py` 挂载 MCP ASGI app 到 `/api/mcp`
- [x] 自动化验证：
  - [x] `backend/tests/test_mcp_basic.py` 覆盖探针 Tool 返回值、FastMCP client 工具发现与调用、`/api/mcp` 挂载、lifespan 组合和非本机绑定拦截
- [x] 开发脚本：
  - [x] 新增 `bin/alphapredator.sh` 一键管理入口，支持环境检查、依赖安装、启动、停止、重启和状态检查
  - [x] 新增/恢复 `bin/dev-backend.sh`、`bin/dev-frontend.sh` 独立前后端启动脚本
- [ ] 外部客户端实连验证：用 MCP Inspector 或 Codex / Hermes 测试 `http://127.0.0.1:<port>/api/mcp` 连接初始化

### 下一步

启动后端后，用 MCP Inspector、Codex 或 Hermes 连接 `http://127.0.0.1:<port>/api/mcp` 做外部客户端实连；如果连接成功，再确认能发现并调用 `get_alpha_predator_info`。

### 已知问题 / 阻塞 / 待人工决策

- 已启用 `get_alpha_predator_info` 探针 Tool，用于验证工具发现和调用链路；该 Tool 不读取业务数据库，也不调用业务 service。
- 尚未完成 MCP Inspector / Codex / Hermes 外部客户端实连验证。
- 当前本机 shell 可用 Python 3.14.6，但未找到 `node` / `npm`；因此脚本已具备前端依赖安装入口，但本机尚无法实际安装或启动前端依赖。
