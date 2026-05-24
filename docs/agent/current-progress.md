# 当前执行进度

> **用途**：记录 agent 每次会话的执行状态，弥补 AI 无持久记忆的缺陷。
> **维护规则**：每次会话结束时由 agent 更新；只记录事实状态，不写主观判断。
> **格式**：当前阶段 → 上一步完成了什么 → 这一步做了什么 → 下一步要做什么 → 已知问题/阻塞/待人工决策内容

---

## 当前阶段

**Phase 2：短线情绪总览**

---

## 上一步做了什么

- 已完成 Phase 1 底座并轨（任务表、DuckDB 行情写入、数据源 contract、amount 口径修正、stock_list 字段收敛）。

## 这一步做了什么

**重构 SentimentOverviewPage（Task 5 推进）**：

按用户需求重新设计短线情绪总览页面，改动如下：

1. **删除**：查询条件卡片、当日热点板块排行表格。
2. **ST 开关**：页面右上角新增「显示 ST 数据」Switch，默认关闭。
   - 后端：`get_hot_sector_history` 新增 `exclude_st: bool = True` 参数，在 `_build_hot_sector_history_sectors` 过滤 ST 股票；路由同步添加 Query 参数。
   - 前端：`getHotSectorHistory(days, excludeSt)` 同步更新；ST 从名称是否含 `ST` 字符判断，streak 层过滤在前端完成。
3. **热点趋势图**：固定拉取 60 个交易日，添加 ECharts `dataZoom` 底部滑动条，默认展示近 20 日，非交易日不存在数据自然不展示。
4. **复盘数据展示改造**：将“默认展示图片”改为“默认展示数据库表格（`daily_hot_info`）”。
   - 后端新增接口：`GET /api/market/hot-review-table`（支持 `trade_date` + `exclude_st`），返回字段：`stock_code`、`stock_name`、`limit_up_time`、`streak_text`、`hot_theme`、`reason`、`short_reason`。
   - 前端新增 `getHotReviewTable()` 并在 `SentimentOverviewPage` 中用表格展示数据库内容。
5. **复盘图片改为按钮弹窗查看**：在表格右上角提供「查看复盘图片」按钮，点击后以 Modal + `Image.PreviewGroup` 形式查看大图，不再默认占据页面主区域。
6. **复盘表格可读性增强**：
   - 新增关键词搜索框（支持按股票、题材、OCR 摘要、涨停解析等字段过滤）；
   - `short_reason` 与 `reason` 列支持“展开/收起”长文本显示。
7. **复盘表格排版对齐图片风格**：
   - 改为按“板块”分组展示，并通过行合并显示 `板块`/`涨停家数`；
   - 板块顺序按涨停家数从高到低排序；
   - 板块内个股按连板数（高到低）和涨停时间排序。
8. **页面布局改为左右结构**：
   - 左侧：`热点板块趋势` + `连板情况`；
   - 右侧：`涨停信息表格`（保留日期选择、关键词过滤、图片弹窗入口）；
   - 使用响应式栅格（窄屏自动上下堆叠）。
9. **连板模块**重构为三部分：
   - Card extra 增加 DatePicker 支持历史日期探索；
   - **当日连板分布**：2板 / 3板 / 4板+ 家数 stat card；
   - **连板晋级成功率**：对比前一交易日数据，计算 2→3、3→4、4+→更高 的转化率（前端计算）；
   - **连板明细**：完整列表含跳转个股详情链接。

全量验证：后端测试 **90 passed**；前端 `npm run build` 通过。

**本次会话新增改动**（全部已验证）：
1. **关键词搜索**：在复盘表格右上角新增Search框，支持按股票/题材/OCR/解析内容过滤。
2. **长文本展开**：`OCR 摘要`、`涨停解析` 列支持"两行折叠"和"点击展开全文"。
3. **板块分组排版**：将表格改为按板块分组显示，板块按涨停家数降序排列，使用行合并进行视觉优化。
4. **左右布局**：页面от纵向堆叠改为响应式左右栅格（左14列：趋势+连板，右10列：涨停表格）。
5. **ST 过滤 bug 修复**：前端补上对复盘表的 ST 过滤保险，当开关关闭时前端确保不显示 ST 股票。
## 下一步要做什么

- 补齐首页热点复盘模块（Task 6）：`HomeSearchPage.tsx` 增加轻量版热点复盘入口（最新交易日板块列表 + 复盘图片入口 + 跳转 `/sentiment`）。
- 验证 JYGS 鉴权前置校验是否完善（Task 4）。

## 本次会话

**个股详情页新增「涨停历史」模块，与热点情绪联动**：

改动概要：
1. **后端 query**（`market_queries.py`）：新增 `get_limit_up_history_by_stock`，按 `stock_code` 从 `daily_hot_info` 查询最近 N 条涨停记录（降序）。
2. **后端 schema**（`market.py`）：新增 `StockLimitUpHistoryRow`、`StockLimitUpHistoryResponse`。
3. **后端 service**（`service.py`）：新增 `get_stock_limit_up_history` 方法，规范化 stock_code 后调用 query 并返回响应。
4. **后端路由**（`market.py`）：新增 `GET /api/market/stocks/{stock_code}/limit-up-history?limit=20`。
5. **前端 api.ts**：新增 `StockLimitUpHistoryRow`、`StockLimitUpHistoryResponse` 类型及 `getStockLimitUpHistory` 函数。
6. **前端 StockDetailPage.tsx**：新增 `LimitUpHistoryCard` 组件 + `useQuery`；K 线图卡片下方展示「涨停历史」表格，包含涨停日期、涨停时间、连板情况（Badge 带颜色）、题材（Tag）、涨停解析（支持展开收起）、OCR 摘要（Tooltip 截断）。

**验证**：后端 89 passed（无回归），前端 `npm run build` 通过。

1. **`limit_up_time` 未填充问题**：大多数股票来自 `field` API，该 API 不返回 `action_info.time`；只有少数来自 `list` API 的推荐股有时间。复盘图片每行包含涨停时间（`HH:MM:SS`），但旧代码把时间格式视为"纯数字/时间"直接跳过，没有提取。
2. **`short_reason` 语义修正**：`short_reason` 应存储图片中每行对应股票的涨停简要概括（最右列关键词标签），而非整张图片 OCR 后的缩写。旧代码已有按行解析的逻辑，但需要与时间提取协同工作。

**改动**（`backend/app/modules/market_data/jygs_review.py`）：
- `_parse_ocr_stock_summaries`：返回类型从 `dict[str, str]` 改为 `dict[str, dict[str, str]]`，新增 `_TIME_PAT = re.compile(r'^\d{1,2}:\d{2}(:\d{2})?$')` 正则，对每行同时提取涨停时间（`time`）和关键词（`summary`）。
- `_process_hot_review_ocr`：处理新返回格式；若 OCR 解析出时间，则在更新 `short_reason` 的同时更新 `limit_up_time`（仅在数据库中该字段为空时）。

**验证**：89 passed（无回归）。

---

**修复 `daily_hot_info.stock_code` 列类型（INTEGER → TEXT）**：

- 在 `backend/app/db/sqlite.py` 新增 `_migrate_daily_hot_info_stock_code()`，检测 INTEGER 类型时重建表并用 `PRINTF('%06d')` 补零。4408 行受损数据已修复，所有代码为 6 位字符串。

**修复 JYGS_REVIEW 任务拉取周末脏数据问题**：

- **根因**：`_generate_date_list` 生成全日历日期（含周末），JYGS API 被请求非交易日时返回上一交易日数据，但代码用请求日期（周末）存库，造成同一批数据被重复写入 3 个日期（周五、周六、周日），且周末数据的 `name` 字段均为空。
- **修复**：`_generate_date_list` 增加 `weekdays_only: bool = False` 参数；JYGS_REVIEW 的两个调用点均改为 `weekdays_only=True`，跳过周六/周日。
- **数据清理**：删除了历史 6 个周末日期共 782 条脏数据（2026-05-09/10、05-16/17、05-23/24）。
- 新增测试 `test_generate_date_list_weekdays_only_skips_weekends`。
- **89 passed**（新增 1 个测试）。

---

## 已知问题/阻塞/待人工决策内容

**已修复**：
- ST 过滤 bug：复盘表格虽然通过后端 API 参数 `exclude_st=true` 进行过滤，但前端的 `filteredReviewRows` 中缺少对应的保险过滤。追加了前端层的 ST 过滤逻辑（与连板数据的过滤方式保持一致），确保 `showSt=false` 时无论后端如何返回，前端都能过滤掉 ST 股票。
- ST 筛选完整联动：
  * 后端：为 `get_limit_up_streaks` 方法新增 `exclude_st` 参数，在数据处理层进行 ST 股票过滤。
  * 后端路由：`/limit-up-streaks` 端点新增 `exclude_st` Query 参数。
  * 前端 API：`getLimitUpStreaks` 函数新增 `excludeSt` 参数。
  * 前端页面：连板查询的 queryKey 中加入 `showSt`，并传递 `!showSt` 给后端，确保页面 ST 开关改变时三个板块同步重新加载数据。
  * 结果：现在改变页面顶部的 ST 开关时，左上热点趋势、左下连板情况、右侧涨停信息表都会实时同步响应。

全量验证：后端 90 passed，前端构建通过。
