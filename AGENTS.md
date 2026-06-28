# AlphaPredator Agent Guide
本文件面向后续在本仓库中工作的编码 agent / AI 助手。

## 交互语言

本项目的交互语言为**中文**。所有与用户的对话、思考输出、设计方案、文档说明均使用中文。

## ⚠️ 硬性规则

以下两条是最核心规则，**必须每次都遵守**：

1. **编码前必须先思考** — 明确假设、说出困惑、反对过度复杂。禁止直接改代码"验证想法"（修 bug 例外）。详见 [code-rules.md rule1](docs/code-rules.md)。
2. **禁止随意新建或修改数据库表** — 必须先输出完整表设计方案 → 等用户审批 → 等用户更新 [AlphaPredator.dbml](docs/human/data-model/AlphaPredator.dbml) → 才能落表。详见 [agent-rules.md rule3](docs/agent-rules.md)。

其他硬性规则定义在以下两个文件中，同样必须遵守：

- [agent-rules.md](docs/agent-rules.md) — Agent 运行规则（文档权限、优先级、兼容性、会话流程、自检）
- [code-rules.md](docs/code-rules.md) — 代码编写规则（思考先行、简单优先、精确修改、目标驱动）

---

## 工作流程规范

**会话开始前**：先读 [`docs/agent/current-progress.md`](docs/agent/current-progress.md) 了解当前活跃需求和进度；读 [`docs/agent/recent-actions.md`](docs/agent/recent-actions.md) 了解最近操作；如果其中记录了当前需求，再继续读取对应的 `docs/agent/Fxx-*.md` 需求文件。

### 1️⃣ 需求分析阶段

- 阅读用户需求
- **立即检查**：是否会触发硬性规则
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
- 检查是否遵守了 [biz-rules.md](docs/human/biz-rules.md) 的规则
- 如有新增或迁移需求文档，更新 [guide.md](docs/guide.md) 索引
- 更新 [`docs/agent/current-progress.md`](docs/agent/current-progress.md) 进度和 [`docs/agent/recent-actions.md`](docs/agent/recent-actions.md) 操作日志
- 提问用户是否需要 commit

---

## 技术栈

Python + React + SQLite + DuckDB

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
