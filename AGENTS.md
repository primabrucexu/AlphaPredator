# AlphaPredator Agent Guide
本文件面向后续在本仓库中工作的编码 agent / AI 助手。

## 交互语言

本项目的交互语言为**中文**。所有与用户的对话、思考输出、设计方案、文档说明均使用中文。

## ⚠️ 硬性规则（必须每次都遵守）

本项目有两个**最核心的硬性规则**，其他所有规则也同样硬性约束：

### ⭐ 最核心的两个硬性规则

#### 硬性规则 1：编码前必须先思考 [code-rules.md rule1]

**在任何编码改动前，必须停下来：**

- 明确你的假设。如果不确定，就提问
- 如果存在多种理解方式，把它们列出来，不要默默选择一种
- 如果有更简单的方案，要说出来。必要时提出反对意见
- 如果有不清楚的地方，停下来说明哪里困惑，然后提问
- **禁止直接改代码来"验证想法"**（修复 bug 例外）

#### 硬性规则 2：禁止随意新建或修改数据库表 [agent-rules.md rule3]

**新建或修改任何数据库表前，必须：**

1. 停止编码
2. 输出完整的设计方案（表名、字段、类型、含义、为什么需要）
3. 等待用户审批
4. 等待用户更新 [AlphaPredator.dbml](docs/human/data-model/AlphaPredator.dbml)
5. 才能在代码中创建和使用这个表

### 其他硬性规则（同样必须遵守）

所有 [agent-rules.md](docs/agent-rules.md) 中的规则都是硬性的：

- **rule1**: 无权限编辑的文档（docs/human 中的人类维护硬规范、agent-rules.md、code-rules.md；用户明确授权时例外）
- **rule2**: 代码和文档优先级（human 最高 > agent > 代码）
- **rule4**: 不要维护兼容性，直接适配最新设计
- **rule5**: 会话开始前读当前进度
- **rule6**: 完成编码后进行自检
- **rule7**: Python 代码执行规则

所有 [code-rules.md](docs/code-rules.md) 中的规则都是硬性的：

- **rule1**: 写代码前先思考（与硬性规则1同步）
- **rule2**: 简单优先，不做 speculative 的东西
- **rule3**: 精确修改，只改必须改的地方
- **rule4**: 目标驱动执行

**违反任何硬性规则都会导致项目混乱。必须百分百遵守。**

---

## 工作流程规范

**会话开始前**：先读 [`docs/agent/current-progress.md`](docs/agent/current-progress.md) 了解当前活跃需求文件；如果其中记录了当前需求，再继续读取对应的 `docs/agent/Fxx-*.md` 需求文件。

### 1️⃣ 需求分析阶段

- 阅读用户需求
- **立即检查**：是否会触发两个硬性规则或其他约束
    - 新建数据库表 → 硬性规则 2
    - 修改现有表结构 → agent-rules.md rule4
    - 新建模块/关键文件夹 → agent-rules.md rule6（需更新索引）
    - 与 `docs/human` 中的 API 文档或数据模型冲突 → agent-rules.md rule2（human 硬规范优先级最高）
- **如果触发任何规则** → 【停止编码】→ 【输出设计方案文档】→ 【等待用户审批】

### 2️⃣ 代码改动阶段（仅在所有规则都通过后）

- 修改代码
- 运行测试验证
- 确保无回归

### 3️⃣ 自检阶段（改动完成后）

- 检查是否遵守了 [agent-rules.md](docs/agent-rules.md) 的所有规则
- 检查是否违反了 [human](docs/human) 目录下的规则
- 如有新增或迁移需求文档，更新 [guide.md](docs/guide.md) 索引
- 更新 [`docs/agent/current-progress.md`](docs/agent/current-progress.md) 中的当前需求指针和事实状态
- 提问用户是否需要 commit

---

## 技术栈

Python + React + SQLite + DuckDB

## 核心规则文档

- [agent-rules.md](docs/agent-rules.md) - Agent 运行规则
- [code-rules.md](docs/code-rules.md) - 代码编写规则

## 代码执行规则

**Python 执行**：禁止直接运行 Python 代码。必须在 [`tmp/`](tmp) 目录创建临时脚本再执行：

```powershell
python tmp/my_script.py
```

**运行与验证**：

- 后端：用 [`bin/dev-backend.sh`](bin/dev-backend.sh) 开发，用 `pytest` 测试
- 前端：用 [`bin/dev-frontend.sh`](bin/dev-frontend.sh) 开发，用 `npm run check:playwright` 冒烟检查

**思考和输出使用中文**

---

## 额外工具

### DuckDB 脚本（`backend/app/db/duckdb_storage.py`）

无参数 SQL：

```powershell
python backend/app/db/duckdb_storage.py --sql "SELECT 1 AS ok"
```

带参数 SQL（`--params` 为 JSON）：

```powershell
python backend/app/db/duckdb_storage.py --sql "SELECT ? AS a, ? AS b" --params "[1, 2]"
```

---

## 关键代码入口

### 后端

- **启动入口**：`backend/app/main.py`
- **路由聚合**：`backend/app/api/router.py`
- **主要 API**：
    - `backend/app/api/routes/health.py`
  - `backend/app/api/routes/market.py`：行情查询、股票搜索、短线情绪接口
  - `backend/app/api/routes/data_init.py`：初始化任务与状态面板
  - `backend/app/api/routes/jygs.py`：韭研公社鉴权
- **主要模块**：
    - `backend/app/modules/market_data/`：行情数据导入、初始化、涨跌停规则、热点复盘
    - `backend/app/modules/jygs/`：韭研公社集成（认证、Playwright 登录、事件追踪）

### 前端

- **启动入口**：`frontend/src/main.tsx`
- **全局布局**：`frontend/src/components/layout/AppShell.tsx`（侧边导航 + 顶部搜索）
- **搜索组件**：`frontend/src/components/StockSearchBar.tsx`
- **API 封装**：`frontend/src/lib/api.ts`（统一的 API 调用）
- **路由入口**：`frontend/src/routes/router.tsx`
- **主要页面**：
    - `HomeSearchPage.tsx`、`StockDetailPage.tsx`、`MarketOverviewPage.tsx`
    - `InitializePage.tsx`、`AiResultsPage.tsx`、`FocusPage.tsx`、`HistoryPage.tsx`
    - `SentimentOverviewPage.tsx`（短线情绪总览）
