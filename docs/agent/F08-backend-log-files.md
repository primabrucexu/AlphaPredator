# F08：后端日志文件输出

## 目标

后端服务启动后，除继续输出控制台日志外，还需要默认将日志写入项目根目录下的 `logs/` 文件夹，便于排查后台任务、接口和 MCP 运行问题。

## 设计方案

- 复用现有 `app.core.logging.configure_logging()` 作为统一日志配置入口。
- 默认日志目录为项目根目录下的 `logs/`。
- 默认日志文件为 `logs/backend.log`。
- 使用 Python 标准库 `TimedRotatingFileHandler` 按天轮转。
- 轮转后的历史日志使用 gzip 压缩，文件名追加 `.gz`。
- 历史日志只保留 7 天。
- 控制台输出保持不变，`app`、`uvicorn`、`uvicorn.error`、`uvicorn.access` 和 root logger 同时写入文件。

## 数据与接口依赖

- 不新增或修改数据库表。
- 不新增 API。
- `logs/` 已在 `.gitignore` 中忽略，运行日志不进入版本控制。

## 代码层面的实现方案

- 在 `backend/app/core/logging.py` 中增加默认日志目录计算、gzip 命名和压缩轮转函数。
- 调整 `configure_logging()`，创建 `logs/` 目录并配置每日 gzip 轮转文件 handler。
- 增加 `backend/tests/test_logging_config.py`，覆盖默认路径、每日轮转、7 天保留和 gzip 压缩行为。

## 验收标准

- 后端导入或启动日志配置后，项目根目录下自动创建 `logs/backend.log`。
- 日志继续输出到控制台。
- 日志文件每天轮转一次。
- 轮转后的历史日志压缩为 `.gz`。
- 只保留最近 7 天历史日志。
- 相关测试通过。

## 当前状态

- [x] 已确认保留 7 天。
- [x] 已确认使用标准库每日轮转并 gzip 压缩。
- [x] 已实现后端文件日志输出。
- [x] 已补充日志配置测试。
- [x] 已完成目标测试和轻量回归验证。

## 已知问题 / 待人工决策

- 暂无。
