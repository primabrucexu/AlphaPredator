# AlphaPredator Task Notifier for Hermes

该包监听 Hermes 对 AlphaPredator 任务创建 MCP Tool 的调用，把任务 UUID 与发起调用的 Hermes Session 关联。插件在后台查询任务状态，并在任务终结后通过 Hermes Session API 把任务级结果注入原 Session。

插件不修改 Hermes 源码或微信通道，不保证消息最终投递到微信用户。

## 兼容范围

- Python 3.11 及以上
- Hermes 0.17.0 及以上的 pip 插件、`post_tool_call` Hook、`dispatch_tool` 和 Session API
- Hermes MCP Server 注册名称默认是 `ap`

## 安装

使用 Hermes 自己的 Python 环境安装，避免把插件装到 AlphaPredator 后端环境：

```powershell
uv pip install --python "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" -e "C:\brucexu\dev\AlphaPredator\integrations\hermes\alphapredator-task-notifier"
hermes plugins enable alphapredator-task-notifier
```

Hermes 0.17.0 的 `plugins enable` 命令不会列出 pip entry point 插件。该版本需要在 `hermes config path` 返回的 `config.yaml` 中保留：

```yaml
plugins:
  enabled:
    - alphapredator-task-notifier
```

生产使用也可以先构建 wheel，再把 wheel 安装到 Hermes 环境。

## Hermes 配置

Hermes Gateway 必须启用只监听本机并带鉴权的 API Server。Hermes 0.17.0 请在 `hermes config env-path` 返回的 `.env` 中配置：

```dotenv
API_SERVER_ENABLED=true
API_SERVER_HOST=127.0.0.1
API_SERVER_PORT=8642
API_SERVER_KEY=替换为至少8字符的本机随机密钥
```

较新版本可使用对应的 `hermes config set` 命令。重启 Hermes Gateway 后生效。密钥只能保存在 Hermes 本机 `.env` 或环境变量中，不要写入 `config.yaml` 或 AlphaPredator 仓库。

可选环境变量：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `ALPHAPREDATOR_MCP_SERVER_NAME` | `ap` | Hermes 中 AlphaPredator MCP Server 的注册名称 |
| `ALPHAPREDATOR_HERMES_API_URL` | `http://127.0.0.1:8642` | Hermes API Server 地址 |
| `ALPHAPREDATOR_TASK_POLL_SECONDS` | `5` | 后台查询间隔，必须大于 0 |
| `API_SERVER_KEY` | 无 | Hermes Session API Bearer Token，必须配置 |

插件状态保存在 `$HERMES_HOME/plugin-data/alphapredator-task-notifier.sqlite3`，不写入项目仓库。Hermes 重启后会恢复尚未完成或尚未注入的任务。

## 升级与卸载

```powershell
uv pip install --python "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" --upgrade -e "C:\brucexu\dev\AlphaPredator\integrations\hermes\alphapredator-task-notifier"
hermes plugins disable alphapredator-task-notifier
uv pip uninstall --python "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" alphapredator-task-notifier
```

Hermes 0.17.0 卸载前需要手工从 `config.yaml` 的 `plugins.enabled` 删除 `alphapredator-task-notifier`，因为该版本的 `plugins disable` 同样不会解析 pip entry point 插件。

卸载包不会自动删除插件 SQLite 状态。如需删除，应先停止 Hermes，再单独备份或删除上述精确文件。

## 验证

```powershell
& C:\brucexu\dev\AlphaPredator\backend\.venv\Scripts\python.exe -m pytest -q
```

真实验证需要在 Hermes 中创建一个短任务，确认：创建立即返回 UUID、等待期间 Session 可继续对话、主动查询可用、终态结果只注入一次。
