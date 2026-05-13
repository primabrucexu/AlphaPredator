# 当前执行进度

> **用途**：记录 agent 每次会话的执行状态，弥补 AI 无持久记忆的缺陷。
> **维护规则**：每次会话结束时由 agent 更新；只记录事实状态，不写主观判断。
> **格式**：当前阶段 → 上一步完成了什么 → 下一步要做什么 → 已知问题/阻塞

---

## 当前阶段

**Phase 2：短线情绪总览**

---

## 上一次会话（2026-05-10）完成的工作

### 本次会话（2026-05-11）完成的工作

- 前端路由补齐：`frontend/src/routes/router.tsx` 新增 `/sentiment` 路由并接入 `SentimentOverviewPage`。
- 前端导航补齐：`frontend/src/components/layout/AppShell.tsx` 侧边栏新增“短线情绪”菜单入口，用户可直接进入热点复盘页面。
- 前端页面改造：`frontend/src/pages/SentimentOverviewPage.tsx` 已补齐 Phase 2 关键展示块：
  - 新增“查询条件”区：趋势范围（5/7/10/20 日）、连板最小板数、连板交易日。
  - 新增“当日热点板块排行”表格（排名、热度、趋势、最高连板）。
  - 热点趋势热力图支持按所选天数动态查询与展示。
  - 连板列表支持按最小板数和交易日条件查询。
- 热点分数口径调整（按用户要求）：`backend/app/modules/market_data/hot_sector_importer.py` 中 `heat_score` 改为“涨停家数（limit-up
  count）”，不再使用启发式热度公式。
- 前端文案同步：`frontend/src/pages/SentimentOverviewPage.tsx` 与 `frontend/src/pages/MarketOverviewPage.tsx`
  将“热度”展示统一改为“涨停家数”。
- 输出方案文档：`docs/agent/phase-phase2-multi-api-hot-review-plan.md`，拆解多 API 聚合模型、口径统一与历史回填策略。
- 更新文档索引：`docs/docs.md` 新增上述方案文档入口。
- `docs/agent/phase2-sentiment-overview-plan.md` 已按 `docs/human/hot-review.md` 全量重写，明确：
  - 全量抓取跟随行情初始化，增量仅 `12:02` / `15:32`。
  - 首页热点复盘模块展示复盘图片，并支持个股跳转详情行情页。
  - 多日对比使用板块“每日涨停家数”折线图，默认近 5 日，支持 3/10/20 快选与日期范围筛选。
- 代码实现（按用户“开始改代码”要求）已推进：
  - 后端新增复盘图片查询能力：`GET /api/market/hot-review-images`。
  - `jygs_review.py` 将 `diagram-url` 结果写入 `parse_notes.summary_image_urls`，供前端读取多图。
  - 前端 `SentimentOverviewPage.tsx` 新增“当日复盘图片”区块，支持“上一张/下一张”左右切换。
  - 前端 `HomeSearchPage.tsx` 增加“热点复盘”入口按钮（首页入口 + 独立页）。
  - 新增/更新测试：`backend/tests/test_phase2_hot_review_api.py` 覆盖图片列表返回。
  - 已完成验证：`pytest backend/tests/test_phase2_hot_review_api.py` 通过；`frontend npm run -s build` 通过。
- **关键修正**：按 `docs/human/data-storage.md` 规范改造数据库表设计：
  - 新增 `daily_hot_pic` 表（涨停简图，对应复盘图片）。
  - 新增 `daily_hot_info` 表（涨停解析，对应个股涨停事实）。
  - 重构 `sync_hot_review_by_date()` 改为直接写入规范表，移除对复杂 5 张聚合表的依赖。
  - 移除 `daily_hot_pic`、`daily_hot_info` 从 obsolete_tables 列表（之前错误的标记为过时）。
  - 新增单元测试 `test_daily_hot_pic_and_daily_hot_info_tables` 验证规范表结构。
  - 已验证：新旧表并存不冲突，两个测试用例均通过。

### 单日拉取日志增强（热点数据 / 交易数据）

- `backend/app/modules/market_data/jygs_review.py`：为 `_post_json` 增加请求开始/响应元数据日志，并在 JSON 解析失败时输出
  `status/content_type/pos/line/col/body_preview`。
- `backend/app/modules/market_data/jygs_review.py`：为 `sync_hot_review_by_date` 增加开始/完成日志（交易日、写入统计）。
- `backend/app/modules/market_data/initializer.py`：为 `_fetch_daily_raw` 增加开始、空响应、原始行数、解析后行数日志。
- `backend/app/modules/market_data/data_source.py`：为 `_rate_limited_call`
  增加失败日志（func、trade_date、ts_code、start/end_date）。
- 已完成本地语法校验：`python -m compileall`（上述 3 个模块）通过。

### 韭研请求头对齐浏览器抓包

- `backend/app/modules/market_data/jygs_review.py`：`_post_json` 已按浏览器抓包补齐请求头（`Accept`、`Origin/Referer`、
  `sec-fetch-*`、`sec-ch-ua*`、`platform`、`timestamp`、`token`、Windows Edge UA）。
- `timestamp` 改为每次请求动态毫秒值；`token/platform` 按当前抓包值对齐。
- 已完成本地语法校验：`python -m compileall backend/app/modules/market_data/jygs_review.py` 通过。

### 韭研公社登录链路改造（按用户要求切换到 Playwright）

- 后端 `backend/app/api/routes/jygs.py`：代理登录路由改为下线提示（410），新增 `POST /api/jygs/auth/login/playwright`。
- 后端新增 `backend/app/modules/jygs/playwright_login.py`：启动本机 Playwright 浏览器，等待用户在网页端登录并捕获
  `SESSION`。
- 登录成功后复用现有 `save_credentials` + `check_credentials_valid` 完成落库与探针校验；失败会自动清理并返回错误。
- 前端 `frontend/src/pages/InitializePage.tsx`：移除代理弹窗/手动 SESSION 输入，改为 “Playwright 一键登录”。
- 前端 `frontend/src/lib/api.ts`：新增 `loginJygsWithPlaywright()` 调用登录接口。
- 已完成本地编译验证：`python -m compileall ...` 和 `npm run -s build` 均通过。

### 阶段切换

### 阶段切换

- 用户宣布 Phase 1 阶段性完成，正式进入 Phase 2。
- 对 Phase 2 已实现内容做了全面 gap 分析。
- 输出了 Phase 2 方案设计文档：`docs/agent/phase2-sentiment-overview-plan.md`。
- 更新了 `docs/docs.md` 索引，新增 Phase 2 方案文档条目。

### Phase 2 现有进展（截至本次会话）

| 模块 | 状态 |
|------|------|
| `backend/app/modules/market_data/hot_sector_importer.py` | ✅ 完整实现，测试通过 |
| SQLite 5 张热点表（schema） | ✅ 完整定义 |
| `service.py` 热点数据整合进 `get_market_overview()` | ✅ 完成 |
| `MarketOverviewPage.tsx` 展示当日热点板块 | ✅ 基础实现完成 |
| `bin/import-hot-sector-images.sh` 导入脚本 | ✅ 已存在 |

---

## 下一步：待完成任务

详细设计见 `docs/agent/phase2-sentiment-overview-plan.md`。

### Batch A：Phase 1 遗留修复（建议优先）

#### 已核验：`daily_bars` 的 `is_up_limit` / `is_down_limit` 已存在并已写入
- `duckdb_storage.py` 已定义字段与补列 migration。
- `initializer.py` 已写入对应布尔字段。
- 本地 DuckDB 已核验两字段存在且有数据。

#### 已完成：`stock_universe` → `stock_list` 命名清理
- 已完成数据源函数与相关测试命名替换。
- SQLite 保留兼容迁移逻辑，旧表会自动重命名到 `stock_list`。

### Batch B：后端 — 热点历史 API
- 新增 `GET /market/hot-sectors/history?days=7` 端点
- 响应包含多日热点板块排行 + trend_tag + 代表性股票

### Batch C：后端 — 连板查询 API
- 新增 `GET /market/limit-up-streaks?trade_date=...&min_boards=2` 端点
- 数据来源：`hot_sector_stock_facts`（`board_count` 字段）

### Batch D：前端 — 短线情绪总览页面

- ✅ 已补齐页面入口：`SentimentOverviewPage.tsx` 路由 `/sentiment` + 侧边栏菜单“短线情绪”
- 区块 A：热点板块趋势热力图（多日 × 多板块）
- 区块 B：当日热点排行（含代表股、最高板数）
- 区块 C：近期连板龙头列表（按 board_count 降序，分日展示）

---

## 本次人工决策（2026-05-05）

- Phase 1 宣布阶段性完成，进入 Phase 2。
- 已确认 Phase 1 两项遗留均已处理：`is_up_limit` 已核验完成，命名清理已完成。
- 韭研登录方式改为 Playwright 一键登录，不再使用代理登录页面流程。

## 本次人工决策（2026-05-11）

- 用户反馈“缺少热点复盘页面入口”，本次先完成路由与导航可达性补齐。
- 用户确认“先输出多 API 热点复盘改造方案文档”，本次先不继续扩散代码改造。
- 用户要求按 `docs/human/hot-review.md` 重新编写 Phase 2 相关内容，先完成方案文档重写对齐。
- 用户确认展示形态为“首页入口 + 独立页”，无需将完整复盘模块直接内嵌首页。
- 用户确认复盘图片展示为“当日多张图，支持左右切换”。
- 用户确认“全量抓取跟随行情初始化”暂不改动，先处理其他差距项。
- 用户指出代码未按 `docs/human/data-storage.md` 设计数据库表，本次完成改正：采纳规范的 `daily_hot_pic` 和 `daily_hot_info`
  两表方案。

---

## 下一步待做任务（优先级排序）

Phase 2 剩余差距（按优先级）：

1. **改造趋势图从热力图→折线图**：对齐 `hot-review.md` "某板块每日涨停家数变化"的折线展示要求
2. **调整趋势范围默认值**：改为近 5 日默认，快捷选项改为 3/10/20（当前为 7/5/7/10/20）
3. **增量抓取调度接入**：让 `run_incremental_sync_if_due()` 真正在应用启动后自动触发（12:02、15:32 时点）
4. **鉴权校验前置**：抓取前强制调用 `check_jygs_auth_available()`，失效凭据时阻断并提示重登
5. **历史 heat_score 回填**：执行一次性脚本，把旧启发式分数重算为涨停家数

---

## 本次会话（2026-05-12）完成的工作

- 输出后续阶段数据库建模分析文档：`docs/agent/phase-phase3to5-database-modeling.md`。
- 分析范围覆盖 Phase 3（操作复盘）、Phase 4（学习用户选股模式）、Phase 5（AI 自主选股）。
- 识别到与 `docs/human/data-storage.md` 的关键落地缺口：`pick_models` 与 `user_stock_samples` 尚未在当前
  `backend/app/db/sqlite.py` 建表。
- 更新文档索引：`docs/docs.md` 已新增该分析文档入口。
- 访问 `https://mairuiapi.com/hsdata` 并生成 OpenAPI 3.0 文档：`docs/agent/mairui-hsdata.openapi.yaml`。
- 在 OpenAPI 中复用了公共参数组件：`licence`、`stock_code`、`market_code`、`date`、`st`、`et`、`lt`、`stock_codes` 等。
- 覆盖 55 个 HSData 接口路径，并按页面字段表生成对应响应 schema（`Resp01`~`Resp55`）。
- 更新文档索引：`docs/docs.md` 新增 HSData OpenAPI 文档入口。
- 重新抓取 `https://mairuiapi.com/hsdata` 页面并覆盖本地快照，确认 9 个页签共 55 个接口卡片。
- 修正 OpenAPI 参数建模口径：
  - URL 固定路径保留为字面量（如 `/hsstock/history/transaction`）。
  - 自然语言占位（如“股票代码(如000001)”“日期(如2020-01-15)”）映射为 **path 参数**（如 `{stock_code}`、`{date}`）。
  - `?st=...&et=...&lt=...`、`?stock_codes=...` 保留为 **query 参数**，不再错误转换为 path。
- 修正市场代码占位替换优先级：`股票代码.市场（如000001.SZ）` 统一映射为 `{market_code}`，避免被误替换成 `{stock_code}`
  残留注释文本。
- 按用户要求将 OpenAPI 公共参数 `Interval` 改为枚举：`5/15/30/60/d/w/m/y`，并在参数描述中补充其对应含义（分钟线/日周月年线）。
- 按用户要求将 OpenAPI 公共参数 `AdjustType` 改为枚举：`n/f/b/fr/br`，并在参数描述中补充其对应含义（不复权/前复权/后复权/等比前复权/等比后复权）。
- 按用户要求将响应 schema 名由 `Resp01`~`Resp55` 重构为语义化命名（如 `HsltListResponse`、
  `HsstockHistoryTransactionResponse`），并同步替换所有 `$ref` 引用。
- 按用户最新要求进一步业务化命名：将响应 schema 名改为业务语义（如 `StockListResponse`、`CompanyProfileResponse`、
  `KlineHistoryResponse`），并通过路径到 schema 的显式映射保证命名稳定。

## 下一步建议（建模相关）

1. 先完成 Phase 4 规范表最小落地：`pick_models`、`user_stock_samples`。
2. 明确 Phase 3 复盘记录的标准字段（操作事实 + 复盘总结是否拆表）。
3. 明确 Phase 5 `skill_spec_json` 的 schema 约束与版本兼容策略。
4. 如需对外发布 HSData OpenAPI，补充统一错误响应（4xx/5xx）与鉴权失败示例。
5. 按业务优先级为 55 个接口补充分组文档（例如实时交易/财务数据）与示例请求。

