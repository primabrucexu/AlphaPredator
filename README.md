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
