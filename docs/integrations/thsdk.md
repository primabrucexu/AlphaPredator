# thsdk 能力与接入说明

## 1. 文档定位

本文记录 AlphaPredator 使用 thsdk 时需要长期保留的信息，包括 SDK 能力索引、项目接入状态、账号配置和架构约束。它不是上游 README 的副本；具体参数和返回样例仍以上游版本文档为准。

- 项目锁定版本：`thsdk==1.7.18`
- 依赖定义：`backend/pyproject.toml`
- 上游版本文档：https://pypi.org/project/thsdk/1.7.18/
- 项目适配器：`backend/app/market_data/provider/thsdk.py`
- 项目抽象接口：`backend/app/market_data/provider/base.py`

状态说明：

- **已接入**：业务可以通过 `MarketDataProvider` 使用。
- **曾实测**：开发过程中使用真实 thsdk 服务完成过冒烟验证，不代表当前账号始终拥有权限。
- **未接入**：仅确认 thsdk 1.7.18 提供该能力，业务代码尚不可直接使用。

## 2. 账号与连接

thsdk 按以下优先级读取账户信息：

1. `THS({...})` 直接传入 `username`、`password`、`mac`。
2. 环境变量 `THS_USERNAME`、`THS_PASSWORD`、`THS_MAC`。
3. 未配置时使用临时游客账户。

AlphaPredator 当前使用 `THS()`，因此正式账户应在启动后端前通过环境变量注入：

```powershell
$env:THS_USERNAME="你的同花顺账号"
$env:THS_PASSWORD="你的同花顺密码"
$env:THS_MAC="aa:bb:cc:dd:ee:ff"
```

账号、密码和设备标识不得写入源码或提交到 Git。游客账户可能受到市场范围、实时性和专业数据权限限制；正式账户的实际能力也以账号授权为准。

## 3. 证券代码

AlphaPredator 对外统一使用 `6位代码.交易所`，只在 thsdk Provider 内转换为 THSCODE：

| AlphaPredator | THSCODE | 市场 |
|---|---|---|
| `600519.SH` | `USHA600519` | 沪市 A 股 |
| `000001.SZ` | `USZA000001` | 深市 A 股 |
| `920000.BJ` | `USTM920000` | 北交所 |

常见的其他上游市场前缀包括 `USHI`（上证指数）、`USZI`（深证指数）、`URFI`（行业或概念板块）、`UNQQ`（美股示例）和 `UFXB`（外汇）。国内固定编码接口通常要求完整的 10 位 THSCODE；不确定市场时可以使用 `search_symbols` 或 `complete_ths_code`。

## 4. 能力矩阵

### 4.1 连接与通用响应

| 能力 | thsdk 接口 | 项目状态 |
|---|---|---|
| 建立、重试和断开连接 | `connect`、`disconnect`、上下文管理器 | 已接入 |
| 底层通用查询 | `query_data` | 未接入 |
| 响应状态及数据 | `Response.success/error/data/extra` | Provider 内部适配 |
| 转换为 DataFrame | `Response.df` | 未使用 |
| SDK 帮助 | `help` | 未接入 |

### 4.2 证券搜索与市场目录

| 能力 | thsdk 接口 | 项目状态 |
|---|---|---|
| 模糊搜索证券 | `search_symbols` | 已接入，曾实测 |
| 查询证券信息 | `query_securities` | 未接入 |
| 补全 THSCODE | `complete_ths_code` | 未接入 |
| A 股列表 | `stock_cn_lists` | 已接入，曾实测 |
| 美股、港股、北交所、英国和 B 股列表 | `stock_us_lists`、`stock_hk_lists`、`stock_bj_lists`、`stock_uk_lists`、`stock_b_lists` | 未接入 |
| 期货、纳斯达克、债券列表 | `futures_lists`、`nasdaq_lists`、`bond_lists` | 未接入 |
| ETF 与 T+0 ETF 列表 | `fund_etf_lists`、`fund_etf_t0_lists` | 未接入 |
| 外汇列表 | `forex_list` | 未接入 |
| 期权列表 | `option_lists` | 上游 1.7.18 标记为未实现 |

### 4.3 行情、K 线与分时

| 能力 | thsdk 接口 | 项目状态 |
|---|---|---|
| A 股最新行情 | `market_data_cn` | 已接入，曾实测 |
| 日 K | `klines(interval="day")` | 已接入，曾实测 |
| 分钟 K | `klines(interval="1m/5m/15m/30m/60m/120m")` | 未接入 |
| 周、月、季、年 K | `klines(interval="week/month/quarter/year")` | 未接入 |
| 当日分时 | `intraday_data` | 未接入 |
| 历史日内分钟快照 | `min_snapshot` | 未接入 |
| 约 3 秒 Level-1 Tick | `tick_level1` | 未接入 |
| 超级盘口历史数据 | `tick_super_level1` | 未接入 |
| 五档盘口 | `depth` | 未接入 |
| 买卖盘深度 | `order_book_ask`、`order_book_bid` | 未接入 |

`klines` 支持 `forward` 前复权、`backward` 后复权和不复权。当前项目的日 K 固定使用前复权。按日期查询时应同时传入 `start_time`、`end_time`，不要再传 `count`；只按数量查询时，Provider 会截取最后 `count` 条，以处理上游偶尔多返回一条的情况。

### 4.4 多市场行情

| 能力 | thsdk 接口 | 项目状态 |
|---|---|---|
| 美股、港股、英国行情 | `market_data_us`、`market_data_hk`、`market_data_uk` | 未接入 |
| 债券、基金、期货、期权行情 | `market_data_bond`、`market_data_fund`、`market_data_future`、`option_data` | 未接入 |
| 外汇、指数、板块行情 | `market_data_forex`、`market_data_index`、`market_data_block` | 未接入 |

### 4.5 板块与成分股

| 能力 | thsdk 接口 | 项目状态 |
|---|---|---|
| 市场板块目录 | `block`、`market_block` | 未接入 |
| 板块成分股 | `block_constituents` | 未接入 |
| 行业与概念板块 | `ths_industry`、`ths_concept` | 未接入 |
| 指数列表 | `index_list` | 未接入 |
| 按板块或市场查询代码 | `codes_by_block`、`codes_by_market` | 未接入 |

### 4.6 交易过程与公司行为

| 能力 | thsdk 接口 | 项目状态 |
|---|---|---|
| 集合竞价 | `call_auction` | 未接入 |
| 集合竞价异动 | `call_auction_anomaly` | 未接入 |
| 大单资金流 | `big_order_flow` | 未接入 |
| 权息资料 | `corporate_action` | 未接入 |

### 4.7 问财、资讯与 IPO

| 能力 | thsdk 接口 | 项目状态 |
|---|---|---|
| 问财基础或自然语言查询 | `wencai_base`、`wencai_nlp` | 未接入 |
| 资讯列表 | `news` | 未接入 |
| 今日 IPO、待上市 IPO | `ipo_today`、`ipo_wait` | 未接入 |

上游示例中还包含 DDE、深度详情等场景。若准备使用未列出签名的低层或示例能力，应先核对锁定版本源码和真实账户权限，再补充本表。

## 5. AlphaPredator 接入约束

1. 业务层只能调用 `MarketDataProvider`，不能直接导入 thsdk。
2. THSCODE 转换、`Response` 解包、字段归一化和异常转换全部留在 `market_data/provider/`。
3. thsdk 是同步阻塞的原生库封装。当前使用一个客户端和可重入锁串行调用，FastAPI 保持单 Worker，不能假设其线程安全。
4. 外部请求失败时抛出明确的 `MarketDataError`，禁止返回伪造行情。
5. 行情时序数据默认在线获取，不写入 SQLite；新增缓存或持久化必须由对应 Feature 明确规定。

## 6. 新能力接入流程

1. 在本文件将目标能力标记为“准备接入”，记录接口、账号权限和预期字段。
2. 在 `MarketDataProvider` 增加业务需要的最小接口，不暴露 thsdk 响应对象。
3. 在 `ThsdkMarketDataProvider` 内完成调用、转换、加锁和异常适配。
4. 使用替身 Provider 编写业务测试，再使用真实账号做单独冒烟验证。
5. 验证成功后更新本表的“已接入”和“曾实测”状态。
