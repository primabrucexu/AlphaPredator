# F04：股票联动套利分析

## 背景

- 项目需要在 5 分钟级别行情数据上分析股票与股票之间的先后联动关系。
- 第一版目标不是解释板块逻辑，也不是完整交易系统，而是先发现 `A -> B` 的统计套利线索。
- 当前设计仅保存分析口径与功能规划，不直接定义或修改数据库表结构。

## 目标

- 基于 5 分钟 K 线识别 A 股票的盘中异动。
- 在 A 股票触发异动后，以可交易口径观察 B 股票后续表现。
- 输出 A 股票触发条件下，B 股票达到不同涨幅阈值的条件概率。
- 通过样本数和 B 自身基准概率对比，降低偶然关联和高波动股票带来的误判。
- 保存联动套利分析的回测记录，便于后续查看、对比和复盘。

## 不做什么

- 第一版不做板块龙头带后排的解释模型。
- 第一版不做自动交易、下单、仓位管理和止盈止损。
- 第一版不把同周期相关性作为核心结论，重点关注 A 先动、B 后动。
- 本文档不新增数据库表；如后续需要落表，必须先按规则提交完整表设计并等待用户审批。

## 核心定义

### 回测范围

- 默认回测开始日期为 `2025-01-01`。
- 页面允许用户选择回测开始日期和结束日期。
- 如用户未选择结束日期，默认使用当前可用行情数据的最新交易日。
- 单个回测任务的时间范围最长不超过 2 年。
- 如用户选择的开始日期和结束日期跨度超过 2 年，页面或接口应拒绝执行并提示用户缩短范围。

### A 股票池

A 股票选择支持两种模式。

第一种：指定 A 股票。

- 用户在页面手动选择一只具体股票作为 A。
- 系统计算该 A 股票触发后，对全市场非 ST B 股票的联动结果。
- 该模式计算范围小，适合作为第一版优先实现和交互式探索入口。

第二种：热点复盘高频涨停股。

- 基于热点复盘数据，选取近一年涨停次数最多的若干只股票作为 A 股票池。
- 默认选取 Top 20，页面允许用户调整 Top N。
- A 股票仍需过滤 ST 股票，ST 过滤优先使用 `stock_list.is_st` 字段。
- 涨停次数优先使用热点复盘中的涨停个股记录统计；如热点复盘数据缺失，再考虑使用日线行情中的 `is_up_limit` 标记补充统计。
- “近一年”以回测结束日为基准，向前滚动一年计算。

### 时间粒度

- 使用 5 分钟 K 线作为分析粒度。
- 设 A 股票在 T 日第 `t` 根 5 分钟 K 触发异动。
- B 股票的可交易买入基准价为 T 日第 `t+1` 根 5 分钟 K 的开盘价。

### A 股票触发类型

第一类：单根 5 分钟 K 瞬时拉升。

```text
(A 当前 5 分钟 K 收盘价 - A 当前 5 分钟 K 开盘价)
/
A 当前 5 分钟 K 开盘价
```

触发阈值：

```text
2%、3%、4%、5%
```

第二类：盘中相对昨收累计涨幅。

```text
(A 当前 5 分钟 K 收盘价 - A 上一交易日收盘价)
/
A 上一交易日收盘价
```

触发阈值：

```text
3%、5%、7%、9%
```

### 首次触发规则

每只 A 股票、每个交易日、每个触发类型、每个触发阈值，只记录第一次触发。

示例：

```text
同一天可以同时记录：
- 单根拉升 > 2%
- 单根拉升 > 3%
- 盘中累计 > 3%
- 盘中累计 > 5%

但同一个触发类型和同一个阈值不重复记录。
```

该规则用于避免同一只股票在同一天连续满足条件时反复灌入样本，但它不能单独解决高波动股票带来的误判。

## B 股票观察口径

### B 股票池

- B 股票范围为全市场非 ST 股票。
- ST 过滤优先使用 `stock_list.is_st` 字段。
- B 股票池不限制板块、不限制是否曾经涨停。
- 第一版暂不额外过滤低流动性股票、新股、次新股或北交所股票。

### 买入基准

B 股票收益统一基于：

```text
B 在 T 日第 t+1 根 5 分钟 K 的开盘价
```

含义：

```text
看到 A 股票在第 t 根 5 分钟 K 触发后，
假设下一根 5 分钟 K 开盘买入 B 股票。
```

### 观察结果

A 在 T 日触发后，观察 B 股票四个结果：

```text
1. T 日触发后到收盘前的最高价涨幅
2. T 日收盘价涨幅
3. T+1 交易日最高价涨幅
4. T+1 交易日收盘价涨幅
```

计算方式统一为：

```text
(观察价格 - B 的 t+1 开盘价)
/
B 的 t+1 开盘价
```

### B 目标涨幅阈值

```text
2%、3%、4%、5%
```

分别统计 B 的四类观察结果是否超过这些阈值。

### B 自身基准概率

B 自身基准概率用于衡量 B 股票在没有指定 A 触发条件时，达到同等涨幅目标的自然概率。

计算口径：

```text
同一回测区间内，
以 B 所有有效 5 分钟 K 的下一根开盘价作为模拟买入点，
统计 B 的 T 日最高、T 日收盘、T+1 日最高、T+1 日收盘
达到对应目标涨幅阈值的自然概率。
```

该口径与 A 触发后的 B 观察口径保持一致，用于计算概率提升和提升倍数。

## 输出格式

基础输出示例：

```text
当 A 股票单根 5 分钟 K 涨幅超过 4% 后，
如果下一根 5 分钟 K 开盘买入 B 股票：

B 股票 T 日最高涨幅超过 3% 的概率是 12%；
B 股票 T 日收盘涨幅超过 3% 的概率是 5%；
B 股票 T+1 日最高涨幅超过 3% 的概率是 18%；
B 股票 T+1 日收盘涨幅超过 3% 的概率是 9%。
```

另一个示例：

```text
当 A 股票盘中相对昨收涨幅超过 7% 后，
如果下一根 5 分钟 K 开盘买入 B 股票：

B 股票 T 日最高涨幅超过 5% 的概率是 6%；
B 股票 T 日收盘涨幅超过 5% 的概率是 2%；
B 股票 T+1 日最高涨幅超过 5% 的概率是 10%；
B 股票 T+1 日收盘涨幅超过 5% 的概率是 4%。
```

建议在最终展示中补充：

```text
- 触发次数
- B 自身基准概率
- 概率提升百分点
- 提升倍数
```

## 防误判机制

第一版至少包含四层基础防护：

```text
1. 首次触发
   避免同一股票同一天重复满足条件导致样本膨胀。

2. 样本数门槛
   触发次数过少的 A-B 关系不展示，或标记为低可信。

3. B 自身基准概率对比
   不只看 A 触发后 B 的上涨概率，还要比较 B 在普通时刻达到同等涨幅的自然概率。

4. 触发覆盖率和可信度等级
   结合样本数和触发覆盖率标记统计结果的可信程度。
```

示例：

```text
当 A 触发后，B 在 T+1 日最高涨幅超过 3% 的概率 = 18%
B 自身基准概率 = 6%
概率提升 = +12 个百分点
提升倍数 = 3.0x
触发样本数 = 42
```

### 样本数门槛

- 回测界面提供最低样本数门槛。
- 默认门槛为 30。
- 默认选项为 20、30、50。
- 用户可以输入自定义门槛。

### 触发覆盖率

触发覆盖率用于衡量某个 A 股票触发条件在回测区间内分布得是否足够广。

```text
触发覆盖率 = 触发交易日数 / 有效交易日数
```

由于首次触发规则限制了每只 A 股票、每个交易日、每个触发类型、每个触发阈值只记录一次触发，因此在固定的 `A 股票 + 触发类型 + 触发阈值` 下：

```text
触发交易日数 = 有效触发次数
```

示例：

```text
回测区间有 200 个有效交易日
A 股票单根 5 分钟 K 涨幅超过 4% 触发了 40 次
触发覆盖率 = 40 / 200 = 20%
```

### 可信度等级

第一版可信度等级按以下规则计算：

```text
高可信：
样本数 >= 50 且触发覆盖率 >= 20%

中可信：
样本数 >= 30 且触发覆盖率 >= 10%

低可信：
样本数 >= 20

不足：
样本数 < 用户选择的最低样本数
```

可信度等级先作为展示和排序辅助，不作为固定过滤规则。后续可根据实际使用效果调整阈值。

## 排序指标

结果默认按综合分排序。

第一版综合分：

```text
综合分 = 概率提升 × log(样本数 + 1)
```

其中：

```text
概率提升 = 条件概率 - B 自身基准概率
```

该排序方式优先展示相对 B 自身基准概率有明显提升、且样本数不太小的 A-B 关系。

页面仍需展示原始指标：

```text
- 条件概率
- B 自身基准概率
- 概率提升
- 提升倍数
- 样本数
- 触发覆盖率
- 可信度等级
```

## 回测记录保存

- 相关回测记录需要保存到数据库中。
- 数据库表设计已由用户审批通过。
- 用户需要将已审批 DBML 同步更新到 `docs/human/data-model/AlphaPredator.dbml` 后，才能进入编码实现。

## 已审批数据库设计 DBML

以下设计用于保存回测任务、触发事件、B 股票基准概率和 A-B 统计结果。

设计假设：

```text
1. 5 分钟 K 原始行情使用独立行情表 5m_level_trade_data，本节不展开该表设计。
2. 联动回测结果需要可复查，所以保存任务配置、A 触发事件、B 基准概率、A->B 统计结果。
3. 按全局存储规则，这些回测任务和统计结果属于非 K 线持久化数据，应存储到 SQLite；DuckDB 仅保留 5 分钟 K 原始行情。
```

行情依赖说明：

```text
F04 计算依赖 5m_level_trade_data 提供：
- full_code
- trade_date
- bar_time
- bar_index
- open / high / low / close
- pre_close
- is_stop 或等价停牌 / 无交易标记
```

如果后续 SQL 中直接引用 `5m_level_trade_data`，需注意该表名以数字开头，可能需要按数据库方言使用引号引用。

已审批 DBML：

```dbml
Table stock_linkage_backtest_job [headercolor: #8a5a00] {
  id varchar(255) [pk, unique, note: '回测任务ID，建议使用UUID。用于关联本次回测产生的触发事件、基准概率和统计结果。']
  job_name varchar(255) [note: '用户自定义任务名称，可为空；用于页面展示和人工识别。']
  a_select_mode varchar(255) [not null, note: 'A股票选择模式。manual_single表示用户指定单只A股票；hot_limit_top表示基于热点复盘选取近一年涨停次数Top N股票。']
  manual_a_full_code varchar(255) [note: '手动指定A股票时的完整股票代码，如000001.SZ；仅a_select_mode=manual_single时使用。']
  hot_top_n integer [note: '热点复盘高频涨停股数量，如20；仅a_select_mode=hot_limit_top时使用。']
  start_date date [not null, note: '回测开始日期，默认2025-01-01。']
  end_date date [not null, note: '回测结束日期；未手动选择时使用当前可用行情数据的最新交易日。']
  min_sample_count integer [not null, default: 30, note: '用户选择的最低样本数门槛，用于过滤或标记样本不足的统计结果。默认30。']
  status varchar(255) [not null, default: 'pending', note: '回测任务状态：pending/running/success/failed。']
  error_message text [note: '任务失败原因；成功时为空。']
  created_at datetime [not null, note: '任务创建时间。']
  updated_at datetime [not null, note: '任务最近更新时间。']
  finished_at datetime [note: '任务完成时间；未完成或失败前可为空。']

  indexes {
    (status, created_at) [name: 'idx_stock_linkage_job_status_created']
    (created_at) [name: 'idx_stock_linkage_job_created']
  }

  Note: '股票联动套利回测任务表。保存一次回测的参数、状态和生命周期信息。'
}

Table stock_linkage_trigger_event [headercolor: #8a5a00] {
  id varchar(255) [pk, unique, note: '触发事件ID，建议使用UUID。每条记录表示一次A股票触发事件。']
  job_id varchar(255) [not null, note: '所属回测任务ID，关联stock_linkage_backtest_job.id。']
  a_full_code varchar(255) [not null, note: '触发异动的A股票完整代码，如000001.SZ。']
  trade_date date [not null, note: '触发事件发生的交易日T。']
  bar_time datetime [not null, note: '触发事件所在5分钟K的时间。具体表示K线开始时间还是结束时间，需与5m_level_trade_data保持一致。']
  bar_index integer [not null, note: '触发事件所在交易日内的5分钟K序号，从1递增。用于定位t以及B股票t+1开盘价。']
  trigger_type varchar(255) [not null, note: '触发类型。single_bar_return表示单根5分钟K涨幅触发；intraday_return_from_pre_close表示盘中相对昨收累计涨幅触发。']
  trigger_threshold numeric [not null, note: '触发阈值，小数形式保存，如0.04表示4%。']
  trigger_return numeric [not null, note: '触发时实际涨幅，小数形式保存。single_bar_return时为当前K收盘相对当前K开盘涨幅；intraday_return_from_pre_close时为当前K收盘相对上一交易日收盘涨幅。']

  indexes {
    (job_id, a_full_code, trigger_type, trigger_threshold) [name: 'idx_stock_linkage_trigger_a_condition']
    (job_id, trade_date, bar_index) [name: 'idx_stock_linkage_trigger_time']
  }

  Note: '股票联动套利A股票触发事件表。用于复查A为何触发，并支撑样本数和触发覆盖率计算。'
}

Table stock_linkage_baseline_metric [headercolor: #8a5a00] {
  id varchar(255) [pk, unique, note: '基准指标ID，建议使用UUID。每条记录表示一个B股票在某观察口径和目标阈值下的自然上涨概率。']
  job_id varchar(255) [not null, note: '所属回测任务ID，关联stock_linkage_backtest_job.id。']
  b_full_code varchar(255) [not null, note: 'B股票完整代码，如000001.SZ。']
  observation_type varchar(255) [not null, note: 'B观察结果类型：t_day_high为T日触发后至收盘前最高价；t_day_close为T日收盘价；next_day_high为T+1交易日最高价；next_day_close为T+1交易日收盘价。']
  target_threshold numeric [not null, note: 'B目标涨幅阈值，小数形式保存，如0.03表示3%。']
  baseline_sample_count integer [not null, note: 'B自身有效模拟买入样本数。按同一回测区间内B所有有效5分钟K的下一根开盘价作为模拟买入点统计。']
  baseline_hit_count integer [not null, note: 'B自身达到目标阈值的次数。']
  baseline_probability numeric [not null, note: 'B自身基准概率，计算方式为baseline_hit_count / baseline_sample_count。']

  indexes {
    (job_id, b_full_code, observation_type, target_threshold) [name: 'uq_stock_linkage_baseline_b_metric', unique]
  }

  Note: 'B股票自身基准概率表。用于衡量B在没有指定A触发条件时达到同等涨幅目标的自然概率。'
}

Table stock_linkage_backtest_result [headercolor: #8a5a00] {
  id varchar(255) [pk, unique, note: '结果ID，建议使用UUID。每条记录表示一个A-B股票对在某触发条件、观察口径和目标阈值下的统计结果。']
  job_id varchar(255) [not null, note: '所属回测任务ID，关联stock_linkage_backtest_job.id。']
  a_full_code varchar(255) [not null, note: 'A股票完整代码，如000001.SZ。']
  b_full_code varchar(255) [not null, note: 'B股票完整代码，如000001.SZ。']
  trigger_type varchar(255) [not null, note: 'A触发类型。single_bar_return表示单根5分钟K涨幅触发；intraday_return_from_pre_close表示盘中相对昨收累计涨幅触发。']
  trigger_threshold numeric [not null, note: 'A触发阈值，小数形式保存，如0.04表示4%。']
  observation_type varchar(255) [not null, note: 'B观察结果类型：t_day_high为T日触发后至收盘前最高价；t_day_close为T日收盘价；next_day_high为T+1交易日最高价；next_day_close为T+1交易日收盘价。']
  target_threshold numeric [not null, note: 'B目标涨幅阈值，小数形式保存，如0.03表示3%。']
  sample_count integer [not null, note: 'A触发后，B有完整行情可观察的有效样本数。']
  hit_count integer [not null, note: '在有效样本中，B观察结果达到target_threshold的次数。']
  condition_probability numeric [not null, note: 'A触发条件下B达到目标阈值的条件概率，计算方式为hit_count / sample_count。']
  baseline_probability numeric [not null, note: 'B自身基准概率，来自stock_linkage_baseline_metric。']
  probability_lift numeric [not null, note: '概率提升，计算方式为condition_probability - baseline_probability。']
  lift_multiple numeric [note: '提升倍数，计算方式为condition_probability / baseline_probability；baseline_probability为0时可为空。']
  trigger_coverage_rate numeric [not null, note: '触发覆盖率，计算方式为触发交易日数 / 有效交易日数。']
  confidence_level varchar(255) [not null, note: '可信度等级：high/medium/low/insufficient。由样本数和触发覆盖率计算。']
  score numeric [not null, note: '默认排序综合分，计算方式为probability_lift * log(sample_count + 1)。']
  created_at datetime [not null, note: '结果记录创建时间。']

  indexes {
    (job_id, score) [name: 'idx_stock_linkage_result_job_score']
    (job_id, a_full_code, b_full_code) [name: 'idx_stock_linkage_result_pair']
    (job_id, trigger_type, trigger_threshold) [name: 'idx_stock_linkage_result_trigger']
    (job_id, observation_type, target_threshold) [name: 'idx_stock_linkage_result_observation']
  }

  Note: '股票联动套利回测结果表。用于页面查询、排序和展示A->B条件概率、基准概率、概率提升及可信度。'
}

Ref fk_stock_linkage_trigger_event_job {
  stock_linkage_trigger_event.job_id > stock_linkage_backtest_job.id [delete: no action, update: cascade]
}

Ref fk_stock_linkage_baseline_metric_job {
  stock_linkage_baseline_metric.job_id > stock_linkage_backtest_job.id [delete: no action, update: cascade]
}

Ref fk_stock_linkage_backtest_result_job {
  stock_linkage_backtest_result.job_id > stock_linkage_backtest_job.id [delete: no action, update: cascade]
}
```

## 待确认问题

- 已审批 DBML 需要由用户同步更新到 `docs/human/data-model/AlphaPredator.dbml`。

## 当前状态

- 已实现第一版股票联动套利分析后端核心：
  - SQLite 初始化创建 4 张联动回测表；DuckDB 初始化只创建 `5m_level_trade_data` 等 K 线行情表。
  - 5 分钟 K 数据拉取复用麦蕊历史行情接口，使用 `interval=5`。
  - 后端支持 `manual_single` 和 `hot_limit_top` 两种 A 股票选择模式。
  - 后端支持后台创建并执行回测任务，保存触发事件、保存 B 基准概率、保存 A-B 统计结果。
  - API 已提供创建回测任务、查询任务详情、查询任务列表和查询结果列表。
- 已新增前端“联动套利”页面，支持输入 A 股票模式、日期范围、样本门槛、提交后台任务、轮询任务状态并展示结果表。
- 后续需求变更应直接更新本文档。
