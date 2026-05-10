# AlphaPredator Agent Guide

本文件面向后续在本仓库中工作的编码 agent / AI 助手。

## 约束：

- agent禁止直接修改本文档中约束部分的内容。在必须修改的时候提出 issue，由人工来修改。
- agent禁止直接修改`docs/human` 目录的文档。在必须修改的时候提出 issue，由人工来修改。
- agent禁止直接修改phase.md文档。当需要修改阶段目标、阶段范围、关键任务、达成标准时，提出 issue，由人工来修改。
- 当出现代码、文档冲突时。永远按照 `docs/human` 目录下的文档调整代码和其他文档
- agent需要输出文档时，永远输出到 `docs/agent` 目录下的文档中。
- phase.md 里定义了每个阶段的目标和任务。永远按照 phase.md 里定义的阶段目标和任务来调整自己的行为。
- phase.md 中只定义了大颗粒度的目标。如果有需要agent可以自行拆分成小颗粒的目标
- 当需要给更细颗粒的目标输出文档时，请按照如下格式输出：phase-<阶段名称>-<目标名称>.md
- agent除非用户明确指出需要进行代码改动，否则永远只输出方案设计文档和计划文档，不要直接输出代码改动。

## 额外工具

### DuckDB 工具脚本使用说明（`backend/app/db/duckdb_storage.py`）

- 默认（无参数）启动 DuckDB UI：
  - `python backend/app/db/duckdb_storage.py`
- 执行 SQL（无参数）：
  - `python backend/app/db/duckdb_storage.py --sql "SELECT 1 AS ok"`
- 执行 SQL（带参数，`--params` 为 JSON）：
  - `python backend/app/db/duckdb_storage.py --sql "SELECT ? AS a, ? AS b" --params "[1, 2]"`
- 参数说明：
  - `--sql`：要执行的 SQL 语句。
  - `--params`：SQL 参数（JSON 字符串，可为数组或对象）。

## 每次会话开始时必须执行

1. 读取 `docs/agent/current-progress.md`，了解当前阶段、上次完成内容、待做任务与已知阻塞。
2. 读取 `docs/phase.md`，确认当前阶段目标与达成标准。
3. 每次会话结束前更新 `docs/agent/current-progress.md`，记录本次完成的内容和下一步任务。

## 项目定位

- 项目是面向个人使用的 A 股智能选股工作台，目标以 `README.md` 与 `docs/phase.md` 为准。
- 技术栈：Python + React + SQLite + DuckDB。
- 功能推进顺序按 Phase 1 -> Phase 4，禁止跳过前置依赖直接实现后续阶段核心能力。

## 关键代码入口

- 后端启动入口：`backend/app/main.py`。
- 后端路由聚合：`backend/app/api/router.py`。
- 主要 API 分组：
    - `backend/app/api/routes/health.py`
    - `backend/app/api/routes/market.py`
    - `backend/app/api/routes/data_init.py`
- 前端启动入口：`frontend/src/main.tsx`。
- 前端路由入口：`frontend/src/routes/router.tsx`。

## 数据与规则事实（实现时必须遵守）

- 数据存储总规则以 `docs/human/data-storage.md` 为准。
- 涨跌停计算规则以 `docs/human/price-limit-rule.md` 为准。
- 发生冲突时，`docs/human` 的规则优先于代码中的历史实现。

## 阶段对齐执行原则

- 始终先定位当前需求对应的阶段，再设计和实现。
- 如果需求超出当前阶段范围，先在 `docs/agent` 输出拆解文档，再实施最小闭环改动。
- 不在阶段文档中写进度状态（已完成/进行中/未完成），只维护目标、范围、任务、标准。

## 文档输出规则

- agent 产生的新文档统一写入 `docs/agent`。
- 细粒度目标文档命名：`phase-<阶段名称>-<目标名称>.md`。
- 建议文档结构：背景 -> 目标 -> 方案 -> 风险 -> 验收。
- `docs/docs.md` 只做导航索引；具体内容写入对应文档。

## 常用工作流程

### 1) 本地开发环境

- 后端依赖初始化：`bin/bootstrap-backend.sh`。
- 启动后端：`bin/dev-backend.sh`。
- 启动前端：`bin/dev-frontend.sh`。

### 2) 数据相关任务

- 导入市场数据批次：`bin/import-market-data.sh`。
- 导入热点复盘图片：`bin/import-hot-sector-images.sh`。
- 准备 Phase 1 样例数据：`bin/prepare-phase1-market-data.sh`。

### 3) 测试与回归

- 后端测试目录：`backend/tests`。
- 涉及数据导入、初始化任务、涨跌停规则、热点图片解析的改动，必须补充或更新对应测试。

## 改动自检清单（提交前 / PR 提交必须包含）

- 是否遵守本文件"约束"部分，且未触碰受限文档。
- 是否与 `docs/phase.md` 当前阶段目标一致。
- 是否与 `docs/human` 规则一致（尤其是数据结构与涨跌停规则）。
- 是否只做了满足需求的最小必要改动，避免跨阶段扩散。
- 是否补充了必要测试或说明未补充原因。
- 如果输出了方案/计划文档，是否放在 `docs/agent` 且命名规范正确。是否更新了`docs/docs.md` 的索引。
- **是否同步更新了 `docs/agent/current-progress.md`**：将本次 PR 完成的内容标记为已完成，更新"下一步待做任务"。此项是 PR
  的必要组成部分，缺少则视为 PR 不完整。
- 所有需要用户决策的问题，在用户决策后及时记录在 `docs/agent/current-progress.md` 的"本次人工决策"部分，确保每次会话的决策都有清晰记录。

---