# 最近操作

> **用途**：记录 agent 最近对所有需求的操作日志，按时间倒序排列。
> **维护规则**：每次会话结束时由 agent 追加；只保留最新 5 条，旧记录自然滚动清理。

| 日期 | 需求 | 动作 |
|------|------|------|
| 2026-06-19 | F05 / 工程脚本 | 新增 `bin/alphapredator.sh` 一键管理脚本，并恢复独立前后端启动脚本；支持环境检查、依赖安装、启动、停止、重启和前端/后端/MCP 状态检查 |
| 2026-06-17 | F05 | 实现 MCP 基础接入：新增 `fastmcp>=3.0`、`/api/mcp` 挂载、lifespan 组合、本机绑定拦截和 `get_alpha_predator_info` 探针 Tool，并补充自动化测试 |
| 2026-06-17 | F05 | 将 MCP 需求收敛为基础接入服务：第一阶段只打通 `/api/mcp` Streamable HTTP 连接，业务 Tool 后移 |
| 2026-06-17 | F05 | 修订 MCP 交易复盘服务设计：补充 `/api/mcp` 挂载、lifespan 组合、本机安全边界、Pydantic schema 复用和 Tool 注解约束 |
| 2026-06-16 | F02 | 优化 5 分钟 K 写入：从 `executemany` 改为 DataFrame 注册 + DuckDB `INSERT SELECT` 批量入库 |
