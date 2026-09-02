# MCP 接入汇总

| 项目 | 状态 | 说明 |
|---|---|---|
| F005 基础接入 | 已实现 | FastMCP、Streamable HTTP、`http://127.0.0.1:8000/api/mcp/` |
| F005.1 Tool 接入 | 部分客户端已验证 | 首批 16 个业务 Tool 已验证；4 个 SR001 Tool 已实现、客户端待验证 |
| SR001 模式选股闭环 | 已实现 | 任务创建、命中结果、交易明细 3 个 Tool 已实现；创建 Tool 默认使用当前最新 revision |
| SR001 Agent 报告 | 已实现 | `get_sr001_screening_report` 一次返回结构化报告和即时生成的内嵌 PDF；第一版支持 revision 3，客户端待验证 |
| Hermes 基础连接验证 | 客户端已验证 | 2026-08-24，Hermes 0.17.0，注册项 `ap`，空能力发现成功 |
| Hermes 业务 Tool 验证 | 客户端已验证 | 2026-08-25，Hermes 0.17.0 发现 16 个业务 Tool，真实任务创建和 UUID 查询成功 |
| Hermes 任务结果插件 | 客户端已验证 | 独立 Python 包；真实任务终态结果通过 Session API 幂等注入原测试 Session |

F005.1 不注册可独立发现的 Resource 或 Prompt；F008 的 PDF 只作为报告 Tool 的内嵌文件内容返回。AlphaPredator 当前实现 20 个业务 Tool；2026-08-25 的 Hermes 日志中 20 个 `ap` Tool 是当时 16 个业务 Tool 加 Hermes 自动增加的 4 个 Resource/Prompt 辅助 Tool。现有 4 个 SR001 Tool 尚未进行真实客户端发现验证。具体范围以 `docs/feature/F005.1-mcp-tools.md` 为准。

SR001 已实现闭环范围以 `docs/feature/F006.3-trend-reversal-strategy.md` 和 `docs/feature/F006.4-mode-screening-with-backtest-analysis.md` 为准；报告范围以 `docs/feature/F008-sr001-agent-report.md` 为准。创建 Tool 的最新 revision 选择和报告 Tool 已完成编码与自动化测试；真实 Hermes 发现、报告调用和 PDF 文件接收仍待验证，因此客户端状态保持“未验证”。
