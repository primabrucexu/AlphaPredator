# 韭研公社接入说明

## 1. 文档定位与风险

AlphaPredator 使用韭研公社网页端接口获取涨停复盘数据。该接口不是面向本项目发布的稳定开放 API，路径、鉴权算法和响应字段都可能变化。接口失效时必须返回明确错误，不能用伪造数据代替。

- 历史 OpenAPI：`docs/integrations/jygs-api.yaml`
- 当前客户端：`backend/app/jygs/client.py`
- 登录与 SESSION 捕获：`backend/app/jygs/playwright_login.py`
- 当前项目接口：`backend/app/jygs/routes.py`
- 历史文档来源：`master:docs/human/api-docs/jygs-api.yml`

## 2. 登录和请求鉴权

韭研认证包含两个不同阶段，不能把它们合并理解为一次固定 token 登录。

### 2.1 登录阶段：取得 SESSION

1. AlphaPredator 打开本机 Edge 或 Chrome 登录韭研公社网页。
2. 用户在网页中完成登录。
3. Playwright 从 `jiuyangongshe.com` 域下捕获名为 `SESSION` 的 Cookie。
4. 当前项目将 SESSION 保存在本地 SQLite 的 `jygs_credentials` 表中。

SESSION 是敏感凭据，不得写入文档、日志或 Git。

### 2.2 API 请求阶段：动态计算 timestamp 和 token

每次调用韭研 API 前都要重新生成一组配套的 `timestamp` 和 `token`：

```text
timestamp = 当前 Unix 时间戳，单位为毫秒，转换为十进制字符串
raw       = "Uu0KfOB8iUP69d3c:" + timestamp
token     = MD5(UTF-8(raw))，输出 32 位小写十六进制字符串
```

请求至少携带：

```text
Cookie: SESSION=<登录得到的 SESSION>
platform: 3
timestamp: <本次请求的毫秒时间戳>
token: <使用同一个 timestamp 计算出的 MD5>
```

关键点：

- `token` 不是登录后保存的固定值，而是每次 API 请求动态生成。
- `token` 和请求头里的 `timestamp` 必须使用完全相同的毫秒时间戳。
- SESSION 用来表示登录身份，`timestamp/token` 用来满足网页端请求签名校验，两者缺一不可。
- 本机时间明显不准确时，服务端可能拒绝带时间戳的请求。
- 这里使用 MD5 是为了兼容网页端协议，不代表它适合用于项目自身的密码存储。
- 历史实现将 `errCode=9` 解释为 token 无效；这属于历史观察，仍需以实际响应为准。

当前公式同时存在于当前 `build_headers()` 和历史提交 `0339331` 的 `make_jygs_token()` 测试中。历史固定样例为：

```text
timestamp = 1781185719708
token     = 661abae951887c634a4f51b0f333bec1
```

该样例只用于验证算法，实际请求不能复用这个过期时间戳。

## 3. 上游接口状态

| 上游接口 | 用途 | 当前项目状态 |
|---|---|---|
| `POST /api/v1/action/diagram-url` | 获取每日涨停简图；当前也作为 SESSION 探针 | 已使用 |
| `POST /api/v1/action/field` | 获取某日按题材分类的全量涨停股票解析 | 已使用 |
| `POST /api/v1/action/list` | 历史上用于某字段下的分页列表 | 已停用；不应作为当前可靠能力 |

`action/field` 的主要结构为题材数组，每个题材包含 `name`、`date`、`count` 和股票 `list`。股票数据中当前关注：

- `code`、`name`
- `article.action_info.time`：涨停时间
- `article.action_info.num`：连板描述
- `article.action_info.expound`：涨停原因

当前解析会去除股票代码中的市场字符并保留最后六位；同一股票出现在多个题材时合并题材名称。

## 4. AlphaPredator 对外接口

以下是本项目自己的 FastAPI 路由，不是韭研上游路径：

| 项目接口 | 作用 |
|---|---|
| `POST /api/jygs/login` | 弹出浏览器登录、捕获 SESSION 并立即校验 |
| `PUT /api/jygs/session` | 手动保存 SESSION |
| `POST /api/jygs/check` | 使用探针检查 SESSION |
| `GET /api/jygs/status` | 查询本地配置及最近校验状态 |
| `GET /api/stocks/{symbol}/limit-up-history` | 查询本地已同步的个股涨停历史 |

数据同步已接入后台任务框架，具体任务范围和状态以对应 Feature 文档及当前代码为准。

## 5. 验证与维护

修改鉴权或响应解析时应至少验证：

1. 固定时间戳能生成预期 token。
2. `timestamp` 与 token 使用同一原始值。
3. SESSION 不带重复的 `SESSION=` 前缀。
4. `errCode="0"` 才视为成功，HTTP 错误和业务错误均转换为明确异常。
5. 文档和 `backend/app/jygs/client.py` 的接口路径、签名算法及字段保持一致。

真实服务验证依赖用户 SESSION。没有完成实时调用时，只能声明结构来自历史文档或代码测试，不能声明当前上游仍然可用。
