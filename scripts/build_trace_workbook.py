import json
import sys
from datetime import datetime, timedelta
from collections import Counter

try:
    import openpyxl
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "openpyxl>=3.1.0"])
    import openpyxl

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
from openpyxl.formatting.rule import CellIsRule
from openpyxl.chart import LineChart, BarChart, Reference
from openpyxl.utils import get_column_letter
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

INPUT_JSON = sys.argv[1]
OUTPUT_XLSX = sys.argv[2]
TITLE = sys.argv[3]

with open(INPUT_JSON, "r", encoding="utf-8") as f:
    payload = json.load(f)
records = payload["records"]
N = len(records)
if N == 0:
    raise ValueError("No trace records found in the input JSON; workbook generation skipped.")
DETAIL_END = N + 1
stats = payload.get("pageStats") or {}
ZERO_DETAIL_METRICS = all((record.get(field) or 0) == 0 for record in records for field in ("credits", "llmCallCount", "toolCallCount", "toolErrorCount"))


def stat_value(name):
    value = stats.get(name)
    return value.get("value") if isinstance(value, dict) else None


PAGE_STATS = {
    "conversations": stat_value("conversations") if stat_value("conversations") is not None else N,
    "credits": stat_value("credits"),
    "duration_p50": stat_value("p50LatencyMs") / 1000 if stat_value("p50LatencyMs") is not None else None,
    "duration_p90": stat_value("p90LatencyMs") / 1000 if stat_value("p90LatencyMs") is not None else None,
    "duration_p99": stat_value("p99LatencyMs") / 1000 if stat_value("p99LatencyMs") is not None else None,
    "ttft_p50": stat_value("ttftP50Ms") / 1000 if stat_value("ttftP50Ms") is not None else None,
    "ttft_p90": stat_value("ttftP90Ms") / 1000 if stat_value("ttftP90Ms") is not None else None,
    "ttft_p99": stat_value("ttftP99Ms") / 1000 if stat_value("ttftP99Ms") is not None else None,
}
LATENCY_SOURCE = "页面" if PAGE_STATS["duration_p50"] is not None else "明细"


def xl_color(css_hex: str) -> str:
    value = css_hex.removeprefix("#").upper()
    if len(value) != 6:
        raise ValueError(f"Expected #RRGGBB, got: {css_hex}")
    return "FF" + value


XL_PRIMARY = xl_color("#4472C4")
XL_PRIMARY_DARK = xl_color("#2F5597")
XL_LIGHT = xl_color("#D9E2F3")
XL_WHITE = xl_color("#FFFFFF")
XL_TEXT = xl_color("#1A1A1A")
XL_GRAY = xl_color("#666666")
XL_BORDER = xl_color("#BFBFBF")
XL_RED = xl_color("#FFC7CE")
XL_RED_TEXT = xl_color("#9C0006")
XL_YELLOW = xl_color("#FFEB9C")
XL_YELLOW_TEXT = xl_color("#9C6500")

thin_side = Side(style="thin", color=XL_BORDER)
header_fill = PatternFill("solid", fgColor=XL_PRIMARY)
light_fill = PatternFill("solid", fgColor=XL_LIGHT)
red_fill = PatternFill("solid", fgColor=XL_RED)
yellow_fill = PatternFill("solid", fgColor=XL_YELLOW)


def clean(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    value = ILLEGAL_CHARACTERS_RE.sub("", str(value))
    return value[:32700]


def dt_ms(value):
    return datetime.fromtimestamp(value / 1000) if value else None


def set_header(ws, row, start_col, end_col):
    for col in range(start_col, end_col + 1):
        c = ws.cell(row=row, column=col)
        c.fill = header_fill
        c.font = Font(name="微软雅黑", bold=True, color=XL_WHITE)
        c.alignment = Alignment(horizontal="center", vertical="center", wrapText=True)
        c.border = Border(bottom=thin_side)


def set_title(ws, cell_range, text):
    ws.merge_cells(cell_range)
    c = ws[cell_range.split(":")[0]]
    c.value = text
    c.fill = PatternFill("solid", fgColor=XL_PRIMARY_DARK)
    c.font = Font(name="微软雅黑", size=16, bold=True, color=XL_WHITE)
    c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[c.row].height = 30


def style_total(ws, row, start_col, end_col):
    for col in range(start_col, end_col + 1):
        c = ws.cell(row=row, column=col)
        c.fill = light_fill
        c.font = Font(name="微软雅黑", bold=True, color=XL_TEXT)
        c.border = Border(top=thin_side)


wb = Workbook()
wb.remove(wb.active)
wb.properties.title = TITLE
summary = wb.create_sheet("汇总")
daily = wb.create_sheet("每日趋势")
users_ws = wb.create_sheet("用户统计")
detail = wb.create_sheet("明细")
fields_ws = wb.create_sheet("字段说明")

# 明细：第1行表头，第2行至DETAIL_END为数据
headers = [
    "对话 ID", "会话 ID", "名称", "开始时间", "结束时间", "日期", "小时", "状态",
    "用户 ID", "用户昵称", "Agent", "产品场景", "任务场景", "模型", "事件数", "积分",
    "模型调用", "工具调用", "工具异常次数", "输入IO", "输出IO", "耗时(ms)", "首Token(ms)",
    "耗时(s)", "首Token(s)", "输入", "输出"
]
for col, name in enumerate(headers, 1):
    detail.cell(row=1, column=col, value=name)
set_header(detail, 1, 1, len(headers))

for i, rec in enumerate(records, 2):
    values = {
        1: clean(rec.get("traceId")),
        2: clean(rec.get("sessionId")),
        3: clean(rec.get("name")),
        4: dt_ms(rec.get("startTimeMs")),
        5: dt_ms(rec.get("endTimeMs")),
        6: dt_ms(rec.get("startTimeMs")).date() if rec.get("startTimeMs") else None,
        7: dt_ms(rec.get("startTimeMs")).hour if rec.get("startTimeMs") else None,
        8: clean(rec.get("status")),
        9: clean(rec.get("userId")),
        10: clean(rec.get("userName")),
        11: clean(rec.get("agentScene")),
        12: clean(rec.get("productScene")),
        13: clean(rec.get("taskScene")),
        14: clean(rec.get("modelName")),
        15: rec.get("eventCount"),
        16: rec.get("credits"),
        17: rec.get("llmCallCount"),
        18: rec.get("toolCallCount"),
        19: rec.get("toolErrorCount"),
        20: clean(rec.get("inputIo")),
        21: clean(rec.get("outputIo")),
        22: rec.get("durationMs"),
        23: rec.get("ttftMs"),
        24: f'=IF(V{i}="","",V{i}/1000)',
        25: f'=IF(W{i}="","",W{i}/1000)',
        26: clean(rec.get("input")),
        27: clean(rec.get("output")),
    }
    for col, value in values.items():
        c = detail.cell(row=i, column=col, value=value)
        c.font = Font(name="微软雅黑", size=10, color=XL_TEXT)
        c.alignment = Alignment(vertical="top", wrapText=col in (3, 26, 27))
    for col in (4, 5):
        detail.cell(i, col).number_format = "yyyy-mm-dd hh:mm:ss"
    detail.cell(i, 6).number_format = "yyyy-mm-dd"
    for col in (15, 17, 18, 19, 22, 23):
        detail.cell(i, col).number_format = "#,##0"
    detail.cell(i, 16).number_format = "#,##0.00"
    for col in (24, 25):
        detail.cell(i, col).number_format = "#,##0.00"
        detail.cell(i, col).fill = light_fill

widths = {
    "A": 36, "B": 36, "C": 24, "D": 20, "E": 20, "F": 12, "G": 8, "H": 12,
    "I": 36, "J": 16, "K": 16, "L": 14, "M": 14, "N": 18, "O": 10, "P": 12,
    "Q": 11, "R": 11, "S": 14, "T": 12, "U": 12, "V": 13, "W": 14, "X": 12,
    "Y": 13, "Z": 48, "AA": 48
}
for col, width in widths.items():
    detail.column_dimensions[col].width = width
detail.freeze_panes = "D2"
detail.auto_filter.ref = f"A1:AA{DETAIL_END}"
detail.sheet_view.zoomScale = 80
detail.conditional_formatting.add(
    f"S2:S{DETAIL_END}",
    CellIsRule(operator="greaterThan", formula=["0"], fill=red_fill, font=Font(color=XL_RED_TEXT))
)
detail.conditional_formatting.add(
    f"X2:X{DETAIL_END}",
    CellIsRule(operator="greaterThan", formula=["600"], fill=yellow_fill, font=Font(color=XL_YELLOW_TEXT))
)
detail.conditional_formatting.add(
    f"Y2:Y{DETAIL_END}",
    CellIsRule(operator="greaterThan", formula=["10"], fill=red_fill, font=Font(color=XL_RED_TEXT))
)

# 日期与用户维度值
start_date = datetime.fromtimestamp(payload["range"]["start"]).date()
end_date = datetime.fromtimestamp(payload["range"]["end"]).date()
days = []
d = start_date
while d <= end_date:
    days.append(d)
    d += timedelta(days=1)
DAILY_START = 4
DAILY_END = DAILY_START + len(days) - 1
DAILY_TOTAL = DAILY_END + 1

user_counts = Counter(clean(r.get("userId")) or "(空)" for r in records)
user_names = {}
for r in records:
    uid = clean(r.get("userId")) or "(空)"
    if uid not in user_names or (not user_names[uid] and clean(r.get("userName"))):
        user_names[uid] = clean(r.get("userName"))
user_ids = [uid for uid, _ in user_counts.most_common()]
USER_START = 4
USER_END = USER_START + len(user_ids) - 1
USER_TOTAL = USER_END + 1

# 每日趋势：第1行标题，第2行说明，第3行表头，第4行起数据
set_title(daily, "A1:G1", "每日对话趋势")
daily.merge_cells("A2:G2")
daily["A2"] = "按自然日统计；若起止时间为日内时刻，首尾日期为不完整自然日。指标均引用“明细”工作表。"
daily["A2"].font = Font(name="微软雅黑", color=XL_GRAY)
daily_headers = ["日期", "对话数", "平均耗时(s)", "最大耗时(s)", "平均首Token(s)", "标题生成记录", "成功对话"]
for col, name in enumerate(daily_headers, 1):
    daily.cell(3, col, name)
set_header(daily, 3, 1, 7)
for idx, day in enumerate(days, DAILY_START):
    daily.cell(idx, 1, day)
    daily.cell(idx, 2, f'=COUNTIFS(明细!$F$2:$F${DETAIL_END},$A{idx})')
    daily.cell(idx, 3, f'=IF(B{idx}=0,"",AVERAGEIFS(明细!$X$2:$X${DETAIL_END},明细!$F$2:$F${DETAIL_END},$A{idx}))')
    daily.cell(idx, 4, f'=IF(B{idx}=0,"",MAXIFS(明细!$X$2:$X${DETAIL_END},明细!$F$2:$F${DETAIL_END},$A{idx}))')
    daily.cell(idx, 5, f'=IF(B{idx}=0,"",AVERAGEIFS(明细!$Y$2:$Y${DETAIL_END},明细!$F$2:$F${DETAIL_END},$A{idx}))')
    daily.cell(idx, 6, f'=COUNTIFS(明细!$F$2:$F${DETAIL_END},$A{idx},明细!$AA$2:$AA${DETAIL_END},"*isNewTopic*")')
    daily.cell(idx, 7, f'=COUNTIFS(明细!$F$2:$F${DETAIL_END},$A{idx},明细!$H$2:$H${DETAIL_END},"success")')
    daily.cell(idx, 1).number_format = "yyyy-mm-dd"
    for col in (2, 6, 7):
        daily.cell(idx, col).number_format = "#,##0"
    for col in (3, 4, 5):
        daily.cell(idx, col).number_format = "#,##0.00"

daily.cell(DAILY_TOTAL, 1, "合计/整体")
daily.cell(DAILY_TOTAL, 2, f"=SUM(B{DAILY_START}:B{DAILY_END})")
daily.cell(DAILY_TOTAL, 3, f"=AVERAGE(明细!$X$2:$X${DETAIL_END})")
daily.cell(DAILY_TOTAL, 4, f"=MAX(明细!$X$2:$X${DETAIL_END})")
daily.cell(DAILY_TOTAL, 5, f"=AVERAGE(明细!$Y$2:$Y${DETAIL_END})")
daily.cell(DAILY_TOTAL, 6, f"=SUM(F{DAILY_START}:F{DAILY_END})")
daily.cell(DAILY_TOTAL, 7, f"=SUM(G{DAILY_START}:G{DAILY_END})")
for col in (3, 4, 5):
    daily.cell(DAILY_TOTAL, col).number_format = "#,##0.00"
style_total(daily, DAILY_TOTAL, 1, 7)
for col, width in zip("ABCDEFG", [15, 12, 16, 16, 18, 16, 13]):
    daily.column_dimensions[col].width = width
daily.freeze_panes = "A4"
daily.auto_filter.ref = f"A3:G{DAILY_END}"

# 用户统计
set_title(users_ws, "A1:H1", "用户对话统计")
users_ws.merge_cells("A2:H2")
users_ws["A2"] = "按用户 ID 聚合，按对话数降序排列；指标均引用“明细”工作表。"
users_ws["A2"].font = Font(name="微软雅黑", color=XL_GRAY)
user_headers = ["用户 ID", "用户昵称", "对话数", "平均耗时(s)", "最大耗时(s)", "平均首Token(s)", "标题生成记录", "对话占比"]
for col, name in enumerate(user_headers, 1):
    users_ws.cell(3, col, name)
set_header(users_ws, 3, 1, 8)
for idx, uid in enumerate(user_ids, USER_START):
    users_ws.cell(idx, 1, uid)
    users_ws.cell(idx, 2, user_names.get(uid, ""))
    users_ws.cell(idx, 3, f'=COUNTIF(明细!$I$2:$I${DETAIL_END},$A{idx})')
    users_ws.cell(idx, 4, f'=IF(C{idx}=0,"",AVERAGEIF(明细!$I$2:$I${DETAIL_END},$A{idx},明细!$X$2:$X${DETAIL_END}))')
    users_ws.cell(idx, 5, f'=IF(C{idx}=0,"",MAXIFS(明细!$X$2:$X${DETAIL_END},明细!$I$2:$I${DETAIL_END},$A{idx}))')
    users_ws.cell(idx, 6, f'=IF(C{idx}=0,"",AVERAGEIF(明细!$I$2:$I${DETAIL_END},$A{idx},明细!$Y$2:$Y${DETAIL_END}))')
    users_ws.cell(idx, 7, f'=COUNTIFS(明细!$I$2:$I${DETAIL_END},$A{idx},明细!$AA$2:$AA${DETAIL_END},"*isNewTopic*")')
    users_ws.cell(idx, 8, f'=IF(OR(C{idx}="",汇总!$A$5="",汇总!$A$5=0),"",C{idx}/汇总!$A$5)')
    users_ws.cell(idx, 3).number_format = "#,##0"
    for col in (4, 5, 6):
        users_ws.cell(idx, col).number_format = "#,##0.00"
    users_ws.cell(idx, 7).number_format = "#,##0"
    users_ws.cell(idx, 8).number_format = "0.00%"
users_ws.cell(USER_TOTAL, 1, "合计/整体")
users_ws.cell(USER_TOTAL, 3, f"=SUM(C{USER_START}:C{USER_END})")
users_ws.cell(USER_TOTAL, 4, f"=AVERAGE(明细!$X$2:$X${DETAIL_END})")
users_ws.cell(USER_TOTAL, 5, f"=MAX(明细!$X$2:$X${DETAIL_END})")
users_ws.cell(USER_TOTAL, 6, f"=AVERAGE(明细!$Y$2:$Y${DETAIL_END})")
users_ws.cell(USER_TOTAL, 7, f"=SUM(G{USER_START}:G{USER_END})")
users_ws.cell(USER_TOTAL, 8, f'=IF(OR(C{USER_TOTAL}="",C{USER_TOTAL}=0),"",SUM(H{USER_START}:H{USER_END}))')
for col in (4, 5, 6):
    users_ws.cell(USER_TOTAL, col).number_format = "#,##0.00"
users_ws.cell(USER_TOTAL, 8).number_format = "0.00%"
style_total(users_ws, USER_TOTAL, 1, 8)
for col, width in zip("ABCDEFGH", [38, 18, 12, 16, 16, 18, 16, 13]):
    users_ws.column_dimensions[col].width = width
users_ws.freeze_panes = "C4"
users_ws.auto_filter.ref = f"A3:H{USER_END}"

# 汇总看板：标题第1行，说明第2行，KPI第4-5与8-9行，图表第12行起
set_title(summary, "A1:L1", TITLE)
summary.merge_cells("A2:L2")
range_start = datetime.fromtimestamp(payload["range"]["start"]).strftime("%Y-%m-%d %H:%M:%S")
range_end = datetime.fromtimestamp(payload["range"]["end"]).strftime("%Y-%m-%d %H:%M:%S")
summary["A2"] = f"统计范围：{range_start} 至 {range_end}｜记录按 traceId 去重｜来源：会话追踪 Trace"
summary["A2"].font = Font(name="微软雅黑", color=XL_GRAY)
summary["A2"].alignment = Alignment(horizontal="center")

cards = [
    ("A", "B", 4, "导出明细记录", f"=COUNTA(明细!$A$2:$A${DETAIL_END})", "#,##0"),
    ("C", "D", 4, "页面汇总对话", PAGE_STATS["conversations"], "#,##0"),
    ("E", "F", 4, "任务会话数", f'=SUMPRODUCT((明细!$B$2:$B${DETAIL_END}<>"")/COUNTIF(明细!$B$2:$B${DETAIL_END},明细!$B$2:$B${DETAIL_END}&""))', "#,##0"),
    ("G", "H", 4, "活跃用户数", f'=SUMPRODUCT((明细!$I$2:$I${DETAIL_END}<>"")/COUNTIF(明细!$I$2:$I${DETAIL_END},明细!$I$2:$I${DETAIL_END}&""))', "#,##0"),
    ("I", "J", 4, "积分消耗（页面）", PAGE_STATS["credits"] if PAGE_STATS["credits"] is not None else "未提供", "#,##0.00"),
    ("K", "L", 4, "成功明细记录", f'=COUNTIF(明细!$H$2:$H${DETAIL_END},"success")', "#,##0"),
    ("A", "B", 8, f"耗时 P50(s)（{LATENCY_SOURCE}）", PAGE_STATS["duration_p50"] if PAGE_STATS["duration_p50"] is not None else f"=MEDIAN(明细!$X$2:$X${DETAIL_END})", "#,##0.00"),
    ("C", "D", 8, f"耗时 P90(s)（{LATENCY_SOURCE}）", PAGE_STATS["duration_p90"] if PAGE_STATS["duration_p90"] is not None else f"=PERCENTILE.INC(明细!$X$2:$X${DETAIL_END},0.9)", "#,##0.00"),
    ("E", "F", 8, f"耗时 P99(s)（{LATENCY_SOURCE}）", PAGE_STATS["duration_p99"] if PAGE_STATS["duration_p99"] is not None else f"=PERCENTILE.INC(明细!$X$2:$X${DETAIL_END},0.99)", "#,##0.00"),
    ("G", "H", 8, f"首Token P50(s)（{LATENCY_SOURCE}）", PAGE_STATS["ttft_p50"] if PAGE_STATS["ttft_p50"] is not None else f"=MEDIAN(明细!$Y$2:$Y${DETAIL_END})", "#,##0.00"),
    ("I", "J", 8, f"首Token P90(s)（{LATENCY_SOURCE}）", PAGE_STATS["ttft_p90"] if PAGE_STATS["ttft_p90"] is not None else f"=PERCENTILE.INC(明细!$Y$2:$Y${DETAIL_END},0.9)", "#,##0.00"),
    ("K", "L", 8, f"首Token P99(s)（{LATENCY_SOURCE}）", PAGE_STATS["ttft_p99"] if PAGE_STATS["ttft_p99"] is not None else f"=PERCENTILE.INC(明细!$Y$2:$Y${DETAIL_END},0.99)", "#,##0.00"),
]
for left, right, row, label, formula, numfmt in cards:
    summary.merge_cells(f"{left}{row}:{right}{row}")
    summary.merge_cells(f"{left}{row + 1}:{right}{row + 1}")
    summary[f"{left}{row}"] = label
    summary[f"{left}{row}"].fill = light_fill
    summary[f"{left}{row}"].font = Font(name="微软雅黑", size=10, color=XL_GRAY)
    summary[f"{left}{row}"].alignment = Alignment(horizontal="center", vertical="center")
    summary[f"{left}{row + 1}"] = formula
    summary[f"{left}{row + 1}"].font = Font(name="微软雅黑", size=16, bold=True, color=XL_PRIMARY_DARK)
    summary[f"{left}{row + 1}"].alignment = Alignment(horizontal="center", vertical="center")
    summary[f"{left}{row + 1}"].number_format = numfmt
    summary[f"{left}{row + 1}"].border = Border(bottom=thin_side)

line = LineChart()
line.title = "每日对话数趋势"
line.y_axis.title = "对话数"
line.x_axis.title = "日期"
line.height = 7.5
line.width = 13
line.add_data(Reference(daily, min_col=2, min_row=3, max_row=DAILY_END), titles_from_data=True)
line.set_categories(Reference(daily, min_col=1, min_row=DAILY_START, max_row=DAILY_END))
line.legend = None
summary.add_chart(line, "A12")

bar = BarChart()
bar.type = "bar"
bar.style = 10
bar.title = "对话数 Top 10 用户"
bar.x_axis.title = "对话数"
bar.height = 7.5
bar.width = 13
bar.add_data(Reference(users_ws, min_col=3, min_row=3, max_row=min(USER_END, 13)), titles_from_data=True)
bar.set_categories(Reference(users_ws, min_col=2, min_row=USER_START, max_row=min(USER_END, 13)))
bar.legend = None
summary.add_chart(bar, "G12")

summary.merge_cells("A28:L28")
summary["A28"] = "分析口径与使用提示"
summary["A28"].fill = header_fill
summary["A28"].font = Font(name="微软雅黑", bold=True, color=XL_WHITE)
summary["A28"].alignment = Alignment(horizontal="left")
notes = [
    "1. 日志通过会话追踪接口按时间段拆分获取，并按 traceId 去重；原始 JSON 文件同步保留。",
    f"2. 页面汇总对话数与积分来自 trace-stats（跨段查询时合计）；延迟分位数来源：{LATENCY_SOURCE}。明细实际导出 {N:,} 条，与页面汇总分开标注。",
    ("3. 明细接口的积分、模型调用、工具调用等字段均返回 0，因此不用于汇总分析；耗时与首 Token 由毫秒换算为秒。" if ZERO_DETAIL_METRICS else "3. 明细积分与调用字段按原始值保留；页面汇总与明细统计分开标注。耗时与首 Token 由毫秒换算为秒。"),
    "4. 每日趋势按自然日统计；若起止时间为日内时刻，首尾日期为不完整自然日。标题生成记录按输出包含 isNewTopic 识别。",
    "5. 明细支持筛选与冻结窗格；输入、输出可能包含业务资料，请按企业数据权限妥善保存。",
]
for i, note in enumerate(notes, 29):
    summary.merge_cells(start_row=i, start_column=1, end_row=i, end_column=12)
    summary.cell(i, 1, note)
    summary.cell(i, 1).font = Font(name="微软雅黑", size=10, color=XL_TEXT)
    summary.cell(i, 1).alignment = Alignment(wrapText=True, vertical="top")
for col in range(1, 13):
    summary.column_dimensions[get_column_letter(col)].width = 12
summary.sheet_view.showGridLines = False
summary.sheet_view.zoomScale = 90

# 字段说明
field_rows = [
    ("traceId", "对话 ID，单轮对话唯一标识"), ("sessionId", "会话 ID，任务会话标识"),
    ("name", "对话名称"), ("input / output", "输入与输出摘要"),
    ("startTimeMs / endTimeMs", "开始与结束时间，已转换为本地日期时间"),
    ("durationMs", "单轮对话耗时，明细另换算为秒"), ("ttftMs", "首 Token 耗时，明细另换算为秒"),
    ("status", "对话状态"), ("userId / userName", "用户 ID 与昵称"),
    ("agentScene / productScene / taskScene", "Agent、产品与任务场景"),
    ("eventCount", "事件数量"),
    ("credits", "明细接口原始字段；本次均返回 0，页面汇总积分见“汇总”" if ZERO_DETAIL_METRICS else "明细接口原始积分字段"),
    ("llmCallCount", "明细接口原始字段；本次均返回 0，不用于汇总" if ZERO_DETAIL_METRICS else "模型调用次数"),
    ("toolCallCount", "明细接口原始字段；本次均返回 0，不用于汇总" if ZERO_DETAIL_METRICS else "工具调用次数"),
    ("toolErrorCount", "明细接口原始字段；本次均返回 0" if ZERO_DETAIL_METRICS else "工具异常次数；大于 0 标红"),
    ("inputIo / outputIo", "输入与输出 IO 信息"),
    ("modelName", "模型名称"), ("日期 / 小时", "由开始时间转换，用于趋势分析"),
]
fields_ws.append(["字段", "说明"])
set_header(fields_ws, 1, 1, 2)
for row in field_rows:
    fields_ws.append(list(row))
for row in fields_ws.iter_rows(min_row=2, max_row=1 + len(field_rows), min_col=1, max_col=2):
    for c in row:
        c.font = Font(name="微软雅黑", size=10, color=XL_TEXT)
        c.alignment = Alignment(vertical="top", wrapText=True)
fields_ws.column_dimensions["A"].width = 38
fields_ws.column_dimensions["B"].width = 64
fields_ws.freeze_panes = "A2"
fields_ws.auto_filter.ref = f"A1:B{1 + len(field_rows)}"

for ws in wb.worksheets:
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0

wb.save(OUTPUT_XLSX)
print(json.dumps({"output": OUTPUT_XLSX, "records": N, "days": len(days), "users": len(user_ids)}, ensure_ascii=False))
