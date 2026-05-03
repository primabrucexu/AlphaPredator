# 个股详情页整改清单 v2（9项）

## P0（先做，阻塞验收）

- [x] 1. 修复悬停不显示当日数据
  - 现象：悬停 K 线不切换到对应日期数据
  - 改动：`frontend/src/pages/StockDetailPage.tsx` 中 `updateAxisPointer` 改为支持“索引值 + 日期字符串”双映射
  - 验收：悬停任意 K 线，顶部和副图信息都切换到该日；移出恢复最新日

- [x] 2. 副图顺序调整
  - 目标顺序：成交量 -> MACD -> KDJ -> RSI
  - 改动：调整 `grid`、`xAxis/yAxis`、`series` 与信息栏渲染顺序
  - 验收：图与信息区顺序一致，不出现错位

- [x] 3. KDJ 取消固定上下限
  - 现象：KDJ 被 0~100 截断，J 值显示不完整
  - 改动：移除 KDJ 轴 `min/max` 固定限制，改为自动范围
  - 验收：极值场景下 K/D/J 全部可见，无遮挡

- [x] 4. 成交量副图补齐均线
  - 目标：VOL 柱 + MA5/MA10/MA20 三条线
  - 改动：前端增加 VOL MA10/MA20 渲染；后端补充 `volume_ma10`、`volume_ma20` 数据
  - 验收：成交量副图 3 条均量线都可见且随时间联动

- [x] 5. 悬停展示全指标详细信息
  - K线：开/高/低/收
  - 成交量：成交量、成交额、换手率、均量
  - MACD：MACD、DIF、DEA
  - KDJ：K、D、J
  - RSI：RSI6、RSI12、RSI24
  - 改动：统一 `hoverIndex` 驱动所有 info bar
  - 验收：悬停主图或任一副图，同步刷新全部指标

- [x] 6. 主图改为白色主题
  - 改动：取消 `theme="dark"`，图表与卡片背景改白底；网格线/轴文字改浅灰体系
  - 验收：白底下可读性正常，涨跌配色仍清晰

## P1（体验优化，P0后做）

- [x] 7. 副图指标信息“就近展示”
  - 目标：每个副图旁显示对应信息，而不是全部堆在顶部
  - 改动：使用 `position: absolute` 叠加层，将各副图 info bar 悬浮在对应副图区域顶部
  - 验收：用户能一眼对应“图-指标值”

- [x] 8. 副图名称显式展示
  - 目标：每块副图都有标题（成交量/MACD/KDJ/RSI）
  - 改动：`SubChartOverlay` 组件在每个副图信息行前显示副图标题
  - 验收：不看代码也能识别当前副图类型

- [x] 9. 成交量信息补充换手率与成交额（按日）
  - 改动：`daily_bars` 增加当日 `turnover_amount_billion`、`turnover_rate`（后端从 SQLite `daily_stock_snapshots` join 提供）
  - 验收：悬停任意日期可看到该日成交额与换手率，不是仅显示最新快照

## 涉及文件清单（按改动方向）

- 前端主文件：`frontend/src/pages/StockDetailPage.tsx`
- 前端类型契约：`frontend/src/lib/api.ts`
- 后端响应模型：`backend/app/schemas/market.py`
- 后端聚合逻辑：`backend/app/modules/market_data/service.py`

## 验收用例（回归最小集）

- [x] 悬停主图任一点，所有信息联动到同一日期
- [x] 悬停副图任一点，也能驱动主信息同步
- [x] 副图顺序严格匹配：成交量、MACD、KDJ、RSI
- [x] KDJ 在异常高/低值场景完整显示
- [x] 成交量副图显示 MA5/10/20 三线
- [x] 白色主题下文字、网格、十字线可读
- [x] 无数据时显示 `--`，页面不报错不闪退

