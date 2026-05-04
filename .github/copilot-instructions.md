# AlphaPredator — GitHub Copilot Instructions

## 项目定位

面向个人使用的 A 股智能选股工作台。技术栈：**Python (FastAPI) + React (TypeScript) + SQLite + DuckDB**。

---

## 必读文档（每次开始工作前）

1. `docs/agent/current-progress.md` — 当前阶段、待完成任务、已知阻塞
2. `docs/phase.md` — Phase 1~4 阶段目标与达成标准
3. `agent.md` — 完整协作约束与工作规范

---

## 硬性约束（不可违反）

- **禁止直接修改** `docs/human/` 目录下的任何文档；如有冲突，以该目录规范为准调整代码。
- **禁止直接修改** `docs/phase.md`；如需变更阶段目标，提 issue 由人工处理。
- **代码与 `docs/human/` 规范冲突时，改代码，不改规范。**
- agent 产生的文档统一输出到 `docs/agent/`，命名格式：`phase-<阶段名称>-<目标名称>.md`。
- 每个 PR **必须** 包含 `docs/agent/current-progress.md` 的同步更新，否则视为 PR 不完整。

---

## 关键代码入口

| 层             | 文件                                               | 说明                     |
|---------------|--------------------------------------------------|------------------------|
| 后端启动          | `backend/app/main.py`                            | FastAPI app + lifespan |
| 路由聚合          | `backend/app/api/router.py`                      | 挂载所有子路由                |
| 行情 API        | `backend/app/api/routes/market.py`               | 搜索、详情、总览               |
| 初始化 API       | `backend/app/api/routes/data_init.py`            | Token、股票列表上传、任务管理      |
| 行情服务          | `backend/app/modules/market_data/service.py`     | 指标计算、数据聚合              |
| 数据初始化         | `backend/app/modules/market_data/initializer.py` | Tushare 拉取 + DuckDB 写入 |
| 涨跌停计算         | `backend/app/modules/market_data/limit_rules.py` | 按板块规则计算                |
| DuckDB schema | `backend/app/db/duckdb_storage.py`               | daily_bars 表定义         |
| SQLite schema | `backend/app/db/sqlite.py`                       | 任务状态、股票列表等             |
| 前端入口          | `frontend/src/main.tsx`                          | React 根挂载              |
| 前端路由          | `frontend/src/routes/router.tsx`                 | 页面路由配置                 |
| 个股详情页         | `frontend/src/pages/StockDetailPage.tsx`         | K线 + 指标图表              |
| 首页搜索          | `frontend/src/pages/HomeSearchPage.tsx`          | 股票搜索 + 初始化状态           |

## PR 检查清单

提交 PR 前必须确认：

- [ ] 未修改 `docs/human/` 任何文件
- [ ] 未修改 `docs/phase.md`
- [ ] 与当前阶段目标（Phase 1）一致，无跨阶段扩散
- [ ] 已补充或更新 `backend/tests/` 中的相关测试
- [ ] **已同步更新 `docs/agent/current-progress.md`**

