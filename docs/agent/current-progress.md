# 当前执行进度

> **用途**：记录当前活跃需求的进度、下一步和阻塞点。不保留历史需求。
> **维护规则**：每次会话结束时由 agent 更新。

---

## 当前活跃需求

- [F06：MACD 形态预警](F06-macd-alert.md)

---

### 完成情况

- [x] 明确第一版只做日线级别 MACD 形态预警
- [x] 完成 DBML 数据库设计审批
- [x] 用户已更新 `docs/human/data-model/AlphaPredator.dbml`
- [x] 落地 SQLite 表：`macd_alert_result`、`macd_alert_backtest_sample`、`macd_alert_report`
- [x] 实现 MACD(8,17,6) 计算、金叉价、趋势维持价和水下/水上金叉临界识别
- [x] 实现默认主板非 ST 扫描、幂等写入和 T+1 跟踪
- [x] 实现预警内置历史同类形态回测摘要和样本明细保存
- [x] 实现 FastAPI 路由：扫描、跟踪、结果列表、样本列表
- [x] 实现 MCP tools：日报、列表、样本、扫描、跟踪
- [x] 实现前端“MACD 预警”页面和侧边栏入口
- [x] 按 SQLite ORM 新规则迁移 MACD 预警及相关后端 SQLite 访问层
- [x] 将 F06 扫描升级为初始化任务体系后台任务类型 `MACD_ALERT_SCAN`
- [x] 前端 MACD 预警页支持扫描任务进度轮询、当前股票展示和终止任务
- [x] 后端目标测试通过
- [x] 前端 TypeScript 编译通过
- [ ] 前端 Vite 完整构建和 Playwright 冒烟验证

### 下一步

F06 扫描已接入现有 `task_info` 初始化任务系统，不新增数据库表。前端 `tsc -b` 已通过；`npm.cmd run build` 在 Vite/esbuild 启动子进程时被系统 EPERM 拦截，升级权限又被当前环境额度/审批限制拒绝。下一步可在可执行 Vite 子进程的环境中补跑：

```powershell
cd frontend
npm.cmd run build
npm.cmd run check:playwright
```

### 已知问题 / 阻塞 / 待人工决策

- MCP 外部客户端实连验证仍依赖 F05 未完成项；不阻塞 F06 代码实现，但影响最终外部客户端端到端验收。
- 当前环境拒绝 Vite/esbuild 升级运行，前端完整构建和 Playwright 冒烟尚未完成。
