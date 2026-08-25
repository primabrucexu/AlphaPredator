# MCP 接入汇总

| 项目 | 状态 | 说明 |
|---|---|---|
| F005 基础接入 | 已实现 | FastMCP、Streamable HTTP、`http://127.0.0.1:8000/api/mcp/` |
| F005.1 Tool 接入 | 客户端已验证 | 自选股与标签 11 个 Tool；任务创建 3 个 Tool；任务查询 2 个 Tool |
| Hermes 基础连接验证 | 客户端已验证 | 2026-08-24，Hermes 0.17.0，注册项 `ap`，空能力发现成功 |
| Hermes 业务 Tool 验证 | 客户端已验证 | 2026-08-25，Hermes 0.17.0 发现 16 个业务 Tool，真实任务创建和 UUID 查询成功 |
| Hermes 任务结果插件 | 客户端已验证 | 独立 Python 包；真实任务终态结果通过 Session API 幂等注入原测试 Session |

F005.1 不提供 Resource 或 Prompt。Hermes 日志中的 20 个 `ap` Tool 包含 16 个业务 Tool，以及 Hermes 为 MCP Server 自动增加的 4 个 Resource/Prompt 辅助 Tool；AlphaPredator 本身仍未实现 Resource 或 Prompt。具体范围以 `docs/feature/F005.1-mcp-tools.md` 为准。
