from __future__ import annotations

import html
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    XPreformatted,
)


TASK_DIR = Path(__file__).resolve().parents[1]
OUTPUT = TASK_DIR / "output" / "pdf" / "TASK_0002_MC时间区间突破_v1_回测报告.pdf"
CODE_FILE = TASK_DIR / "MultiCharts" / "v1.txt"
REF_DIR = TASK_DIR / "参考"

NAVY = colors.HexColor("#17324D")
TEAL = colors.HexColor("#0E7490")
CYAN = colors.HexColor("#DFF4F7")
ORANGE = colors.HexColor("#F59E0B")
LIGHT = colors.HexColor("#F4F7FA")
MID = colors.HexColor("#D6E0E8")
TEXT = colors.HexColor("#1F2937")
MUTED = colors.HexColor("#5B6773")
RED = colors.HexColor("#B42318")

pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))


def make_styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "TitleCN",
            parent=base["Title"],
            fontName="STSong-Light",
            fontSize=26,
            leading=34,
            textColor=NAVY,
            alignment=TA_LEFT,
            spaceAfter=10,
        ),
        "subtitle": ParagraphStyle(
            "SubtitleCN",
            parent=base["Normal"],
            fontName="STSong-Light",
            fontSize=13,
            leading=21,
            textColor=TEAL,
            spaceAfter=14,
        ),
        "h1": ParagraphStyle(
            "H1CN",
            parent=base["Heading1"],
            fontName="STSong-Light",
            fontSize=18,
            leading=24,
            textColor=NAVY,
            spaceAfter=10,
        ),
        "h2": ParagraphStyle(
            "H2CN",
            parent=base["Heading2"],
            fontName="STSong-Light",
            fontSize=13,
            leading=18,
            textColor=TEAL,
            spaceBefore=8,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "BodyCN",
            parent=base["BodyText"],
            fontName="STSong-Light",
            fontSize=10.2,
            leading=17,
            textColor=TEXT,
            spaceAfter=6,
        ),
        "small": ParagraphStyle(
            "SmallCN",
            parent=base["BodyText"],
            fontName="STSong-Light",
            fontSize=8.5,
            leading=13,
            textColor=MUTED,
        ),
        "callout": ParagraphStyle(
            "CalloutCN",
            parent=base["BodyText"],
            fontName="STSong-Light",
            fontSize=11,
            leading=18,
            textColor=NAVY,
            leftIndent=8,
            rightIndent=8,
        ),
        "pending": ParagraphStyle(
            "PendingCN",
            parent=base["BodyText"],
            fontName="STSong-Light",
            fontSize=15,
            leading=24,
            textColor=RED,
            alignment=TA_CENTER,
        ),
        "caption": ParagraphStyle(
            "CaptionCN",
            parent=base["BodyText"],
            fontName="STSong-Light",
            fontSize=8.5,
            leading=12,
            textColor=MUTED,
            alignment=TA_CENTER,
            spaceBefore=6,
        ),
        "code": ParagraphStyle(
            "Code",
            fontName="Courier",
            fontSize=7.2,
            leading=9.2,
            textColor=colors.HexColor("#111827"),
            leftIndent=4,
            rightIndent=4,
            borderColor=MID,
            borderWidth=0.6,
            borderPadding=7,
            backColor=colors.HexColor("#FBFCFD"),
        ),
    }


STYLES = make_styles()


def para(text: str, style: str = "body") -> Paragraph:
    return Paragraph(text, STYLES[style])


def bullet(text: str) -> Paragraph:
    return Paragraph("• " + text, STYLES["body"])


def fit_image(path: Path, max_width: float, max_height: float) -> Image:
    img = Image(str(path))
    scale = min(max_width / img.imageWidth, max_height / img.imageHeight)
    img.drawWidth = img.imageWidth * scale
    img.drawHeight = img.imageHeight * scale
    img.hAlign = "CENTER"
    return img


def info_table(rows, widths):
    data = [[para(str(cell), "small") for cell in row] for row in rows]
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.4, MID),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def callout(text: str, color=CYAN):
    table = Table([[para(text, "callout")]], colWidths=[166 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), color),
                ("BOX", (0, 0), (-1, -1), 0.8, TEAL),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ]
        )
    )
    return table


def pending_box(title: str, details: str):
    content = para(f"<b>{title}</b><br/><br/>{details}", "pending")
    table = Table([[content]], colWidths=[162 * mm], rowHeights=[92 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF7ED")),
                ("BOX", (0, 0), (-1, -1), 1.3, ORANGE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ]
        )
    )
    return table


def on_page(canvas, doc):
    page = canvas.getPageNumber()
    width, height = canvas._pagesize
    canvas.saveState()
    if page == 1:
        canvas.setFillColor(NAVY)
        canvas.rect(0, height - 20 * mm, width, 20 * mm, stroke=0, fill=1)
        canvas.setFillColor(TEAL)
        canvas.rect(0, 0, width, 8 * mm, stroke=0, fill=1)
        canvas.restoreState()
        return
    canvas.setStrokeColor(MID)
    canvas.line(18 * mm, height - 14 * mm, width - 18 * mm, height - 14 * mm)
    canvas.setFont("STSong-Light", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, height - 10.5 * mm, "TASK_0002 | MultiCharts 时间区间突破 | v1")
    canvas.drawRightString(width - 18 * mm, 10 * mm, f"第 {page} 页")
    canvas.restoreState()


def build_story():
    story = []

    story.extend(
        [
            Spacer(1, 32 * mm),
            para("TASK_0002", "subtitle"),
            para("MultiCharts 时间区间突破策略", "title"),
            para("第一版代码与回测资料合并报告", "subtitle"),
            Spacer(1, 10 * mm),
            callout(
                "核心时点：09:45 完成区间统计并提交 next bar 停止单，最快 09:46 成交；11:00 K 棒不得进场。"
            ),
            Spacer(1, 16 * mm),
            info_table(
                [
                    ["项目", "内容"],
                    ["软件", "MultiCharts 64 位版"],
                    ["商品", "CFFEX.IF.HOT（IF 连续月）"],
                    ["周期", "1 分钟 K 线"],
                    ["策略范围", "日盘基本型；夜盘版本待后续开发"],
                    ["报告日期", "2026-08-14"],
                    ["验收状态", "代码已整理；交易列表与绩效概要待实测补充"],
                ],
                [34 * mm, 128 * mm],
            ),
            Spacer(1, 9 * mm),
            para("研究与学习用途。回测结果不代表未来实盘收益。", "small"),
        ]
    )

    story.extend(
        [
            PageBreak(),
            para("一、任务状态与验收范围", "h1"),
            info_table(
                [
                    ["资料", "状态", "说明"],
                    ["策略说明第 1-2 页", "已归档", "作为原始需求依据"],
                    ["MultiCharts v1 代码", "已完成", "完整源代码收入本报告"],
                    ["编译参考截图", "已归档", "目标机器仍需重新编译确认"],
                    ["MC 交易列表", "待补充", "不得根据逻辑自行生成"],
                    ["MC 策略绩效概要", "待补充", "不得推测收益指标"],
                ],
                [48 * mm, 30 * mm, 84 * mm],
            ),
            Spacer(1, 8 * mm),
            para("策略参数", "h2"),
            info_table(
                [
                    ["参数", "默认值", "作用"],
                    ["Time1 / Time2", "09:31 / 09:45", "统计参考区间，首尾均包含"],
                    ["UpValue / DnValue", "1.0 / 1.0", "突破触发价偏移"],
                    ["SP / SL", "30 / 50 点", "每手停利与停损"],
                    ["StopTime", "11:00", "11:00 K 棒起禁止进场"],
                    ["CloseTime", "14:58", "下一根 14:59 开盘平仓"],
                    ["每次数量", "1 手", "每天最多一次进场"],
                    ["手续费 / 滑点", "0 / 0", "本次验收预设"],
                ],
                [47 * mm, 38 * mm, 77 * mm],
            ),
            Spacer(1, 8 * mm),
            callout(
                "日期输入沿用参考代码默认值 1160621-1160630。进行 7 月 8 日验收时，应在 MultiCharts 信号参数中改成实际测试区间。",
                colors.HexColor("#EFF6FF"),
            ),
        ]
    )

    story.extend(
        [
            PageBreak(),
            para("二、关键时间逻辑", "h1"),
            info_table(
                [
                    ["时间", "动作", "含义"],
                    ["09:31", "开始统计", "初始化当日 RangeHigh / RangeLow"],
                    ["09:31-09:45", "持续更新", "区间端点均包含"],
                    ["09:45 K 棒完成", "挂 next bar 停止单", "本轮使用 Time >= Time2"],
                    ["09:46", "最快可能成交", "7 月 8 日 4681.4 应核对为此时间"],
                    ["10:59", "最后可能成交", "10:58 最后一次允许挂下一根订单"],
                    ["11:00", "禁止进场", "不能在该 K 棒产生新仓位"],
                    ["14:58", "提交强制平仓", "next bar at market"],
                    ["14:59", "预期平仓成交", "以交易列表实测为准"],
                ],
                [34 * mm, 52 * mm, 76 * mm],
            ),
            Spacer(1, 9 * mm),
            para("为什么不是 09:47？", "h2"),
            bullet("09:45 这根 K 棒已经包含在区间内，完成区间更新后即可令 RangeReady 为 True。"),
            bullet("同一轮计算发出的 next bar 订单作用于 09:46。"),
            bullet("若写成 Time > Time2，第一次判断会在 09:46，next bar 才会落到 09:47。"),
            Spacer(1, 4 * mm),
            para("为什么不是 11:00？", "h2"),
            bullet("在 10:59 执行的 next bar 订单可能作用于 11:00，因此必须提前一根停止发单。"),
            bullet("Time < CalcTime(StopTime, -1) 使最后可能成交时间停在 10:59。"),
            Spacer(1, 6 * mm),
            callout(
                "待验收记录：7 月 8 日进场价 4681.4，正确进场时间应为 09:46。当前未收到 MC 交易列表，因此本报告只记录预期，不声称已经完成数据核对。",
                colors.HexColor("#FFF7ED"),
            ),
        ]
    )

    for index, filename in enumerate(["策略说明_第1页.png", "策略说明_第2页.png"], 1):
        story.extend(
            [
                PageBreak(),
                para(f"三、原始策略说明 - 第 {index} 页", "h1"),
                fit_image(REF_DIR / filename, 158 * mm, 220 * mm),
                para("原始附件按原样收入，不把图片中的文字自动视为已验证代码。", "caption"),
            ]
        )

    code_lines = CODE_FILE.read_text(encoding="utf-8").splitlines()
    numbered = [f"{i:03d}  {line}" for i, line in enumerate(code_lines, 1)]
    chunks = [numbered[i : i + 44] for i in range(0, len(numbered), 44)]
    for index, chunk in enumerate(chunks, 1):
        story.extend(
            [
                PageBreak(),
                para(f"四、MultiCharts v1 完整代码 - {index}/{len(chunks)}", "h1"),
                XPreformatted(html.escape("\n".join(chunk)), STYLES["code"]),
            ]
        )

    story.extend(
        [
            PageBreak(),
            para("五、代码设计说明", "h1"),
            info_table(
                [
                    ["设计点", "实现", "目的"],
                    ["区间状态", "RangeStarted / RangeReady", "保证先统计再挂单"],
                    ["每日一次", "TradedToday / TradesAtDayStart", "出场后不重复进场"],
                    ["最早成交", "Time >= Time2 + next bar", "允许 09:46 成交"],
                    ["停止进场", "CalcTime(StopTime, -1)", "排除 11:00 K 棒"],
                    ["点数转换", "SP/SL * BigPointValue", "把价格点数转换为每手金额"],
                    ["收盘退出", "14:58 next bar market", "预期 14:59 平仓"],
                ],
                [42 * mm, 62 * mm, 58 * mm],
            ),
            Spacer(1, 9 * mm),
            para("需要在 MultiCharts 中再次确认", "h2"),
            bullet("目标机器上的 PowerLanguage 编译结果。"),
            bullet("IF 连续合约的交易时段、BigPointValue 与换月拼接方式。"),
            bullet("同一分钟两侧都被触发时的 K 棒内成交路径设置。"),
            bullet("手续费、滑点、Bar Magnifier 与精细回测配置。"),
            bullet("7 月 8 日 4681.4 的进场时间是否确认为 09:46。"),
        ]
    )

    story.extend(
        [
            NextPageTemplate("landscape"),
            PageBreak(),
            para("六、MultiCharts 编译参考截图", "h1"),
            fit_image(REF_DIR / "TRB代码_编译通过截图.png", 255 * mm, 150 * mm),
            para("截图显示参考版本在 MultiCharts 公式编辑器中编译成功；交付源代码仍需在目标环境重新验证。", "caption"),
            NextPageTemplate("landscape"),
            PageBreak(),
            para("七、历史参考代码截图", "h1"),
            fit_image(REF_DIR / "TRB历史参考代码截图.png", 245 * mm, 125 * mm),
            para("历史代码用于比较写法，不覆盖本报告 v1 源代码。", "caption"),
            NextPageTemplate("portrait"),
            PageBreak(),
        ]
    )

    story.extend(
        [
            para("八、MC 交易列表", "h1"),
            para("本页应放置 MultiCharts Strategy Performance Report 中的交易列表截图或导出内容。", "body"),
            Spacer(1, 8 * mm),
            pending_box(
                "等待实测资料",
                "至少需要显示日期、进出场时间、方向、信号名称、成交价、数量和单笔损益。重点核对 7 月 8 日 4681.4 是否在 09:46 进场，以及每天是否最多只有一次进场。",
            ),
            Spacer(1, 8 * mm),
            para("收到截图后，应替换本页提示框并重新生成同名 PDF。", "small"),
            PageBreak(),
            para("九、MC 策略绩效概要", "h1"),
            para("本页应放置 MultiCharts 策略绩效概要截图或导出内容。", "body"),
            Spacer(1, 8 * mm),
            pending_box(
                "等待实测资料",
                "建议保留净利润、总交易次数、胜率、平均交易、获利因子、最大回撤和手续费等指标，并同时记录数据区间、商品、周期及回测属性。",
            ),
            Spacer(1, 8 * mm),
            para("在真实绩效概要到达前，本报告不填写或估算任何收益指标。", "small"),
            PageBreak(),
            para("十、v1 边界与后续版本", "h1"),
            para("当前边界", "h2"),
            bullet("仅针对日盘商品的基本型回测。"),
            bullet("以自然日 Date 变化重置变量，不适用于 21:00 开始的跨日夜盘。"),
            bullet("连续合约回测包含换月与价格拼接影响。"),
            bullet("交易列表和绩效概要尚未到位，数值验收未完成。"),
            para("建议的 v2 方向", "h2"),
            bullet("按交易时段而不是自然日定义交易日。"),
            bullet("明确未成交双向停止单的取消和 OCO 行为。"),
            bullet("记录实际区间高低、触发价和订单时间，便于逐笔核对。"),
            bullet("加入夜盘样例，并验证跨午夜重置。"),
            Spacer(1, 10 * mm),
            callout(
                "版本结论：v1 已完成基本逻辑与资料框架；待补齐 MC 交易列表和策略绩效概要后，才能把状态改为完整验收。"
            ),
        ]
    )

    return story


def build_pdf():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    portrait_size = A4
    landscape_size = landscape(A4)
    doc = BaseDocTemplate(
        str(OUTPUT),
        pagesize=portrait_size,
        title="TASK_0002 MultiCharts 时间区间突破 v1 回测报告",
        author="量化学习知识库",
        subject="策略说明、PowerLanguage 代码、交易列表与绩效概要",
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=20 * mm,
        bottomMargin=18 * mm,
    )
    portrait_frame = Frame(
        18 * mm,
        18 * mm,
        portrait_size[0] - 36 * mm,
        portrait_size[1] - 38 * mm,
        id="portrait-frame",
    )
    landscape_frame = Frame(
        18 * mm,
        18 * mm,
        landscape_size[0] - 36 * mm,
        landscape_size[1] - 38 * mm,
        id="landscape-frame",
    )
    doc.addPageTemplates(
        [
            PageTemplate("portrait", pagesize=portrait_size, frames=[portrait_frame], onPage=on_page),
            PageTemplate("landscape", pagesize=landscape_size, frames=[landscape_frame], onPage=on_page),
        ]
    )
    doc.build(build_story())
    print(OUTPUT)


if __name__ == "__main__":
    build_pdf()
