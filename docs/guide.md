# AlphaPredator 文档索引

用于快速定位项目目标、阶段规划、数据规则与 Agent 协作约束。

## 快速使用说明

- **先看什么**
  - 开发/实现前：先看 [Agent Guide](../AGENTS.md) 和 [当前执行进度](agent/current-progress.md)
  - 对齐业务设计：优先看 `docs/human` 下的文档
  - 查阶段目标：看 [阶段目标清单](phase.md)
- **文档属性**
  - **只读规范**：`../AGENTS.md`、`agent-rules.md`、`code-rules.md`、`docs/human/*`
  - **工作文档**：`docs/agent/*`、`docs/plans/*`

## 按任务查文档

- **要理解市场数据抓取 / 股票列表 / 日线导入**
  - [市场数据抓取设计](human/market-data.md)
  - [A股市场数据源设计文档](human/mysj.md)
  - [麦蕊数据 API 文档](human/api-docs/mysj.yaml)
- **要理解热点复盘 / 韭研公社**
  - [热点复盘设计文档](human/hot-review.md)
  - [韭研公社 API 文档](human/api-docs/jygs-api.yml)
- **要核对库表 / 存储模型**
  - [数据模型设计](human/data-model/AlphaPredator.dbml)
- **要了解当前任务做到哪里**
  - [当前执行进度](agent/current-progress.md)
- **要查近期改造方案 / 历史计划**
  - [Phase 2 最新文档设计改造规划](agent/phase-phase2-latest-design-refactor-plan.md)
  - [Phase 2 短线情绪评分与页面设计](agent/phase-phase2-sentiment-overview-scoring-design.md)
  - [Phase 4 AI 选股模式数据库设计方案（待审批）](agent/phase-phase4-ai-pattern-db-design.md)
  - [Phase 1 数据源 / 存储 / 任务对齐计划](plans/2026-05-14-phase1-data-source-storage-task-alignment.md)
  - [Phase 1 / Phase 2 数据源对齐计划](plans/2026-05-14-phase1-phase2-data-source-alignment.md)

## 按模块查入口

- **项目与阶段**
  - [项目总览（README）](../README.md)
  - [阶段目标清单](phase.md)
- **规则与约束**
  - [Agent Guide](../AGENTS.md)
  - [agent-rules.md](agent-rules.md)
  - [code-rules.md](code-rules.md)
  - [code-style.md](code-style.md)
- **业务 / 数据设计**
  - [市场数据抓取设计](human/market-data.md)
  - [A股市场数据源设计文档](human/mysj.md)
  - [热点复盘设计文档](human/hot-review.md)
  - [数据模型设计](human/data-model/AlphaPredator.dbml)
- **Agent 工作区**
  - [docs/agent 使用说明](agent/README.md)
  - [当前执行进度](agent/current-progress.md)
  - [Phase 2 最新文档设计改造规划](agent/phase-phase2-latest-design-refactor-plan.md)
  - [Phase 4 AI 选股模式数据库设计方案（待审批）](agent/phase-phase4-ai-pattern-db-design.md)
- **专项计划**
  - [Phase 1 数据源 / 存储 / 任务对齐计划](plans/2026-05-14-phase1-data-source-storage-task-alignment.md)
  - [Phase 1 / Phase 2 数据源对齐计划](plans/2026-05-14-phase1-phase2-data-source-alignment.md)

## 项目级文档

- [项目总览（README）](../README.md)：项目目标、技术栈与总入口。

## 阶段规划

- [阶段目标清单](phase.md)：项目阶段目标，包括：前置依赖、本阶段范围、关键任务、达成标准。

## 规则与协作约束

- [Agent Guide](../AGENTS.md)：AI / 编码 agent 在本仓库协作时必须遵守的约束。
- [agent-rules.md](agent-rules.md)：agent 协作规则、文档优先级与任务收尾要求。
- [code-rules.md](code-rules.md)：编码规则、思考方式与精确修改原则。
- [code-style.md](code-style.md)：代码风格补充规范（含强制直接导入规则）。

## 人类维护规范（docs/human）

- [市场数据抓取设计](human/market-data.md)：市场数据抓取方式、存储位置与同步方式说明。
- [A股市场数据源设计文档](human/mysj.md)：市场数据源设计与背景说明。
- [热点复盘设计文档](human/hot-review.md)：热点复盘数据处理与展示设计。
- [数据模型设计](human/data-model/AlphaPredator.dbml)：核心数据模型定义。
- [韭研公社 API 文档](human/api-docs/jygs-api.yml)：韭研公社接口说明。
- [麦蕊数据 API 文档](human/api-docs/mysj.yaml)：麦蕊接口说明。

## Agent 工作区文档（docs/agent）

- [docs/agent 使用说明](agent/README.md)：agent 工作文档的目录职责、命名规范与推荐模板。
- [当前执行进度](agent/current-progress.md)：记录当前阶段、上一步完成内容、下一步待做任务与已知阻塞。
- [Phase 2 最新文档设计改造规划](agent/phase-phase2-latest-design-refactor-plan.md)：对照最新文档梳理代码差距与改造顺序。
- [Phase 2 短线情绪评分与页面设计](agent/phase-phase2-sentiment-overview-scoring-design.md)：定义短线情绪页面信息架构、情绪温度公式、板块影响公式与所需数据清单。
- [Phase 4 AI 选股模式数据库设计方案（待审批）](agent/phase-phase4-ai-pattern-db-design.md)：用于用户审批 Phase 4 新增表与字段设计后再进入编码。

## 历史计划与专项方案（docs/plans）

- [Phase 1 数据源 / 存储 / 任务对齐计划](plans/2026-05-14-phase1-data-source-storage-task-alignment.md)
  ：梳理数据源、存储模型与任务链路的对齐方案。
- [Phase 1 / Phase 2 数据源对齐计划](plans/2026-05-14-phase1-phase2-data-source-alignment.md)：统一 Phase 1 与 Phase 2
  的数据源和字段口径。
