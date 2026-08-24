# AlphaPredator

个人使用的 A 股行情与自选股助手，提供在线行情、日 K 和常用技术指标，以及按标签自动分组的自选股。韭研公社数据展示、登录、查询和同步能力当前暂时停用。

## 本地启动

要求：Python 3.11+、Node.js 20+。

后端：

```powershell
cd backend
python -m pip install -e ".[dev]"
python -m uvicorn app.main:app --reload --workers 1
```

### MCP Server 接入

| 注册项 | 值 |
|---|---|
| 名称 | `AlphaPredator` |
| 传输类型 | Streamable HTTP |
| Server URL | `http://127.0.0.1:8000/api/mcp/` |

### 同花顺账号文件（F004）

AlphaPredator 的正式同花顺登录只允许通过手工编写项目根目录下的 `data/ths_credentials.json` 配置。项目不提供账号密码配置页面或文件写入 API；Web 进程和独立后台 Worker 统一读取这个文件。文件格式为：

```json
{
  "username": "你的同花顺账号",
  "password": "你的同花顺密码"
}
```

保存或修改文件后需要重启后端，使 Web 进程和独立后台 Worker 重新读取配置。文件不存在时保留 thsdk 游客账号行为；文件存在但格式错误时会明确报错。程序不会读取或保存机器网卡 MAC；创建正式账号客户端时只传入账号密码，由 SDK 使用账号派生默认 MAC。SDK 自带的敏感连接日志已在 Provider 边界禁用。该 JSON 文件包含明文密码，仅供本机个人环境使用；`data/` 已被 Git 忽略，不要强制添加或提交该文件。

也可以在 IDE 中直接运行 `app.main`，或执行：

```powershell
python -m app.main
```

前端：

```powershell
cd frontend
npm install
npm run dev
```

打开 http://127.0.0.1:5173 。首次使用请进入“任务”页刷新股票搜索目录，以启用本地拼音搜索。

## 验证

```powershell
cd backend
python -m pytest -q

cd ../frontend
npm run build
```

页面行情与前复权日 K 仍然在线获取；任务页可以把从 2025-01-01 开始的全市场前复权日线保存到 `data/market_data.duckdb`。该 DuckDB 只由独立 Worker 访问，不供 Web 直接查询。K 线拖到已加载范围左端时会继续加载更早数据。MA、EXPMA、MACD、KDJ 和成交量/成交额等图表偏好保存在浏览器 `localStorage`，刷新页面后继续使用。SQLite 保存股票搜索目录、自选股、标签和任务；既有韭研认证、涨停历史和历史任务也继续保留，但当前不展示业务数据，不提供登录、查询或新同步能力。历史韭研任务仍在通用任务记录中作为审计信息保留。自选页的独立标签栏可搜索、新建、排序、重命名和删除标签；个股标签输入支持按名称前缀选择已有标签或直接创建新标签。自选页面按所选标签动态筛选，同一股票可以出现在多个标签分组中，并可在每个标签内独立拖动排序。已保留的韭研 SESSION 仍属于敏感信息，不要提交到仓库。
