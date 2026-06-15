# F05：MCP 交易复盘服务

## 背景

- 需要将 AlphaPredator 的交易复盘能力通过 MCP（Model Context Protocol）暴露给 AI Agent，使用户能在 Agent 对话中直接管理复盘记录。
- 第一期仅暴露交易复盘模块，后续按需扩展行情查询、联动套利等能力。

## 目标

- 以 Streamable HTTP 协议提供 MCP 服务端点。
- 将现有 `trade_review_service` 的 7 个能力封装为 MCP Tool。
- 集成到现有 FastAPI 后端，复用 service 层，不引入独立进程。

## 不做什么

- 第一期不暴露交易复盘以外的能力（行情查询、联动套利等后续规划）。
- 第一期不加认证（先裸奔，绑定 localhost）。
- 不做 stdio 传输（仅 HTTP）。

## 目标平台

- **OpenAI Codex**（Windows 客户端）
- **Hermes**（新 Agent 客户端）

两个平台均支持 Streamable HTTP 传输，当前设计无需做平台差异化。

## 技术选型

| 项目 | 选择 |
|------|------|
| MCP 库 | `fastmcp>=3.0`（PrefectHQ/fastmcp） |
| 传输协议 | Streamable HTTP（单端点 POST/GET/DELETE） |
| 集成方式 | `fastmcp.http_app()` 挂载到现有 FastAPI `api.mount()` |
| 端点路径 | `/api/mcp` |
| 认证 | 无（先裸奔，仅绑定 localhost） |

## 架构

```
Agent (Codex / Hermes)
    │  POST /api/mcp  (JSON-RPC 请求)
    │  GET  /api/mcp  (SSE 服务器推送)
    │  DELETE /api/mcp (结束会话)
    ▼
┌─────────────────────────────┐
│  FastAPI (/api 前缀)         │
│                              │
│  ┌─────────────────────────┐│
│  │ FastMCP 实例 (新增)      ││
│  │ • JSON-RPC 解析          ││
│  │ • Session 管理            ││
│  │ • SSE 流推送             ││
│  │ • @mcp.tool 注册与调度   ││
│  └──────────┬──────────────┘│
│             │ 直接函数调用   │
│  ┌──────────▼──────────────┐│
│  │ trade_review_service     ││ ← 复用现有
│  │ parse_trade_screenshot   ││
│  └─────────────────────────┘│
└─────────────────────────────┘
```

**原则**：MCP 层只做协议适配，不写业务逻辑。

## MCP Tool 定义

### Tool 1：list_trade_reviews

查询交易复盘列表。

| 属性 | 内容 |
|------|------|
| 名称 | `list_trade_reviews` |
| 只读 | ✓ |
| 说明 | 列出所有交易复盘记录，支持按月份、股票代码、状态筛选 |

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `month` | `string?` | | 月份筛选，格式 YYYY-MM |
| `stock_code` | `string?` | | 股票代码筛选 |
| `status` | `string?` | | 状态筛选：open / closed |
| `limit` | `int` | | 每页条数，默认 50，最大 200 |
| `offset` | `int` | | 分页偏移，默认 0 |

**返回**：`{ total: int, items: [...] }`

### Tool 2：get_trade_review_detail

获取单条复盘的完整详情。

| 属性 | 内容 |
|------|------|
| 名称 | `get_trade_review_detail` |
| 只读 | ✓ |
| 说明 | 获取单条交易复盘的完整详情，包括操作明细、决策备注和 AI 分析结果 |

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `review_id` | `string` | ✓ | 复盘记录 ID |

**返回**：`TradeReviewDetail`（含 operations、decision_notes、ai_result）

### Tool 3：create_trade_review

创建新的复盘记录。

| 属性 | 内容 |
|------|------|
| 名称 | `create_trade_review` |
| 只读 | ✗ |
| 说明 | 创建新的交易复盘记录，包含股票信息、交易区间、盈亏、操作明细和决策备注 |

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `stock_code` | `string` | ✓ | 股票代码 |
| `stock_name` | `string` | ✓ | 股票名称 |
| `start_date` | `string` | ✓ | 建仓日期，YYYY-MM-DD |
| `end_date` | `string?` | | 清仓日期，持仓中则为空 |
| `status` | `string` | ✓ | open（持仓中）/ closed（已清仓） |
| `total_buy_amount` | `float?` | | 总买入金额 |
| `total_sell_amount` | `float?` | | 总卖出金额 |
| `realized_pnl` | `float?` | | 已实现盈亏 |
| `return_rate` | `float?` | | 收益率 |
| `entry_reason` | `string` | | 买入理由，默认空 |
| `entry_expectation` | `string` | | 买入预期，默认空 |
| `reflection_did_well` | `string` | | 做得好，默认空 |
| `reflection_did_poorly` | `string` | | 做得不好，默认空 |
| `reflection_redo_plan` | `string` | | 重做计划，默认空 |
| `operations` | `array` | | 操作明细列表 |
| `decision_notes` | `array` | | 决策备注列表 |

**返回**：`TradeReviewDetail`

### Tool 4：update_trade_review

更新已有复盘记录。

| 属性 | 内容 |
|------|------|
| 名称 | `update_trade_review` |
| 只读 | ✗ |
| 说明 | 更新已有交易复盘记录，操作明细和决策备注会全量替换 |

**参数**：与 `create_trade_review` 相同 + `review_id`（必填）

**返回**：`TradeReviewDetail`

### Tool 5：delete_trade_review

删除复盘记录。

| 属性 | 内容 |
|------|------|
| 名称 | `delete_trade_review` |
| 只读 | ✗ |
| 说明 | 删除指定的交易复盘记录 |

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `review_id` | `string` | ✓ | 复盘记录 ID |

**返回**：`{ deleted: true }`

### Tool 6：get_monthly_trade_stats

获取月度交易统计。

| 属性 | 内容 |
|------|------|
| 名称 | `get_monthly_trade_stats` |
| 只读 | ✓ |
| 说明 | 获取指定月份的实时交易统计，包括总笔数、胜率、总盈亏、平均收益率、最大盈利和最大亏损 |

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `month_key` | `string` | ✓ | 月份，格式 YYYY-MM |

**返回**：`MonthlyStatsResponse`（trade_count, win_count, loss_count, realized_pnl, average_return_rate, max_gain, max_loss, reviews）

### Tool 7：parse_trade_screenshot

OCR 解析同花顺交易截图。

| 属性 | 内容 |
|------|------|
| 名称 | `parse_trade_screenshot` |
| 只读 | ✓ |
| 说明 | 接受同花顺交易截图的 base64 编码，用本地 RapidOCR 识别并返回结构化的交易数据，供人工校对后创建复盘 |

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `image_base64` | `string` | ✓ | 图片的 base64 编码内容（不含 `data:xxx;base64,` 前缀） |
| `mime_type` | `string` | | 图片 MIME 类型，默认 image/jpeg |

**返回**：`OcrParseResponse`（stock_name, stock_code, start_date, end_date, status, total_buy_amount, total_sell_amount, realized_pnl, return_rate, operations）

## OCR 截图交互流程

```
人 (截图) → Agent 平台 (base64编码) → MCP Tool parse_trade_screenshot → OCR解析
    ← Agent 展示解析结果，请求确认                              ← 返回结构化数据
    → 人确认/修改
    → MCP Tool create_trade_review → 写入SQLite
    ← "复盘已创建 ✓"
```

**关键点**：

- 人在 Agent 对话中粘贴同花顺交易截图。
- Agent 平台（Codex / Hermes）负责将图片编码为 base64，作为 Tool 的 `image_base64` 参数。
- 如果平台不支持自动编码，备选路径：通过 AlphaPredator Web 前端上传截图做 OCR，再用 Agent 管理复盘记录。

## 新增 / 修改文件

### 新增

- `backend/app/api/routes/mcp.py`：FastMCP 实例创建 + 7 个 `@mcp.tool` 定义

### 修改

- `backend/app/main.py`：调用 `mcp.http_app(path="/")` 并 `api.mount("/mcp", mcp_app)`，传入 lifespan
- `backend/pyproject.toml`：新增 `fastmcp>=3.0` 依赖

## 核心代码结构预览

```python
# backend/app/api/routes/mcp.py

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from app.modules.trade_review.service import trade_review_service
from app.modules.trade_review.ocr_parser import parse_trade_screenshot

mcp = FastMCP(
    "AlphaPredator",
    instructions="A股智能选股工作台。提供交易复盘管理能力，包括查询、创建、更新、删除复盘记录，月度统计和OCR截图解析。",
)

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def list_trade_reviews(
    month: str | None = None,
    stock_code: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """列出所有交易复盘记录，支持按月份、股票代码、状态筛选"""
    result = trade_review_service.list_reviews(month, stock_code, status, limit, offset)
    return result.model_dump()

# ... 其余 6 个 Tool
```

```python
# backend/app/main.py （新增挂载代码）

from app.api.routes.mcp import mcp as mcp_server

mcp_app = mcp_server.http_app(path="/")

# 在 app 创建后：
app = FastAPI(lifespan=mcp_app.lifespan, ...)
app.mount("/mcp", mcp_app)
```

## 待验证项

- OpenAI Codex 和 Hermes 对粘贴图片的 base64 自动编码支持情况（影响 OCR Tool 的实际使用体验）。
- Streamable HTTP 连接在 Windows 环境下的稳定性。

## 后续规划

- 第二期：暴露行情查询 Tool（search_stocks、get_stock_detail、get_kline 等）。
- 第三期：暴露短线情绪、联动套利 Tool。
- 按需添加认证（API Key 或 OAuth）。
