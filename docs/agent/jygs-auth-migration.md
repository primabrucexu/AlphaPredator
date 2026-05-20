# 韭研公社认证迁移方案：SQLite → JSON 文件

## 概述

已将韭研公社（JYGS）的认证凭据存储方式从 **SQLite 数据库** 迁移到 **JSON 文件**（`data/config/jygs_auth.json`）。

---

## 🔄 迁移内容

### 存储位置变更

| 项目 | 原方案 | 新方案 |
|------|--------|--------|
| **Session ��据** | `SQLite: jygs_auth.auth_cookie` | **JSON: `data/config/jygs_auth.json`** |
| **验证状态** | `SQLite: jygs_auth.{is_valid, last_error, last_checked_at}` | **JSON: 同上文件** |
| **更新时间** | `SQLite: jygs_auth.{updated_at, last_checked_at}` | **JSON: 同上文件** |

### JSON 文件格式

```json
{
  "session": "jYs4aPqXXXXXXXXXXXXXX...",
  "saved_at": "2026-05-19T10:30:45.123456+00:00",
  "expires_at": null,
  "is_valid": true,
  "last_checked_at": "2026-05-19T10:35:00.654321+00:00",
  "last_error": ""
}
```

---

## 📁 新增/修改文件

### 新增文件
- ✅ `backend/app/modules/jygs/auth_file.py` - JSON 文件存储模块

### 修改文件
- ✅ `backend/app/modules/jygs/auth.py` - 修改从 SQLite 读写改为 JSON
- ✅ `backend/app/modules/market_data/jygs_review.py` - 移除 JygsRepo 调用，使用 JSON 存储

---

## 🔧 实现细节

### `auth_file.py` 模块

**三个核心函数**：

```python
# 读取认证信息
load_credentials_from_file() -> dict | None

# 保存 session
save_credentials_to_file(session: str, expires_at: str | None = None) -> None

# 更新验证状态
update_auth_check_status(is_valid: bool, last_error: str = '') -> None

# 清除认证文件
clear_credentials_from_file() -> None
```

**特点**：
- 自动创建 `data/config` 目录（如果不存在）
- 更新 session 时保留验证状态不变
- 更新验证状态时保留 session 等信息不变
- 完整的異常处理和日志记录

### `auth.py` 函数（已更新）

```python
load_credentials()      # 从 JSON 读取凭据
save_credentials()      # 保存到 JSON
clear_credentials()     # 清除 JSON 文件
get_session()          # 获取 SESSION（不变）
check_credentials_valid()  # 验证凭据（改用 auth_file）
```

### `jygs_review.py`（已更新）

```python
get_jygs_auth_status()        # 从 JSON 读取状态
save_jygs_auth_cookie()       # 保存到 JSON
check_jygs_auth_available()   # 验证并更新 JSON
```

---

## 🚀 部署说明

### 迁移步骤

#### 1. 备份现有数据（可选）
```sql
-- 如需保留旧认证，执行此 SQL 查询
SELECT auth_cookie, updated_at, is_valid, last_error FROM jygs_auth WHERE id = 1;
```

#### 2. 更新代码
```bash
cd backend
git pull  # 获取最新代码
```

#### 3. 重启后端
```bash
# 停止旧进程
# 启动新后端
bin/dev-backend.sh
```

#### 4. 手动迁移旧认证（如需恢复）

如果想把旧数据库中的 session 复制到新 JSON 文件：

```bash
# 从数据库读取 session
sqlite3 data/alphapredator.db "SELECT auth_cookie FROM jygs_auth WHERE id = 1;"

# 假设返回 "SESSION=abc123xyz..."
# 则创建 data/config/jygs_auth.json：

cat > data/config/jygs_auth.json << 'EOF'
{
  "session": "abc123xyz...",
  "saved_at": "2026-05-19T10:00:00",
  "expires_at": null,
  "is_valid": false,
  "last_checked_at": null,
  "last_error": ""
}
EOF
```

#### 5. 验证迁移成功
- 前端 → 数据初始化 → 检查认证状态
- 查看 `data/config/jygs_auth.json` 文件是否存在
- 查看后端日志是否有 "JYGS credentials loaded from file" 日志

---

## ✅ 优点

| 优点 | 说明 |
|------|------|
| **配置管理** | Session 作为配置文件，便���备份、版本控制 |
| **隔离性** | 认证与业务数据库完全隔离 |
| **可读性** | JSON 格式人类可读，易于故障排查 |
| **灵活性** | 无需依赖数据库即可读写认证 |
| **安全性** | 可在 Git 中 ignore 该文件，防止泄密 |

---

## ⚠️ 注意事项

### 1. 文件权限
```bash
# 建议设置认证文件权限为 600（仅所有者可读写）
chmod 600 data/config/jygs_auth.json
```

### 2. Git 忽略
建议在 `.gitignore` 中添加：
```
data/config/jygs_auth.json
```

### 3. 数据库中有残留数据
旧的 `jygs_auth` 表仍存在于数据库中，但不再被使用。可选：
```sql
-- 清空旧表（谨慎操作）
DELETE FROM jygs_auth;
```

### 4. 日志地址变更
- **修前**："Loaded from local SQLite jygs_auth table"
- **修后**："Loaded from data/config/jygs_auth.json"

---

## 🧪 测试验证

### 测试场景 1：首次登录

```
前端 → 一键登录 → 浏览器授权 → 
  ↓
jygs_review.py:auto_login_jygs_with_browser() →
  ↓
save_jygs_auth_cookie() → auth_file.save_credentials_to_file() →
  ↓
创建 data/config/jygs_auth.json ✅
```

### 测试场景 2：验证认证

```
前端 → 检查 JYGS 认证���态 →
  ↓
check_jygs_auth_available() → auth_file.update_auth_check_status() →
  ↓
修改 data/config/jygs_auth.json（更新 is_valid 等） ✅
```

### 测试场景 3：初始化任务

```
前端 → 韭研公社热点复盘 (JYGS_REVIEW) →
  ↓
fetch_and_parse_jygs_review_for_date() → _read_cookie() →
  ↓
get_session() → load_credentials_from_file() →
  ↓
读取 data/config/jygs_auth.json ✅
```

---

## 📊 日志输出示例

### 首次保存认证
```log
INFO - JYGS credentials saved to file: /path/to/data/config/jygs_auth.json (session_len=40)
```

### 读取认证
```log
INFO - JYGS credentials loaded from file. session_len=40
```

### 更新验证状态
```log
INFO - JYGS auth check status updated: is_valid=True
```

---

## 🔄 回滚方案

如需回滚到SQLite存储（**不推荐**）：

```bash
git checkout <previous-commit>  # 切换回原始版本
bin/dev-backend.sh            # 重启后端
```

---

## 📝 总结

✅ **认证凭据完全迁移到 JSON 文件**
- 位置：`data/config/jygs_auth.json`
- 格式：标准 JSON，包含凭据和验证状态
- 自动化：目录和文件优雅自动创建
- 向后兼容：旧数据可手动迁移

---

**已验证部分**：
- ✅ 文件创建和读写
- ✅ 目录自动创建
- ✅ 错误处理
- ✅ 日志记录
- ✅ 代码语法检查


