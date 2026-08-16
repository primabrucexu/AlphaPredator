# AlphaPredator

个人使用的 A 股行情与自选股助手。第一版提供在线行情、日 K 和常用技术指标、自选分组、个股标签，以及韭研公社涨停历史。

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

打开 http://127.0.0.1:5173 。首次使用请进入“数据设置”，刷新股票目录以启用本地拼音搜索。

## 验证

```powershell
cd backend
python -m pytest -q

cd ../frontend
npm run build
```

行情与日 K 在线获取，不写入 SQLite。SQLite 只保存股票搜索目录、自选分组、标签、韭研认证和涨停历史。韭研 SESSION 是敏感信息，仅供本机个人环境使用，不要提交到仓库。
