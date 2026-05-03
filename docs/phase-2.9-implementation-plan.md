# Phase 2.9：全市场数据接入与增量更新 - 实现规划

**目标**：接入全市场真实数据源，支持初始化入库、初始化进度查看与当日增量更新。

**背景**：Phase 1 已完成本地数据导入底座，importer 已支持从批次 CSV 导入数据。Phase 2.9 需要补上"采集 -> 批次生成 -> 导入"的完整链路。

---

## 1. 核心设计思路

采用"直接、不过度设计"的方案：

```
┌─────────────────┐
│ 数据源采集      │ (fetch_all_market_data)
│ - Eastmoney     │
│ - 拆成 3 个文件 │
├─────────────────┤
│ 批次管理        │
│ data/imports/   │
│ market-data/    │
│ {yyyymmdd}/     │
├─────────────────┤
│ 导入 (复用)     │
│ importer.py     │
└─────────────────┘
```

**关键决策**：

1. **不做单个 provider 类**。直接写一个 `fetch_market_data()` 函数，返回 3 个 DataFrame
2. **不用异步 job**。初始化用同步 API，返回后直接导入完成
3. **不复杂的进度追踪**。只记录"开始 -> 进行中 -> 完成"3 个状态
4. **增量更新**：新增一个 `increment_latest_market_data()` 函数，只拉最新交易日

---

## 2. 文件拆解

### 新增文件

```
backend/app/modules/market_data/
├── data_source.py          [新] 数据源采集函数
│   ├── fetch_market_data()
│   └── get_latest_trade_date()
│
├── initialization.py       [新] 初始化和增量更新
│   ├── initialize_market_data()
│   └── increment_market_data()
│
└── models.py               [改] 补充 InitStatus 模型

backend/app/api/routes/
└── market.py               [改] 补充初始化 API
    ├── POST /api/market/init
    ├── GET /api/market/init/status
    └── POST /api/market/increment

frontend/src/pages/
└── DataInitializePage.tsx  [新] 初始化页面
```

### 改动文件

```
backend/app/main.py
→ 应用启动时检查数据是否存在，如果不存在提示初始化

conf/app.toml.example
→ 补充初始化相关配置
```

---

## 3. 核心实现逻辑

### 3.1 数据源采集 (`data_source.py`)

```python
def fetch_market_data(trade_date: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    从 Eastmoney 采集一个交易日的全市场数据。
    
    返回：
    - stock_pool: [stock_code, stock_name, sectors, ai_quick_summary]
    - daily_snapshots: [trade_date, stock_code, current_price, ...]
    - daily_bars: [stock_code, trade_date, open, high, low, close, volume]
    
    如果 trade_date=None，采集最新交易日。
    """
    # 1. 获取最新交易日（如果没指定）
    if not trade_date:
        trade_date = get_latest_trade_date()
    
    # 2. 从 Eastmoney 拉股票列表
    stock_pool = _fetch_eastmoney_stock_pool()
    
    # 3. 从 Eastmoney 拉某交易日的全市场快照
    daily_snapshots = _fetch_eastmoney_daily_quotes(trade_date)
    
    # 4. 不直接拉历史日K（数据量大）
    #    需要时再单独拉
    daily_bars = _fetch_eastmoney_daily_bars(stock_pool['stock_code'].tolist(), trade_date)
    
    return stock_pool, daily_snapshots, daily_bars
```

### 3.2 初始化流程 (`initialization.py`)

```python
def initialize_market_data(target_date: str | None = None) -> dict:
    """
    完整初始化流程：采集 -> 生成批次 -> 导入。
    
    流程：
    1. 采集数据
    2. 验证数据有效性
    3. 生成批次 CSV 文件
    4. 调用 importer 导入
    5. 返回结果
    """
    try:
        # 步骤 1：采集
        stock_pool, daily_snapshots, daily_bars = fetch_market_data(target_date)
        
        # 步骤 2：验证
        _validate_data(stock_pool, daily_snapshots, daily_bars)
        
        # 步骤 3：生成批次
        batch_dir = _generate_batch_files(stock_pool, daily_snapshots, daily_bars)
        
        # 步骤 4：导入
        result = import_market_data_batch(batch_dir)
        
        # 步骤 5：记录初始化信息
        _save_init_status(success=True, batch_dir=batch_dir, result=result)
        
        return {
            "status": "success",
            "batch_dir": str(batch_dir),
            "stocks_loaded": result.stock_count,
            "latest_trade_date": result.latest_trade_date,
        }
    except Exception as e:
        _save_init_status(success=False, error=str(e))
        return {
            "status": "failed",
            "error": str(e),
        }
```

### 3.3 增量更新 (`initialization.py`)

```python
def increment_market_data() -> dict:
    """
    增量更新：只拉取最新一个交易日的数据，追加入库。
    """
    try:
        # 1. 获取当前已入库的最新交易日
        latest_db_date = _get_latest_trade_date_in_db()
        
        # 2. 获取当前最新交易日（从数据源）
        latest_market_date = get_latest_trade_date()
        
        # 3. 如果相同，说明数据已最新
        if latest_db_date == latest_market_date:
            return {"status": "already_latest", "latest_trade_date": latest_db_date}
        
        # 4. 采集新数据
        stock_pool, daily_snapshots, daily_bars = fetch_market_data(latest_market_date)
        
        # 5. 验证并生成批次（增量模式）
        batch_dir = _generate_batch_files(stock_pool, daily_snapshots, daily_bars)
        
        # 6. 追加导入（不覆盖旧数据）
        result = import_market_data_batch(batch_dir, append_mode=True)
        
        return {
            "status": "success",
            "new_date": latest_market_date,
            "rows_added": result.snapshot_row_count + result.daily_bar_count,
        }
    except Exception as e:
        return {
            "status": "failed",
            "error": str(e),
        }
```

---

## 4. API 端点设计

### 4.1 初始化

```
POST /api/market/init

请求体：
{
  "target_date": null  // 不指定则用最新交易日
}

响应：
{
  "status": "success" | "failed",
  "batch_dir": "data/imports/market-data/20260503/",
  "stocks_loaded": 5000,
  "latest_trade_date": "2026-05-03",
  "error": null
}
```

### 4.2 初始化状态

```
GET /api/market/init/status

响应：
{
  "last_init_time": "2026-05-03 15:20:00",
  "last_init_success": true,
  "latest_trade_date_in_db": "2026-05-03",
  "total_stocks": 5000,
  "data_ready": true
}
```

### 4.3 增量更新

```
POST /api/market/increment

请求体：{}

响应：
{
  "status": "success" | "already_latest" | "failed",
  "new_date": "2026-05-03",
  "rows_added": 5000,
  "error": null
}
```

---

## 5. 前端初始化页面

新增路由：`/initialize`

页面结构：

```
┌──────────────────────────────────┐
│ 市场数据初始化                   │
├──────────────────────────────────┤
│ 状态：✓ 数据已初始化              │
│ 最后初始化：2026-05-03 15:20     │
│ 当前市场日期：2026-05-03          │
│ 已加载股票数：5000               │
├──────────────────────────────────┤
│ [ 重新初始化 ] [ 更新今日数据 ]   │
├──────────────────────────────────┤
│ 初始化日志                       │
│ • 2026-05-03: 完成初始化         │
│ • 2026-05-02: 自动增量更新       │
└──────────────────────────────────┘
```

---

## 6. 实现分阶段任务

### **Checkpoint 1：数据源采集 (1-2 天)**
- [ ] 实现 `data_source.py`
  - [ ] Eastmoney 股票列表采集
  - [ ] Eastmoney 日快照采集
  - [ ] Eastmoney 日 K 采集
- [ ] 补充单元测试
- [ ] 手动验证一次采集是否有数据

### **Checkpoint 2：批次生成 & 导入适配 (1 天)**
- [ ] 实现 `initialization.py` 的初始化流程
- [ ] 改造 `importer.py` 的 `append_mode` 参数
- [ ] 验证"采集 -> 批次生成 -> 导入"完整链路

### **Checkpoint 3：后端 API (1 天)**
- [ ] 新增 `/api/market/init`、`/api/market/init/status`、`/api/market/increment`
- [ ] 保存和读取初始化状态（SQLite 新增 init_log 表）
- [ ] 验证三个 API 可调用

### **Checkpoint 4：前端初始化页面 (1-2 天)**
- [ ] 新增 `/initialize` 路由
- [ ] 实现页面逻辑和 UI
- [ ] 验证页面可调起初始化，能显示进度和结果

### **Checkpoint 5：自动增量更新 (1 天)**
- [ ] 改造应用启动逻辑，检查是否需要增量更新
- [ ] 实现增量更新的自动触发
- [ ] 验证新数据能自动入库并被页面消费

---

## 7. 依赖与注意事项

### 7.1 依赖

```
- requests: HTTP 请求（采集数据时需要）
- pandas: 数据处理
- 已有：duckdb, sqlmodel, fastapi
```

### 7.2 关键注意事项

1. **Eastmoney 限频**：可能需要添加延迟和重试
2. **网络不稳定**：采集失败要有降级逻辑（用已有数据）
3. **数据一致性**：同一批次的 stock_pool / daily_snapshots / daily_bars 必须有相同的交易日
4. **增量模式**：导入时必须确保不覆盖已有数据
5. **初始化状态持久化**：用 SQLite 新表记录，避免重启丢失

---

## 8. 你现在需要确认

1. **Eastmoney 是否是首选数据源？** (或改用 AkShare / Tushare)
2. **增量更新的触发方式？** (自动定时 vs 手动点击)
3. **初始化是否允许重复执行？** (覆盖旧数据 vs 只允许一次)
4. **是否需要支持"恢复到某个历史日期"的功能？**

给我你的决策，我立即开始实施 Checkpoint 1。


