# AlphaPredator 编码 Agent 运行准则

## 1. 项目与事实来源

- AlphaPredator 是个人使用的 A 股行情与自选股助手。
- 功能索引以 `docs/feature/index.json` 为准。
- 具体需求、范围和验收标准以对应 Feature 文档为准。
- 具体依赖和版本以 `backend/pyproject.toml` 与 `frontend/package.json` 为准。

## 2. 工作流程

- 新功能或用户可见行为变化需要在 `docs/feature` 下记录；开发过程中同步更新范围、设计决策和验收状态。
- 执行编码任务前需要先生成简短计划和验收标准，确认后再执行。
- 只修改完成当前任务所必需的文件，不顺带重构无关代码，除非有特别说明。

## 3. 技术栈

- 后端：Python + FastAPI + SQLite + SQLAlchemy + pytest
- 前端：React 19 + TypeScript + Vite
- 股票行情数据来源：thsdk

## 4. 架构边界

1. 行情业务必须通过 `MarketDataProvider` 获取数据，不得直接调用 thsdk，也不得依赖 thsdk 的响应对象。
2. thsdk 的连接、数据转换、并发控制和异常适配放在 `backend/app/market_data/provider/`。
3. 不同调用入口应复用 service 层的业务逻辑，避免重复编码。
4. 外部服务不可用时返回明确错误，禁止生成伪造数据。
5. Feature 文档中的“非目标”只约束该 Feature；除非明确标记为项目级决策，不得据此限制后续 Feature。

## 5. 数据存储

- SESSION、账号、密码、本地数据库及其他敏感信息不得提交。
- 行情时序数据默认不落库，由 `MarketDataProvider` 在线获取；如需缓存或持久化，必须由对应 Feature 明确规定。
- 修改持久化模型时，必须评估存量数据库兼容性；涉及表结构或数据语义变化时，需要提供迁移方案和迁移测试。

## 6. 文档资料管理

- Feature 文档模板使用 `docs/feature/template.md`。
- 新增、重命名或调整 Feature 时，同步更新 `docs/feature/index.json`。

## 7. 验证

- 后端修改：在 `backend` 下执行 `python -m pytest -q`。
- 前端修改：在 `frontend` 下执行 `npm.cmd run build`。
- 同时影响前后端时，两项都必须执行。
- 报告实际执行结果；未执行或失败时明确说明原因。
