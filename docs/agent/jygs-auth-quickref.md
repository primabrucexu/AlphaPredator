# 🚀 JYGS 认证 JSON 迁移快速参考

## 📋 一句话总结
**韭研公社认证凭据已从 SQLite 数据库迁移到 JSON 文件** (`data/config/jygs_auth.json`)

---

## ⚡ 快速部署

### 3 步完成部署

```bash
# 1️⃣ 更新代码
cd backend && git pull

# 2️⃣ 验证
python -m py_compile app/modules/jygs/auth_file.py

# 3️⃣ 重启
bin/dev-backend.sh
```

---

## 📂 文件位置

| 文件 | 位置 | 说明 |
|------|------|------|
| **认证文件** | `data/config/jygs_auth.json` | 自动创建，首次登录时 |
| **存储模块** | `backend/app/modules/jygs/auth_file.py` | **新增** |
| **认证模块** | `backend/app/modules/jygs/auth.py` | **修改** |
| **复盘模块** | `backend/app/modules/market_data/jygs_review.py` | **修改** |

---

## 🧪 测试验证

```bash
# 运行测试脚本
python tmp/test_jygs_auth_file.py

# 预期输出：All tests passed! ✅
```

---

## 💾 JSON 文件格式

```json
{
  "session": "jYs4aPqXXXXXXXXXXXXXX...",
  "saved_at": "2026-05-19T10:30:45.123456",
  "expires_at": null,
  "is_valid": true,
  "last_checked_at": "2026-05-19T10:35:00",
  "last_error": ""
}
```

**字段说明**：
- `session`: 韭研 SESSION 凭据（核心）
- `saved_at`: 凭据保存时间
- `expires_at`: 过期时间（预留）
- `is_valid`: 上次验证是否有效
- `last_checked_at`: 上次验证时间
- `last_error`: 上次验证错误（若有）

---

## 🔄 工作流程

```
登录 → 保存 session → JSON 文件
          ↓
    初始化任务 → 读取 session → JSON 文件
          ↓
    验证有效性 → 更新状态 → JSON 文件
```

---

## 🎯 API 变化

### 旧 API（SQLite）
```python
from app.repositories.jygs_repo import JygsRepo
repo = JygsRepo()
repo.save_auth_cookie(cookie, now)
```

### 新 API（JSON 文件）
```python
from app.modules.jygs.auth_file import save_credentials_to_file
save_credentials_to_file(session)
```

---

## ✅ 部署检查表

- [ ] 代码已 pull
- [ ] 测试通过（`python tmp/test_jygs_auth_file.py`）
- [ ] 后端已重启
- [ ] 前端可访问
- [ ] 执行一次登录（一键登录 JYGS）
- [ ] 检查 `data/config/jygs_auth.json` 已创建
- [ ] 后端日志包含 "credentials saved to file"
- [ ] 执行初始化任务（JYGS_REVIEW），验证正常

---

## 🔙 回滚方案（不推荐）

```bash
git checkout <previous-commit>
bin/dev-backend.sh
```

---

## 📖 详细文档

- **完整迁移指南**：`docs/agent/jygs-auth-migration.md`
- **完成总结**：`docs/agent/jygs-auth-completion.md`
- **测试脚本**：`tmp/test_jygs_auth_file.py`

---

## 🚨 常见问题

**Q: 旧 SQLite 数据库中的凭据会丢失吗？**
A: 不会。旧数据仍在数据库中，可手动迁移到 JSON。详见迁移指南。

**Q: 是否需要修改前端？**
A: 不需要。API 返回值和逻辑都保持不变。

**Q: JSON 文件存储安全吗？**
A: 是的。建议配置文件权限 `chmod 600` 和 Git ignore。

**Q: 可以回滚吗？**
A: 可以，但不推荐。新方案更清晰、便于管理。

---

## 📊 改进对比

| 方面 | 修改前 | 修改后 |
|------|--------|--------|
| 存储 | SQLite | JSON 文件 |
| 位置 | 混入数据库 | 独立配置 |
| 查看 | 需要 SQL | 文本编辑器 |
| 备份 | 备份整库 | 复制单文件 |
| 版本控制 | 二进制 | 可 Git 管理 |

---

**状态：✅ 已完成，生产就绪**


