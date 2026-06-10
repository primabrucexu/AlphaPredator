# AlphaPredator 文档索引

用于快速定位需求文件、数据规则与 Agent 协作约束。

## 快速使用说明

- **开发/实现前**：先看 [Agent Guide](../AGENTS.md) 和 [当前执行进度](agent/current-progress.md)。
- **当前需求**：如果 `current-progress.md` 指向某个 `Fxx-*.md` 文件，继续读取该需求文件。
- **业务需求**：优先看 `docs/agent/Fxx-*.md`。
- **硬规范**：API 文档、数据模型和外部事实来源看 `docs/human`。

## 文档属性

- **规则文档**：`../AGENTS.md`、`agent-rules.md`、`code-rules.md`、`code-style.md`。
- **人类维护硬规范**：`docs/human/api-docs/*`、`docs/human/data-model/*`、`docs/human/mysj.md`。
- **需求与工作文档**：`docs/agent/*`。

## 当前入口

- [当前执行进度](agent/current-progress.md)：记录当前活跃需求文件、最近动作、下一步和阻塞。
- [docs/agent 使用说明](agent/README.md)：需求文件命名规范、模板和维护规则。

## 功能需求

- [F01：热点复盘](agent/F01-hot-review.md)：韭研公社复盘图片抓取、解析、存储、展示与热点变化对比。
- [F02：市场数据](agent/F02-market-data.md)：股票列表、日线行情、同步任务、涨跌停计算与市场判断。
- [F03：交易复盘](agent/F03-trading-review.md)：单标的操作复盘、月度 AI 复盘总结和问题归因。
- [F04：AI 选股](agent/F04-pattern-pick.md)：AI 学习用户选股模式、生成选股技能和多模型交叉评判。

## 规则与协作约束

- [Agent Guide](../AGENTS.md)：AI / 编码 agent 在本仓库协作时必须遵守的约束。
- [agent-rules.md](agent-rules.md)：agent 协作规则、文档优先级与任务收尾要求。
- [code-rules.md](code-rules.md)：编码规则、思考方式与精确修改原则。
- [code-style.md](code-style.md)：代码风格补充规范。

## 人类维护硬规范

- [A股市场数据源说明](human/mysj.md)：麦蕊数据接入说明。
- [数据模型设计](human/data-model/AlphaPredator.dbml)：核心数据模型定义。
- [韭研公社 API 文档](human/api-docs/jygs-api.yml)：韭研公社接口说明。
- [麦蕊数据 API 文档](human/api-docs/mysj.yaml)：麦蕊接口说明。

## 历史工作文档

以下文档保留为历史资料或专项记录，不作为新需求命名模板：

- [Phase 2 最新文档设计改造规划](agent/phase-phase2-latest-design-refactor-plan.md)
- [Phase 2 短线情绪评分与页面设计](agent/phase-phase2-sentiment-overview-scoring-design.md)
- [交易复盘系统设计记录](agent/trading-review-system-design.md)
- [stock_code 类型修复记录](agent/stock-code-datatype-fix.md)
- [JYGS 鉴权快速参考](agent/jygs-auth-quickref.md)
- [JYGS 鉴权迁移记录](agent/jygs-auth-migration.md)
- [JYGS 鉴权完成记录](agent/jygs-auth-completion.md)
- [OCR 实现总结](agent/ocr-implementation-summary.md)
- [OCR 部署说明](agent/ocr-deployment-guide.md)
- [OCR 完成总结](agent/ocr-completion-summary.md)
