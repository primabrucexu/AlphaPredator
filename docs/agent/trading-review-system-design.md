# 交易复盘系统设计方案（基于 AlphaPredator 现状）

> 说明：本文档用于在当前仓库基础上扩展“交易复盘系统”设计，覆盖页面结构、AI 输入输出格式、数据表设计方案。
>
> 注意：本文档中的“数据表设计”仅为方案输出。根据仓库 `AGENTS.md` 的硬性规则，**任何新建或修改数据库表的实现，都必须等待用户审批并由用户先更新 `docs/human/data-model/AlphaPredator.dbml` 后，才能进入编码阶段**。

---

## 1. 设计目标

在现有 AlphaPredator 的行情、个股详情、短线情绪、AI 结果页基础上，新增一套面向个人交易者的复盘能力，核心目标如下：

1. **记录单标的完整交易过程**：从建仓到清仓形成一条完整复盘记录。
2. **沉淀主观决策信息**：不仅保存成交记录，也保存建仓理由、关键节点原因、最终反思。
3. **生成单标的 AI 复盘**：帮助用户识别每笔交易的主要问题、亮点和改进点。
4. **生成月度 AI 总结**：识别重复错误动作、问题场景、能力短板，并量化实际亏损影响与收益机会影响。
5. **与现有仓库风格保持一致**：优先复用现有前端页面组织方式、后端 API 风格与 AI 结果展示思路，不额外引入复杂架构。

---

## 2. 与现有仓库的衔接方式

结合当前仓库已有页面与模块，建议复盘系统以“新增业务域”的方式接入，而不是改造已有行情主流程。

### 2.1 前端接入建议

当前前端已有页面包括：
- `HomeSearchPage.tsx`
- `StockDetailPage.tsx`
- `MarketOverviewPage.tsx`
- `SentimentOverviewPage.tsx`
- `AiResultsPage.tsx`
- `HistoryPage.tsx`
- `FocusPage.tsx`
- `InitializePage.tsx`

建议新增一个独立的复盘业务分组，挂在现有侧边导航中，优先采用以下页面拆分：

1. **交易复盘首页**
2. **单标的复盘详情页**
3. **新建 / 编辑复盘页**
4. **月度复盘页**
5. **AI 复盘结果页（可选复用现有 AiResultsPage 的展示模式）**

### 2.2 后端接入建议

当前后端路由主要集中在：
- `backend/app/api/routes/market.py`
- `backend/app/api/routes/data_init.py`
- `backend/app/api/routes/jygs.py`

建议为复盘系统新增单独路由域，例如：
- `backend/app/api/routes/trade_review.py`

这样可以避免把复盘逻辑混入已有行情接口，保持边界清晰。

同时建议在 `backend/app/modules/` 下新增复盘模块目录，例如：
- `backend/app/modules/trade_review/`

用于承载：
- 复盘记录查询
- OCR 结果整理
- AI prompt 构造
- 月度归纳分析

---

## 3. 页面结构设计

## 3.1 页面总览

建议新增以下页面：

### A. 交易复盘首页 `TradeReviewHomePage`

用途：
- 浏览全部单标的复盘记录
- 快速筛选月份、股票、标签、盈亏状态
- 进入新建复盘、详情页、月度复盘页

建议布局：
- 顶部：月份筛选 / 股票搜索 / 盈亏筛选 / 新建按钮
- 中部：复盘记录列表
- 右侧或顶部卡片：当月统计摘要

列表字段建议：
- 股票代码
- 股票名称
- 交易周期（开始日期 ~ 结束日期）
- 本轮盈亏金额
- 收益率
- AI 标签 / 类型
- 是否已完成 AI 复盘
- 更新时间

---

### B. 单标的复盘详情页 `TradeReviewDetailPage`

用途：
- 查看一轮交易的完整复盘内容
- 查看客观成交记录
- 查看主观复盘内容
- 查看 AI 单标的总结

建议分区：

#### 区块 1：基础信息
- 股票代码
- 股票名称
- 交易区间
- 总买入金额
- 总卖出金额
- 已实现盈亏
- 收益率

#### 区块 2：成交明细时间线
按时间顺序展示：
- 操作时间
- 操作类型
- 成交价格
- 成交数量
- 成交金额
- 备注

#### 区块 3：主观复盘
- 建仓理由
- 初始预期
- 关键操作原因列表
- 最终自我总结

#### 区块 4：AI 单标的总结
- 主要问题
- 做得好的地方
- 最值得改进的一点
- 操作标签 / 类型
- AI 分析生成时间

#### 区块 5：原始材料
- 上传的交易图
- OCR 识别结果
- 人工修正前后对比（可选）

---

### C. 新建 / 编辑复盘页 `TradeReviewEditorPage`

用途：
- 创建一条完整复盘记录
- 上传交易截图并校对 OCR
- 填写主观复盘信息
- 触发 AI 分析

建议采用分步式编辑：

#### Step 1：基础信息
- 股票代码
- 股票名称
- 交易开始日期
- 交易结束日期
- 本轮状态（进行中 / 已清仓）

#### Step 2：上传交易图与 OCR 校对
- 上传图片
- 展示 OCR 解析出的成交记录
- 支持人工逐条修正

#### Step 3：填写主观复盘
- 建仓理由
- 建仓时预期
- 关键操作原因（可多条）
- 最终自我总结

#### Step 4：确认并生成 AI 总结
- 保存记录
- 触发 AI 单标的总结生成

---

### D. 月度复盘页 `TradeReviewMonthlyPage`

用途：
- 按月份查看复盘汇总
- 查看 AI 月度总结
- 查看错误模式、问题场景、能力短板

建议布局：

#### 区块 1：月份切换 + 总览卡片
- 月份选择器
- 本月总收益
- 交易次数
- 胜率
- 盈亏比
- 最大单笔亏损 / 收益

#### 区块 2：本月做得好的地方
- 有效交易模式
- 正确判断
- 代表案例链接

#### 区块 3：重复问题分析
分成两个子卡片：

1. **错误动作类**
   - 问题名称
   - 出现次数
   - 实际亏损影响
   - 收益机会影响
   - 对应案例

2. **问题场景类**
   - 场景名称
   - 出现次数
   - 实际亏损影响
   - 收益机会影响
   - 对应案例

#### 区块 4：能力短板
- 当前最主要的 1~3 个能力短板
- 每个短板的推导依据
- 对应案例链接

#### 区块 5：下个月行动建议
- 应继续什么
- 应避免什么
- 应重点关注什么

---

### E. AI 结果展示页 `TradeReviewAiResultPage`（可选）

如果希望与现有 `AiResultsPage.tsx` 保持一致，可以将 AI 分析结果单独做成标准结果页。

适合场景：
- 单标的 AI 总结查看
- 月度总结查看
- 保留 AI 生成历史版本

如果不希望增加页面数量，也可以直接内嵌在详情页与月度页中。

---

## 4. 页面间流程设计

### 4.1 单标的复盘主流程

1. 用户进入交易复盘首页
2. 点击“新建复盘”
3. 填写基础信息
4. 上传交易截图
5. 系统 OCR 识别成交记录
6. 用户人工校正
7. 用户填写建仓理由、关键操作原因、最终总结
8. 保存复盘记录
9. 触发 AI 单标的分析
10. 在详情页查看完整结果

### 4.2 月度复盘主流程

1. 用户进入月度复盘页
2. 选择月份
3. 系统汇总该月所有已完成复盘记录
4. 计算交易结果指标
5. 构造 AI 月度分析输入
6. 生成月度总结
7. 用户查看错误模式、问题场景、能力短板与行动建议

---

## 5. AI 输入输出设计

## 5.1 单标的 AI 分析

### 5.1.1 输入结构

建议 AI 输入由两部分组成：

#### A. 客观交易数据
```json
{
  "stock_code": "600000",
  "stock_name": "示例股票",
  "trade_period": {
    "start_date": "2026-05-01",
    "end_date": "2026-05-08"
  },
  "summary": {
    "total_buy_amount": 20000,
    "total_sell_amount": 18600,
    "realized_pnl": -1400,
    "return_rate": -0.07
  },
  "operations": [
    {
      "trade_time": "2026-05-01T09:35:00",
      "operation_type": "buy",
      "price": 10.25,
      "quantity": 1000,
      "amount": 10250
    },
    {
      "trade_time": "2026-05-02T10:10:00",
      "operation_type": "sell",
      "price": 9.8,
      "quantity": 1000,
      "amount": 9800
    }
  ]
}
```

#### B. 主观复盘数据
```json
{
  "entry_reason": "看好板块发酵，认为次日有溢价",
  "entry_expectation": "预期至少有一次冲高确认",
  "key_decisions": [
    {
      "decision_type": "sell",
      "decision_time": "2026-05-02T10:10:00",
      "reason": "早盘快速下杀，担心资金离场"
    }
  ],
  "final_reflection": {
    "did_well": "及时止损，没有继续扩大亏损",
    "did_poorly": "买入前没有做好高位分歧预案",
    "redo_plan": "以后做高位票前先定义什么情况走、什么情况留"
  }
}
```

### 5.1.2 输出结构

建议标准化为：
```json
{
  "major_issue": "买入前对高位分歧场景缺少预案，导致次日下杀时处理被动。",
  "strengths": [
    "出现不利走势后没有继续盲目加仓",
    "复盘中能够识别自己的问题场景"
  ],
  "top_improvement": "在高波动交易中，买入前先定义持有、减仓和退出条件。",
  "trade_tags": [
    "高位分歧交易",
    "预案不足"
  ],
  "confidence_notes": "本次分析已结合建仓预期、关键操作原因和最终自我总结，避免仅从事后走势倒推结论。"
}
```

---

## 5.2 月度 AI 总结

### 5.2.1 输入结构

月度输入应由三层组成：

#### A. 月度整体指标
```json
{
  "month": "2026-05",
  "summary": {
    "trade_count": 12,
    "win_count": 5,
    "loss_count": 7,
    "realized_pnl": -8600,
    "average_return_rate": -0.018,
    "max_gain": 3200,
    "max_loss": -4500
  }
}
```

#### B. 单标的复盘摘要列表
```json
[
  {
    "review_id": "tr_001",
    "stock_code": "600000",
    "stock_name": "示例股票A",
    "realized_pnl": -4000,
    "return_rate": -0.1,
    "entry_reason": "看板块发酵",
    "entry_expectation": "次日冲高",
    "key_points": [
      "高位介入",
      "次日快速下杀",
      "没有预案"
    ],
    "final_reflection": "高位票参与前没有想清楚分歧时怎么应对",
    "single_trade_ai_summary": {
      "major_issue": "高位分歧场景处理被动",
      "trade_tags": ["高位分歧交易", "预案不足"]
    }
  }
]
```

#### C. 分析原则提示词
用于约束 AI：
- 不要简单用结果倒推结论
- 对卖飞 / 少赚要结合当时利润情况和交易预期分析
- 不只归纳错误动作，还要归纳问题场景
- 能力短板需由重复动作、重复场景和结果影响综合推导

### 5.2.2 输出结构

建议标准化为：
```json
{
  "monthly_overview": {
    "performance_summary": "本月整体小幅亏损，亏损主要集中在高位分歧交易与追高被套。",
    "did_well": [
      "部分止损执行较果断",
      "对热点板块的识别仍有一定准确性"
    ]
  },
  "repeated_issues": {
    "action_patterns": [
      {
        "name": "追高被套",
        "count": 3,
        "actual_loss_impact": -10000,
        "opportunity_cost_impact": 0,
        "evidence_review_ids": ["tr_001", "tr_003", "tr_008"],
        "analysis": "本月有 3 笔交易属于追高后承接不足，被动承受回撤。"
      }
    ],
    "scenario_patterns": [
      {
        "name": "高位分歧场景缺少预案",
        "count": 4,
        "actual_loss_impact": -7200,
        "opportunity_cost_impact": -1800,
        "evidence_review_ids": ["tr_001", "tr_004", "tr_006", "tr_010"],
        "analysis": "在高波动和高分歧环境下，进入交易前没有明确退出条件，导致临场处理被动。"
      }
    ]
  },
  "capability_gaps": [
    {
      "name": "高位分歧处理能力弱",
      "reason": "重复出现高位分歧场景缺少预案的问题，并造成明显实际亏损。"
    },
    {
      "name": "持盈能力偏弱",
      "reason": "在浮盈较薄时多次提前兑现，收益扩展不足。"
    }
  ],
  "top_priorities": [
    "减少高位分歧票的临时性参与",
    "建立买入前退出预案",
    "区分低利润垫止盈与合理落袋"
  ],
  "next_month_actions": [
    "仅参与���己能解释清楚分歧应对方案的交易",
    "对高位股设置固定的减仓与退出条件",
    "每周复盘一次提前止盈案例，校正持盈标准"
  ]
}
```

---

## 6. AI 分析规则落地建议

为了与前面的复盘原则一致，建议在系统实现中固定以下 AI 分析约束：

### 6.1 单标的分析规则
1. 优先基于用户填写的建仓理由、关键操作原因、最终自我总结理解交易。
2. 不因为“卖出后继续上涨”就直接定义为卖飞。
3. 对“过早止盈 / 少赚”类问题，必须结合卖出时利润水平与原始预期分析。
4. 输出语言尽量具体，避免空泛评价。

### 6.2 月度分析规则
1. 不只总结收益结果，还要识别高频错误动作。
2. 不只分析动作，还要识别高频问题场景。
3. 每类问题尽量量化：次数、实际亏损影响、收益机会影响。
4. 能力短板必须有可回溯依据，不能凭空下判断。
5. 行动建议要尽量可执行，避免鸡汤式表达。

---

## 7. 数据表设计方案

> 再次说明：以下仅为设计方案，不代表可以直接编码建表。

为了支持单标的复盘、OCR 校对、AI 结果和月度汇总，建议新增以下数据结构。

## 7.1 表一：`trade_review_session`

用途：保存“一只股票从建仓到清仓的一整轮操作”的主记录。

| 字段名 | 类型 | 含义 | 说明 |
| --- | --- | --- | --- |
| id | TEXT | 主键 | 建议使用 UUID / 业务 ID |
| stock_code | TEXT | 股票代码 | 统一 6 位字符串 |
| stock_name | TEXT | 股票名称 | 冗余保存，便于展示 |
| start_date | TEXT | 建仓日期 | `YYYY-MM-DD` |
| end_date | TEXT | 清仓日期 | 未清仓时可为空 |
| status | TEXT | 状态 | `open` / `closed` |
| total_buy_amount | REAL | 总买入金额 | 聚合字段 |
| total_sell_amount | REAL | 总卖出金额 | 聚合字段 |
| realized_pnl | REAL | 已实现盈亏 | 聚合字段 |
| return_rate | REAL | 收益率 | 聚合字段 |
| entry_reason | TEXT | 建仓理由 | 主观复盘内容 |
| entry_expectation | TEXT | 建仓预期 | 主观复盘内容 |
| reflection_did_well | TEXT | 做对了什么 | 自我总结 |
| reflection_did_poorly | TEXT | 做错了什么 | 自我总结 |
| reflection_redo_plan | TEXT | 如果重来怎么做 | 自我总结 |
| ai_status | TEXT | AI 分析状态 | `pending` / `done` / `failed` |
| created_at | TEXT | 创建时间 | ISO 时间 |
| updated_at | TEXT | 更新时间 | ISO 时间 |

为什么需要：
- 这是单标的复盘的主实体。
- 页面列表、详情页、月度聚合都需要依赖它。

---

## 7.2 表二：`trade_review_operation`

用途：保存一轮复盘中的每一笔成交操作明细。

| 字段名 | 类型 | 含义 | 说明 |
| --- | --- | --- | --- |
| id | TEXT | 主键 | UUID / 业务 ID |
| review_id | TEXT | 关联复盘主表 | 指向 `trade_review_session.id` |
| trade_time | TEXT | 操作时间 | 精确到秒 |
| operation_type | TEXT | 操作类型 | `buy` / `sell` / `add` / `reduce` / `t_buy` / `t_sell` 等 |
| price | REAL | 成交价格 | |
| quantity | INTEGER | 成交数量 | |
| amount | REAL | 成交金额 | |
| source | TEXT | 数据来源 | `ocr` / `manual` / `import` |
| note | TEXT | 备注 | 可选 |
| sort_index | INTEGER | 排序序号 | 保证展示稳定 |
| created_at | TEXT | 创建时间 | |
| updated_at | TEXT | 更新时间 | |

为什么需要：
- 支撑成交时间线展示。
- 支撑盈亏、持仓变化和 AI 客观数据输入。

---

## 7.3 表三：`trade_review_decision_note`

用途：保存关键操作节点对应的主观原因。

| 字段名 | 类型 | 含义 | 说明 |
| --- | --- | --- | --- |
| id | TEXT | 主键 | |
| review_id | TEXT | 关联复盘主表 | |
| related_operation_id | TEXT | 关联操作记录 | 可为空；允许只记录决策，不强绑操作 |
| decision_type | TEXT | 决策类型 | `add` / `reduce` / `sell` / `t` / `other` |
| decision_time | TEXT | 决策时间 | |
| reason | TEXT | 决策原因 | 用户填写 |
| created_at | TEXT | 创建时间 | |
| updated_at | TEXT | 更新时间 | |

为什么需要：
- 建仓理由是整轮交易级别的，但关键操作原因通常是多条、按节点出现。
- 将其独立存储，比塞进主表更清晰。

---

## 7.4 表四：`trade_review_attachment`

用途：保存交易截图、OCR 原始文本等附件信息。

| 字段名 | 类型 | 含义 | 说明 |
| --- | --- | --- | --- |
| id | TEXT | 主键 | |
| review_id | TEXT | 关联复盘主表 | |
| attachment_type | TEXT | 附件类型 | `trade_screenshot` / `ocr_raw` / `other` |
| file_path | TEXT | 文件路径 | 本地或对象存储路径 |
| original_name | TEXT | 原始文件名 | |
| mime_type | TEXT | 文件类型 | |
| ocr_text | TEXT | OCR 原始结果 | 非 OCR 附件可为空 |
| created_at | TEXT | 创建时间 | |

为什么需要：
- 交易图和 OCR 原始数据是复盘链路的重要输入材料。
- 便于后续追溯 OCR 与人工修正差异。

---

## 7.5 表五：`trade_review_ai_result`

用途：保存单标的 AI 分析结果与月度 AI 分析结果。

| 字段名 | 类型 | 含义 | 说明 |
| --- | --- | --- | --- |
| id | TEXT | 主键 | |
| result_type | TEXT | 结果类型 | `single_review` / `monthly_review` |
| review_id | TEXT | 关联单标的复盘 | 月度结果时可为空 |
| month_key | TEXT | 月份键 | 例如 `2026-05`；单标的结果时可为空 |
| model_name | TEXT | 使用模型 | 便于追溯 |
| input_payload_json | TEXT | 输入快照 | JSON 字符串 |
| output_payload_json | TEXT | 输出结果 | JSON 字符串 |
| status | TEXT | 状态 | `done` / `failed` |
| error_message | TEXT | 错误信息 | 失败时记录 |
| created_at | TEXT | 创建时间 | |

为什么需要：
- 保留 AI 结果可追溯性。
- 支持重新生成、版本比对、调试输入输出。

---

## 7.6 表六：`trade_review_monthly_summary`（可选）

用途：缓存月度聚合结果，避免每次页面打开都全量重算。

| 字段名 | 类型 | 含义 | 说明 |
| --- | --- | --- | --- |
| month_key | TEXT | 主键 | 例如 `2026-05` |
| trade_count | INTEGER | 交易次数 | |
| win_count | INTEGER | 盈利次数 | |
| loss_count | INTEGER | 亏损次数 | |
| realized_pnl | REAL | 月度总盈亏 | |
| average_return_rate | REAL | 平均收益率 | |
| max_gain | REAL | 最大盈利 | |
| max_loss | REAL | 最大亏损 | |
| generated_at | TEXT | 汇总生成时间 | |

为什么可选：
- 如果月度统计量不大，可以先不建表，实时聚合。
- 如果后续需要缓存和历史版本管理，再引入更合适。

---

## 8. 接口设计建议

## 8.1 单标的复盘接口

建议新增：
- `POST /api/trade-reviews`
- `GET /api/trade-reviews`
- `GET /api/trade-reviews/{review_id}`
- `PUT /api/trade-reviews/{review_id}`
- `POST /api/trade-reviews/{review_id}/attachments`
- `POST /api/trade-reviews/{review_id}/ai-summary`

## 8.2 月度复盘接口

建议新增：
- `GET /api/trade-reviews/monthly/{month_key}`
- `POST /api/trade-reviews/monthly/{month_key}/ai-summary`

## 8.3 AI 结果查询接口

建议新增：
- `GET /api/trade-review-ai-results/{result_id}`
- `GET /api/trade-reviews/{review_id}/ai-results`

---

## 9. 实施优先级建议

建议按以下顺序推进，而不是一次性做全：

### Phase 1：最小可用版
- 单标的复盘主表 + 操作明细
- 新建 / 编辑页
- 详情页
- 单标的 AI 总结

### Phase 2：月度汇总版
- 月度统计页
- 月度 AI 总结
- 重复错误动作 / 问题场景分析
- 能力短板输出

### Phase 3：增强版
- OCR 原始结果管理
- AI 历史版本管理
- 代表案例跳转联动
- 月度缓存与性能优化

---

## 10. 待人工决策事项

在真正进入编码前，仍需你确认以下问题：

1. **页面入口放哪里**：侧边导航新增独立菜单，还是先放到 `HistoryPage` / `AiResultsPage` 相关入口中。
2. **AI 结果是否独立页面**：是单独做 `TradeReviewAiResultPage`，还是直接嵌入详情页 / 月度页。
3. **数据表是否全部需要**：尤其是 `trade_review_monthly_summary` 是否先跳过。
4. **附件存储方案**：本地路径、SQLite 元数据、还是后续接对象存储。
5. **是否需要支持“未清仓中的交易复盘”**：如果需要，主表状态和收益字段的口径要进一步定义。

---

## 11. 建议的下一步

如果你认可这份设计，建议下一步按 `AGENTS.md` 规则分两步走：

### 第一步：人工确认数据模型方案
- 确认哪些表真正需要
- 确认字段口径
- 由你更新 `docs/human/data-model/AlphaPredator.dbml`

### 第二步：再进入编码设计
- 前端页面路由与导航接入
- 后端 API 与 schema 设计
- AI prompt 构造与结果落库

这样能确保复盘系统扩展不会破坏当前项目已有结构。
