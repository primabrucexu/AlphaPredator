# 当前执行进度

> **用途**：记录当前活跃需求和最近事实状态，帮助后续 agent / AI 助手接续工作。
> **维护规则**：每次会话结束时由 agent 更新；只记录事实状态，不写主观判断。记录完成后清理不活跃文件的相关内容动作。
> **格式**：当前活跃需求文件 → 然后按照每个文件进行分组，记录如下内容：最近动作（只保留最近 5 条） → 下一步 → 已知问题 / 阻塞 / 待人工决策。

---

## 当前活跃需求文件

- [F05：MCP 交易复盘服务](F05-mcp-service.md)

---

## F05：MCP 交易复盘服务

### 最近动作

- 已完成 F05 设计文档 `docs/agent/F05-mcp-service.md`，确认技术选型（fastmcp + Streamable HTTP + 集成到 FastAPI）、7 个 MCP Tool 定义、OCR 交互流程和目标平台（Codex / Hermes）。

### 下一步

- 编码实现：添加 fastmcp 依赖，创建 `backend/app/api/routes/mcp.py`，定义 7 个 Tool，挂载到 FastAPI `/api/mcp`。
- 实现后用 MCP Inspector 或 Codex / Hermes 验证 Tool 调用。

### 已知问题 / 阻塞 / 待人工决策

- Codex 和 Hermes 对粘贴图片的 base64 自动编码支持情况待验证。

---

## F04：股票联动套利分析

### 最近动作

- 已新增 `docs/agent/F04-stock-linkage-arbitrage.md`，记录 5 分钟级别股票联动套利分析的触发口径、B 股票观察口径、输出格式和待确认问题。
- 已完成 F04 非行情表数据库设计审批，并由用户同步到 `docs/human/data-model/AlphaPredator.dbml`。
- 已实现 F04 第一版后端核心：DuckDB schema 初始化、5 分钟 K 拉取函数、5 分钟 K 写入函数、联动回测服务、创建回测 API、结果查询 API。
- 已将 F04 联动回测从同步 API 改为后台任务执行模式：创建任务后异步执行，任务状态保存到 `stock_linkage_backtest_job`，API 支持任务详情、任务列表和结果查询。
- 已新增前端“联动套利”页面并接入侧边导航；页面已支持提交后台任务、轮询任务状态、任务成功后加载结果；已运行后端 F04 相关测试，结果 14 passed；已运行前端 `npm.cmd run build` 成功；已用 Playwright + 本机 Edge 冒烟检查 `/stock-linkage` 页面标题、模式和按钮渲染。

### 下一步

- 使用真实 5 分钟 K 数据执行一次小范围手动 A 股票回测，检查后台任务状态流转、结果数、概率排序和页面交互耗时。

### 已知问题 / 阻塞 / 待人工决策

- 无。

---

## F02：市场数据

### 最近动作

- 已将初始化任务进度区的任务类型切换控件从右侧分段按钮改为左侧下拉框；已运行前端 `npm.cmd run build` 成功；已用 Playwright 检查下拉选择“热点复盘”会请求对应 latest 任务接口。
- 已将麦蕊历史行情拉取逻辑从逐股预查 `hscp/gsjj` 公司简介改为直接请求历史行情；当历史行情返回 `{"error":"数据不存在"}` 时按未上市/无数据股票跳过，其他非数组响应仍作为失败处理；已运行 `.\.venv\Scripts\pytest.exe backend\tests\test_market_data_5m_import.py`，结果 4 passed；已运行 `.\.venv\Scripts\pytest.exe backend\tests\test_v2_initializer.py`，结果 28 passed；已运行前端 `npm.cmd run build` 和 `npm.cmd run check:playwright` 成功。
- 已将麦蕊数据源配置从单独 licence 文本升级为 `data/config/mairui.json`，页面可保存 licence、请求速率阈值和并发拉取数；令牌桶速率从该 JSON 配置读取；`MARKET_DATA` 初始化任务按配置并发拉取历史行情并串行写入 DuckDB；麦蕊 HTTP 诊断日志输出脱敏 endpoint、`rate_limit`、`rate_wait`、网络耗时、总耗时和响应字节数；已运行 `.\.venv\Scripts\pytest.exe backend\tests\test_mairui_config.py backend\tests\test_market_data_rate_limit.py backend\tests\test_v2_initializer.py`，结果 37 passed；已运行 `.\.venv\Scripts\pytest.exe backend\tests\test_market_data_5m_import.py`，结果 4 passed；已运行前端 `npm.cmd run build` 和 `npm.cmd run check:playwright` 成功。
- 已移除 SQLite schema 中未使用的 `task_item_info` 建表语句，保留基于 `task_info` 合成的任务进度接口；已运行 `.\.venv\Scripts\pytest.exe backend\tests\test_sqlite_models_smoke.py`，结果 3 passed；已运行 `.\.venv\Scripts\pytest.exe backend\tests\test_v2_initializer.py`，结果 28 passed。
- 已将麦蕊 HTTP 非 200 响应标记为任务级致命错误：数据源层抛出 `MairuiHttpStatusError`，`MARKET_DATA` 初始化遇到该错误直接失败任务，不再继续后续股票；并发拉取改为窗口式提交，避免一次性排入全部股票请求；已运行 `.\.venv\Scripts\pytest.exe backend\tests\test_market_data_rate_limit.py`，结果 7 passed；已运行 `.\.venv\Scripts\pytest.exe backend\tests\test_v2_initializer.py`，结果 29 passed；已运行 `.\.venv\Scripts\pytest.exe backend\tests\test_market_data_5m_import.py`，结果 4 passed。
- 已将个股详情页价格图指标从 MA 改为 `EXPMA(8,17,21,55)`，MACD 参数改为 `(8,17,6)`，KDJ 参数改为 `(6,3,3)`；后端指标序列字段同步改为 `expma8`、`expma17`、`expma21`、`expma55`；已新增 `backend\tests\test_stock_detail_indicators.py` 覆盖新指标口径；已运行 `.\.venv\Scripts\pytest.exe backend\tests\test_stock_detail_indicators.py backend\tests\test_market_data_importer.py`，结果 2 passed；已运行前端 `npm.cmd run build` 成功。

### 下一步

- 当前不是活跃需求；后续如继续市场数据工作，再更新 [F02：市场数据](F02-market-data.md)。

### 已知问题 / 阻塞 / 待人工决策

- 无。
