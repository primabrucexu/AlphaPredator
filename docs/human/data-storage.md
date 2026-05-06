# 本项目数据存储设计
> 本项目当前需要存储的数据包括：
> - 全市场当日的交易数据
> - 股票列表
> - 用户选股样本
> - 用户选股模式


## 1. 全市场当日的交易数据
- 存储方式：duckDB
- 用途：用于在详情页展示日K线图、计算技术指标、查询涨跌停等。
- 数据来源：tushare的daily接口
- 结构返回字段说明：
  - `ts_code`：股票代码（tushare特有格式，如 `000001.SZ`）
  - `trade_date`：交易日期（字符串格式，`YYYYMMDD`）
  - `open`：开盘价
  - `high`：最高价
  - `low`：最低价
  - `close`：收盘价
  - `pre_close`：昨收价（除权价）
  - `change`：涨跌额
  - `pct_chg`：涨跌幅（%）
  - `vol`：成交量（手）
  - `amount`：成交额（千元）
- duckDB表结构设计：
```sql
CREATE TABLE daily_bars (
    ts_code VARCHAR NOT NULL,
    trade_date VARCHAR NOT NULL,
    open DOUBLE NOT NULL,
    high DOUBLE NOT NULL,
    low DOUBLE NOT NULL,
    close DOUBLE NOT NULL,
    pre_close DOUBLE NOT NULL,
    change DOUBLE NOT NULL,
    pct_chg DOUBLE NOT NULL,
    vol DOUBLE NOT NULL,
    amount DOUBLE NOT NULL,
    is_up_limit BOOLEAN NOT NULL,
    is_down_limit BOOLEAN NOT NULL,
);
```
### 备注
- `is_up_limit` 和 `is_down_limit` 字段用于标记当日是否涨停或跌停，方便后续查询和分析。
- 涨跌停计算规则见 [A股涨跌停计算规则](price-limit-rule.md)。
- 如何判断这只股票属于那只个板块？可以通过股票列表中的板块信息进行关联查询。

## 2. 股票列表
- 存储方式：SQLite
- 用途：用于在首页搜索功能中快速定位股票的 `ts_code`，以及提供股票的基本信息（名称、行业、上市日期等）。
- 数据来源：用户通过csv格式的股票列表文件上传
- csv字段说明：
  - `ts_code`：股票代码（tushare特有格式，如 `000001.SZ`）
  - `symbol`：股票代码（6位，如 `000001`）
  - `name`：股票名称
  - `industry`：所属行业
  - `list_date`：上市日期
  - `cnspell`：股票名称拼音简称
  - `market`：所属市场，有且仅有四个：主板、创业板、科创板、北交所
  - `list_data`：上市日期
  - `list_status`：上市状态 L（上市）其余字母表示非上市
- SQLite表结构设计：
```sql
CREATE TABLE stock_list (
    ts_code VARCHAR PRIMARY KEY,
    symbol VARCHAR NOT NULL,
    name VARCHAR NOT NULL,
    is_st INTEGER NOT NULL,
    industry VARCHAR NOT NULL,
    list_date VARCHAR NOT NULL,
    cnspell VARCHAR NOT NULL,
    market VARCHAR NOT NULL,
    list_status VARCHAR NOT NULL
);
```
### 备注
- `is_st` 字段用于标记是否ST股票，获取方式：通过name字段中包含`ST`则为1，否则为0。

## 3. 用户选股样本
- 存储方式：SQLite
- 用途：用于存储用户上传的选股样本数据，供AI学习用户的选股偏好
- 数据来源：用户通过特定页面输入选股样本数据
- sqlite表结构设计：
```sql
CREATE TABLE user_stock_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_code VARCHAR NOT NULL,
    trade_date VARCHAR NOT NULL,
    pick_model_id INTEGER NOT NULL
);
```
### 备注
- `pick_model_id` 字段用于关联用户选股模式表，表示该选股样本属于哪个选股模式。

## 4. 用户选股模式
- 存储方式：SQLite
- 用途：用于存储用户创建的选股模式信息，供AI学习用户的选股偏好
- 数据来源：用户通过特定页面输入选股模式数据
- sqlite表结构设计：
```sql
CREATE TABLE pick_models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR NOT NULL,
    description TEXT
);
```

## 5. 韭研公社每日复盘数据

- 存储方式：SQLite
- 用途：用于从韭研公社中获取的每日复盘数据，供AI学习市场热点信息
- 数据来源：通过API调用自动获取

### 5.1 每日涨停简图存储表

- sqlite表结构设计：

```sql
CREATE TABLE daily_hot_pic
(
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  trade_date        VARCHAR NOT NULL,
  summary_image_url VARCHAR NOT NULL,
  source            VARCHAR NOT NULL -- 数据来源，目前只有韭研公社，填写为jygs
);
```

### 5.2 每日涨停解析存储表

```sql
CREATE TABLE daily_hot_info
(
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  trade_date    TEXT    NOT NULL,            -- 交易日期
  limit_up_time TEXT    NOT NULL DEFAULT '', -- HH:MM:SS格式的涨停时间
  stock_code    INTEGER NOT NULL,            -- 6位数字的股票代码
  name          VARCHAR NOT NULL,            -- 股票名称
  streak_text   VARCHAR NOT NULL,            -- 连板信息文本，如“两天两板”，无内容则表示首次涨停
  hot_theme     VARCHAR NOT NULL,            -- 涨停题材
  reason        TEXT    NOT NULL,            -- 涨停解析内容
  source        VARCHAR NOT NULL             -- 数据来源，目前只有韭研公社，填写为jygs
);
```