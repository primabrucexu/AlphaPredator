# DuckDB 日行情表结构说明

> 本文档定义 AlphaPredator 在 DuckDB 中保存的股票日行情事实表结构与约束口径。

## 1. 设计原则

- 日行情事实数据仅保存在 DuckDB，不写入 SQLite。
- SQLite 仅用于任务状态、元数据与股票清单（如 `init_task`、`stock_universe`）。
- 查询接口（首页搜索后的详情页、批量行情读取）以 DuckDB 为唯一日行情数据源。

## 2. 表定义

当前核心表：`daily_bars`

```sql
CREATE TABLE IF NOT EXISTS daily_bars (
    stock_code VARCHAR NOT NULL,
    trade_date VARCHAR NOT NULL,
    open_price DOUBLE NOT NULL,
    high_price DOUBLE NOT NULL,
    low_price DOUBLE NOT NULL,
    close_price DOUBLE NOT NULL,
    volume BIGINT NOT NULL,
    turnover_amount_billion DOUBLE NOT NULL DEFAULT 0.0
)
```

字段语义：

- `stock_code`：6 位股票代码（如 `000001`）
- `trade_date`：交易日（`YYYY-MM-DD`）
- `open_price` / `high_price` / `low_price` / `close_price`：开高低收
- `volume`：成交量
- `turnover_amount_billion`：成交额（亿元）

## 3. 写入映射规则

初始化从 `tushare.daily(trade_date=YYYYMMDD)` 获取数据，写入 DuckDB 时按下列规则转换：

- `ts_code` -> `stock_code`：取点号前 6 位（如 `000001.SZ` -> `000001`）
- `trade_date`：`YYYYMMDD` -> `YYYY-MM-DD`
- `open/high/low/close` -> `open_price/high_price/low_price/close_price`
- `vol` -> `volume`（转整数）
- `amount`（千元）-> `turnover_amount_billion = amount / 1e6`

## 4. 幂等与覆盖策略

- 单日导入采用“先删后插”：
  - `DELETE FROM daily_bars WHERE trade_date = ?`
  - 再批量插入当日全量
- 导入后执行行数校验：
  - `COUNT(*) WHERE trade_date = ?` 必须等于本次写入行数
- 校验失败视为导入失败并回滚任务。

## 5. 查询建议

常用查询：

```sql
-- 某只股票全部日线
SELECT *
FROM daily_bars
WHERE stock_code = '000001'
ORDER BY trade_date;
```

```sql
-- 最新交易日全市场数据
SELECT *
FROM daily_bars
WHERE trade_date = (SELECT MAX(trade_date) FROM daily_bars)
ORDER BY turnover_amount_billion DESC;
```

## 6. 迁移说明

- 历史上 SQLite 可能存在 `market_daily_quote` 表，仅作兼容保留。
- 自本方案起，日行情写入与读取都以 DuckDB `daily_bars` 为准。

