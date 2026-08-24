# AlphaPredator

个人使用的 A 股行情与自选股助手。第一版提供在线行情、日 K 和常用技术指标、按标签自动分组的自选股，以及韭研公社涨停历史。

## 本地启动

要求：Python 3.11+、Node.js 20+。

后端：

```powershell
cd backend
python -m pip install -e ".[dev]"
$env:THS_USERNAME="你的同花顺账号" # 可选；未设置时 thsdk 使用临时游客账号
$env:THS_PASSWORD="你的同花顺密码"
$env:THS_MAC="你的MAC地址"
python -m uvicorn app.main:app --reload --workers 1
```

### 同花顺账号文件（F004）

> F004 已完成设计但尚未实现；以下文件读取行为将在该功能实现后生效。当前版本仍使用上面的环境变量配置正式账号。

F004 实现后，AlphaPredator 的正式同花顺登录只允许通过手工编写项目根目录下的 `data/ths_credentials.json` 配置。项目不提供账号密码配置页面或文件写入 API；Web 进程和独立后台 Worker 统一读取这个文件。文件格式保持为：

```json
{
  "username": "你的同花顺账号",
  "password": "你的同花顺密码"
}
```

保存或修改文件后需要重启后端，使 Web 进程和独立后台 Worker 重新读取配置。程序不会读取或保存机器网卡 MAC；创建 thsdk 客户端时只传入账号密码，由 SDK 使用账号派生默认 MAC。该 JSON 文件包含明文密码，仅供本机个人环境使用；`data/` 已被 Git 忽略，不要强制添加或提交该文件。

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

打开 http://127.0.0.1:5173 。首次使用请进入“数据设置”，刷新股票目录以启用本地拼音搜索；点击“登录韭研公社”会弹出本机 Edge 或 Chrome，登录完成后自动保存 SESSION。涨停历史同步不限制日期跨度，并按所选范围逐日拉取，请在大范围同步期间保持应用运行。

## 验证

```powershell
cd backend
python -m pytest -q

cd ../frontend
npm run build
```

行情与前复权日 K 在线获取，不写入 SQLite；K 线拖到已加载范围左端时会继续加载更早数据。MA、EXPMA、MACD、KDJ 和成交量/成交额等图表偏好保存在浏览器 `localStorage`，刷新页面后继续使用。SQLite 只保存股票搜索目录、自选股、标签、韭研认证和涨停历史。自选页的独立标签栏可搜索、新建、排序、重命名和删除标签；个股标签输入支持按名称前缀选择已有标签或直接创建新标签。自选页面按所选标签动态筛选，同一股票可以出现在多个标签分组中，并可在每个标签内独立拖动排序。韭研 SESSION 是敏感信息，仅供本机个人环境使用，不要提交到仓库。
