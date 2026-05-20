# stock_code 数据类型修复公告

## 问题描述

### 原始问题

在 `daily_hot_info` 表中，`stock_code` 字段被错误地定义为 `INTEGER` 类型，导致以下问题：

- 股票代码 `"000711"` 存储为整数 `711`，**丢失前导零**
- 查询或展示时变成 `"711"`，与实际代码不符
- 无法正确关联到其他表中的股票代码（text 类型）

### 根本原因

1. **数据库 schema** (`schema.sql`)：第 111 行定义 `stock_code INTEGER`
2. **代码** (`jygs_review.py`)：第 232、244、317 行使用 `int(code)` 进行类型转换

## 修复内容

### 1. Schema 变更

```sql
-- 修前
stock_code
INTEGER NOT NULL,

-- 修后
stock_code    TEXT    NOT NULL,
```

**文件**：`backend/app/db/schema.sql` 第 111 行

### 2. 代码变更

```python
# 修前 (第 232、244 行)
int(code),
int(code),

# 修后
code,
code,

# 修前 (第 317 行)
int(code) if code.isdigit() else 0,

# 修后
code,
```

**文件**：`backend/app/modules/market_data/jygs_review.py`

## 影响范围

| 表              | 字段         | 类型             | 影响           |
|----------------|------------|----------------|--------------|
| daily_hot_info | stock_code | INTEGER → TEXT | 历史数据错误，新数据正确 |

## 需要的行动

### 立即行动

1. **清理历史数据**（如果已初始化过）
   ```bash
   # 删除错误的数据（仅限 daily_hot_info 表）
   sqlite3 data/alphapredator.db "DELETE FROM daily_hot_info;"
   sqlite3 data/alphapredator.db "DELETE FROM daily_hot_pic;"
   ```

2. **重新初始化**
    - 在前端"数据初始化"页面触发 `JYGS_REVIEW` 任务
    - 选择所需的交易日期范围
    - 等待完成

### 验��修复

运行 SQL 查询验证 `stock_code` 格式：

```sql
-- 验证：应该看到 6 位数字（带前导零）
SELECT DISTINCT stock_code
FROM daily_hot_info
WHERE LENGTH(stock_code) = 6 LIMIT 10;

-- 示例输出：
-- 000001
-- 000002
-- 000711
-- 300124
```

## 相关联查询示例

修复后，可以正确进行跨表关联：

```sql
-- 关联到 stock_profiles
SELECT dh.trade_date,
       dh.stock_code,
       dh.name,
       sp.sectors_json
FROM daily_hot_info dh
         LEFT JOIN stock_profiles sp ON dh.stock_code = sp.stock_code
WHERE dh.trade_date = '2026-05-19' LIMIT 5;
```

## 时间线

| 时间         | 事项            |
|------------|---------------|
| 2026-05-19 | 发现问题并修复       |
| 立即         | 清理历史错误数据      |
| 立即         | 重新初始化 JYGS 数据 |

## 代码版本

- 修复文件：
    - `backend/app/db/schema.sql`
    - `backend/app/modules/market_data/jygs_review.py`
- 状态：✅ 已部署

## QA

**Q：为什么会这样设计？**
A：这是早期开发中的错误，当时没有充分考虑股票代码中含有前导零的属性。

**Q：旧数据还能用吗？**
A：不能。建议全部删除，重新初始化。

**Q：会影响 API 响应吗？**
A：不会。API schemas 中 `stock_code` 一直定义为 `str`，只是数据库存储格式错误。

**Q：需要更新前端吗？**
A：不需要。修复是数据库侧，API 契约不变。

---

## 快速修复流程

```bash
# 1. 确保后端代码已更新
cd backend
git pull

# 2. 清理历史错误数据
rm data/alphapredator.db  # 覆盖整个数据库最简单

# 3. 重启后端（会自动重建 schema）
bin/dev-backend.sh

# 4. 在前端触发重新初始化
# 前端 → 数据初始化 → 韭研公社热点复盘

# 5. 验证（几分钟后）
sqlite3 data/alphapredator.db "SELECT COUNT(*) FROM daily_hot_info;"
```

---

## 相关 Issues

- 症状：000711 变成 711
- 原因：INTEGER vs TEXT
- 修复：使用 TEXT 存储 6 位数字字符串，保留前导零

