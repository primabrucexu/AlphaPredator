# MCP 接入汇总

| 项目 | 状态 | 说明 |
|---|---|---|
| F005 基础接入 | 已实现 | FastMCP、Streamable HTTP、`http://127.0.0.1:8000/api/mcp/` |
| F005.1 Tool 接入 | 部分客户端已验证 | 首批 16 个业务 Tool 已验证；新增 SR001 3 个 Tool 已实现、客户端待验证 |
| SR001 模式选股闭环 | 已实现 | 任务创建、命中结果、交易明细 3 个 Tool；固定 revision 1，自动化测试通过，客户端待验证 |
| Hermes 基础连接验证 | 客户端已验证 | 2026-08-24，Hermes 0.17.0，注册项 `ap`，空能力发现成功 |
| Hermes 业务 Tool 验证 | 客户端已验证 | 2026-08-25，Hermes 0.17.0 发现 16 个业务 Tool，真实任务创建和 UUID 查询成功 |
| Hermes 任务结果插件 | 客户端已验证 | 独立 Python 包；真实任务终态结果通过 Session API 幂等注入原测试 Session |

F005.1 不提供 Resource 或 Prompt。AlphaPredator 当前实现 19 个业务 Tool；2026-08-25 的 Hermes 日志中 20 个 `ap` Tool 是当时 16 个业务 Tool 加 Hermes 自动增加的 4 个 Resource/Prompt 辅助 Tool。新增 3 个 SR001 Tool 尚未进行真实客户端发现验证；AlphaPredator 本身仍未实现 Resource 或 Prompt。具体范围以 `docs/feature/F005.1-mcp-tools.md` 为准。

SR001 第一版范围以 `docs/feature/F006.3-trend-reversal-strategy.md` 和 `docs/feature/F006.4-mode-screening-with-backtest-analysis.md` 为准。自动化测试已完成，因此标记为“已实现”；真实 Hermes 完成创建、通知和结果查询后才能标记“客户端已验证”。
