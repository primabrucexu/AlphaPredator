from __future__ import annotations

from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .sr001_report import OpportunitySection, ReportStock, SR001ScreeningReport


PDF_FONT_NAME = "AlphaPredatorChinese"
FONT_CANDIDATES = (
    Path("C:/Windows/Fonts/msyh.ttc"),
    Path("C:/Windows/Fonts/msyh.ttf"),
    Path("C:/Windows/Fonts/simsun.ttc"),
)
MACD_LABELS = {
    "h_s_minus_4": "T-4",
    "h_s_minus_3": "T-3",
    "h_s_minus_2": "T-2",
    "h_s_minus_1": "T-1",
    "h_s": "T",
}
RANKING_LABELS = {
    "win_rate": "历史胜率前 10",
    "average_return": "平均收益前 10",
    "maximum_return": "最大收益前 10",
}


class SR001ReportPdfError(ValueError):
    pass


def register_chinese_font() -> str:
    if PDF_FONT_NAME in pdfmetrics.getRegisteredFontNames():
        return PDF_FONT_NAME
    for path in FONT_CANDIDATES:
        if not path.is_file():
            continue
        try:
            pdfmetrics.registerFont(TTFont(PDF_FONT_NAME, path, subfontIndex=0))
            return PDF_FONT_NAME
        except Exception:
            continue
    raise SR001ReportPdfError("未找到可用的微软雅黑或宋体，无法生成中文 PDF")


def _percent(value: str | None) -> str:
    if value is None:
        return "-"
    try:
        return f"{Decimal(value) * 100:.2f}%"
    except (InvalidOperation, ValueError) as exc:
        raise SR001ReportPdfError(f"收益统计值无效：{value}") from exc


def _decimal3(value: object) -> str:
    if value is None:
        return "—"
    try:
        return f"{Decimal(str(value)):.3f}"
    except (InvalidOperation, ValueError) as exc:
        raise SR001ReportPdfError(f"MACD 信号值无效：{value}") from exc


def _macd_lines(stock: ReportStock) -> list[str]:
    return [
        f"{label}: {_decimal3(stock.macd_signal_window.get(key))}"
        for key, label in MACD_LABELS.items()
    ]


def _paragraph(text: object, style: ParagraphStyle) -> Paragraph:
    escaped = (
        str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    return Paragraph(escaped, style)


def _multiline(lines: list[str], style: ParagraphStyle) -> Paragraph:
    escaped = [
        line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        for line in lines
    ]
    return Paragraph("<br/>".join(escaped), style)


def _table(data, widths, font_name: str, *, header_rows: int = 1) -> Table:
    table = Table(data, colWidths=widths, repeatRows=header_rows, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("FONTSIZE", (0, 0), (-1, -1), 6.5),
        ("BACKGROUND", (0, 0), (-1, header_rows - 1), colors.HexColor("#E8EEF7")),
        ("TEXTCOLOR", (0, 0), (-1, header_rows - 1), colors.HexColor("#1F3556")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B8C2D1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("ROWBACKGROUNDS", (0, header_rows), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
    ]))
    return table


def _stock_rows(stocks: list[ReportStock], body: ParagraphStyle) -> list[list[object]]:
    rows: list[list[object]] = [[
        "排名", "股票", "T日", "MACD信号窗口", "历史交易", "历史收益",
    ]]
    for stock in stocks:
        rows.append([
            str(stock.rank or "—"),
            _multiline([stock.code, stock.name], body),
            stock.signal_date or "-",
            _multiline(_macd_lines(stock), body),
            _multiline([
                f"完成: {stock.completed_trades}",
                f"盈/亏/平: {stock.winning_trades}/{stock.losing_trades}/{stock.flat_trades}",
            ], body),
            _multiline([
                f"胜率: {_percent(stock.win_rate)}",
                f"平均: {_percent(stock.average_return)}",
                f"最大: {_percent(stock.maximum_return)}",
                f"最小: {_percent(stock.minimum_return)}",
            ], body),
        ])
    return rows


def _insufficient_rows(section: OpportunitySection, body: ParagraphStyle) -> list[list[object]]:
    rows: list[list[object]] = [[
        "股票", "T日", "历史区间", "历史交易", "已有统计",
    ]]
    for stock in section.insufficient_history.items:
        rows.append([
            _multiline([stock.code, stock.name], body),
            stock.signal_date or "-",
            f"{stock.data_start_date or '-'} ~ {stock.data_end_date or '-'}",
            _multiline([
                f"完成: {stock.completed_trades}",
                f"盈/亏/平: {stock.winning_trades}/{stock.losing_trades}/{stock.flat_trades}",
            ], body),
            _multiline([
                f"胜率: {_percent(stock.win_rate)}",
                f"平均: {_percent(stock.average_return)}",
            ], body),
        ])
    return rows


def render_sr001_screening_report_pdf(report: SR001ScreeningReport) -> bytes:
    font_name = register_chinese_font()
    output = BytesIO()
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "ReportTitle", parent=styles["Title"], fontName=font_name,
        fontSize=18, leading=24, textColor=colors.HexColor("#17365D"),
        alignment=TA_CENTER, spaceAfter=8,
    )
    heading = ParagraphStyle(
        "ReportHeading", parent=styles["Heading2"], fontName=font_name,
        fontSize=12, leading=16, textColor=colors.HexColor("#17365D"),
        spaceBefore=8, spaceAfter=5,
    )
    subheading = ParagraphStyle(
        "ReportSubheading", parent=styles["Heading3"], fontName=font_name,
        fontSize=9, leading=12, textColor=colors.HexColor("#284B73"),
        spaceBefore=6, spaceAfter=4,
    )
    body = ParagraphStyle(
        "ReportBody", parent=styles["BodyText"], fontName=font_name,
        fontSize=7.5, leading=10, textColor=colors.HexColor("#263238"),
    )
    small = ParagraphStyle(
        "ReportSmall", parent=body, fontSize=7, leading=9,
        textColor=colors.HexColor("#52606D"),
    )

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont(font_name, 7)
        canvas.setFillColor(colors.HexColor("#667085"))
        canvas.drawCentredString(A4[0] / 2, 8 * mm, f"第 {document.page} 页")
        canvas.restoreState()

    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=11 * mm,
        bottomMargin=14 * mm,
        title=f"SR001 revision {report.rule_revision} 规则执行报告",
        author="AlphaPredator",
    )
    story: list[object] = [
        _paragraph("SR001 规则执行报告", title),
        _paragraph("1. 报告基本信息", heading),
        _table([
            ["来源任务", report.task_uuid, "规则版本", f"{report.rule_id} revision {report.rule_revision}"],
            ["扫描日期", report.as_of_date, "扫描范围", "全市场" if report.scope.type == "all_market" else f"指定股票 {report.scope.symbol_count} 只"],
            ["任务状态", report.task_status, "榜单上限", f"每项 {report.report_limit} 只"],
        ], [27 * mm, 63 * mm, 27 * mm, 63 * mm], font_name),
        Spacer(1, 5 * mm),
    ]
    summary_data = report.rule_summary.summary_data
    story.extend([
        _paragraph("2. 规则口径摘要", heading),
        _paragraph(f"用途：{summary_data.purpose}", body),
        _paragraph(f"适用范围：{summary_data.applicable_scope}", body),
    ])
    story.append(KeepTogether([
        _paragraph("D/T/B 定义", subheading),
        *[
            _paragraph(f"• {term}：{definition}", body)
            for term, definition in summary_data.term_definitions.items()
        ],
    ]))
    story.append(_paragraph("入选逻辑", subheading))
    for item in summary_data.selection_logic:
        story.append(_paragraph(f"• {item}", body))
    story.append(_paragraph("历史交易模拟", subheading))
    trade = summary_data.trade_simulation_summary
    for label, text in (
        ("买入", trade.entry), ("止盈", trade.take_profit),
        ("退出", trade.exit), ("止损", trade.stop_loss),
    ):
        story.append(_paragraph(f"• {label}：{text}", body))
    story.extend([
        _paragraph("历史数据与解释边界", subheading),
        _paragraph(f"• {summary_data.insufficient_history_definition}", body),
    ])
    for item in summary_data.interpretation_limits:
        story.append(_paragraph(f"• {item}", body))

    summary = report.execution_summary
    story.extend([
        _paragraph("3. 执行摘要", heading),
        _table([
            ["扫描", "全部命中", "T点", "B点", "其他过滤", "跳过", "失败"],
            [summary.scanned_stocks, summary.matched_stocks, summary.pending_entry_stocks,
             summary.bought_today_stocks, summary.filtered_other_states,
             summary.skipped_stocks, summary.failed_stocks],
        ], [25.7 * mm] * 7, font_name),
        _paragraph("4. 命中情况", heading),
    ])

    for state in ("pending_entry", "bought_today"):
        section = report.opportunities[state]
        story.extend([
            _paragraph(section.label, subheading),
            _paragraph(
                f"共 {section.total} 只；历史数据完整候选 {section.ranked_candidates} 只。"
                "以下三个榜单独立排序，同一股票可以跨榜重复。",
                body,
            ),
        ])
        for field, label in RANKING_LABELS.items():
            stocks = getattr(section.leaderboards, field)
            if stocks:
                story.extend([
                    PageBreak(),
                    _paragraph(label, subheading),
                    _table(
                        _stock_rows(stocks, small),
                        [10 * mm, 29 * mm, 21 * mm, 30 * mm, 38 * mm, 52 * mm],
                        font_name,
                    ),
                ])
            else:
                story.append(KeepTogether([
                    _paragraph(label, subheading),
                    _paragraph("无符合项。", body),
                ]))
        insufficient = section.insufficient_history
        if insufficient.items:
            story.append(KeepTogether([
                _paragraph("历史数据不足", subheading),
                _paragraph(
                    f"共 {insufficient.total} 只，展示 {insufficient.returned} 只，"
                    f"截断：{'是' if insufficient.truncated else '否'}。这些股票不参与榜单。",
                    small,
                ),
                _table(
                    _insufficient_rows(section, small),
                    [32 * mm, 23 * mm, 43 * mm, 39 * mm, 43 * mm],
                    font_name,
                ),
            ]))
        else:
            story.append(KeepTogether([
                _paragraph("历史数据不足", subheading),
                _paragraph("无历史数据不足股票。", body),
            ]))

    story.append(Spacer(1, 4 * mm))
    story.append(KeepTogether([
        _paragraph("5. 声明", heading),
        *[_paragraph(f"• {item}", body) for item in report.disclaimers],
    ]))

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()


__all__ = [
    "SR001ReportPdfError",
    "register_chinese_font",
    "render_sr001_screening_report_pdf",
]
