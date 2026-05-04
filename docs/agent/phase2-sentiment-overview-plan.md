# Phase 2：短线情绪总览 — 方案设计与执行计划

## 背景

Phase 1 已阶段性完成，具备基础行情查看能力。现进入 Phase 2：将韭研公社复盘图片转成可落库、可回溯、可在页面消费的热点板块数据，并完成短线情绪总览页面。

---

## 当前进展

### 已完成

| 模块 | 状态 | 说明 |
|------|------|------|
| `hot_sector_importer.py` | ✅ 完成 | OCR 解析 + 结构化 + SQLite 入库，测试全通过 |
| SQLite 5 张热点表 | ✅ 完成 | `hot_sector_image_sources` / `stock_facts` / `sector_mappings` / `daily_aggregates` / `recent_3d` |
| `service.py` 热点整合 | ✅ 完成 | `get_market_overview()` 已优先读取 image pipeline 数据 |
| `MarketOverviewPage.tsx` | ✅ 完成 | 展示当日热点板块列表 + Echarts 柱状图 |
| `bin/import-hot-sector-images.sh` | ✅ 完成 | 导入脚本已存在 |

### 缺口（对照 Phase 2 达成标准）

| 缺口 | 达成标准映射 |
|------|-------------|
| 后端：缺少跨交易日热点历史查询 API | 多个交易日之间的热点变化图表 |
| 后端：缺少连板股票查询逻辑 + API | 页面展示股票连板情况 |
| 前端：缺少独立的"短线情绪总览"页面 | 当日热点、历史变化、连板 |
| Phase 1 已核验：`is_up_limit`/`is_down_limit` 已在 DuckDB 中落地 | 无需额外修复，后续仅关注显示效果联调 |
| Phase 1 已完成：`stock_universe` → `stock_list` 命名清理 | 命名已统一，保留兼容迁移逻辑 |

---

## 方案设计

### 任务 1：后端 — 热点历史 API

**目标**：新增 `GET /market/hot-sectors/history` 端点，支持多日热点趋势查询。

**响应结构**：

```python
class HotSectorHistoryDay(BaseModel):
    trade_date: str
    sectors: list[HotSectorDetailItem]

class HotSectorDetailItem(BaseModel):
    name: str                         # sector_name_canonical
    heat_score: int
    rank_today: int
    source_stock_count: int
    max_board_count: int
    representative_stock_codes: list[str]
    representative_stock_names: list[str]
    trend_tag: str                    # new / persistent / fading
    days_present_3d: int
    trend_label: str                  # 持续 N 日 / 新晋热点 / 热度回落

class HotSectorHistoryResponse(BaseModel):
    trade_dates: list[str]           # 按日期升序
    days: list[HotSectorHistoryDay]
```

**查询参数**：
- `days: int = 7`（最近 N 个交易日，最大 30）

**数据来源**：`hot_sector_daily_aggregates` JOIN `hot_sector_recent_3d`

---

### 任务 2：后端 — 连板股票 API

**目标**：新增 `GET /market/limit-up-streaks` 端点，返回近期连板股票列表。

**数据来源**：`hot_sector_stock_facts`（已有 `board_count` 字段）

**响应结构**：

```python
class LimitUpStreakItem(BaseModel):
    trade_date: str
    stock_code: str
    stock_name: str
    board_count: int                  # 连板数
    limit_up_time: str
    reason_clean: str
    primary_sector: str               # 来自 sector_mappings

class LimitUpStreaksResponse(BaseModel):
    trade_date: str
    streaks: list[LimitUpStreakItem]  # 按 board_count DESC 排序
```

**查询参数**：
- `trade_date: str | None = None`（默认最新日期，格式 YYYY-MM-DD）
- `min_boards: int = 2`（最低连板数）

---

### 任务 3：前端 — 短线情绪总览页面

**新页面**：`SentimentOverviewPage.tsx`（路由 `/sentiment`）

**布局方案**（3 个区块）：

#### 区块 A：热点板块趋势热力图
- X 轴：交易日（近 7 日）
- Y 轴：板块名称（按最新一日 rank 排序）
- 颜色深浅：heat_score
- 点击板块名：可展开该板块近期连板股列表

#### 区块 B：当日热点板块排行
- 复用 `MarketOverviewPage` 中的热点列表
- 增加：连板代表股票名称、最高板数 badge

#### 区块 C：近期连板龙头
- 分日展示近 3 日的连板股
- 按 board_count 降序排列
- 字段：股票名、代码、板数、封板时间、涨停原因、所属板块

---

### 任务 4：Phase 1 遗留修复（已完成）

- 已将数据源与测试中的 `stock_universe` 命名清理为 `stock_list`。
- SQLite 保留兼容迁移：检测到旧表时自动重命名为 `stock_list`。

---

## 执行计划（分批）

| 批次 | 任务 | 预计工作量 |
|------|------|-----------|
| Batch A | 已完成：Phase 1 遗留命名清理（4.1） | 小 |
| Batch B | 后端：热点历史 API（任务 1） | 中 |
| Batch C | 后端：连板查询 API（任务 2） | 小 |
| Batch D | 前端：短线情绪总览页面（任务 3） | 大 |
| Batch E | 集成测试 + 文档更新 | 小 |

> Batch A 已完成，后续可直接推进 Batch B。

---

## 验收标准

对照 Phase 2 达成标准逐条验证：

- [ ] 能够自动解析韭研公社的复盘图片，提取热点板块信息 → **已满足**
- [ ] 提取的信息能够存储在数据库中，并且可以通过页面展示 → 待 Batch D 完成后验证
- [ ] 页面能够展示当日热点板块列表，以及多个交易日之间的热点变化图表 → 待 Batch B + D 完成后验证
- [ ] 页面能够展示股票连板情况 → 待 Batch C + D 完成后验证

---

## 风险与注意事项

1. OCR 依赖 `rapidocr`：本地无图片不影响测试（已有 monkeypatch 机制）。
2. 连板数据完全依赖图片 OCR 的 `board_count` 字段，如图片质量差识别率低，可能需要 `needs_review` 过滤。
3. Phase 1 遗留修复中的 migration 需要判断 SQLite 文件是否已存在（生产数据保护）。

