# AlphaPredator Agent Guide
本文件面向后续在本仓库中工作的编码 agent / AI 助手。

## 技术栈

Python + React + SQLite + DuckDB

## 行为准则

- [agent-rules.md](docs/agent-rules.md)
- [code-rules.md](docs/code-rules.md)

## 额外工具

### DuckDB 工具脚本使用说明（`backend/app/db/duckdb_storage.py`）

- 执行 SQL（无参数）：
  - `python backend/app/db/duckdb_storage.py --sql "SELECT 1 AS ok"`
- 执行 SQL（带参数，`--params` 为 JSON）：
  - `python backend/app/db/duckdb_storage.py --sql "SELECT ? AS a, ? AS b" --params "[1, 2]"`
- 参数说明：
  - `--sql`：要执行的 SQL 语句。
  - `--params`：SQL 参数（JSON 字符串，可为数组或对象）。

## 关键代码入口

- 后端启动入口：`backend/app/main.py`。
- 后端路由聚合：`backend/app/api/router.py`。
- 主要 API 分组：
    - `backend/app/api/routes/health.py`
    - `backend/app/api/routes/market.py`
    - `backend/app/api/routes/data_init.py`
- 前端启动入口：`frontend/src/main.tsx`。
- 前端路由入口：`frontend/src/routes/router.tsx`。