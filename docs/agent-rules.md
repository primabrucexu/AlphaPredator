# agent运行规则文档

- 使用对象：在本仓库中工作的编码 agent / AI 助手

## rule1: 你没有权限编辑的文档

- 本文档
- [human](human)：该目录下的人类维护硬规范，包括 API 文档、数据模型和外部事实来源
- [code-rules.md](code-rules.md)：该文档定义了代码编写规则

> 例外：当用户明确要求修改本文件或重构文档规则时，可以按用户授权修改。

## rule2: 你必须遵守如下的代码和文档优先级

- [human](human) 目录下的文档优先级最高。任何冲突都要以它为准
- [agent](agent) 目录下的需求文件优先级次之。它是你输出和维护单需求设计文档、计划文档和当前工作状态的地方
- 代码的优先级最低。当出现冲突时，永远按照这个优先级解决冲突

普通功能设计不放在 [human](human) 目录。功能需求应按 `Fxx-<feature>.md` 命名并维护在 [agent](agent) 目录。

## rule3：禁止随意新建或修改数据库表

- 你禁止创建任何不在 [AlphaPredator.dbml](human/data-model/AlphaPredator.dbml) 描述中的数据库表
- 你禁止修改任何在 [AlphaPredator.dbml](human/data-model/AlphaPredator.dbml) 描述中的数据库表结构
- 如果需要新增数据库表，
    1. 用dbml格式输出完整的设计方案，包含表名、字段、字段类型、字段含义、以及为什么需要这个表
    2. 要求用户审阅并批准设计方案
    3. 要求用户更新 [AlphaPredator.dbml](human/data-model/AlphaPredator.dbml) 来包含这个新表的设计
    4. 创建这个表，并在代码中使用它

  
## rule4: 数据库设计不要直接写入功能设计文档

- Agent 输出功能设计文档时，如果涉及数据库表、字段、索引、外键或迁移方案，不要在功能设计文档中直接展开完整数据库设计。
- 数据库相关设计必须通过文件引用间接表达，例如引用独立 DBML 草案、独立数据库设计说明，或引用 [AlphaPredator.dbml](human/data-model/AlphaPredator.dbml) 中对应表设计。
- 功能设计文档中只保留数据库设计的目的、边界、审批状态和引用路径，避免大段表结构冲淡功能设计重点。
- 该规则不降低 rule3 的审批要求：新增或修改表结构仍必须先提供完整 DBML 设计方案，等待用户审批，并由用户更新 [AlphaPredator.dbml](human/data-model/AlphaPredator.dbml) 后才能落表。


## rule5: 不要维护兼容性

1. 当用户更改了某些设计后，你不要维护任何代码的兼容性。直接修改代码来适配最新的设计，并且移除过时设计。
2. 为了避免本项目存在大量冗余文档，你需要及时更新 [agent](agent) 下面相关的 `Fxx-*.md` 需求文件来反映最新的设计。对于过时的设计文档，你需要在更新后删除它们
3. 特别是当数据表设计变更后，不需要处理任何旧数据的兼容性问题，直接按照最新设计来处理数据即可

## rule6: 在对话开始前需要执行的动作

- 阅读[当前执行进度](agent/current-progress.md)：了解当前活跃需求和进度。
- 阅读[最近操作](agent/recent-actions.md)：了解 agent 最近 5 条操作。
- 如果 [当前执行进度](agent/current-progress.md) 指向某个 `Fxx-*.md` 需求文件，继续读取该需求文件后再开始需求分析。

## rule7: 在你完成每次编码或设计任务后，你需要进行自检的项目

- 是否遵守本文件"约束"部分，且未触碰受限文档。
- 是否违反 [human](human) 目录下定义的规则
- 如果有新增或迁移需求文档，更新[guide.md](guide.md)中的索引
- 更新[当前执行进度](agent/current-progress.md)：只记录当前活跃需求，使用完成情况勾选框追踪进度。如活跃需求未变则更新进度，如切换需求则完整替换。
- 在[最近操作](agent/recent-actions.md)追加本次会话动作，保持最新 5 条。
- 当某个需求不再活跃时，必须先检查是否有阻塞或待人工决策内容，如有则同步写入对应 `Fxx-*.md` 文件，然后从 `current-progress.md` 移除。
- 提问用户是否需要进行commit，如果需要，是否需要打标签（feature/fix）

## rule8: python代码执行规则

禁止通过python命令直接运行python代码。在 [tmp](../tmp) 创建临时脚本然后通过python命令执行

## rule9: 新建需求文件的命名规范与模板

- 文件名格式：`Fxx-<feature>.md`，`Fxx` 使用两位数字编号（F01、F02...），`<feature>` 使用 kebab-case。
- 一个文件只描述一个相对独立需求。
- 需求变化时更新对应需求文件，不新增全局规划文档。
- 新增或迁移需求文件后，必须更新 [guide.md](guide.md) 索引。

推荐模板：

```markdown
# Fxx：<需求名称>

## 目标

## 设计方案

## 数据与接口依赖

## 代码层面的实现方案

## 验收标准

## 当前状态

## 已知问题 / 待人工决策
```
