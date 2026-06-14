# 当前执行进度

> **用途**：记录当前活跃需求和最近事实状态，帮助后续 agent / AI 助手接续工作。
> **维护规则**：每次会话结束时由 agent 更新；只记录事实状态，不写主观判断。
> **格式**：当前需求 → 最近动作 → 下一步 → 已知问题 / 阻塞 / 待人工决策。

---

## 当前需求

- 当前活跃需求文件：[F04：股票联动套利分析](F04-stock-linkage-arbitrage.md)
- 相关需求文件：[F02：市场数据](F02-market-data.md)

## 最近动作

- 已将项目文档体系从全局 Phase 规划调整为单需求文件驱动。
- 已删除 `docs/phase.md`。
- 已将以下功能设计文档迁移到 `docs/agent/Fxx-*.md`：
  - `docs/agent/F01-hot-review.md`
  - `docs/agent/F02-market-data.md`
  - `docs/agent/F03-trading-review.md`
  - `docs/agent/F04-pattern-pick.md`
- 已保留 `docs/human/api-docs/*`、`docs/human/data-model/AlphaPredator.dbml` 和 `docs/human/mysj.md` 作为人类维护硬规范。
- 已将前端 Playwright 冒烟脚本调整为优先调用本机 `msedge` / `chrome`，并支持通过 `PLAYWRIGHT_BROWSER_CHANNEL` 指定浏览器 channel。
- 已将后端 JYGS Python Playwright 登录入口调整为优先调用本机 `msedge` / `chrome`，并支持通过 `PLAYWRIGHT_BROWSER_CHANNEL` 指定浏览器 channel。
- 已通过 `tmp/jygs_playwright_capture.py` 捕获韭研公社真实浏览器请求，确认复盘接口 token 生成规则为 `md5("Uu0KfOB8iUP69d3c:" + timestamp)`。
- 已新增 JYGS 动态请求头构造模块，并将鉴权探针和复盘抓取请求从固定 token 改为动态 token。
- 已运行 `pytest backend\tests\test_jygs_request_headers.py backend\tests\test_jygs_playwright_browser.py`，结果 6 passed；已运行 `pytest backend\tests\test_v2_initializer.py -k jygs`，结果 1 passed。
- 已删除本地 `data/status/jygs-flow-trace.jsonl`，并将 JYGS flow trace 默认开关改为关闭。
- 已新增 `docs/agent/F04-stock-linkage-arbitrage.md`，记录 5 分钟级别股票联动套利分析的触发口径、B 股票观察口径、输出格式和待确认问题。
- 已更新 `docs/guide.md`，加入 F04 文档索引。
- 已完成 F04 非行情表数据库设计审批，并由用户同步到 `docs/human/data-model/AlphaPredator.dbml`。
- 已实现 F04 第一版后端核心：DuckDB schema 初始化、5 分钟 K 拉取函数、5 分钟 K 写入函数、联动回测服务、创建回测 API、结果查询 API。
- 已将 F04 联动回测从同步 API 改为后台任务执行模式：创建任务后异步执行，任务状态保存到 `stock_linkage_backtest_job`，API 支持任务详情、任务列表和结果查询。
- 已新增前端“联动套利”页面并接入侧边导航；页面已支持提交后台任务、轮询任务状态、任务成功后加载结果。
- 已运行后端 F04 相关测试，结果 14 passed；已运行前端 `npm.cmd run build` 成功；已用 Playwright + 本机 Edge 冒烟检查 `/stock-linkage` 页面标题、模式和按钮渲染。

## 下一步

- 使用真实 5 分钟 K 数据执行一次小范围手动 A 股票回测，检查后台任务状态流转、结果数、概率排序和页面交互耗时。
- 暂停后可继续补齐首页热点复盘模块：`HomeSearchPage.tsx` 增加轻量版热点复盘入口，包含最新交易日板块列表、复盘图片入口和跳转 `/sentiment`。

## 已知问题 / 阻塞 / 待人工决策

- 旧的 Phase 历史文档仍保留在 `docs/agent`，当前仅作为历史资料，不作为新需求命名模板。
