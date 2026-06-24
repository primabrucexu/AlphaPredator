# F06：MACD 形态预警

## 目标

基于日线 MACD(8,17,6) 识别“金叉临界”形态，在收盘后输出可读的预警文案，并支持用历史日线数据回测该形态的后续金叉概率和交易收益。

第一版重点不是泛化技术指标平台，而是回答两个具体问题：

- 今天有哪些股票出现“绿柱连续缩短、接近金叉”的形态？
- 昨天已经进入预警池的股票，今天是否形成金叉、继续维持趋势，还是趋势走弱？
- 历史上出现同类形态后，5 个交易日内形成金叉并按规则交易的胜率和收益如何？
- 预警股票上次涨停属于什么题材，该题材当前是否仍然活跃？

## 不做什么

- 第一版只做日线级别，不做 5 分钟、15 分钟、30 分钟等分时级别。
- 第一版不做实时盘中预警，只做收盘后扫描。
- 第一版不做微信、邮件、声音等外部通知。
- 第一版不做复杂规则配置系统，形态规则先内置。
- 第一版不引入 AI 判断形态，所有结果由明确公式计算。
- 第一版不判断股票的静态题材归属，不调用外部题材/概念接口；只使用本地涨停复盘中的“上次涨停题材”作为题材归属依据。

## 核心形态定义

### 金叉临界

预警日记为 T。

同时满足：

- 使用日线 MACD(8,17,6)。
- T 日 `macd_hist < 0`，仍为绿柱。
- T 日 `DIF < DEA`，尚未金叉。
- MACD 绿柱连续缩短，默认连续 2 天。

根据 T 日 DIF / DEA 位置，将临界形态分为：

```text
underwater  水下金叉临界：DIF < 0 且 DEA < 0
above_zero  水上金叉临界：DIF > 0 且 DEA > 0
mixed       零轴附近金叉临界：DIF 和 DEA 分处零轴两侧
```

第一版预警体系纳入 `underwater` 和 `above_zero`。`mixed` 先保留结构化能力，可在页面中默认隐藏或作为低优先级结果展示。

绿柱连续缩短定义：

```text
macd_hist < 0
abs(macd_hist[T]) < abs(macd_hist[T-1])
abs(macd_hist[T-1]) < abs(macd_hist[T-2])
```

如果配置为连续 N 天，则需要最近 N 根绿柱的绝对值逐日缩小。

## 临界价格

预警需要同时输出两个关键价格：

```text
金叉价 X：若下一交易日收盘价不低于 X，则形成金叉。
趋势维持价 Y：若下一交易日收盘价不低于 Y，则 MACD 绿柱继续缩短，金叉趋势仍在维持。
```

项目现有 MACD 计算口径：

```text
EMA8  = EMA(close, 8)
EMA17 = EMA(close, 17)
DIF   = EMA8 - EMA17
DEA   = EMA(DIF, 6)
MACD  = (DIF - DEA) * 2
```

### 金叉价

在已知 T 日 EMA8、EMA17、DEA 的情况下，T+1 日 `DIF >= DEA` 的临界收盘价可推导为：

```text
cross_trigger_price = 9 * DEA_T - 7 * EMA8_T + 8 * EMA17_T
```

说明：

- 该价格表示“下一交易日收盘后，按 MACD(8,17,6) 计算刚好形成 DIF >= DEA 的收盘临界价”。
- 金叉类型由 T 日 DIF / DEA 所处区域确定，输出为水下金叉临界、水上金叉临界或零轴附近金叉临界。
- 如果金叉价高于下一交易日涨停价，不删除该结果，标记为“金叉价理论不可达”，并降低排序优先级。
- 重点预警列表默认只展示金叉价距离 T 日收盘价不超过 5% 的结果；全部预警结果仍保留，可在页面、报告和分页接口中查看。

### 趋势维持价

趋势维持价用于回答：

```text
如果明天还不能金叉，至少收在哪里，才说明 MACD 仍在继续向金叉靠近？
```

定义：

```text
diff_T = DIF_T - DEA_T
diff_next = DIF_next - DEA_next
```

对于当前“尚未金叉”的预警样本，`diff_T < 0`。如果 `diff_next > diff_T`，表示 DIF 与 DEA 的距离继续收窄，也就是绿柱继续缩短，金叉趋势仍在维持。

在已知 T 日 EMA8、EMA17、DIF、DEA 的情况下，T+1 日维持金叉趋势的临界收盘价可推导为：

```text
trend_keep_price = 9 * (DEA_T + 7 / 5 * (DIF_T - DEA_T)) - 7 * EMA8_T + 8 * EMA17_T
```

输出解释：

- 若下一交易日收盘价 `>= cross_trigger_price`：形成金叉。
- 若下一交易日收盘价 `< cross_trigger_price` 且 `>= trend_keep_price`：尚未金叉，但绿柱继续缩短，金叉趋势仍在。
- 若下一交易日收盘价 `< trend_keep_price`：绿柱重新放大，金叉趋势走弱。

## 收盘预警输出

单条预警应以用户能直接阅读的文字为主，同时保留结构化字段支撑排序、筛选和回测。

### 输出示例

```text
2026-06-05 收盘 MACD 形态分析：
600545 卓郎智能连续 2 天 MACD 绿柱缩短，今日收盘 MACD 柱值 -0.18，DIF 仍在 DEA 下方，但已有水下金叉趋势。
若下一交易日收盘价不低于 2.74 元，则按 MACD(8,17,6) 计算将形成水下金叉。若收盘价不低于 2.61 元，即使尚未金叉，MACD 绿柱也会继续缩短，金叉趋势仍在维持。
金叉价较今日收盘价高 2.62%，趋势维持价较今日收盘价低 2.25%。
该股上次涨停题材为“机器人”，距今 2 个交易日；机器人题材近 5 个交易日去重涨停 12 只，当前活跃度排名第 3，题材热度仍在。
```

```text
2026-06-05 收盘 MACD 形态分析：
300000 示例股票连续 2 天 MACD 绿柱缩短，今日收盘 MACD 柱值 -0.04，DIF 和 DEA 均位于零轴上方，属于水上金叉临界。
若下一交易日收盘价不低于 18.36 元，则按 MACD(8,17,6) 计算将形成水上金叉。若收盘价不低于 17.92 元，则金叉趋势仍在维持；若低于该价格，绿柱将重新放大。
金叉价较今日收盘价高 1.44%，趋势维持价较今日收盘价低 0.99%。
该股上次涨停题材为“算力”，距今 8 个交易日；算力题材近 5 个交易日去重涨停 2 只，当前活跃度较弱。
```

### 结构化字段

```text
trade_date: 2026-06-05
stock_code: 600545
stock_name: 卓郎智能
pattern_key: golden_cross_setup
pattern_name: 金叉临界
cross_zone: underwater
summary: 连续2天MACD绿柱缩短，今日收盘MACD柱值-0.18，有水下金叉趋势
cross_trigger_price: 2.74
cross_trigger_distance_pct: 2.62
trend_keep_price: 2.61
trend_keep_distance_pct: -2.25
close_price: 2.67
macd_dif: -0.2150
macd_dea: -0.1250
macd_hist: -0.1800
green_shrink_days: 2
last_limit_up_date: 2026-06-03
last_limit_up_theme: 机器人
last_limit_up_days_ago: 2
theme_heat_window_days: 5
theme_recent_limit_up_count: 12
theme_recent_rank: 3
theme_heat_level: strong
```

## 题材活跃度标注

第一版不解决“某只股票天然属于哪些题材”的问题。原因是当前没有可靠的股票题材归属接口，强行从名称、概念或文本推断会降低可解释性。

采用更保守的事实口径：

```text
股票题材归属 = 该股在预警日前最近一次涨停复盘中的 hot_theme。
题材活跃度 = 该 hot_theme 在预警日前最近 N 个交易日的去重涨停股票数和排名。
```

默认参数：

```text
universe_scope = market
markets = ["主板"]
exclude_st = true
last_limit_up_lookback_days = 120
theme_heat_window_days = 5
```

### 上次涨停题材

从 `daily_hot_info` 中查询：

- `stock_code` 等于预警股票。
- `trade_date <= alert_date`。
- 取距离预警日最近的一条涨停复盘记录。
- 使用该记录的 `hot_theme` 作为“上次涨停题材”。

如果近 120 个交易日内没有涨停复盘记录：

```text
last_limit_up_theme = null
theme_heat_level = none
summary 中提示：近120日未找到涨停题材归属。
```

### 题材当前活跃度

在 `theme_heat_window_days` 个交易日窗口内统计同一 `hot_theme`：

```text
theme_recent_limit_up_count = 该题材近5个交易日去重涨停股票数
theme_recent_rank = 按去重涨停股票数排序后的题材排名
```

活跃度分级：

```text
strong  题材近5日排名前5，且去重涨停股票数 >= 5
medium  题材近5日排名前10，且去重涨停股票数 >= 3
weak    题材近5日有涨停记录，但未达到 medium
none    无上次涨停题材，或该题材近5日无涨停记录
```

## T+1 跟踪扫描

每日收盘扫描分为两类：

```text
新预警扫描：按默认股票池（主板非ST）寻找当天新出现的金叉临界标的。
跟踪扫描：继续跟踪上一交易日已经进入预警池的标的。
```

跟踪扫描用于回答：

```text
T 日进入预警池的股票，T+1 收盘后实际走到了哪一步？
```

### 跟踪范围

T+1 日跟踪范围包括：

- T 日 `macd_alert_result` 中状态为 `active` 的股票。
- 后续实现回测/实盘统一后，也可扩展为最近 5 个交易日内仍处于观察期的预警股票。

第一版先明确：

```text
T+1 跟踪 T 日扫描出的 active 预警标的。
```

### 跟踪结果

对每个跟踪标的，用 T+1 实际收盘价重新计算 MACD，并输出：

```text
cross_confirmed  已形成金叉：T+1 收盘 DIF >= DEA
trend_kept       未金叉但趋势维持：T+1 收盘价 >= T日趋势维持价，绿柱继续缩短
trend_weakened   趋势走弱：T+1 收盘价 < T日趋势维持价，绿柱重新放大
data_missing     T+1 缺少行情数据，无法判断
```

输出示例：

```text
2026-06-06 跟踪结果：
600545 卓郎智能昨日进入水下金叉临界，今日收盘 2.68 元，未达到金叉价 2.74 元，但高于趋势维持价 2.61 元，MACD 绿柱继续缩短，金叉趋势仍在。
```

如果形成金叉：

```text
2026-06-06 跟踪结果：
600545 卓郎智能昨日进入水下金叉临界，今日收盘 2.76 元，高于昨日测算金叉价 2.74 元，收盘后已形成水下金叉。
```

如果趋势走弱：

```text
2026-06-06 跟踪结果：
600545 卓郎智能昨日进入水下金叉临界，今日收盘 2.58 元，低于趋势维持价 2.61 元，MACD 绿柱重新放大，金叉趋势走弱。
```

### 页面展示

预警页增加两个列表：

- 今日新增预警：当天新扫描出的金叉临界标的。
- 昨日预警跟踪：上一交易日预警池在今天的跟踪结果。

这样用户每天收盘后能同时看到：

- 今天新进入观察池的股票。
- 昨天观察池里哪些已经金叉，哪些仍可继续观察，哪些应该剔除。

## 金叉趋势历史回测规则

金叉趋势历史回测是预警结果的一部分，不是独立于预警之外的后续操作。

当某只股票在 T 日扫描中触发“金叉临界”预警时，系统需要立刻对该股票历史上同类形态进行回测，并把回测摘要直接写入本次预警结果。

预警内置回测需要验证两件事：

```text
1. 趋势判断是否有效：T 日预警后，T+1 是否形成金叉、维持趋势或走弱。
2. 交易规则是否有效：T+1 开盘买入后，后续 5 个交易日内是否金叉，并按卖出规则计算收益。
```

这里的“金叉趋势”不是只看最终有没有金叉，也要单独统计：

```text
T+1 已金叉
T+1 未金叉但绿柱继续缩短
T+1 绿柱重新放大
```

这样才能判断 `trend_keep_price` 是否真的有解释力。

### 样本生成

对每条当前预警结果，按同一只股票、同一 `cross_zone`、同一参数口径回看历史日线。

当某个交易日 T 满足“金叉临界”定义时，生成一条历史样本，并记录 `cross_zone`。

默认回看范围：

```text
backtest_lookback_days = 720
```

如果有效样本数过少，预警仍然输出，但回测可信度标记为 `insufficient`。

### 买入规则

```text
T+1 开盘价买入。
```

注意：

- 不要求 T+1 已经形成金叉。
- 只要 T 日触发预警，历史样本就进入买入观察。

### T+1 趋势验证

对每个历史样本，先用 T+1 的实际收盘价验证 T 日输出的两档价格：

```text
t1_cross_confirmed  T+1 收盘价 >= T日金叉价，且 T+1 收盘后 DIF >= DEA
t1_trend_kept       T+1 收盘价 < T日金叉价，但 >= T日趋势维持价，绿柱继续缩短
t1_trend_weakened   T+1 收盘价 < T日趋势维持价，绿柱重新放大
t1_data_missing     T+1 缺少行情数据，无法判断
```

T+1 趋势验证不影响买入规则。也就是说：

- T+1 已金叉：继续进入后续卖出逻辑。
- T+1 趋势维持：继续观察 T+2 到 T+5 是否金叉。
- T+1 趋势走弱：仍按历史样本记录，但通常后续金叉成功率和收益应单独统计。

### 金叉观察规则

```text
从 T+1 到 T+5，最多观察 5 个交易日。
```

- 期间首次出现 `DIF >= DEA`，记为金叉成功。
- 如果金叉发生时 `DIF < 0` 且 `DEA < 0`，记为水下金叉成功。
- 如果金叉发生时 `DIF > 0` 且 `DEA > 0`，记为水上金叉成功。
- 如果金叉发生时 DIF 和 DEA 分处零轴两侧，记为零轴附近金叉成功。
- 5 个交易日内未出现 `DIF >= DEA`，记为金叉失败。

### 卖出规则

只有金叉成功样本进入卖出逻辑。

```text
从金叉日开始，最多持有 10 个交易日。
```

卖出优先级：

1. 第一次出现红柱缩短时，按当日收盘价卖出。
2. 如果 10 个交易日内没有出现红柱缩短，按第 10 个交易日收盘价卖出。

红柱缩短定义：

```text
macd_hist > 0
macd_hist < macd_hist[前一交易日]
```

### 收益计算

```text
return_pct = sell_price / buy_price - 1
```

其中：

- `buy_price` 为 T+1 开盘价。
- `sell_price` 为红柱缩短日收盘价，或超时卖出日收盘价。

### 样本状态

```text
pending_cross        预警后数据不足，尚无法判断 5 日内是否金叉
cross_failed         T+1 到 T+5 未形成金叉
cross_success        已形成金叉，但后续卖出数据不足
sold_by_red_shrink   金叉后出现红柱缩短，按规则卖出
sold_by_timeout      金叉后 10 个交易日内未红柱缩短，按第10日收盘卖出
insufficient_data    后续行情数据不足，不能完成判断
```

## 回测输出

回测输出直接作为每条预警结果的组成部分展示。

例如：

```text
历史同类形态样本 18 次，5日内金叉 11 次，金叉成功率 61.1%；完成交易 10 次，胜率 60.0%，平均收益 3.7%，平均持有 5.4 天。T+1 趋势维持率 65.0%。
```

### 汇总指标

```text
预警样本数
5日内金叉成功数
5日内水下金叉成功数
5日内水上金叉成功数
金叉失败数
金叉成功率
水下金叉成功率
水上金叉成功率
T+1 已金叉数
T+1 趋势维持数
T+1 趋势走弱数
T+1 趋势维持率
完成交易数
盈利交易数
胜率
平均收益率
最大收益率
最大亏损率
平均持有天数
超时卖出数
数据不足样本数
```

### 样本明细

```text
股票代码
股票名称
预警日
预警日收盘价
临界金叉价
金叉价距离
趋势维持价
趋势维持价距离
上次涨停题材
题材热度等级
T+1 买入日
T+1 买入价
T+1 收盘价
T+1 趋势状态：t1_cross_confirmed / t1_trend_kept / t1_trend_weakened / t1_data_missing
金叉日
预警类型：underwater / above_zero / mixed
金叉类型：underwater / above_zero / mixed
卖出日
卖出原因：red_shrink / timeout
卖出价
收益率
持有天数
样本状态
```

## 页面设计

新增“MACD 预警”页面。

### 预警页

- 交易日选择器：默认最新有日线数据的交易日。
- 股票池过滤：默认主板非 ST；后续可扩展为全部 A 股、指定市场、是否排除 ST。
- 形态过滤：第一版支持“水下金叉临界”和“水上金叉临界”。
- 扫描按钮：提交后台扫描任务，页面轮询展示进度、当前处理股票、任务状态和终止按钮。
- 结果表：展示股票、形态、临界价、距离、MACD 值、绿柱缩短天数和文案摘要。
- 操作：跳转个股详情。

### 历史样本明细

- 第一版不做独立批量回测页。
- 每条预警结果内展示该标的历史同类形态回测摘要。
- 如需查看样本明细，可从预警行展开或通过报告查看。

第一版可将页面组织为两个 Tab：

- 今日预警与跟踪。
- 历史样本明细。

## API 设计

### 扫描预警

```text
POST /api/macd-alerts/scan
```

请求：

```json
{
  "trade_date": "2026-06-05",
  "universe_scope": "market",
  "markets": ["主板"],
  "exclude_st": true,
  "green_shrink_days": 2
}
```

当前实现已升级为后台任务模式。接口不再同步等待扫描完成，而是创建并启动初始化任务体系中的 `MACD_ALERT_SCAN` 任务。

响应：

```json
{
  "task_id": "uuid",
  "task_type": "MACD_ALERT_SCAN",
  "start_date": "20260605",
  "end_date": "20260605",
  "status": "RUNNING",
  "total_items": 5200,
  "processed_items": 120,
  "current_label": "600545.SH",
  "progress_percent": 2.3
}
```

进度查询复用现有初始化任务接口：

```text
GET /api/data-init/tasks/{task_id}
GET /api/data-init/tasks/{task_id}/items
POST /api/data-init/tasks/{task_id}/terminate
```

### 跟踪上一交易日预警

```text
POST /api/macd-alerts/track
```

请求：

```json
{
  "trade_date": "2026-06-06",
  "source_trade_date": "2026-06-05"
}
```

响应：

```json
{
  "trade_date": "2026-06-06",
  "source_trade_date": "2026-06-05",
  "tracked_count": 18,
  "cross_confirmed_count": 5,
  "trend_kept_count": 8,
  "trend_weakened_count": 4,
  "data_missing_count": 1,
  "report_generatable": true,
  "report_generation_hint": "可按需调用 POST /api/macd-alerts/reports 生成 HTML/PDF 报告。",
  "results": []
}
```

### 查询预警结果

```text
GET /api/macd-alerts/results?trade_date=2026-06-05&pattern_key=golden_cross_setup&cross_zone=underwater
```

### 查询预警内置回测样本

```text
GET /api/macd-alerts/results/{alert_id}/backtest-samples
```

该接口分页返回某条预警结果对应的历史同类形态样本。

### 按需生成报告

```text
POST /api/macd-alerts/reports
```

请求：

```json
{
  "report_type": "daily_brief",
  "trade_date": "2026-06-05",
  "source_trade_date": "2026-06-04",
  "formats": ["html", "pdf"]
}
```

响应：

```json
{
  "report_id": "uuid",
  "report_type": "daily_brief",
  "formats": ["html", "pdf"],
  "html_file_path": "data/reports/macd-alert/2026-06-05/brief-report.html",
  "pdf_file_path": "data/reports/macd-alert/2026-06-05/brief-report.pdf",
  "mime_types": {
    "html": "text/html",
    "pdf": "application/pdf"
  }
}
```

## 报告文件设计

考虑到单次扫描、跟踪和回测可能包含大量结果，报告文件采用按需生成策略。扫描、跟踪和回测完成时只保存结构化结果；只有用户或 Agent 明确需要报告时，才生成报告文件。

这样可以避免每天自动产生大量无人阅读的文件，同时保留 Agent 直接返回报告文件的能力。

### 报告类型

第一版支持：

```text
daily_scan      每日新增预警报告
daily_tracking  每日跟踪报告
daily_brief     每日综合报告，包含新增预警 + 昨日跟踪
backtest        回测报告
```

### 报告格式

第一版默认生成 HTML，并由 HTML 转成 PDF：

```text
data/reports/macd-alert/YYYY-MM-DD/daily-report.html
data/reports/macd-alert/YYYY-MM-DD/daily-report.pdf
data/reports/macd-alert/YYYY-MM-DD/tracking-report.html
data/reports/macd-alert/YYYY-MM-DD/tracking-report.pdf
data/reports/macd-alert/YYYY-MM-DD/brief-report.html
data/reports/macd-alert/YYYY-MM-DD/brief-report.pdf
data/reports/macd-alert/alerts/{alert_result_id}/backtest-report.html
data/reports/macd-alert/alerts/{alert_result_id}/backtest-report.pdf
```

可选生成 CSV 明细：

```text
data/reports/macd-alert/YYYY-MM-DD/daily-results.csv
data/reports/macd-alert/alerts/{alert_result_id}/samples.csv
```

Markdown 不作为第一版主要阅读格式。原因是手机端阅读长 Markdown 表格体验较差；HTML 负责排版，PDF 负责移动端阅读、归档和分享。

### HTML / PDF 报告结构

每日综合报告建议结构：

```text
# 2026-06-05 MACD 金叉临界预警报告

> 以下为技术形态观察结果，不构成买卖建议。

## 数据状态
- 本地最新交易日
- 扫描交易日
- 默认股票池：主板非 ST

## 今日新增预警摘要
- 新增预警数量
- 水下/水上数量
- 题材热度 strong / medium 数量

## 昨日预警跟踪
- 已金叉
- 趋势维持
- 趋势走弱
- 数据缺失

## 重点标的
- 按 score / 题材热度 / 金叉价距离排序列出 Top N

## 全部明细
- 表格列出预警标的核心字段
```

### Agent 返回策略

MCP 默认返回短摘要，不自动生成报告文件。用户需要完整报告时，Agent 调用 `generate_macd_alert_report` 生成 HTML/PDF，然后返回文件引用。

生成报告后的 MCP 返回：

```json
{
  "text_summary": "适合直接展示给用户的短摘要",
  "report": {
    "report_id": "uuid",
    "report_type": "daily_brief",
    "formats": ["html", "pdf"],
    "html_file_path": "data/reports/macd-alert/2026-06-05/brief-report.html",
    "pdf_file_path": "data/reports/macd-alert/2026-06-05/brief-report.pdf",
    "mime_types": {
      "html": "text/html",
      "pdf": "application/pdf"
    }
  },
  "has_more": true,
  "next_action_hint": "可打开 PDF 报告查看完整明细，或调用 list_macd_alert_results 分页查询结构化结果。"
}
```

这样 Agent 可以先给用户摘要；当用户说“生成报告”或“发我文件”时，再生成 HTML/PDF 文件。

## 数据与接口依赖

- 股票列表：`stock_list`。
- 日线行情：`day_level_trade_data`。
- 上次涨停题材与题材活跃度：`daily_hot_info`。
- MACD 计算口径：复用现有后端 MACD(8,17,6) 算法。
- 数据模型：必须以 `docs/human/data-model/AlphaPredator.dbml` 为准。

## 数据库设计方案（待审批）

以下 DBML 是设计方案，不能直接落表。必须先经用户审批，并由用户更新 `docs/human/data-model/AlphaPredator.dbml` 后，才能修改 SQLite schema。F06 仅从 DuckDB 读取日线 K 线数据，不新增或修改 DuckDB 表。

### 预警结果表

```dbml
Table macd_alert_result [headercolor: #7a3f8f] {
  id varchar(255) [pk, unique, note: '预警结果ID，建议使用UUID。']
  trade_date date [not null, note: '触发预警的交易日，YYYYMMDD。']
  stock_code varchar(255) [not null, note: '6位股票代码，如600545。']
  stock_name varchar(255) [not null, note: '股票名称，冗余保存便于展示历史结果。']
  pattern_key varchar(255) [not null, note: '形态键，第一版为golden_cross_setup。']
  pattern_name varchar(255) [not null, note: '形态展示名称，如金叉临界。']
  cross_zone varchar(255) [not null, note: '预警日金叉位置类型：underwater/above_zero/mixed。']
  close_price numeric [not null, note: '预警日收盘价。']
  next_cross_trigger_price numeric [not null, note: '下一交易日形成金叉所需的最低收盘价。']
  cross_trigger_distance_pct numeric [not null, note: '金叉价相对预警日收盘价的涨跌幅，小数形式，如0.0262表示2.62%。']
  next_limit_up_price numeric [note: '按预警日收盘价和涨跌停规则估算的下一交易日涨停价；无法估算时为空。']
  cross_trigger_reachable boolean [not null, default: true, note: '金叉价在下一交易日是否理论可达；当金叉价高于涨停价时为false。']
  cross_trigger_unreachable_reason varchar(255) [note: '金叉价理论不可达原因，如above_limit_up；可达时为空。']
  next_trend_keep_price numeric [not null, note: '下一交易日维持金叉趋势所需的最低收盘价；达到该价表示绿柱继续缩短。']
  trend_keep_distance_pct numeric [not null, note: '趋势维持价相对预警日收盘价的涨跌幅，小数形式。']
  macd_dif numeric [not null, note: '预警日DIF值。']
  macd_dea numeric [not null, note: '预警日DEA值。']
  macd_hist numeric [not null, note: '预警日MACD柱值。']
  green_shrink_days integer [not null, default: 2, note: '连续绿柱缩短天数。']
  last_limit_up_date date [note: '该股预警日前最近一次涨停日期；近120日无涨停记录时为空。']
  last_limit_up_theme varchar(255) [note: '该股预警日前最近一次涨停复盘题材，来自daily_hot_info.hot_theme。']
  last_limit_up_days_ago integer [note: '最近一次涨停距预警日的交易日间隔。']
  theme_heat_window_days integer [not null, default: 5, note: '题材活跃度统计窗口交易日数。']
  theme_recent_limit_up_count integer [not null, default: 0, note: '该题材在统计窗口内的去重涨停股票数。']
  theme_recent_rank integer [note: '该题材在统计窗口内按去重涨停股票数排序的排名；无题材时为空。']
  theme_heat_level varchar(255) [not null, default: 'none', note: '题材热度等级：strong/medium/weak/none。']
  next_track_date date [note: '下一次跟踪日期，通常为下一交易日；尚未跟踪时可为空。']
  track_status varchar(255) [not null, default: 'pending', note: '跟踪状态：pending/cross_confirmed/trend_kept/trend_weakened/data_missing。']
  tracked_close_price numeric [note: '跟踪日实际收盘价；尚未跟踪或缺数据时为空。']
  tracked_macd_dif numeric [note: '跟踪日DIF值；尚未跟踪或缺数据时为空。']
  tracked_macd_dea numeric [note: '跟踪日DEA值；尚未跟踪或缺数据时为空。']
  tracked_macd_hist numeric [note: '跟踪日MACD柱值；尚未跟踪或缺数据时为空。']
  tracked_at datetime [note: '跟踪计算时间；尚未跟踪时为空。']
  backtest_lookback_days integer [not null, default: 720, note: '预警内置回测回看交易日数量。']
  backtest_sample_count integer [not null, default: 0, note: '该标的历史同类形态样本数。']
  backtest_cross_success_count integer [not null, default: 0, note: '历史样本中5个交易日内形成金叉的次数。']
  backtest_cross_success_rate numeric [note: '历史样本金叉成功率。']
  backtest_t1_cross_confirmed_count integer [not null, default: 0, note: '历史样本中T+1已形成金叉的次数。']
  backtest_t1_trend_kept_count integer [not null, default: 0, note: '历史样本中T+1趋势维持的次数。']
  backtest_t1_trend_weakened_count integer [not null, default: 0, note: '历史样本中T+1趋势走弱的次数。']
  backtest_t1_trend_keep_rate numeric [note: '历史样本T+1趋势维持率。']
  backtest_completed_trade_count integer [not null, default: 0, note: '历史样本中完成买入和卖出的交易数。']
  backtest_profit_trade_count integer [not null, default: 0, note: '历史样本中收益率大于0的完成交易数。']
  backtest_win_rate numeric [note: '历史同类形态交易胜率。']
  backtest_avg_return_pct numeric [note: '历史同类形态平均收益率。']
  backtest_max_return_pct numeric [note: '历史同类形态最大收益率。']
  backtest_max_loss_pct numeric [note: '历史同类形态最大亏损率。']
  backtest_avg_holding_days numeric [note: '历史同类形态平均持有交易日数。']
  backtest_confidence_level varchar(255) [not null, default: 'insufficient', note: '回测可信度：high/medium/low/insufficient。']
  score numeric [not null, default: 0, note: '排序分，用于前端默认排序；可由临界价距离、绿柱缩短幅度、金叉价是否可达等计算。']
  summary text [not null, note: '面向用户展示的一句话预警摘要。']
  status varchar(255) [not null, default: 'active', note: '结果状态：active/ignored/archived。']
  created_at datetime [not null, note: '创建时间。']
  updated_at datetime [not null, note: '最近更新时间；重复扫描或跟踪覆盖结果时同步更新。']

  indexes {
    (trade_date, pattern_key, cross_zone) [name: 'idx_macd_alert_result_date_pattern_zone']
    (stock_code, trade_date) [name: 'idx_macd_alert_result_stock_date']
    (trade_date, score) [name: 'idx_macd_alert_result_date_score']
    (trade_date, stock_code, pattern_key, cross_zone) [name: 'uq_macd_alert_result_unique', unique]
  }

  Note: 'MACD日线形态预警结果表。保存每日收盘后扫描得到的金叉临界预警，支撑水下/水上金叉临界结果回看和前端列表展示。'
}
```

### 回测样本表

```dbml
Table macd_alert_backtest_sample [headercolor: #7a3f8f] {
  id varchar(255) [pk, unique, note: '回测样本ID，建议使用UUID。']
  alert_result_id varchar(255) [not null, note: '所属预警结果ID，关联macd_alert_result.id。']
  stock_code varchar(255) [not null, note: '6位股票代码，如600545。']
  stock_name varchar(255) [not null, note: '股票名称，冗余保存便于展示。']
  alert_date date [not null, note: '预警日T，YYYYMMDD。']
  alert_close_price numeric [not null, note: '预警日收盘价。']
  next_cross_trigger_price numeric [not null, note: 'T+1形成金叉所需的最低收盘价。']
  cross_trigger_distance_pct numeric [not null, note: '金叉价相对预警日收盘价的涨跌幅，小数形式。']
  next_trend_keep_price numeric [not null, note: 'T+1维持金叉趋势所需的最低收盘价。']
  trend_keep_distance_pct numeric [not null, note: '趋势维持价相对预警日收盘价的涨跌幅，小数形式。']
  alert_macd_dif numeric [not null, note: '预警日DIF值。']
  alert_macd_dea numeric [not null, note: '预警日DEA值。']
  alert_macd_hist numeric [not null, note: '预警日MACD柱值。']
  alert_cross_zone varchar(255) [not null, note: '预警日金叉位置类型：underwater/above_zero/mixed。']
  last_limit_up_date date [note: '该股预警日前最近一次涨停日期；近120日无涨停记录时为空。']
  last_limit_up_theme varchar(255) [note: '该股预警日前最近一次涨停复盘题材。']
  last_limit_up_days_ago integer [note: '最近一次涨停距预警日的交易日间隔。']
  theme_heat_window_days integer [not null, default: 5, note: '题材活跃度统计窗口交易日数。']
  theme_recent_limit_up_count integer [not null, default: 0, note: '该题材在统计窗口内的去重涨停股票数。']
  theme_recent_rank integer [note: '该题材在统计窗口内按去重涨停股票数排序的排名；无题材时为空。']
  theme_heat_level varchar(255) [not null, default: 'none', note: '题材热度等级：strong/medium/weak/none。']
  buy_date date [note: '买入日，通常为T+1；数据不足时为空。']
  buy_price numeric [note: '买入价，取T+1开盘价。']
  t1_close_price numeric [note: 'T+1收盘价，用于验证金叉价和趋势维持价。']
  t1_track_status varchar(255) [note: 'T+1趋势验证状态：t1_cross_confirmed/t1_trend_kept/t1_trend_weakened/t1_data_missing。']
  t1_macd_dif numeric [note: 'T+1 DIF值。']
  t1_macd_dea numeric [note: 'T+1 DEA值。']
  t1_macd_hist numeric [note: 'T+1 MACD柱值。']
  cross_date date [note: '首次形成DIF>=DEA的日期；未金叉时为空。']
  cross_type varchar(255) [note: '实际金叉类型：underwater/above_zero/mixed/none。']
  sell_date date [note: '卖出日期；未完成交易时为空。']
  sell_price numeric [note: '卖出价格。']
  sell_reason varchar(255) [note: '卖出原因：red_shrink/timeout。']
  return_pct numeric [note: '收益率，小数形式，如0.05表示5%。']
  holding_days integer [note: '从买入到卖出的持有交易日数。']
  status varchar(255) [not null, note: '样本状态：pending_cross/cross_failed/cross_success/sold_by_red_shrink/sold_by_timeout/insufficient_data。']
  created_at datetime [not null, note: '记录创建时间。']

  indexes {
    (alert_result_id, alert_date) [name: 'idx_macd_alert_sample_result_date']
    (alert_result_id, return_pct) [name: 'idx_macd_alert_sample_result_return']
    (stock_code, alert_date) [name: 'idx_macd_alert_sample_stock_date']
  }

  Note: 'MACD形态预警内置回测样本表。每条记录表示某条预警结果对应的一次历史同类形态样本。'
}
```

### 报告文件表

```dbml
Table macd_alert_report [headercolor: #7a3f8f] {
  id varchar(255) [pk, unique, note: '报告ID，建议使用UUID。']
  report_type varchar(255) [not null, note: '报告类型：daily_scan/daily_tracking/daily_brief/backtest。']
  trade_date date [note: '报告对应交易日；回测报告可为空。']
  source_trade_date date [note: '跟踪报告对应的来源预警日；非跟踪报告可为空。']
  alert_result_id varchar(255) [note: '单条预警报告关联的预警结果ID；非单条预警报告可为空。']
  html_file_path text [note: 'HTML报告文件相对路径，如data/reports/macd-alert/2026-06-05/brief-report.html。']
  pdf_file_path text [note: 'PDF报告文件相对路径，如data/reports/macd-alert/2026-06-05/brief-report.pdf。']
  csv_file_path text [note: 'CSV明细文件相对路径；未生成CSV时为空。']
  formats_json text [not null, note: '已生成格式JSON数组，如["html","pdf"]。']
  title varchar(255) [not null, note: '报告标题。']
  summary text [note: '报告摘要，便于列表展示。']
  created_at datetime [not null, note: '报告生成时间。']

  indexes {
    (report_type, trade_date) [name: 'idx_macd_alert_report_type_date']
    (alert_result_id) [name: 'idx_macd_alert_report_alert_result']
  }

  Note: 'MACD预警报告文件索引表。报告按需生成，保存HTML/PDF/CSV文件路径，便于前端和MCP返回报告引用。'
}
```

### 外键关系

```dbml
Ref fk_macd_alert_result_stock_code {
  macd_alert_result.stock_code > stock_list.code [delete: no action, update: no action]
}

Ref fk_macd_alert_backtest_sample_alert_result {
  macd_alert_backtest_sample.alert_result_id > macd_alert_result.id [delete: no action, update: cascade]
}

Ref fk_macd_alert_backtest_sample_stock_code {
  macd_alert_backtest_sample.stock_code > stock_list.code [delete: no action, update: no action]
}

Ref fk_macd_alert_report_alert_result {
  macd_alert_report.alert_result_id > macd_alert_result.id [delete: set null, update: cascade]
}
```

## MCP 接入设计

F06 后续需要接入 MCP，让 Codex / Hermes 等 Agent 客户端可以查询 MACD 预警、跟踪结果和预警内置回测摘要。

MCP 接入原则：

- MCP Tool 复用后端 service，不单独实现第二套业务逻辑。
- 只读 Tool 必须标注 `ToolAnnotations(readOnlyHint=True)`。
- 会写入或更新预警、跟踪、报告文件的 Tool 不能标注只读。
- Tool 返回默认限制数量，避免一次返回大量股票或回测样本撑爆 Agent 上下文。
- 所有面向 Agent 的摘要必须包含“技术形态观察结果，不构成买卖建议”的提示。

### Tool 列表

| Tool | 类型 | 副作用 | 说明 |
|------|------|--------|------|
| `get_macd_alert_daily_brief` | 只读 | 无 | 返回某交易日 MACD 预警日报，适合 Agent 直接汇报 |
| `list_macd_alert_results` | 只读 | 无 | 分页查询预警结果 |
| `list_macd_alert_tracking_results` | 只读 | 无 | 分页查询 T+1 跟踪结果 |
| `scan_macd_alerts` | 写入 | 生成/覆盖预警结果 | 对指定交易日执行扫描 |
| `track_macd_alerts` | 写入 | 更新跟踪状态 | 跟踪上一交易日 active 预警标的 |
| `list_macd_alert_backtest_samples` | 只读 | 无 | 分页查询某条预警结果的历史同类形态样本 |
| `get_macd_alert_report` | 只读 | 无 | 返回报告文件元信息和短摘要 |
| `generate_macd_alert_report` | 写入 | 生成报告文件 | 按需生成 HTML/PDF/CSV 报告文件 |

### 日报 Tool

```text
get_macd_alert_daily_brief(trade_date?: string, limit?: int)
```

默认行为：

- `trade_date` 为空时使用本地日线数据最新交易日。
- `limit` 默认 10，最大 30。
- 同时返回：
  - 数据新鲜度。
  - 今日新增预警摘要。
  - 昨日预警跟踪摘要。
  - 题材热度为 `strong` 或 `medium` 且金叉价距离较近的重点标的。
  - 报告可生成提示。
  - 非买卖建议声明。

返回结构示例：

```json
{
  "trade_date": "2026-06-05",
  "latest_trade_date": "2026-06-05",
  "is_data_fresh": true,
  "disclaimer": "以下为技术形态观察结果，不构成买卖建议。",
  "new_alert_count": 18,
  "tracking": {
    "tracked_count": 12,
    "cross_confirmed_count": 3,
    "trend_kept_count": 6,
    "trend_weakened_count": 3
  },
  "report_generatable": true,
  "report_generation_hint": "可调用 generate_macd_alert_report 生成 HTML/PDF 报告。",
  "highlights": []
}
```

### 分页与返回限制

列表类 Tool 必须支持：

```text
limit: 默认20，最大100
offset: 默认0
summary_only: 默认false
sort_by: score / cross_trigger_distance_pct / theme_heat_level / trade_date
```

MCP 默认不返回全量样本。预警结果只返回回测摘要，历史样本必须通过 `list_macd_alert_backtest_samples(alert_result_id, limit, offset)` 分页读取。

### 报告文件按需生成

`scan_macd_alerts`、`track_macd_alerts` 和 `get_macd_alert_daily_brief` 默认不生成报告文件，只返回 `text_summary` 和 `report_generatable=true`。

当用户需要报告时，调用：

```text
generate_macd_alert_report(report_type, trade_date?, source_trade_date?, alert_result_id?, formats?)
```

返回报告文件引用：

```text
report_id
report_type
formats
html_file_path
pdf_file_path
csv_file_path
summary
```

Agent 面向用户回答时优先展示 `text_summary`。当报告已生成时，附上 PDF 文件路径；需要继续结构化筛选时，再调用分页 Tool。

### 数据新鲜度

所有 MCP Tool 返回结果中应包含：

```text
latest_trade_date
requested_trade_date
is_data_fresh
data_warning
```

如果本地日线数据最新交易日早于请求交易日，Tool 不能静默返回空结果，必须提示：

```text
本地最新日线数据为 YYYY-MM-DD，请求交易日为 YYYY-MM-DD，预警结果可能不可用或过期。
```

### 幂等策略

`scan_macd_alerts` 和 `track_macd_alerts` 可能被 MCP 客户端重复调用，因此必须幂等：

- 同一交易日、同一股票、同一形态、同一 `cross_zone` 只保留一条预警结果。
- 重复扫描时更新已有记录，不重复插入。
- 重复跟踪时覆盖 `track_status` 和跟踪日指标。

第一版暂不支持同一天多套扫描参数并存；如果后续需要支持，应增加 `params_hash` 字段区分不同扫描口径。

### 预警内置回测策略

`scan_macd_alerts` 生成每条预警结果时，同步计算该标的历史同类形态回测摘要，并写入 `macd_alert_result`。

MCP 默认只返回摘要字段：

```text
backtest_sample_count
backtest_cross_success_rate
backtest_win_rate
backtest_avg_return_pct
backtest_confidence_level
```

历史样本明细不随预警列表默认返回，必须通过：

```text
list_macd_alert_backtest_samples(alert_result_id, limit, offset)
```

分页查看。

### 安全与注解

- `get_macd_alert_daily_brief`、`list_macd_alert_results`、`list_macd_alert_tracking_results`、`list_macd_alert_backtest_samples` 使用 `readOnlyHint=True`。
- `get_macd_alert_report` 使用 `readOnlyHint=True`。
- `scan_macd_alerts`、`track_macd_alerts`、`generate_macd_alert_report` 不使用 `readOnlyHint=True`。
- 暂不暴露删除 Tool；如果后续提供清理历史结果能力，必须标注 destructive 并增加用户确认语义。

## 代码层面的实现方案

### 后端

- 新增 `backend/app/modules/macd_alert/`：
  - MACD 序列计算和临界价计算。
  - 预警扫描。
  - HTML / PDF / CSV 报告按需生成。
  - 回测样本生成。
  - 回测汇总指标计算。
- 新增 `backend/app/schemas/macd_alert.py`：
  - 扫描请求/响应。
  - 预警内置回测摘要响应。
  - 样本明细响应。
- 新增 `backend/app/api/routes/macd_alert.py`：
  - `/api/macd-alerts/scan`
  - `/api/macd-alerts/track`
  - `/api/macd-alerts/results`
  - `/api/macd-alerts/results/{alert_id}/backtest-samples`
- 扩展 `backend/app/api/routes/mcp.py`：
  - 暴露 MACD 预警 MCP Tool。
  - 严格区分只读 Tool 和写入 Tool 注解。
  - MCP Tool 复用同一套 service 与 schema。
- 复用 DuckDB 日线行情读取，不重新拉取外部数据。

### 前端

- 新增 MACD 预警页面。
- 增加预警结果 Tab 和回测结果 Tab。
- 支持从预警结果跳转到个股详情页。
- 第一版不做复杂图表，先保证结果表和汇总指标清晰。

## 验收标准

- 用户可以选择交易日并扫描日线 MACD 水下/水上金叉临界预警，默认扫描主板非 ST。
- 预警结果能输出类似“600545 卓郎智能连续 2 天 MACD 绿柱缩短，若下一交易日收盘价不低于 X 则形成水下金叉；若不低于 Y 则金叉趋势仍在维持”的文案。
- 预警结果能区分水下金叉临界和水上金叉临界。
- 金叉价高于下一交易日涨停价的结果不删除，标记为“金叉价理论不可达”，并降低排序优先级。
- 重点预警列表默认只展示金叉价距离不超过 5% 的结果，全部结果仍可查看。
- 预警结果能标注该股上次涨停题材，并展示该题材近 5 个交易日活跃度。
- 如近 120 个交易日没有涨停复盘记录，预警结果明确标注无近期涨停题材归属。
- T+1 扫描时能跟踪 T 日 active 预警标的，并标注已金叉、趋势维持、趋势走弱或数据缺失。
- MCP 可以查询 MACD 预警日报、预警列表、跟踪列表和回测结果。
- MCP 扫描和跟踪具备幂等性，不重复插入同一交易日同一标的同一形态结果。
- MCP 列表类 Tool 默认分页，不能默认返回全量样本。
- MCP 返回包含数据新鲜度和非买卖建议声明。
- 扫描、跟踪和回测完成后不自动生成报告文件；用户或 Agent 需要时按需生成 HTML/PDF 报告。
- 每条预警发出时同步生成该标的历史同类形态回测摘要。
- 预警内置回测按照 T+1 开盘买入、T+1 趋势验证、5 个交易日内观察金叉、金叉后最多持有 10 个交易日、红柱缩短或超时卖出的规则计算。
- 回测输出 T+1 已金叉、趋势维持、趋势走弱的统计，用于验证趋势维持价是否有效。
- 回测输出汇总指标和样本明细。
- 第一版只使用日线数据，不读取或依赖 5 分钟 K 线。
- 如需要落表，必须先完成数据库设计审批并更新 `docs/human/data-model/AlphaPredator.dbml`。

## 当前状态

- 已完成需求口径整理、数据库设计草案和 human DBML 更新核对。
- DBML 已审批并更新到 `docs/human/data-model/AlphaPredator.dbml`。
- 已完成后端核心、SQLite schema、FastAPI、MCP 和前端页面实现。
- 已将扫描升级为 `MACD_ALERT_SCAN` 后台任务，复用现有 `task_info` 进度体系，不新增数据库表。
- 已新增个股 MACD 即时验证入口：按股票代码和截止日复用批量预警规则计算截止日触发状态、最近触发、历史样本和汇总指标；该能力不落库、不新增数据库表，仅用于核验计算口径。

## 已知问题 / 待人工决策

- MCP 外部客户端实连验证仍依赖 F05 未完成项；不阻塞 F06 代码实现，但会影响最终 MCP 外部客户端端到端验收。

