# docs/agent 使用说明

本目录用于存放 AI / 编码 agent 维护的工作文档。当前规则采用**单需求文件驱动**，不再使用全局 Phase 规划文档。

## 目录职责

- 维护单个需求的背景、目标、方案、验收、当前状态和待决策事项。
- 记录 agent 产出的设计文档、计划文档、排查记录和实现总结。
- 为实现过程提供可追溯依据，但不替代项目级规则文档。

## 文档优先级

- `docs/human`：人类维护的硬规范，包含 API 文档、数据模型和外部事实来源。
- `docs/agent/Fxx-*.md`：功能需求与设计文件。
- 代码：当代码与文档冲突时，以文档为准。

## 适用场景

- 新功能或功能改造需要明确目标、范围、方案和验收标准。
- 同一需求存在多种实现路径，需要记录方案取舍。
- 需求状态、阻塞、待人工决策需要被后续会话继续读取。

## 不适用场景

- 修改 API 文档、数据模型或外部事实来源；这些内容应由人维护在 `docs/human`。
- 维护全局阶段规划；本项目不再使用 `docs/phase.md`。

## 命名规范

- 功能需求文件格式：`Fxx-<feature>.md`
- `Fxx` 使用两位数字编号，例如 `F01`、`F02`。
- `<feature>` 使用 kebab-case，聚焦单一需求。

示例：

- `F01-hot-review.md`
- `F02-market-data.md`
- `F03-trading-review.md`
- `F04-pattern-pick.md`

## 推荐模板

```markdown
# Fxx：<需求名称>

## 背景

## 目标

## 不做什么

## 设计方案

## 数据与接口依赖

## 验收标准

## 当前状态

## 已知问题 / 待人工决策
```

## 维护规则

- 一个 `Fxx-*.md` 文件只描述一个相对独立需求。
- 需求变化时更新对应需求文件，不新增 Phase 规划。
- 与 `docs/human` 冲突时，以 `docs/human` 为准。
- 新增或迁移需求文件后，更新 [docs/guide.md](../guide.md) 索引。
- 会话结束前更新 [current-progress.md](current-progress.md)，只记录当前需求、最近动作、下一步和阻塞。

## 快速开始

1. 阅读 [current-progress.md](current-progress.md)，确认当前活跃需求文件。
2. 阅读对应 `Fxx-*.md` 文件。
3. 若是新需求，创建新的 `Fxx-<feature>.md` 并更新 [docs/guide.md](../guide.md)。
4. 进入实现前，按 [code-rules.md](../code-rules.md) 先输出假设、取舍和验证标准。
