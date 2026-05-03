# Phase 2.9：AkShare -> Tushare 迁移计划

## 1. 目标

- 将 Phase 2.9 的市场数据来源从 `AkShare` 切换为 `Tushare`。
- 保持现有导入链路不变：`采集 -> 批次 CSV -> importer 入库 -> 前端初始化页`。
- 保持现有 API 契约不变：`/api/data-init/start`、`/api/data-init/status`、`/api/data-init/update`。
- 股票清单必须通过 CSV 上传获取，不再依赖在线接口拉股票池。
- `Tushare Token` 必须支持在页面上配置（可保存并用于后续初始化/增量更新）。
- 支持按市场板块筛选拉取范围，枚举值固定为：`主板` / `创业板` / `科创板`。
- 支持可回滚：切换失败时能快速恢复到旧数据或旧 provider。

## 2. 迁移原则

- 最小改动：优先只替换 `data_source.py` 内部实现。
- 兼容优先：`initializer.py`、`updater.py`、`importer.py` 的入参/出参尽量不改。
- 可验证：每个阶段都有可执行验证命令和验收标准。
- 可回滚：保留 provider 开关，避免一次性硬切。

## 3. 当前链路与改造边界

当前依赖 `AkShare` 的关键点：

- `backend/app/modules/market_data/data_source.py`
  - `fetch_spot_snapshot()`
  - `fetch_stock_pool()`
  - `fetch_daily_bars_for_stock()`
- `backend/pyproject.toml` 中直接依赖 `akshare`

迁移后保持不变的关键点：

- `backend/app/modules/market_data/initializer.py`
- `backend/app/modules/market_data/updater.py`
- `backend/app/modules/market_data/importer.py`
- `backend/app/api/routes/data_init.py`
- `frontend/src/pages/InitializePage.tsx`
- `frontend/src/lib/api.ts`

新增能力：

- 上传股票清单 CSV 并持久化到本地数据库（作为初始化数据源）

## 4. 分阶段实施

### Checkpoint A：配置与依赖准备

1. 依赖调整
   - 从 `backend/pyproject.toml` 移除 `akshare`
   - 增加 `tushare`（并保留 `pandas`）
2. 配置调整
   - 在 `conf/app.toml.example` 增加：
     - `market_data_provider = "tushare"`
     - `tushare_token = ""`（示例为空）
   - 在 `backend/app/core/settings.py` 增加同名配置读取
3. 密钥策略
   - 优先从环境变量读取 token（例如 `TUSHARE_TOKEN`）
   - 配置文件仅作本地开发兜底
4. 上传入口准备
   - 新增股票清单上传 API（例如：`POST /api/data-init/upload-stock-list`）
   - 约定上传文件必须为 CSV，并校验表头字段
5. Token 页面配置入口
   - 新增 Token 配置 API（例如：`GET/POST /api/data-init/token`）
   - 初始化页面新增 Token 输入与保存按钮
   - 服务端保存 Token（避免明文回传，读取时仅返回“是否已配置”）

验收标准：
- 项目可安装依赖并启动
- 缺少 token 时返回明确错误信息
- 可通过上传接口接收股票清单 CSV，并完成落库
- 可在页面配置 Token，保存后可立即用于初始化和增量更新

### Checkpoint B：数据采集实现替换

1. 在 `data_source.py` 用 Tushare 重写 AkShare 逻辑（函数名保持不变）
   - `fetch_spot_snapshot(trade_date)`
   - `fetch_stock_pool(snapshot_rows)`
   - `fetch_daily_bars_for_stock(stock_code, start_date, end_date)`
2. 增加市场板块筛选能力（基于股票清单 CSV 的 `market` 字段）
   - 入参使用枚举数组：`["主板", "创业板", "科创板"]`
   - 默认值：`["主板", "创业板", "科创板"]`（全量）
   - 仅对筛选后的股票执行逐股 `daily` 拉取
3. 字段映射目标（保持 importer 兼容）：
   - `stock_code`
   - `stock_name`
   - `trade_date`
   - `current_price`
   - `change_amount`
   - `change_pct`
   - `turnover_amount_billion`
   - `turnover_rate`
   - `open_price/high_price/low_price/close_price/volume`
4. 单位与精度校验
   - 明确 Tushare 字段单位并统一到当前系统单位
   - 对关键数值做 round/类型转换，保持与现有 CSV 规范一致
5. 限频与重试
   - 保留当前重试策略和轻量限速

说明：
- 不新增“字段清洗步骤”作为独立流程，仅保留必要的格式校验与类型转换。
- 股票池来源固定为“已上传并落库的 CSV 股票清单”。

验收标准：
- `data_source.py` 输出字段和类型与当前 importer 要求一致
- 同一交易日可生成完整 `stock_pool.csv`、`daily_stock_snapshots.csv`、`daily_bars.csv`

### Checkpoint C：初始化与增量联调

1. 执行全量初始化
   - 初始化前必须先配置 Token；未配置时直接返回错误
   - 初始化前必须先上传股票清单 CSV；未上传时直接返回错误
   - 通过 `/api/data-init/start` 触发
   - 支持传入 `market_filters`（枚举：主板/创业板/科创板）
   - 通过 `/api/data-init/status` 观察状态推进
2. 执行当日增量更新
   - 通过 `/api/data-init/update` 触发
3. 数据一致性检查
   - SQLite 快照行数 > 0
   - DuckDB 日K行数 > 0
   - `market_snapshot.json` 可读取

验收标准：
- 初始化可从 `running -> done`
- 增量更新返回成功且数据有变化

### Checkpoint D：测试与回归

1. 新增/更新后端测试
   - `data_source` 字段映射测试
   - 初始化流程测试（mock tushare）
   - 增量流程测试（mock tushare）
2. 回归测试
   - `python -m pytest backend/tests`
   - 前端 `npm run build`
3. API 契约回归
   - 确认前端无需改接口字段
   - 确认新增上传接口与初始化页联动正常

验收标准：
- 后端测试通过
- 前端构建通过
- 初始化页面可正常操作

### Checkpoint E：灰度切换与回滚

1. 切换策略
   - 增加 provider 开关（默认 `tushare`）
   - 支持临时切回 `akshare`（若保留旧实现）
2. 灰度方式
   - 先跑一次初始化（离线验证）
   - 再跑一次增量（交易日验证）
3. 回滚方案
   - 保留最近一次成功导入批次目录
   - 保留数据库备份（sqlite/duckdb）
   - 切回旧 provider 或恢复备份

验收标准：
- 可在 10 分钟内回滚到可用状态

## 5. 关键风险与对策

1. Tushare 配额/限频
   - 对策：批量拉取、分页节流、失败重试、分段初始化
2. 字段单位差异导致数据失真
   - 对策：建立字段单位映射表与样本校验脚本
3. 历史行情拉取耗时高
   - 对策：初始化按股票分批，支持断点续跑（后续增强）
4. token 管理不当
   - 对策：页面配置时服务端持久化保存，日志中禁止打印 token，接口不回显明文 token

## 6. 建议执行顺序（2-3 天）

- Day 1：Checkpoint A + B（依赖/配置 + 数据采集替换）
- Day 2：Checkpoint C + D（初始化/增量联调 + 测试回归）
- Day 3：Checkpoint E（灰度切换 + 回滚演练）

## 7. 完成定义（DoD）

同时满足以下条件才算迁移完成：

- `AkShare` 不再是运行时必需依赖
- 股票清单通过 CSV 上传并成功落库
- Token 可通过页面配置并成功保存
- 全量初始化与当日增量更新均可成功
- 前端初始化页面可正常展示状态与触发更新
- 后端测试与前端构建通过
- 有明确可执行的回滚路径

