# 当前执行进度

> **用途**：记录当前活跃需求和最近事实状态，帮助后续 agent / AI 助手接续工作。
> **维护规则**：每次会话结束时由 agent 更新；只记录事实状态，不写主观判断。
> **格式**：当前需求 → 最近动作 → 下一步 → 已知问题 / 阻塞 / 待人工决策。

---

## 当前需求

- 当前活跃需求文件：[F01：热点复盘](F01-hot-review.md)
- 相关需求文件：[F02：市场数据](F02-market-data.md)

## 最近动作

- 已将项目文档体系从全局 Phase 规划调整为单需求文件驱动。
- 已删除 `docs/phase.md`。
- 已将以下功能设计文档迁移到 `docs/agent/Fxx-*.md`：
  - `docs/agent/F01-hot-review.md`
  - `docs/agent/F02-market-data.md`
  - `docs/agent/F03-trading-review.md`
  - `docs/agent/F04-pattern-pick.md`
- 已保留 `docs/human/api-docs/*`、`docs/human/data-model/AlphaPredator.dbml` 和 `docs/human/mysj.md` 作为人类维护硬规范。

## 下一步

- 继续补齐首页热点复盘模块：`HomeSearchPage.tsx` 增加轻量版热点复盘入口，包含最新交易日板块列表、复盘图片入口和跳转 `/sentiment`。
- 验证 JYGS 鉴权前置校验是否完善。

## 已知问题 / 阻塞 / 待人工决策

- 旧的 Phase 历史文档仍保留在 `docs/agent`，当前仅作为历史资料，不作为新需求命名模板。
