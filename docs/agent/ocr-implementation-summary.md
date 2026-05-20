# OCR 功能实现总结

## 概述

已在 `backend/app/modules/market_data/jygs_review.py` 中完整实现了 OCR 识别功能，自动从��研公社复盘图片中识别文字，填充
`daily_hot_info.short_reason` 字段。

---

## 实现方案

### 核心函数

#### 1. `_download_image_data(image_url: str, timeout: float = 10.0) -> bytes | None`

- **功能**：从给定 URL 下载图片到内存
- **返回**：图片二进制数据，或下载失败时返回 None
- **特点**：支持超时控制，失败时日志记录但不抛出异常

#### 2. `_ocr_image_to_text(image_data: bytes) -> str`

- **功能**：对图片字节流运行 OCR 识别
- **库**：使用 RapidOCR（已在项目依赖中）
- **返回**：识别的文本，识别失败返回空字符串
- **处理**：
  - 将字节流转换为 PIL Image
  - 使用 RapidOCR 引擎识别
  - 连接所有识别行的文字
  - 性能日志记录（行数、字符数、耗时）

#### 3. `_process_hot_review_ocr(trade_date: str, sqlite_path: Path | None = None) -> dict[str, Any]`

- **功能**：处理某个交易日的所有复盘图片
- **流程**：
  1. 从 `daily_hot_pic` 表读取该日所有图片 URL
  2. 逐张下载并运�� OCR
  3. 提取的文本截断至 500 字符
  4. 更新所有 `daily_hot_info` 记录的 `short_reason` 字段
  5. **提前返回**：仅处理第一张成功的图片（复盘图片通常包含完整摘要）
- **返回**：处理统计信息 `{trade_date, images_processed, ocr_success}`

#### 4. `fetch_and_parse_jygs_review_for_date(trade_date: str) -> int`（修改）

- **新增行为**：在同步数据后自动调用 `_process_hot_review_ocr`
- **流程**：
  1. 调用 `sync_hot_review_by_date()` 拉取 API 数据
  2. 立即调用 `_process_hot_review_ocr()` 处理图片
  3. 返回股票数量统计

---

## 技术栈

| 组件           | 作用      | 说明                        |
|--------------|---------|---------------------------|
| RapidOCR     | 文字识别    | 已有依赖 `rapidocr>=3.8.1`    |
| PIL (Pillow) | 图片处理    | **新增依赖** `Pillow>=10.0.0` |
| ONNXRuntime  | 推理引擎    | RapidOCR 运行时（已有）          |
| urllib       | HTTP 请求 | 标准库，用于下载图片                |
| io.BytesIO   | 内存流     | 标准库，字节流处理                 |

---

## 执行流程

```
fetch_and_parse_jygs_review_for_date(trade_date='2025-05-19')
    ↓
sync_hot_review_by_date(trade_date='2025-05-19')
    ├── 拉取 JYGS API 数据（diagram-url, field, list）
    ├── 写入 daily_hot_pic（图片 URL）
    └── 写入 daily_hot_info（股票信息，short_reason=''）
    ↓
_process_hot_review_ocr(trade_date='2025-05-19')
    ├── SELECT * FROM daily_hot_pic WHERE trade_date = '2025-05-19'
    ├── FOR EACH image_url:
    │   ├── 下载图片（URL → 字节流）
    │   ├── 运行 RapidOCR 识别
    │   ├── 提取文字，截断至 500 字符
    │   └── UPDATE daily_hot_info SET short_reason = ? (首张图片成功后 BREAK)
    └── 返回处理统计
    ↓
return stock_facts_count
```

---

## 关键设计决策

### 1. 同步执行

- **原因**：整个流程时间可控（通常 < 10 秒），且保证数据一致性
- **权衡**：初始化任务会稍微变慢，但用户体验更好（一次性完成）

### 2. 仅处理首张图片

```python
break  # Only process the first successful image per day
```

- 韭研复盘圖片通常只有 1-2 张，第一张包含完整摘要
- 避免重复识别，节省时间和资源

### 3. 文本截断至 500 字符

- SQLite 字段无硬性限制，但 500 字符对于"短_reason"足够
- OCR 识别可能包含页面杂质或水印文字，截断能去除尾部噪声

### 4. 容错设计

```python
image_data = _download_image_data(image_url)
if not image_data:
  logger.warning('Skipped image %d due to download failure')
  continue  # 跳过，不中断流程
```

- 网络故障、图片链接失效时优雅降级
- 日志记录便于排查

---

## 依赖更新

在 `backend/pyproject.toml` 中添加：

```toml
"Pillow>=10.0.0",
```

**安装方式**：

```bash
pip install -e .
# or
pip install Pillow>=10.0.0
```

---

## 性能预期

| 操作           | 耗时         | 说明           |
|--------------|------------|--------------|
| 下载图片 (1-2MB) | 100-500ms  | 网络延迟         |
| RapidOCR 识别  | 500-2000ms | GPU 加速可显著降低  |
| 数据库更新        | 10-50ms    | 简单 UPDATE 操作 |
| **总计**       | **1-3s**   | 单个交易日的完整处理   |

---

## 日志示例

```
INFO - Fetching JYGS review data for 2025-05-19
INFO - JYGS sync done. trade_date=2025-05-19 images=1 stocks=15
INFO - Starting OCR processing for JYGS images. trade_date=2025-05-19
INFO - OCR processing start. trade_date=2025-05-19
INFO - Processing image 1/1: https://...
DEBUG - Downloading image from https://...
DEBUG - Downloaded image. size=512340 bytes elapsed_ms=234
DEBUG - OCR extracted 8 lines, total 342 chars. elapsed_ms=1245
INFO - Updated short_reason for trade_date=2025-05-19 with OCR result (len=342)
INFO - OCR processing completed. result={'trade_date': '2025-05-19', 'images_processed': 1, 'ocr_success': 1}
```

---

## 之后可能的优化

1. **异步执行**：如果 OCR 耗时过长，可迁移到后台任务
2. **缓存 RapidOCR 引擎**：避免重复初始化（全局单例）
3. **文本清晰化**：后 OCR 处理移除水印、页脚等
4. **评分机制**：根据 confidence score 过滤低质识别结果
5. **GPU 加速**：配置 ONNXRuntime 使用 GPU，加速 > 50%

---

## 测试验证

可运行的测试用例应覆盖：

- ✅ 成功识别（有有效图片）
- ✅ 无图片场景（daily_hot_pic 为空）
- ✅ 网络失败（图片 URL 无效）
- ✅ 识别失败（图片内容无文字）
- ✅ 数据库更新正确性（short_reason 字段填充正确）

