# AlphaPredator K线涨跌停颜色设计文档

## 1. 背景与目标

在已有 K 线渲染中，“普通上涨/下跌”与“涨停/跌停”目前颜色语义不够区分。

本设计目标：

1. 在不破坏 A 股“红涨绿跌”认知的前提下，清晰区分“普通涨跌”与“涨停/跌停”。
2. 颜色方案支持亮色与暗色主题。
3. 提供色弱用户可识别的非颜色兜底线索。
4. 采用语义化色值 Token，避免图表代码中散落硬编码。

补充约束：

- 本文档只负责视觉语义，不负责规则计算；
- 若 `is_limit_up`、`is_limit_down` 等字段是在后续版本新增，应通过 `docs/market-data-reinitialize-workflow.md` 定义的重初始化流程补齐历史数据，而不是在前端临时推断。

## 2. 状态定义

K 线单根蜡烛按以下四种状态渲染：

- `up_normal`：普通上涨
- `down_normal`：普通下跌
- `up_limit`：涨停
- `down_limit`：跌停

判定优先级：

1. 若 `is_limit_up=true`，使用 `up_limit`。
2. 若 `is_limit_down=true`，使用 `down_limit`。
3. 其余按 `close >= open` 归类 `up_normal`，否则 `down_normal`。

> 说明：涨停/跌停状态以服务端计算落库字段为准，不建议前端按百分比临时推算。

## 3. 建议颜色方案（亮色主题）

### 3.1 主色表

| 状态 | 填充色（fill） | 边框色（stroke） | 含义 |
|---|---|---|---|
| `up_normal` | `#E64B4B` | `#C62828` | 普通上涨（红） |
| `down_normal` | `#2FA164` | `#1E7A4C` | 普通下跌（绿） |
| `up_limit` | `#8E24AA` | `#6A1B9A` | 涨停（紫红，显著区别于普通上涨） |
| `down_limit` | `#1565C0` | `#0D47A1` | 跌停（蓝色，显著区别于普通下跌） |

### 3.2 文字与提示色

- `limit_tag_text`: `#FFFFFF`
- `limit_up_badge_bg`: `#6A1B9A`
- `limit_down_badge_bg`: `#0D47A1`

## 4. 暗色主题映射

| 状态 | 填充色（fill） | 边框色（stroke） |
|---|---|---|
| `up_normal` | `#FF6B6B` | `#FF8A80` |
| `down_normal` | `#43C17C` | `#69F0AE` |
| `up_limit` | `#B05CCC` | `#CE93D8` |
| `down_limit` | `#3B82F6` | `#93C5FD` |

## 5. 色弱兜底（必须）

仅靠颜色会导致识别困难，涨跌停必须增加非颜色信号：

1. `up_limit`：在蜡烛上方叠加小三角或“涨停”角标。
2. `down_limit`：在蜡烛下方叠加小三角或“跌停”角标。
3. 涨跌停 K 线边框加粗（例如 `2px`），普通 K 线保持 `1px`。
4. tooltip 文本中显式显示状态：`普通上涨/普通下跌/涨停/跌停`。

## 6. 图表渲染规则

## 6.1 K 线本体

- 使用逐点 itemStyle（按每根 K 线状态赋值）。
- 涨跌停优先级高于普通涨跌。
- 影线颜色与边框色一致，避免视觉冲突。

## 6.2 成交量副图（建议同步）

- 普通上涨量柱：`up_normal` 色
- 普通下跌量柱：`down_normal` 色
- 涨停当日量柱：`up_limit` 色
- 跌停当日量柱：`down_limit` 色

## 6.3 提示面板

hover K 线时，信息面板增加：

- `limit_status`: `NONE | UP_LIMIT | DOWN_LIMIT`
- 若为涨跌停，显示角标（与主图同色）

## 7. 接口字段要求

为了稳定判定，建议前端直接消费服务端字段：

- `is_limit_up: boolean`
- `is_limit_down: boolean`
- `limit_up_price: number | null`
- `limit_down_price: number | null`
- `limit_status: string`

当字段缺失时，前端降级为普通涨跌配色，并记录告警日志。

## 8. 验收标准

1. 用户可在不看 tooltip 的情况下区分“普通涨跌”与“涨跌停”。
2. 主图与成交量副图的涨跌停颜色语义一致。
3. 色弱模式下仍可通过角标/边框加粗识别涨跌停。
4. 亮色与暗色主题下对比度均可读。
5. 当服务端返回涨跌停标识时，前端不再做百分比推断。

## 9. 分期建议

- `P0`：主图颜色升级 + tooltip 状态文本 + 成交量同步色
- `P1`：色弱模式（角标 + 边框加粗）+ 主题切换细化
- `P2`：用户可配置配色方案（保留默认推荐）

## 10. 备注

本设计文档仅覆盖“涨跌停视觉语义”。指标计算、涨跌停规则计算与历史固化策略，遵循 `docs/price-limit-rule-design.md`；新增字段后的补齐与重建链路，遵循 `docs/market-data-reinitialize-workflow.md`。
