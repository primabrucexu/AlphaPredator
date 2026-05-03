# 市场数据按交易日统一抓取改造计划

> 说明：本文档是实施计划文档。目标是把“全量初始化”和“每日增量更新”统一为**按交易日、全市场批量抓取**，不再采用逐股票循环拉取作为主路径。

## 1. 背景

当前链路存在策略分叉：

- 初始化：以逐股票拉历史K线为主
- 增量：以按日期拉全市场为主

这会带来：

- 逻辑不一致、维护成本高
- 调用次数偏高（股票数 x 天数）
- 失败重试和幂等处理复杂

另外还有一个字段口径问题：

- Tushare `daily` 返回了当日成交额（`amount`），但当前日K主链路主要保存 `volume`，导致“逐日成交额”在部分展示场景缺失或只能用快照近似替代。

## 2. 目标

1. 初始化与增量统一为“按交易日”抓取。
2. 共享同一套清洗、校验、写入规则。
3. 保持接口路径尽量不变，优先兼容迁移。
4. 降低 API 调用量并提升可重试性。
5. 补齐“日K维度成交额”字段，确保存储与展示完整。

## 3. 现状 vs 目标链路

### 3.1 现状

- 初始化：
  - 上传股票池 -> 拉当日快照 -> 逐股拉区间K线 -> 聚合后导入
- 增量：
  - 拉当日全市场快照 + 当日全市场K线 -> upsert

### 3.2 目标

统一为：

`确定交易日序列 -> 按每个 trade_date 批量抓取全市场 -> 本地过滤/清洗 -> 日级幂等写入 -> 重建最新快照`

仅保留一处差异：

- 初始化：交易日范围来自 `start_date..end_date`
- 增量：交易日范围来自 `DB最新交易日+1 .. 最新可用交易日`

## 4. 文件级改造清单

## 4.1 `backend/app/modules/market_data/data_source.py`

- 新增/规范日级抓取函数（建议）：
  - `fetch_market_daily_snapshot_by_date(trade_date, use_uploaded_universe, market_filters)`
  - `fetch_market_daily_bars_by_date(trade_date, use_uploaded_universe, market_filters)`
- 新增交易日工具函数（建议）：
  - `list_trade_dates(start_date, end_date)`（基于 trade_cal）
- `fetch_daily_bars_for_stock(...)` 保留为兼容兜底，不作为主链路。
- 日K映射字段补齐：
  - 从 `daily.amount` 映射并输出 `turnover_amount_billion`（统一单位：亿元）

## 4.2 `backend/app/modules/market_data/initializer.py`

- `_run_initialization` 从“逐股票循环”切换为“逐交易日循环”。
- 进度展示从“按股票 processed_stocks”扩展为“按交易日 processed_trade_dates”（可兼容保留旧字段）。
- 避免 `all_bars` 全历史常驻内存，改为日级分批处理。

## 4.3 `backend/app/modules/market_data/updater.py`

- `run_daily_update` 改为“补齐缺失交易日区间”，不是只更新当天。
- 复用与初始化相同的日级抓取与清洗函数。
- 结果结构增加日期范围信息。
- 日K upsert 时同步写入每日成交额字段，避免仅快照有成交额。

## 4.3.1 存储层字段改造（新增）

- `backend/app/db/duckdb.py`
  - `daily_bars` 新增列：`turnover_amount_billion DOUBLE`（单位：亿元）
- `backend/app/modules/market_data/importer.py`
  - `daily_bars.csv` 必填字段新增 `turnover_amount_billion`
  - DuckDB 插入语句同步扩展
- `backend/app/modules/market_data/service.py` / `backend/app/schemas/market.py`
  - `DailyBar` 输出模型补齐 `turnover_amount_billion`
- `frontend/src/lib/api.ts`
  - `DailyBar` 类型补齐 `turnover_amount_billion`

## 4.4 `backend/app/schemas/data_init.py`

- `UpdateResult` 增加：
  - `start_trade_date`
  - `end_trade_date`
  - `processed_trade_dates`
  - （兼容）保留原字段一段时间

## 4.5 `backend/app/api/routes/data_init.py`

- `/update` 响应按新 `UpdateResult` 返回多交易日补齐结果。

## 4.6 `frontend/src/lib/api.ts` 与 `frontend/src/pages/InitializePage.tsx`

- 更新 `UpdateResult` 类型与显示文案：
  - 从“单日更新”改为“区间补齐（N个交易日）”。

## 4.7 `frontend/src/pages/StockDetailPage.tsx`

- Hover 信息面板中的成交量区补充“当日成交额（亿元）”。
- 如有换手率当日值可用，同步展示；无则回退为 `--`。

## 5. 数据一致性与幂等规则

1. 以 `(trade_date, stock_code)` 作为日快照幂等键。
2. 以 `(stock_code, trade_date)` 作为日K幂等键（逻辑上；物理层可先删后插）。
3. 每个交易日写入前先清该日旧数据，再写新数据。
4. 快照与K线必须同日；任一为空时该日标记失败并可重试。
5. `market_snapshot.json` 始终基于“最后一个成功写入交易日”重建。
6. 当日成交额口径统一为“亿元”，快照与日K字段单位一致。

## 6. 性能与内存策略

- 按日分块处理，避免全历史聚合到单个大列表。
- 单日抓取中复用同一批数据构造快照与日K，减少重复请求。
- 事务按日提交，失败可从下个未完成交易日继续。
- 统一由数据源层执行全局限速，避免多处节流分叉。

## 7. 测试改造计划

重点文件：`backend/tests/test_phase29_initializer.py`

- 将 updater mock 从 `fetch_daily_bars_for_stock` 改为日级批量函数。
- 新增初始化测试：
  - 验证“按交易日循环”次数
  - 非交易日跳过行为
  - 验证 `turnover_amount_billion` 在日K链路中被写入
- 新增增量测试：
  - 当数据库落后多日时可一次补齐
  - 重跑不重复写入（幂等）
  - 验证补齐多日时成交额字段不缺失
- 新增失败恢复测试：
  - 中间某日失败后，重跑可补齐且不破坏已完成数据

补充：`data_source` 单测覆盖

- 交易日列表计算
- 全市场日级抓取后按股票池过滤
- 字段映射完整性
 - `amount -> turnover_amount_billion` 的单位换算正确性

## 8. 分阶段实施建议

1. 在 `data_source` 增加日级统一接口（旧接口暂保留）。
2. 初始化切换到新接口（可加开关灰度）。
3. 增量切换到“按区间补齐”。
4. 更新 schema/API/前端类型；短期兼容旧响应字段。
5. 清理逐股主路径与过时逻辑。

## 9. 风险与回退

- 风险：交易日列表错误导致漏补。
  - 回退：临时切回仅“更新当天”模式。
- 风险：日级写入改造引入状态不一致。
  - 回退：保留“抓取后一次性导入”兜底路径。
- 风险：前端依赖旧 `UpdateResult`。
  - 回退：后端短期同时返回新旧字段。

## 10. 验收标准

1. 初始化主流程不再依赖逐股 `daily(ts_code=...)`。
2. 增量更新支持自动补齐缺失交易日。
3. 初始化与增量输出字段口径一致。
4. 多次重跑结果一致、无重复写入。
5. 在当前限速设置下（`tushare_rate_limit=50`）任务可稳定执行。
6. 前端初始化页可展示区间补齐结果。
7. 详情页 hover 可展示“当日成交额（亿元）”，且与日K同日数据一致。
