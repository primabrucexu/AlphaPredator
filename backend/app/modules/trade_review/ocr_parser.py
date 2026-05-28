"""
trade_review OCR 解析器

使用 RapidOCR（本地，无需外部 API）识别同花顺交易记录截图，
解析出股票名称、交易日期、成交明细等结构化数据。
"""
from __future__ import annotations

import base64
import io
import re
from typing import Optional

import numpy as np
from PIL import Image
from rapidocr import RapidOCR  # type: ignore

from app.schemas.trade_review import OcrOperationItem, OcrParseResponse

# 操作类型映射：截图中的中文 → 系统类型
_OP_TYPE_MAP = {
    '建仓': 'buy',
    '加仓': 'add',
    '清仓': 'sell',
    '减仓': 'reduce',
    'T买': 't_buy',
    'T卖': 't_sell',
    '买入': 'buy',
    '卖出': 'sell',
}

# 时间戳正则：2026-05-21 09:44:37
_TIME_RE = re.compile(r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}')

# 金额数字正则（允许逗号千位符）
_NUM_RE = re.compile(r'-?[\d,]+(?:\.\d+)?')


def _strip_num(text: str) -> Optional[float]:
    """把 '14,641.39' / '17.95%' 等解析为 float，失败返回 None。"""
    text = text.replace(',', '').replace('%', '').strip()
    try:
        return float(text)
    except ValueError:
        return None


def _ocr_lines(image_bytes: bytes) -> list[str]:
    """调用 RapidOCR 识别图片，返回按 y 坐标排序的文本行列表。"""

    img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    img_array = np.array(img)

    engine = RapidOCR()
    result, _ = engine(img_array)

    if not result:
        return []

    # result 格式: [[box_points, text, score], ...]
    # box_points: [[x0,y0],[x1,y1],[x2,y2],[x3,y3]]
    # 按 y 轴排序
    lines_with_y = []
    for item in result:
        box, text, _ = item[0], item[1], item[2]
        y_center = sum(pt[1] for pt in box) / 4
        lines_with_y.append((y_center, str(text).strip()))

    lines_with_y.sort(key=lambda x: x[0])
    return [t for _, t in lines_with_y if t]


def _parse_lines(lines: list[str]) -> OcrParseResponse:
    """
    从 OCR 文本行中解析同花顺交易记录。

    同��顺页面关键结构（自上而下）：
    - 股票名称（大标题行）
    - 总盈亏日期范围（含「年」「月」「日」）
    - 盈亏金额 + 百分比（红色大数字，通常在同一或相邻行）
    - 持股天数 / 交易税费 / 累计买入 / 累计卖出
    - 交易记录：每笔有"建仓/清仓/加仓/减仓"关键词 + 时间
      - 下面几行：价格 数字 / 金额 数字 / 数量 数字 / 税费/费用 数字
    """
    resp = OcrParseResponse(raw_lines=lines)

    # ----- 1. 股票名称 -----
    # 寻找第一个非纯数字、非时间、不含特殊符号的短文本行作为股票名称
    for line in lines[:10]:
        clean = line.strip()
        if (
            2 <= len(clean) <= 8
            and not re.search(r'[\d%./\-+:,()]', clean)
            and clean not in {'现价', '更多', '看行情', 'BS点', '均线', '日线', '前复权'}
        ):
            resp.stock_name = clean
            break

    # ----- 2. 日期范围 -----
    date_range_re = re.compile(r'(\d{4})年(\d{2})月(\d{2})日.*?(\d{4})年(\d{2})月(\d{2})日')
    for line in lines:
        m = date_range_re.search(line)
        if m:
            resp.start_date = f'{m.group(1)}-{m.group(2)}-{m.group(3)}'
            resp.end_date = f'{m.group(4)}-{m.group(5)}-{m.group(6)}'
            break

    # ----- 3. 总盈亏金额 + 收益率 -----
    pnl_re = re.compile(r'^(-?[\d,]+\.\d{2})$')          # 纯金额行
    rate_re = re.compile(r'^(-?[\d.]+)%$')                # 纯百分比行
    # 也处理 "2,628.33 17.95%" 出现在同一行的情况
    combo_re = re.compile(r'(-?[\d,]+\.\d{2})\s+(-?[\d.]+)%')

    for line in lines:
        m = combo_re.search(line)
        if m:
            resp.realized_pnl = _strip_num(m.group(1))
            resp.return_rate = (_strip_num(m.group(2)) or 0) / 100
            break
        if pnl_re.match(line.strip()) and resp.realized_pnl is None:
            resp.realized_pnl = _strip_num(line.strip())
        if rate_re.match(line.strip()) and resp.return_rate is None:
            val = _strip_num(line.strip())
            if val is not None:
                resp.return_rate = val / 100

    # ----- 4. 累计买入 / 累计卖出 -----
    buy_total_re = re.compile(r'累计买入\s*([\d,]+\.?\d*)')
    sell_total_re = re.compile(r'累计卖出\s*([\d,]+\.?\d*)')
    # 有时候"累计买入"和数字在相邻不同行，用索引配对
    for i, line in enumerate(lines):
        m = buy_total_re.search(line)
        if m:
            resp.total_buy_amount = _strip_num(m.group(1))
        m = sell_total_re.search(line)
        if m:
            resp.total_sell_amount = _strip_num(m.group(1))
        # 相邻行配对
        if line.strip() == '累计买入' and i + 1 < len(lines):
            resp.total_buy_amount = _strip_num(lines[i + 1])
        if line.strip() == '累计卖出' and i + 1 < len(lines):
            resp.total_sell_amount = _strip_num(lines[i + 1])

    # ----- 5. 交易操作明细 -----
    operations: list[OcrOperationItem] = []
    op_indices: list[tuple[int, str]] = []  # (行索引, 操作类型)

    for i, line in enumerate(lines):
        for zh, en in _OP_TYPE_MAP.items():
            if zh in line:
                op_indices.append((i, en))
                break

    for idx, (op_line_idx, op_type) in enumerate(op_indices):
        # 从当前操作行向下最多 8 行提取数字
        window = lines[op_line_idx: op_line_idx + 9]
        window_text = ' '.join(window)

        # 提取时间
        trade_time_str = ''
        t_match = _TIME_RE.search(window_text)
        if t_match:
            trade_time_str = t_match.group().replace(' ', 'T')

        # 提取 价格、金额、数量
        price_val: Optional[float] = None
        amount_val: Optional[float] = None
        quantity_val: Optional[int] = None

        price_re = re.compile(r'价格\s*([\d,]+\.?\d*)')
        amount_re = re.compile(r'金额\s*([\d,]+\.?\d*)')
        qty_re = re.compile(r'数量\s*(-?[\d,]+)')

        m = price_re.search(window_text)
        if m:
            price_val = _strip_num(m.group(1))
        m = amount_re.search(window_text)
        if m:
            amount_val = _strip_num(m.group(1))
        m = qty_re.search(window_text)
        if m:
            raw_qty = _strip_num(m.group(1))
            if raw_qty is not None:
                quantity_val = abs(int(raw_qty))

        # 部分截图"价格"/"金额"不在同行，尝试数字对齐匹配
        if price_val is None or amount_val is None:
            nums = _NUM_RE.findall(window_text.replace(trade_time_str, ''))
            float_nums = []
            for n in nums:
                v = _strip_num(n)
                if v is not None and v > 0:
                    float_nums.append(v)
            # 启发：金额通常最大，价格通常 < 1000，数量是整百
            candidates = sorted(float_nums, reverse=True)
            if len(candidates) >= 2 and amount_val is None:
                amount_val = candidates[0]
            if len(candidates) >= 2 and price_val is None:
                for v in candidates:
                    if v < 1000:
                        price_val = v
                        break

        if trade_time_str and price_val is not None:
            operations.append(
                OcrOperationItem(
                    trade_time=trade_time_str,
                    operation_type=op_type,
                    price=price_val,
                    quantity=quantity_val or 0,
                    amount=amount_val or round(price_val * (quantity_val or 0), 2),
                )
            )

    # 按时间排序
    operations.sort(key=lambda o: o.trade_time)
    resp.operations = operations

    # 判断 status：如果识别到"清仓"操作，则状态为 closed
    sell_types = {'sell', 't_sell'}
    all_types = {o.operation_type for o in operations}
    if sell_types & all_types:
        resp.status = 'closed'
    elif operations:
        resp.status = 'open'

    return resp


def parse_trade_screenshot(image_base64: str) -> OcrParseResponse:
    """
    主入口：接受 base64 图片，返回结构化交易数据。
    调用方无需关心 OCR 细节。
    """
    image_bytes = base64.b64decode(image_base64)
    lines = _ocr_lines(image_bytes)
    return _parse_lines(lines)

