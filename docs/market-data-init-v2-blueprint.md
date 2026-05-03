# 市场数据初始化 V2 方案（全新重构草案）

> 本文档用于完整记录新的初始化思路。该方案以“完全抛弃现有初始化代码实现”为前提，仅保留业务目标与数据结果要求。

## 1. 目标与范围

### 1.1 业务目标

- 导入从 `20240101` 到当前日期的全市场交易日线数据。
- 核心数据获取方式固定为：`tushare.daily(trade_date=YYYYMMDD)`。
- 初始化页面支持手动选择导入时间范围。
- 页面可展示当前系统已入库的数据日期范围。
- 支持指定某一天重复导入（重导）。

### 1.2 非功能要求

- 按日期递增顺序执行，便于前端进度条按时间线展示。
- 单日数据必须完整写入成功后，才能进入下一日。
- 全流程仅在内存中处理，不允许 CSV/中间文件中转。
- 任务过程可追踪、可恢复、可审计。

### 1.3 约束前提

- 交易日判断使用 ChnCal。
- 任务状态与已入库范围以 SQLite 为准。
- 同一时刻仅允许一个初始化任务处于运行态（防并发冲突）。

## 2. 核心设计原则

1. **日期驱动**：先生成完整日期列表，再逐日处理。
2. **交易日优先**：每个日期先判定是否交易日，非交易日仅记录跳过。
3. **单日原子提交**：一个交易日的数据写入要么全部成功，要么全部回滚。
4. **内存直写**：抓取后直接写库，不落盘中转。
5. **幂等可重导**：同一天可重复导入且不会产生重复脏数据。

## 3. 初始化全流程（V2）

### 阶段 A：任务创建与范围解析

- 前端提交 `start_date`、`end_date`（格式 `YYYYMMDD`）。
- 后端校验日期合法性与范围有效性。
- 生成闭区间日期列表（升序）。
- 创建任务主记录，初始化进度统计。

### 阶段 B：逐日执行（升序）

对列表中的每一天 `D` 执行：

1. 使用 ChnCal 判断 `D` 是否为交易日。
2. 若非交易日：写入日明细 `SKIPPED_NON_TRADING`，推进进度。
3. 若是交易日：调用 tushare `daily(trade_date=D)` 获取当日全量数据。

### 阶段 C：单日原子入库

对交易日数据在单日事务中执行：

1. 清理或覆盖当日旧数据（按 `trade_date=D`）。
2. 批量写入当日新数据。
3. 完整性校验（如行数 > 0、关键字段非空、主键冲突为 0）。
4. 校验通过则提交事务；失败则回滚并标记任务失败。

### 阶段 D：任务收敛与展示

- 每日结束后更新任务进度与当前处理日期。
- 所有日期处理完成后更新任务状态为成功。
- 计算并更新“已入库范围”（最小/最大 `trade_date`）。
- 前端轮询查看任务进度与失败明细。

## 4. 数据模型（SQLite）

## 4.1 任务主表 `init_task`

建议字段：

- `task_id` (PK)
- `mode` (`RANGE` | `REIMPORT_DAY`)
- `start_date`
- `end_date`
- `status` (`PENDING` | `RUNNING` | `SUCCESS` | `FAILED` | `CANCELED`)
- `total_days`
- `processed_days`
- `trading_days`
- `done_trading_days`
- `current_date`
- `error_message`
- `created_at`
- `started_at`
- `finished_at`

## 4.2 日执行明细表 `init_task_day`

建议字段：

- `task_id`
- `trade_date`
- `is_trading_day`
- `status` (`PENDING` | `SKIPPED_NON_TRADING` | `FETCHING` | `WRITING` | `SUCCESS` | `FAILED`)
- `row_count`
- `started_at`
- `finished_at`
- `error_message`

约束建议：

- 唯一键：`(task_id, trade_date)`

## 4.3 行情事实表 `market_daily_quote`

建议字段（按 tushare daily 对齐）：

- `trade_date`
- `ts_code`
- `open`
- `high`
- `low`
- `close`
- `pre_close`
- `change`
- `pct_chg`
- `vol`
- `amount`
- `updated_at`

约束建议：

- 主键：`(trade_date, ts_code)`
- 索引：`trade_date`

## 4.4 范围元数据表 `data_range_meta`（可选）

建议字段：

- `dataset` (PK)
- `min_trade_date`
- `max_trade_date`
- `trading_day_count`
- `updated_at`

用途：快速返回“当前已有数据范围”。

## 5. 状态机与进度口径

### 5.1 任务状态机

- `PENDING -> RUNNING -> SUCCESS`
- `RUNNING -> FAILED`
- `RUNNING -> CANCELED`（可选）

### 5.2 单日状态机

- 非交易日：`PENDING -> SKIPPED_NON_TRADING`
- 交易日成功：`PENDING -> FETCHING -> WRITING -> SUCCESS`
- 失败：任一步 `-> FAILED`

### 5.3 前端进度口径

- 主进度：`processed_days / total_days`
- 辅助指标：
  - `done_trading_days / trading_days`
  - `skipped_non_trading_days`
  - `failed_days`
- 展示字段：`current_date`、`current_phase`、最近错误信息

## 6. 幂等与重导策略

### 6.1 幂等目标

- 同一主键 `(trade_date, ts_code)` 仅有一条有效记录。
- 重复导入同一天不会产生重复行。

### 6.2 推荐策略：单日覆盖重导

- 在同一事务中先删除 `trade_date=D` 的历史行，再插入当日全量。
- 插入后执行完整性校验，通过才提交。

优点：

- 语义清晰。
- 易于保证“当日数据全量一致”。
- 非常适合补数和修复场景。

## 7. API 设计草案（初始化页面）

### 7.1 查询概览

- `GET /api/init/overview`
- 返回：
  - 当前运行任务信息
  - 最近一次任务状态
  - 已入库范围（min/max）
  - 累计交易日数

### 7.2 创建区间初始化任务

- `POST /api/init/tasks`
- 入参：`mode=RANGE`, `start_date`, `end_date`
- 出参：`task_id`, `status`

### 7.3 查询任务进度

- `GET /api/init/tasks/{task_id}`
- 返回：任务状态、进度百分比、当前日期、成功/跳过/失败统计、错误信息

### 7.4 查询任务日明细

- `GET /api/init/tasks/{task_id}/days`
- 返回：按日期分页的明细状态（便于定位失败日）

### 7.5 单日重导

- `POST /api/init/reimport-day`
- 入参：`trade_date`
- 行为：触发指定交易日覆盖重导

## 8. 实施里程碑

### M1（MVP）

- 日期范围选择 + 任务创建
- ChnCal 交易日判断
- tushare daily 按日抓取
- 单日事务写入 + 回滚
- 任务进度查询与前端进度条
- 已入库范围展示

### M2（稳定性增强）

- 网络抖动重试（限次 + 退避）
- 速率限制保护
- 失败日期快速重跑
- 关键日志与审计字段完善

### M3（治理与运维增强）

- 完整性校验规则扩展（空值率、阈值、抽样）
- 任务取消能力
- 告警通知（任务失败、长时运行）

## 9. 风险与对策

1. **tushare 接口限流/超时**
   - 对策：限速 + 重试退避 + 失败即停 + 断点可重导。
2. **交易日判断异常导致漏导**
   - 对策：固定 ChnCal 版本 + 关键节假日样例回归 + 单日重导兜底。
3. **单日部分写入导致不一致**
   - 对策：严格事务化写入，校验不过一律回滚。
4. **重复导入引入脏数据**
   - 对策：主键约束 + 单日覆盖策略 + 导入后行数核验。

## 10. 验收标准

满足以下条件视为方案达标：

1. 可从任意起止日期发起初始化，系统按日期递增执行。
2. 非交易日正确跳过，交易日通过 tushare daily 完成导入。
3. 同一天可重复导入且不产生重复数据。
4. 单日失败不会污染数据库，修复后可继续或重导。
5. 初始化页面可实时查看进度与当前已有数据范围。
6. 全流程无 CSV/文件中转，仅内存处理后直写数据库。

## 11. 结论

该方案将初始化能力重构为“日期驱动 + 交易日判定 + 单日原子写入 + 幂等重导”的统一链路，满足可观测、可恢复、可重复执行的长期演进要求，并与前端进度展示天然一致。

