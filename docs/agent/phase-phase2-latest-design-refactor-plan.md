# Phase 2 最新文档设计代码改造规划

## 背景

- 需求来源：根据最新文档设计，检查现有实现与设计的偏差，并输出一份可执行的改造规划文档。
- 阶段上下文：当前阶段为 `Phase 2：短线情绪总览`，目标是打通韭研公社复盘数据的抓取、解析、存储、查询与展示链路。
- 约束条件：
    - 以 `docs/human/` 文档为最高优先级，其次是 `docs/agent/`，最后才是现有代码。
    - 不维护旧设计兼容性，应以最新设计为准收敛实现。
    - 不允许新增不在 `docs/human/data-model/AlphaPredator.dbml` 中定义的数据库表。

## 设计基线（本次对照依据）

### 1. 文档基线

- `docs/agent/F01-hot-review.md`
    - 热点数据来源为韭研公社复盘图片与对应 API。
    - 需要支持：热点板块、题材、连板、复盘图片展示。
    - 默认展示 5 个交易日，提供近 3 / 10 / 20 个交易日快捷范围。
    - 多交易日热点变化对比方式应为“折线图”，并支持点击图例过滤。
    - 初始化页面需要提供韭研公社登录入口，并在凭据失效时提示重新登录。
- `docs/human/data-model/AlphaPredator.dbml`
    - Phase 2 相关表为 `daily_hot_pic`、`daily_hot_info`、`task_info`、`daily_task_info`。
    - `daily_hot_info` 包含 `short_reason` 字段。
- 历史 Phase 目标
    - Phase 2 曾强调“抓取 → 解析 → 存储 → 展示”完整链路，且复盘任务模式与市场数据拉取一致。
    - 数据初始化页面需要支持复盘抓取任务的创建、启动、进度跟踪与重试。

### 2. 本次核查的关键实现范围

- 后端
    - `backend/app/db/sqlite.py`
    - `backend/app/modules/market_data/jygs_review.py`
    - `backend/app/modules/market_data/initializer.py`
    - `backend/app/modules/market_data/service.py`
    - `backend/app/queries/market_queries.py`
    - `backend/app/api/routes/data_init.py`
    - `backend/app/api/routes/market.py`
    - `backend/app/api/routes/jygs.py`
- 前端
    - `frontend/src/pages/InitializePage.tsx`
    - `frontend/src/pages/SentimentOverviewPage.tsx`
    - `frontend/src/pages/HomeSearchPage.tsx`
    - `frontend/src/pages/MarketOverviewPage.tsx`
    - `frontend/src/lib/api.ts`
    - `frontend/src/components/layout/AppShell.tsx`
- 测试
    - `backend/tests/test_phase2_hot_review_api.py`
    - `backend/tests/test_v2_initializer.py`
    - 相关 Phase 2 / JYGS 测试文件

## 现状结论

当前代码并非“完全缺失 Phase 2”，而是处于**两套设计并存、主链路尚未收敛**的状态：

1. 已经具备韭研公社登录、任务创建、按日期抓取、图片/涨停解析写库、前端独立页面展示等基础能力。
2. 但后端查询层与前端展示层仍大量依赖旧的 `hot_sector_*` 表体系，而最新数据模型已经切换到 `daily_hot_pic` /
   `daily_hot_info`。
3. 因此目前最核心的问题不是“缺功能”，而是**数据模型、查询链路、页面交互、任务语义没有统一到最新文档设计**。

## 差距清单

### 一、数据模型与存储层

#### 差距 1：Phase 2 存在两套并行数据模型，且主查询仍依赖旧表

- 文档要求：以 `daily_hot_pic`、`daily_hot_info` 为主存储模型。
- 当前实现：
    - `backend/app/db/sqlite.py` 同时维护旧表：
        - `hot_sector_image_sources`
        - `hot_sector_stock_facts`
        - `hot_sector_sector_mappings`
        - `hot_sector_daily_aggregates`
        - `hot_sector_recent_3d`
    - 同时又新增了新表：
        - `daily_hot_pic`
        - `daily_hot_info`
- 问题：
    - `jygs_review.py` 写入的是新表；
    - `market_queries.py` 与 `service.py` 查询的却主要还是旧表；
    - 导致“抓到的数据”和“页面读到的数据”不是同一套来源。
- 影响：后端 API 返回结果无法稳定反映最新抓取结果，是当前最优先改造点。

#### 差距 2：`daily_hot_info` 缺失 `short_reason` 字段落地

- 文档要求：`AlphaPredator.dbml` 中 `daily_hot_info.short_reason` 为必填字段。
- 当前实现：
    - `backend/app/db/sqlite.py` 创建的 `daily_hot_info` 表没有 `short_reason`。
    - `backend/app/modules/market_data/jygs_review.py` 插入语句也没有写 `short_reason`。
- 影响：当前库表与文档定义不一致，后续如果要承接 OCR/一句话原因、AI 学习样本提炼，会缺字段。

#### 差距 3：任务表命名与字段仍沿用旧实现，不符合最新数据模型

- 文档要求：使用 `task_info`、`daily_task_info`。
- 当前实现：使用 `init_task`、`init_task_day`。
- 影响：
    - 代码与设计文档的术语不一致；
    - 新同学或后续 agent 阅读文档时很难直接映射到代码；
    - 后续若按文档补全能力，会不断遇到“表名不一致”的认知成本。

### 二、抓取任务与鉴权流程

#### 差距 4：JYGS 任务创建前只检查“是否保存了凭据”，未检查“凭据当前是否有效”

- 文档要求：每次抓取前都要检查凭据可用性，不可用时提示重新登录。
- 当前实现：
    - `initializer.create_task()` 在 `task_type == 'JYGS_REVIEW'` 时只调用 `load_credentials()` 判断是否存在凭据；
    - 不会在任务创建阶段主动校验凭据是否过期。
- 影响：
    - 用户能成功创建任务，但任务运行时才逐日失败；
    - 错误反馈滞后，体验与文档要求不符。

#### 差距 5：JYGS 单日失败后任务仍可能整体标记为 `SUCCESS`

- 当前实现：
    - `initializer._process_jygs_review_day()` 遇到异常后会把单日标记为 `FAILED`，但整体任务只增加 `processed_days`
      ，并继续后续日期；
    - `_run_task()` 在循环结束后仍会调用 `finalize_task_success_if_running()`。
- 影响：
    - 出现“任务整体成功，但内部很多天失败”的结果；
    - 与“任务创建/启动/进度跟踪/重试”的设计目标不匹配；
    - 前端很难据此做出正确的用户提示。

#### 差距 6：任务模式已定稿，需要按“与市场数据拉取一致”收敛实现

- 已确认口径：热点复盘任务模式与市场数据拉取保持一致。
- 当前实现：仍保留 `JYGS_REVIEW` 任务类型与专用处理分支，任务语义与失败判定和市场数据任务尚未完全一致。
- 改造要求：统一创建/启动/进度/重试/终止与整体状态判定规则，避免“同为初始化任务但语义不同”。

### 三、查询层与 API 层

#### 差距 7：热点历史、连板榜、复盘图片接口未统一切到最新表模型

- 当前实现：
    - `market_queries.py`：
        - `get_hot_sector_trade_dates()` 读 `hot_sector_daily_aggregates`
        - `get_limit_up_streak_rows()` 读 `hot_sector_stock_facts` / `hot_sector_sector_mappings`
    - `service.py.get_hot_review_images()` 读 `hot_sector_image_sources.parse_notes`
- 问题：这些接口与 `jygs_review.py` 写入的新表链路脱节。
- 直接后果：
    - 即使 `daily_hot_pic` / `daily_hot_info` 有数据，`/market/hot-review-images`、`/market/limit-up-streaks`、
      `/market/hot-sector-history` 也可能读不到；
    - 当前 API 不是最新设计的可靠实现。

#### 差距 8：热点趋势计算仍依赖旧聚合表，未明确基于 `daily_hot_info` 的统一算法

- 文档要求：支持按交易日、按板块维度查询热点变化。
- 当前实现：直接读取旧聚合结果表，不是从 `daily_hot_info` 派生。
- 改造含义：
    - 需要重新定义统一计算口径，例如：
        - 板块热度 = 当日 `daily_hot_info` 中该 `hot_theme` 命中的涨停家数；
        - 最高连板 = 解析 `streak_text` 后的最大板数；
        - 趋势标签 = 基于近 3 个交易日出现频率/排名变化推导。
- 注意：由于文档未定义额外聚合表，优先建议**查询时聚合**或使用只读 SQL 视图思路，不再扩散新持久化表。

### 四、前端页面与交互层

#### 差距 9：热点复盘主展示位置不符合文档描述

- 文档要求：热点复盘模块应在首页展示，并可查看详情。
- 当前实现：
    - 首页 `frontend/src/pages/HomeSearchPage.tsx` 只有“热点复盘”跳转按钮；
    - 核心展示页面在独立路由 `/sentiment`。
- 影响：首页没有真正承接文档中的“热点复盘模块”。

#### 差距 10：热点变化图形态与默认筛选不符合文档要求

- 文档要求：
    - 用折线图展示某板块在多个交易日内每日涨停家数变化；
    - 默认展示 5 个交易日；
    - 提供近 3 / 10 / 20 个交易日快捷按钮；
    - 支持点击图例过滤。
- 当前实现：
    - `SentimentOverviewPage.tsx` 使用的是热力图，不是折线图；
    - 默认是 7 日；
    - 选项是 5 / 7 / 10 / 20；
    - 没有“按板块点击过滤”的交互闭环。
- 影响：页面主交互与文档设计偏差明显。

#### 差距 11：复盘页缺少基于热点股票明细的联动视图

- 文档要求：在热点复盘模块中展示个股，并支持点击跳转个股详情。
- 当前实现：
    - 页面仅展示“热点板块排行”“复盘图片”“近期连板龙头”；
    - 缺少按日期展开的热点股票明细列表（来自 `daily_hot_info`）。
- 影响：页面无法完整承载“题材 → 股票 → 个股行情联动”的使用路径。

#### 差距 12：初始化页虽然已有韭研登录与任务能力，但说明文案和状态表达仍偏实现导向

- 当前实现：初始化页已具备：
    - Playwright 一键登录；
    - JYGS_REVIEW 任务创建；
    - 任务进度、失败重试、终止。
- 仍需补齐：
    - 明确区分“已保存凭据”和“凭据有效”；
    - 在凭据失效时直接阻止任务启动并给出重登录入口；
    - 将页面文案调整为“复盘抓取 / 解析 / 展示”完整链路，而不是仅“抓取”。

### 五、测试与技术债

#### 差距 13：测试仍覆盖两套旧/新表结构，未形成统一验收口径

- 当前测试现状：
    - `test_phase2_hot_review_api.py` 同时验证旧表和新表；
    - 服务层实现也因此保持了双轨兼容。
- 问题：这会持续阻碍代码收敛到最新设计。
- 改造方向：
    - 以后端 API 的最新 contract 为准重写测试；
    - 让测试只验证 `daily_hot_pic` / `daily_hot_info` 驱动的最终行为。

#### 差距 14：旧热点图片 OCR 导入链路仍在仓库中，占用认知空间

- 涉及：
    - `backend/app/modules/market_data/hot_sector_importer.py`
    - 旧表 `hot_sector_*`
    - 若干旧测试
- 问题：与最新文档定义的 Phase 2 主路径已经不一致。
- 处理建议：不是第一步就删，但必须在改造后明确退场计划。

## 改造目标

### 做什么

1. 统一 Phase 2 数据主链路：`JYGS API / 图片` → `daily_hot_pic` / `daily_hot_info` → 市场/情绪 API → 前端页面。
2. 统一任务与鉴权语义，确保“任务是否可启动、是否成功”与用户直觉一致。
3. 统一页面交互，使初始化页、首页、短线情绪页符合最新文档设计。
4. 统一测试口径，移除旧实现对新设计的干扰。

### 不做什么

1. 不在本轮直接进入 Phase 3/4 的功能开发。
2. 不新增文档未定义的新数据库表。
3. 不为旧热点 OCR 链路做长期兼容封装。

## 新增联动范围（Phase 1）

已确认：因引入新数据源，`Phase 1` 的市场数据获取链路也需同步改造，重点覆盖以下两点：

1. **数据存储方式并轨**：明确新数据源与既有历史数据在 DuckDB/SQLite 的落库策略、字段映射与幂等写入语义。
2. **任务信息存储并轨**：市场数据任务与复盘任务统一到同一任务信息模型（`task_info` / `daily_task_info`），避免 `init_task` /
   `init_task_day` 双轨持续存在。

该联动范围优先级与 Phase 2 P0 并列，不再视为后续优化项。

## 推荐改造方案

### 方案 A：以 `daily_hot_pic` / `daily_hot_info` 为唯一事实来源，查询时聚合热点趋势（推荐）

- 做法：
    - 后端所有热点相关 API 改为只从 `daily_hot_pic` / `daily_hot_info` 读取。
    - 热点板块趋势、最高连板、板块榜单等指标在查询时通过 SQL 聚合计算。
    - 前端围绕这些 API 做页面改造。
- 优点：
    - 与最新文档数据模型完全一致；
    - 不新增表，符合仓库规则；
    - 技术收敛最彻底。
- 缺点：
    - 需要重写一批查询逻辑；
    - 若后期数据量大，再考虑缓存/物化方案。

### 方案 B：保留旧聚合表，新增同步桥接逻辑

- 做法：抓到 `daily_hot_*` 后再同步写一份旧 `hot_sector_*` 聚合表，页面先不大改。
- 不推荐原因：
    - 继续扩大双轨模型；
    - 与“不维护兼容性”的仓库规则冲突；
    - 长期成本更高。

## 分阶段改造任务

### Task 0：补齐 Phase 1 新数据源接入与任务存储并轨设计

**目标：** 先稳定 Phase 1 数据底座，避免 Phase 2 在不稳定数据基线之上迭代。

**涉及文件：**

- `backend/app/modules/market_data/data_source.py`
- `backend/app/modules/market_data/initializer.py`
- `backend/app/db/duckdb_storage.py`
- `backend/app/db/sqlite.py`
- `backend/app/repositories/init_task_repo.py`
- `backend/tests/test_v2_initializer.py`
- `backend/tests/test_market_data_importer.py`

**改造内容：**

1. 定义“新数据源 -> 内部标准行情行”映射 contract（字段、单位、日期、空值规则）。
2. 明确双数据源优先级与回退策略（主源失败时的降级路径）。
3. 调整 DuckDB 写入层，保证多源写入时仍满足“按交易日幂等覆盖 + 原子性校验”。
4. 将任务信息存储收敛到 `task_info` / `daily_task_info`，并提供从 `init_task` / `init_task_day` 的迁移路径。

**验收标准：**

- 新数据源下的 Phase 1 任务可完整跑通，且数据可查。
- 任务主表/子表语义与命名与数据模型一致。
- Phase 1/Phase 2 共用同一任务状态机语义。

### Task 1：冻结任务模式口径并更新实现约束

**目标：** 将已确认决策落到可执行约束，避免实现再次分叉。

- 热点复盘任务模式与市场数据拉取保持一致。
- 迁移期允许短暂保留旧 `hot_sector_*` 表，但不得作为新功能事实来源。

**落地约束：**

- 初始化页对复盘抓取的入口、状态、重试语义与市场数据任务统一。
- 后端任务状态机规则统一（含失败日对整体任务状态的影响）。

### Task 2：统一 SQLite Schema 与任务模型命名

**涉及文件：**

- `backend/app/db/sqlite.py`
- `backend/app/repositories/init_task_repo.py`
- `backend/app/schemas/data_init.py`
- `backend/app/modules/market_data/initializer.py`
- 相关测试

**改造内容：**

1. 将 `init_task` / `init_task_day` 收敛为文档命名：`task_info` / `daily_task_info`。
2. 为 `daily_hot_info` 补齐 `short_reason` 字段及迁移逻辑。
3. 将任务类型命名统一到文档口径（如 `MARKET_DATA_LOAD` vs `MARKET_DATA` 需要一并定稿）。

**验收标准：**

- schema 与 `AlphaPredator.dbml` 对齐；
- 任务查询、列表、详情、重试、终止接口仍可正常工作；
- 测试只围绕新表名/新字段通过。

### Task 3：重写热点查询层，切断对旧 `hot_sector_*` 表的依赖

**涉及文件：**

- `backend/app/queries/market_queries.py`
- `backend/app/modules/market_data/service.py`
- `backend/app/schemas/market.py`
- `backend/app/api/routes/market.py`
- 相关测试

**改造内容：**

1. `get_hot_review_images()` 改为直接读取 `daily_hot_pic`。
2. `get_limit_up_streaks()` 改为直接读取 `daily_hot_info`：
    - 通过 `streak_text` 解析板数；
    - 支持最小板数过滤；
    - 返回股票、封板时间、题材等。
3. `get_hot_sector_history()` 改为基于 `daily_hot_info.hot_theme` 聚合：
    - 计算每日题材出现次数；
    - 计算最高连板；
    - 计算近 3 日趋势标签。
4. 明确 `hot_theme` 多值拆分规则（如 `、` 分隔）。

**验收标准：**

- 只要 `daily_hot_pic` / `daily_hot_info` 有数据，三个 Phase 2 API 就能返回可用结果；
- 不再要求旧 `hot_sector_*` 表存在。

### Task 4：修正 JYGS 任务的鉴权前置校验与失败语义

**涉及文件：**

- `backend/app/modules/market_data/initializer.py`
- `backend/app/api/routes/data_init.py`
- `backend/app/api/routes/jygs.py`
- `backend/app/modules/jygs/auth.py`
- 相关测试

**改造内容：**

1. 在创建/启动 `JYGS_REVIEW` 任务前做一次凭据有效性检查，而不是只检查是否存在。
2. 若凭据无效：
    - 直接返回明确错误；
    - 前端引导用户重新登录。
3. 修正任务完成语义：
    - 若存在失败日，整体任务不应直接标记为 `SUCCESS`；
    - 可以采用“有失败即 FAILED”或“允许部分成功但明确新增状态”的方案。
    - 由于当前状态枚举未定义 `PARTIAL_SUCCESS`，建议本轮先采用“有失败即 FAILED”。

**验收标准：**

- 无效 SESSION 不能启动任务；
- 任务整体状态能真实反映执行结果。

### Task 5：按文档重构前端短线情绪展示

**涉及文件：**

- `frontend/src/pages/SentimentOverviewPage.tsx`
- `frontend/src/lib/api.ts`
- 必要时新增组件文件

**改造内容：**

1. 将热点趋势图从热力图改为折线图。
2. 默认范围调整为 5 个交易日。
3. 快捷按钮调整为：近 3 / 10 / 20 日，并保留自定义范围扩展能力。
4. 提供题材点击/图例过滤交互。
5. 新增“热点股票明细”区域，展示 `daily_hot_info` 对应股票，并支持跳转个股详情。
6. 复盘图片区支持多图切换与空态展示。

**验收标准：**

- 页面核心交互与 `docs/agent/F01-hot-review.md` 一致；
- 用户可从题材趋势查看到具体个股，再跳到个股页。

### Task 6：在首页补上“热点复盘模块”

**涉及文件：**

- `frontend/src/pages/HomeSearchPage.tsx`
- 可复用 `SentimentOverviewPage` 的子组件

**改造内容：**

1. 首页不再只放“热点复盘”跳转按钮。
2. 增加轻量版热点复盘模块，至少展示：
    - 最新交易日热点板块列表；
    - 复盘图片入口；
    - 查看详情跳转到 `/sentiment`。

**验收标准：**

- 首页即可感知当日热点复盘信息，符合文档的入口设计。

### Task 7：清理旧热点链路与统一测试

**涉及文件：**

- `backend/tests/test_phase2_hot_review_api.py`
- 旧 `hot_sector_*` 相关测试文件
- `backend/app/modules/market_data/hot_sector_importer.py`（视最终方案决定是否保留）

**改造内容：**

1. API 测试改为只验证新表链路。
2. 删除或降级旧热点表相关测试，避免继续绑定过时设计。
3. 若确认不再使用旧 OCR 导入链路，再安排单独清理任务。

**验收标准：**

- Phase 2 测试能够准确反映最新设计；
- 代码中不存在“因为测试仍依赖旧表，所以不敢删旧实现”的情况。

## 优先级建议

### P0（必须先做）

1. 完成 Phase 1 新数据源接入 contract 与存储并轨（DuckDB + 任务信息表）。
2. 将“任务模式与市场数据拉取一致”的决策落实到任务状态机与接口语义。
3. 统一后端 API 到 `daily_hot_pic` / `daily_hot_info`。
4. 修正 JYGS 鉴权前置校验与任务失败语义。

### P1（随后完成）

4. 补齐 `short_reason`、任务表命名与 schema 对齐。
5. 重构 `SentimentOverviewPage` 为折线趋势 + 股票明细联动。
6. 首页增加热点复盘模块。

### P2（收尾优化）

7. 清理旧 `hot_sector_*` 链路。
8. 收敛测试与文档说明。

## 风险与待决策项

### 风险 1：任务模式虽已定稿，但实现未完全并轨

- 表现：复盘任务在代码里仍可能保留“特例语义”（如创建前校验、失败判定、重试策略与市场数据任务不一致）。
- 缓解：先统一任务状态机和接口 contract，再推进页面与查询改造。

### 风险 2：`hot_theme` 为多题材串联文本，直接聚合会影响统计准确性

- 缓解：统一拆分符与清洗规则，例如按 `、` 拆分、去空格、去重。

### 风险 3：`streak_text` 文本格式可能不统一，影响“最高连板/连板榜”计算

- 缓解：先补一个稳定解析器，无法解析时降级为 1 板或空值，并在测试中覆盖常见格式。

### 风险 4：旧表清理过快会影响当前未覆盖到的隐式依赖

- 缓解：先完成 API 与页面迁移，再删除旧表读取逻辑；删除前跑全量相关测试。

## 建议的实施顺序

1. 先做后端查询统一，不动页面结构。
2. 再修任务与鉴权语义，让数据获取链路稳定。
3. 然后改短线情绪页与首页模块。
4. 最后做 schema 命名收敛、旧链路删除、测试清理。

## 验收清单

- [ ] `JYGS_REVIEW` 抓取结果写入后，`/api/market/hot-review-images` 能直接返回 `daily_hot_pic` 数据。
- [ ] `/api/market/limit-up-streaks`、`/api/market/hot-sector-history` 不再依赖旧 `hot_sector_*` 表。
- [ ] 无效韭研 SESSION 不能启动任务，并能在初始化页提示重新登录。
- [ ] 任务整体状态与单日执行结果一致，不会出现“整体成功但多日失败”。
- [ ] `daily_hot_info` 与 `AlphaPredator.dbml` 字段一致，包含 `short_reason`。
- [ ] 短线情绪页使用折线图展示近 N 日板块涨停家数变化，默认 5 日，支持 3/10/20 快捷范围与过滤交互。
- [ ] 首页存在热点复盘模块，而不只是跳转按钮。
- [ ] Phase 2 相关测试只围绕最新设计通过。

## 最终建议

建议将本次改造定义为一次**Phase 2 数据链路收敛**，目标不是继续堆功能，而是：

- 统一事实表；
- 统一查询口径；
- 统一任务语义；
- 统一页面入口与交互。

只要这四件事完成，后续无论是“AI 学习用户选股偏好”还是“热点题材与个股联动分析”，都能建立在稳定的数据底座之上。
