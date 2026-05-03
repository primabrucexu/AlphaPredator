# A股涨跌停计算与落库设计文档

> 说明：本文档负责维护 A 股涨停价 / 跌停价及相关状态字段的计算、固化、版本化与导入补全规则。K 线页面如何使用这些字段见 `docs/kline-limit-color-design.md`；页面展示方式见 `docs/stock-detail-page-design.md`；当新增字段后需要重建市场数据时，流程见 `docs/market-data-reinitialize-workflow.md`；整体业务边界见 `docs/business-requirements.md`。

## 1. 文档边界

### 1.1 本文档负责
- 涨停价 / 跌停价计算口径
- 涨跌停状态字段设计
- 历史数据是否重算的原则
- 初始化与日更时的计算落点
- 规则版本化要求
- 股票导入时 `ST` 状态补全规则
- 异常场景处理规则

### 1.2 本文档不负责
- K 线页面如何渲染涨跌停颜色
- 涨跌停角标、提示面板或图表主题设计
- 盘中逐笔、盘口、Level2 等高频行情逻辑
- AI 如何使用涨跌停信息进行筛选或判断

## 2. 设计目标

涨跌停数据在 AlphaPredator 中不是一个前端临时推导值，而是一组需要稳定、可回溯、可复用的日度事实字段。

本设计目标：

1. 在初始化和每日更新时直接计算涨跌停相关数据，并与日行情一并保存。
2. 历史记录按“当日生效规则”固化，不因未来规则调整而漂移。
3. 通过规则版本字段保证口径可追溯。
4. 在缺少专用 `ST` 字段时，支持股票导入阶段基于名称补全 `is_st`。

## 3. 总原则

### 3.1 历史不可变原则
- 每个交易日的涨跌停数据，按**该交易日生效规则**计算并落库。
- 后续如果交易所规则变化，**历史数据默认不重算**。
- 只有以下场景才允许回填历史：
  1. 已确认历史计算存在程序错误；
  2. 业务明确发起专项回补，并保留版本说明。

### 3.2 先计算后查询原则
- 涨跌停相关字段应在数据初始化 / 日更写入前计算完成。
- 查询接口只读取已固化字段，不在查询时动态推算。

### 3.3 服务端判定优先原则
- 前端不按百分比自行推断涨停 / 跌停。
- 前端只消费服务端落库的 `limit_up_price`、`limit_down_price`、`is_limit_up`、`is_limit_down`、`limit_status` 等字段。

## 4. 规则优先级

推荐按下面顺序解析当日涨跌停规则：

1. **不限价日**
   - 如新股上市初期等交易所定义的不限价场景。
2. **风险警示股（ST / *ST）规则**
   - 当股票处于风险警示状态时，优先采用 ST 规则。
3. **板块默认规则**
   - 主板 / 创业板 / 科创板 / 北交所使用各自默认涨跌幅限制。
4. **未知规则**
   - 当必要字段缺失或无法判定时，不做强行推算，返回无效状态。

## 5. 计算口径

## 5.1 基本公式

设：
- `prev_close`：昨收价
- `limit_pct`：涨跌幅限制比例（如 0.10、0.05、0.20、0.30）
- `tick_size`：最小报价单位，第一版默认 `0.01`

则：

- `raw_limit_up = prev_close * (1 + limit_pct)`
- `raw_limit_down = prev_close * (1 - limit_pct)`

计算后需要按最小报价单位四舍五入：

- `limit_up_price = round(raw_limit_up, tick_size)`
- `limit_down_price = round(raw_limit_down, tick_size)`

推荐要求：
- 使用 `Decimal` 而非二进制浮点计算；
- 统一采用 `ROUND_HALF_UP`；
- `limit_down_price` 最低不得小于 `tick_size`。

## 5.2 命中状态

当日行情确定后：

- `is_limit_up = (current_price >= limit_up_price)`
- `is_limit_down = (current_price <= limit_down_price)`

说明：
- 若当日为不限价日，则 `is_limit_up=false`、`is_limit_down=false`；
- 若规则无效或数据缺失，则状态字段设为 `null` 或通过 `limit_status` 标明不可判定。

## 6. 建议落库字段

建议在日度行情快照表（如 `daily_stock_snapshots`）中增加以下字段：

- `limit_up_price`
- `limit_down_price`
- `limit_pct`
- `is_limit_up`
- `is_limit_down`
- `limit_rule`
- `limit_status`
- `limit_rule_version`

字段语义建议：

- `limit_rule`
  - 示例：`BOARD_10`、`BOARD_20`、`BOARD_30`、`ST_5`、`NO_LIMIT_IPO`
- `limit_status`
  - 示例：`NORMAL`、`NO_LIMIT`、`SUSPENDED`、`INVALID`
- `limit_rule_version`
  - 示例：`v1`

## 7. 规则版本化

### 7.1 为什么需要版本号
交易所规则虽然稳定，但并非永远不变。为了确保历史记录可回溯，必须保留规则版本号。

### 7.2 版本原则
- 同一批次写入的数据使用同一个 `limit_rule_version`。
- 新版本规则只影响新写入的交易日。
- 历史数据不因新版本自动重算。

### 7.3 回填原则
若因程序 bug 需要修复历史数据：
- 应记录回填原因；
- 明确回填范围；
- 保留新旧版本口径说明。

## 8. 初始化与日更链路

## 8.1 初始化流程中的位置
推荐顺序：

`股票池 -> 历史日线 / 快照采集 -> 标准化 -> 涨跌停计算 -> 批次文件生成 -> importer 入库`

要求：
- 涨跌停计算必须发生在写入批次 CSV 之前；
- 生成的批次文件中直接携带涨跌停字段；
- importer 入库时不再临时推算。

## 8.2 每日更新流程中的位置
推荐顺序：

`拉取当日行情 -> 标准化 -> 涨跌停计算 -> upsert SQLite / DuckDB`

要求：
- 初始化与日更共用同一套规则解析与计算函数；
- 保证口径一致，避免两套实现分叉。

## 8.3 新增字段后的补齐策略

当涨跌停相关字段是在已有数据链路运行后新增的，例如：

- `limit_up_price`
- `limit_down_price`
- `limit_pct`
- `is_limit_up`
- `is_limit_down`
- `limit_rule`
- `limit_status`
- `limit_rule_version`

第一版推荐处理方式不是要求用户重新上传股票列表，而是触发“重新初始化市场数据”流程。

即：

`保留 stock_universe 与 Token -> 清理旧的派生市场数据 -> 重新拉取/重建 -> 重新计算涨跌停字段 -> 重新入库`

该流程的完整职责见 `docs/market-data-reinitialize-workflow.md`。

## 9. ST 状态补全规则

## 9.1 背景
当前股票清单可能缺少显式 `st` 字段，但涨跌停规则又依赖风险警示状态。

因此第一版允许在导入股票清单时，基于股票名称补全 `is_st`。

## 9.2 补全时机
- 在 CSV 上传 / 导入股票清单时执行；
- 补全结果写入 `stock_universe`；
- 后续初始化与日更直接复用该字段。

## 9.3 识别规则
建议按“前缀识别”而不是“包含识别”执行，避免误判。

推荐识别对象：
- `STxxx`
- `*STxxx`
- `SSTxxx`
- `S*STxxx`

推荐流程：
1. 先对名称做标准化（去空格、统一大小写、统一星号形式）；
2. 使用前缀规则判定；
3. 将结果写入：
   - `is_st`
   - `st_source`（如 `name_prefix`）
   - 可选 `st_tag`（如 `ST`、`*ST`）

## 9.4 优先级
后续若接入权威风险警示字段，优先级应为：

1. 权威 `risk_warning` / 交易所字段
2. 导入时补全的 `is_st`
3. 名称即时推断（不推荐在查询阶段使用）

## 10. 异常场景处理

### 10.1 昨收缺失
- 若 `prev_close` 缺失或小于等于 0，则不计算涨跌停价；
- `limit_status = INVALID`。

### 10.2 不限价日
- `limit_status = NO_LIMIT`
- `limit_up_price = null`
- `limit_down_price = null`
- `is_limit_up = false`
- `is_limit_down = false`

### 10.3 停牌
第一版建议：
- 若行情状态可判定为停牌，则 `limit_status = SUSPENDED`；
- 可保留理论涨跌停价，也可在实现层面约定返回空值，但同一版本内必须统一。

### 10.4 字段缺失
- 任一必要字段缺失时不做猜测性补齐；
- 应显式返回无效状态并记录日志。

## 11. 接口输出建议

在市场详情接口和列表接口中，建议直接输出：

- `limit_up_price`
- `limit_down_price`
- `limit_pct`
- `is_limit_up`
- `is_limit_down`
- `limit_rule`
- `limit_status`

说明：
- 页面层只读取这些字段；
- `docs/kline-limit-color-design.md` 中的四态配色应以这些字段为准。

## 12. 验收要求

满足以下条件视为设计落地完成：

1. 初始化时可直接生成并落库涨跌停字段。
2. 每日更新时使用同一套规则函数补齐涨跌停字段。
3. 历史数据默认不会因新规则版本自动重算。
4. 每条日行情记录可追溯到其 `limit_rule_version`。
5. 股票导入时可基于名称补全 `is_st`。
6. 前端不再按涨跌幅临时推断涨跌停，而只消费服务端字段。

## 13. 与现有文档关系

- 本文档负责“怎么算、何时算、如何存”。
- `docs/market-data-reinitialize-workflow.md` 负责“新增字段后是否需要重建，以及如何重建”。
- `docs/kline-limit-color-design.md` 负责“怎么算出来之后，页面如何渲染颜色与状态语义”。
- `docs/stock-detail-page-design.md` 负责“详情页如何消费这些字段并与图表结构对齐”。
- 几份文档应保持字段命名一致，但职责分离。

