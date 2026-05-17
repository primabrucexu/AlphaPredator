# AlphaPredator

面向个人使用的 **A 股智能选股工作台**。主要功能如下
- 和常规炒股软件一样具备个股行情查看、搜索等基础功能
- [TODO] 短线情绪总览
- [TODO] 支持AI学习用户选股模式。你可以给AI提供你的选股数据和简单描述。让AI复刻你的成功
- [TODO] 支持AI根据某些描述，生成可执行的选股技能。并且还支持多个模型对同一份描述交叉评判 

---

## Guide
- [技术栈](#技术栈)
- [项目结构](#项目结构)
- [数据存储说明](docs/human/data-model/data-storage.md)
- [文档索引](docs/guide.md)

---

## 市场数据来源

麦蕊智数

---

## 技术栈
python + react + sqlite + duckdb

---

## 项目结构

```
AlphaPredator/
├── agent.md                        # AI/编码 agent 协作约束与工作指南
├── README.md
│
├── bin/                            # 常用脚本
│   ├── bootstrap-backend.sh        # 后端虚拟环境初始化
│   ├── dev-backend.sh              # 启动后端开发服务
│   ├── dev-frontend.sh             # 启动前端开发服务
│   ├── import-market-data.sh       # 导入市场行情数据批次
│   ├── import-hot-sector-images.sh # 导入热点复盘图片
│   └── prepare-phase1-market-data.sh
│
├── conf/                           # 配置模板
│   ├── app.toml.example
│   └── models.toml.example
│
├── data/                           # 运行时数据（不入库）
│
├── docs/
│   ├── docs.md                     # 文档导航索引
│   ├── phase.md                    # 阶段目标清单（Phase 1~4）
│   ├── human/                      # 人工维护的规则文档（agent 禁止修改）
│   │   ├── data-storage.md         # 数据存储设计规范
│   │   └── price-limit-rule.md     # A 股涨跌停计算规则
│   └── agent/                      # agent 产出的工作文档
│       └── README.md               # agent 文档目录使用说明
│
├── backend/                        # Python 后端（FastAPI）
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py                 # 服务启动入口
│   │   ├── api/
│   │   │   ├── router.py           # 路由聚合
│   │   │   └── routes/
│   │   │       ├── health.py       # 健康检查
│   │   │       ├── market.py       # 行情查询 API
│   │   │       └── data_init.py    # 数据初始化 API
│   │   ├── core/
│   │   │   └── settings.py         # 配置项
│   │   ├── db/
│   │   │   ├── sqlite.py           # SQLite 连接与 schema
│   │   │   └── duckdb_storage.py   # DuckDB 连接与 schema
│   │   ├── modules/
│   │   │   └── market_data/
│   │   │       ├── data_source.py      # 行情数据源
│   │   │       ├── initializer.py      # 数据初始化任务
│   │   │       ├── updater.py          # 每日增量更新
│   │   │       ├── importer.py         # 批次导入
│   │   │       ├── hot_sector_importer.py  # 热点图片导入
│   │   │       ├── limit_rules.py      # 涨跌停规则计算
│   │   │       └── service.py          # 行情查询服务
│   │   └── schemas/
│   │       ├── market.py           # 行情相关 Schema
│   │       └── data_init.py        # 数据初始化相关 Schema
│   └── tests/                      # 后端测试
│
└── frontend/                       # React 前端（Vite + TypeScript）
    ├── package.json
    └── src/
        ├── main.tsx                # 前端启动入口
        ├── App.tsx                 # 根组件
        ├── styles.css
        ├── routes/
        │   └── router.tsx          # 路由配置
        ├── pages/                  # 页面组件
        │   ├── HomeSearchPage.tsx      # 首页搜索
        │   ├── StockDetailPage.tsx     # 个股详情
        │   ├── MarketOverviewPage.tsx  # 市场总览
        │   ├── InitializePage.tsx      # 数据初始化
        │   ├── AiResultsPage.tsx       # AI 选股结果
        │   ├── FocusPage.tsx           # 自选股
        │   └── HistoryPage.tsx         # 历史记录
        ├── components/
        │   └── layout/
        │       └── AppShell.tsx    # 全局布局
        └── lib/
            └── api.ts              # 后端 API 封装
```

---

