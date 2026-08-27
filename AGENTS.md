# AlphaPredator 编码 Agent 运行准则

## 1. 项目与事实来源

- AlphaPredator 是个人使用的 A 股行情与自选股助手。
- 功能索引以 `docs/feature/index.json` 为准。
- 具体需求、范围和验收标准以对应 Feature 文档为准。
- 具体依赖和版本以 `backend/pyproject.toml` 与 `frontend/package.json` 为准。

## 2. 工作流程

- 新需求设计时，需要先完成充分的讨论工作再写入文档记录
- 新功能或用户可见行为变化需要在 `docs/feature` 下记录；开发过程中同步更新范围、设计决策和验收状态。
- 执行编码任务前需要先生成简短计划和验收标准，确认后再执行。
- 只修改完成当前任务所必需的文件，不顺带重构无关代码，除非有特别说明。
- 当发现某项约束需要沉淀为项目级规则时，应主动提醒用户更新本文档。

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
6. 后台任务必须通过 `backend/app/tasks/` 的任务框架接入。Handler 使用 `build_items()` 将循环元素逐一生成子任务，并统一通过 `run_item()` 执行；没有循环的任务也必须返回一个子任务，不得绕过子任务执行路径。
7. 新增或修改生产任务类型时，必须在统一的 `register_production_handlers()` 中注册，并由 FastAPI Web 进程和独立 Worker 进程在启动时分别调用。Web 注册用于创建任务时执行 `build_items()`，Worker 注册用于执行 `run_item()` 和 `summarize()`；必须验证两个进程都能识别同一 `task_type`，禁止只在单一进程中依赖导入副作用注册。
8. 每个进程最多维护一个 thsdk 客户端；进程内所有 thsdk 调用必须串行，并保证相邻底层调用间隔不小于 50ms。Web 和 Worker 可以各自维护一个客户端，但不得在同一进程创建多个客户端并发访问原生库。
9. thsdk 正式账号客户端只传入统一配置中的账号和密码，使用 SDK 默认派生 MAC；不得读取、持久化或显式传入机器真实 MAC，也不得在日志、任务或 API 中暴露完整派生 MAC。
10. `COMPUTE` 调度只用于选股、规则计算和历史回测类任务；页面将 `COMPUTE` 任务统一归入“模式选股”，将 `EXCLUSIVE_UPDATE` 数据更新任务统一归入“任务”。若未来需要非选股类 `COMPUTE`，必须先重新确认菜单与任务分类。

## 5. 数据存储

- SESSION、账号、密码、本地数据库及其他敏感信息不得提交。
- 行情时序数据默认不落库，由 `MarketDataProvider` 在线获取；如需缓存或持久化，必须由对应 Feature 明确规定。
- 持久化行情使用的 DuckDB 只能由独立 Worker 进程打开和访问；FastAPI Web、页面请求和 MCP 不得直接连接 DuckDB。所有 DuckDB 行情更新和计算必须通过 `backend/app/tasks/` 任务交给 Worker 串行执行。
- 修改持久化模型时，必须评估存量数据库兼容性；涉及表结构或数据语义变化时，需要提供迁移方案和迁移测试。

## 6. 文档资料管理

- 项目文档存放在 `docs/`，分类和目录职责详见 `docs/README.md`。
- Feature 文档模板使用 `docs/feature/template.md`。
- `docs/` 下每个文档分类目录都需要维护 `index.json`，用于提供该分类下文档的快速索引。
- 新增、删除、重命名文档，或调整文档摘要和状态时，需要同步更新对应目录的 `index.json`。
- `docs/TODO.md` 用于集中索引项目中待后续评估、验证或实施的改进事项。Agent 在工作中明确发现不属于当前任务范围、但需要后续跟进的改进时，可以直接记录，无需为记录动作另行确认；具体背景、证据和方案应写入对应 Feature、规则或集成文档，`docs/TODO.md` 只维护指向来源文档的链接和当前状态。
- 记录 TODO 不代表需求已经确认，也不授权扩大当前任务的实现范围；后续实施前仍需按正常流程确认范围、设计和验收标准。
- 每个 Feature 文档必须包含独立的 `MCP` 小节；F005.1 完成具体 Tool 确认前统一标记为“待确认”，确认后再更新接入状态，同时同步 `docs/feature/index.json` 的 `mcp_status`。
- `docs/integrations/mcp.md` 只做 MCP 基础接入、Tool 和真实客户端验证状态的简单汇总，不重复维护完整业务能力分类。
- 新增、修改或删除 MCP Tool 时，必须同步更新来源 Feature 的 `MCP` 小节和 `docs/integrations/mcp.md`；涉及 Feature 聚合状态或集成索引摘要、状态变化时，同时更新对应 `index.json`。
- MCP 状态必须区分“计划中”“已实现”和“客户端已验证”；自动化测试通过不能代替 Hermes 等目标客户端的真实调用验证。

## 7. 验证

- 后端修改：在 `backend` 下执行 `python -m pytest -q`。
- 前端修改：在 `frontend` 下执行 `npm.cmd run build`。
- 同时影响前后端时，两项都必须执行。
- 报告实际执行结果；未执行或失败时明确说明原因。
