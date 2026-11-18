"""Build the Excel executive dashboard from processed pipeline outputs.

Run after build_report.py:  python src/build_dashboard.py
All KPI cards and chart series are formulas linked to the data sheets, so editing a
data sheet in Excel updates the dashboard. Re-running this script rebuilds it from the
latest pipeline outputs.
"""
import json
from pathlib import Path
import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.chart.marker import DataPoint
from openpyxl.chart.shapes import GraphicalProperties
from openpyxl.chart.text import RichText
from openpyxl.drawing.line import LineProperties
from openpyxl.drawing.text import CharacterProperties, Paragraph, ParagraphProperties, Font as DFont
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as L

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'processed'
QA = ROOT / 'data' / 'quality'
DEST = ROOT / 'dashboard' / 'warehouse_intelligence_dashboard.xlsx'

# ---- Design tokens -------------------------------------------------------
FONT = 'Arial'
NAVY, NAVY_2 = '0B1F3A', '1C3354'
CANVAS, CARD, RULE = 'F4F5F7', 'FFFFFF', 'E3E5E9'
INK, INK_2, INK_3 = '0B1F3A', '52514E', '8A8F98'
ACCENT, MUTED, GRID = '2A78D6', 'C3C7CE', 'E8EAED'
HIGHLIGHT_ZONE = 'High-Bay'


def fill(c): return PatternFill('solid', start_color=c, end_color=c)
def font(size=10, color=INK, bold=False, italic=False): return Font(name=FONT, size=size, color=color, bold=bold, italic=italic)


thin = Side(style='thin', color=RULE)
BOX = Border(left=thin, right=thin, top=thin, bottom=thin)

# ---- Load pipeline outputs ----------------------------------------------
zone = pd.read_csv(OUT / 'zone_summary.csv')
shift = pd.read_csv(OUT / 'shift_summary.csv')
stock = pd.read_csv(OUT / 'stock_accuracy_by_zone.csv')
weekly = pd.read_csv(OUT / 'weekly_trend.csv')
prio = pd.read_csv(OUT / 'sku_recount_priority.csv')
audit = json.loads((QA / 'quality_audit.json').read_text())
metrics = json.loads((ROOT / 'reports' / 'metrics.json').read_text())

wb = Workbook()
dash = wb.active
dash.title = 'Dashboard'


# ---- Data sheets ----------------------------------------------------------
def data_sheet(name, headers, rows, formats, widths, note=None):
    ws = wb.create_sheet(name)
    ws.sheet_view.showGridLines = False
    for j, h in enumerate(headers, 1):
        c = ws.cell(1, j, h)
        c.font = font(9, 'FFFFFF', True); c.fill = fill(NAVY)
        c.alignment = Alignment(horizontal='left' if j == 1 else 'right', vertical='center', wrap_text=True)
    ws.row_dimensions[1].height = 30
    for i, row in enumerate(rows, 2):
        for j, v in enumerate(row, 1):
            c = ws.cell(i, j, v)
            c.font = font(10); c.number_format = formats[j - 1]
            c.border = Border(bottom=thin)
            c.alignment = Alignment(horizontal='left' if j == 1 else 'right')
            if i % 2 == 1: c.fill = fill('F8F9FA')
    for j, w in enumerate(widths, 1): ws.column_dimensions[L(j)].width = w
    ws.freeze_panes = 'A2'
    if note:
        c = ws.cell(len(rows) + 3, 1, note); c.font = font(9, INK_3, italic=True)
    return ws


zone_rows = []
for i, r in enumerate(zone.itertuples(), 2):
    zone_rows.append([r.zone, int(r.pick_events), int(r.requested_units), int(r.picked_units), int(r.slow_picks),
                      int(r.mismatched_scans), int(r.breakdown_events), int(r.short_picks), float(r.benchmark_gap_hours),
                      float(r.active_pick_hours), f'=E{i}/B{i}', f'=F{i}/B{i}', f'=D{i}/C{i}', f'=I{i}*3600/B{i}',
                      f'=G{i}/B{i}', f'=H{i}/B{i}'])
data_sheet('Zone KPIs',
           ['Zone', 'Pick events', 'Requested units', 'Picked units', 'Slow picks', 'Wrong-location scans',
            'Pallet breakdowns', 'Short picks', 'Benchmark gap (h)', 'Active pick (h)', 'Slow pick rate',
            'Wrong-location rate', 'Unit fill rate', 'Gap sec per pick', 'Breakdown rate', 'Short pick rate'],
           zone_rows, ['@'] + ['#,##0'] * 7 + ['0.0', '0.0', '0.0%', '0.00%', '0.00%', '0.0', '0.0%', '0.00%'],
           [14] + [12] * 15, 'Source: picks_clean, SQL query 02. Rates are formulas on the counts.')

shift_rows = [[r.shift, int(r.pick_events), int(r.picked_units), int(r.slow_picks), float(r.active_pick_hours),
               float(r.benchmark_gap_hours), f'=C{i}/E{i}', f'=D{i}/B{i}'] for i, r in enumerate(shift.itertuples(), 2)]
data_sheet('Shift KPIs', ['Shift', 'Pick events', 'Picked units', 'Slow picks', 'Active pick (h)', 'Benchmark gap (h)',
                          'Units per active hour', 'Slow pick rate'],
           shift_rows, ['@', '#,##0', '#,##0', '#,##0', '0.0', '0.0', '0.0', '0.0%'], [12] + [14] * 7,
           'Active pick hours are recorded picking time, not paid hours.')

stock_rows = [[r.zone, int(r.count_events), int(r.exact_matches), int(r.abs_variance_units), f'=C{i}/B{i}']
              for i, r in enumerate(stock.itertuples(), 2)]
data_sheet('Stock Accuracy', ['Zone', 'Count events', 'Exact matches', 'Absolute variance (units)', 'Exact match rate'],
           stock_rows, ['@', '#,##0', '#,##0', '#,##0', '0.0%'], [14, 14, 14, 16, 16],
           'Source: cycle_counts_clean, SQL query 05. Measured per count event.')

week_rows = [[pd.Timestamp(r.week_start).to_pydatetime(), int(r.pick_events), int(r.picked_units), int(r.slow_picks),
              float(r.benchmark_gap_hours), f'=D{i}/B{i}', f'=SUM($D$2:$D${len(weekly)+1})/SUM($B$2:$B${len(weekly)+1})']
             for i, r in enumerate(weekly.itertuples(), 2)]
data_sheet('Weekly Trend', ['Week starting', 'Pick events', 'Picked units', 'Slow picks', 'Benchmark gap (h)',
                            'Slow pick rate', 'Period average'],
           week_rows, ['d mmm yyyy', '#,##0', '#,##0', '#,##0', '0.0', '0.0%', '0.0%'], [16] + [13] * 6)

prio_rows = [[r.sku_id, r.zone, int(r.picks), int(r.counts), r.mismatch_pct / 100, r.short_pick_pct / 100,
              r.count_discrepancy_pct / 100, float(r.priority_score)] for r in prio.itertuples()]
data_sheet('Recount Priority', ['SKU', 'Zone', 'Pick events', 'Count events', 'Wrong-location rate', 'Short pick rate',
                                'Count discrepancy rate', 'Priority score'],
           prio_rows, ['@', '@', '#,##0', '#,##0', '0.0%', '0.0%', '0.0%', '0.000'], [12, 12, 12, 12, 16, 14, 18, 14],
           'SQL query 08. Score = average percentile rank of the three rates (1 = worst). Min 60 picks and 8 counts per SKU.')

src = 'Live GOV.UK API' if audit['calendar_source_type'] == 'live_public_api' else 'Offline copy of GOV.UK API data'
dq_rows = [['Raw pick records', audit['pick_raw_records']], ['Duplicate pick exports removed', audit['pick_duplicate_exports_removed']]]
dq_rows += [[f'Rejected picks: {k.replace("_", " ")}', v] for k, v in audit['pick_rejections_by_reason'].items()]
dq_rows += [['Validated pick events', audit['pick_clean_records']], ['Raw stock count records', audit['stockcount_raw_records']],
            ['Duplicate stock counts removed', audit['stockcount_duplicate_exports_removed']]]
dq_rows += [[f'Rejected counts: {k.replace("_", " ")}', v] for k, v in audit['stockcount_rejections_by_reason'].items()]
dq_rows += [['Validated stock counts', audit['stockcount_clean_records']], ['Bank holiday calendar source', src]]
data_sheet('Data Quality', ['Check', 'Result'], dq_rows, ['@', '#,##0'], [42, 30],
           'Every rejected record is logged with its reason in data/quality/.')

# ---- Chart data: ordered views linked by formula to the data sheets ------
cd = wb.create_sheet('Chart Data')
cd.sheet_view.showGridLines = False
cd['A1'] = 'Helper ranges for dashboard charts. Values are formulas; order is set by build_dashboard.py.'
cd['A1'].font = font(9, INK_3, italic=True)


def lookup(sheet, col, key_cell):
    return f"=INDEX('{sheet}'!${col}$2:${col}$6,MATCH({key_cell},'{sheet}'!$A$2:$A$6,0))"


def block(row, title, keys, sheet, col, fmt):
    cd.cell(row, 1, title).font = font(9, INK, True)
    for k, key in enumerate(keys):
        cd.cell(row + 1 + k, 1, key).font = font(9)
        c = cd.cell(row + 1 + k, 2, lookup(sheet, col, f'A{row + 1 + k}')); c.number_format = fmt; c.font = font(9)
    return row + 1, row + len(keys)


z = zone.assign(gsp=zone.benchmark_gap_hours * 3600 / zone.pick_events)
gap_keys = list(z.sort_values('gsp', ascending=False).zone)
slow_keys = list(z.sort_values('slow_pick_rate', ascending=False).zone)
stock_keys = list(stock.assign(r=stock.exact_matches / stock.count_events).sort_values('r').zone)
g1 = block(3, 'Gap seconds per pick', gap_keys, 'Zone KPIs', 'N', '0.0')
g2 = block(10, 'Slow pick rate', slow_keys, 'Zone KPIs', 'K', '0.0%')
g3 = block(17, 'Stock count exact match', stock_keys, 'Stock Accuracy', 'E', '0.0%')
cd.column_dimensions['A'].width = 34; cd.column_dimensions['B'].width = 12
cd.cell(24, 1, 'Recount priority (label, score)').font = font(9, INK, True)
for k, r in enumerate(prio.itertuples()):
    cd.cell(25 + k, 1, f"='Recount Priority'!A{k+2}&\"  ·  \"&'Recount Priority'!B{k+2}").font = font(9)
    c = cd.cell(25 + k, 2, f"='Recount Priority'!H{k+2}"); c.number_format = '0.00'; c.font = font(9)
g4 = (25, 24 + len(prio))
cd.cell(36, 1, 'Weekly labels').font = font(9, INK, True)
nweeks = len(weekly)
for k in range(nweeks):
    # Month name on the first week of each month only, so the axis reads cleanly.
    c = cd.cell(37 + k, 1, f"=IF(DAY('Weekly Trend'!A{k+2})<=7,TEXT('Weekly Trend'!A{k+2},\"mmm\"),\"\")"); c.font = font(9)

# ---- Chart styling helpers ---------------------------------------------------


def txt(size=800, color=INK_2, bold=False):
    cp = CharacterProperties(sz=size, b=bold, solidFill=color, latin=DFont(typeface=FONT))
    return RichText(p=[Paragraph(pPr=ParagraphProperties(defRPr=cp), endParaRPr=cp)])


def frame(ch, w, h):
    ch.width, ch.height = w, h
    ch.roundedCorners = False
    ch.legend = None
    ch.graphical_properties = GraphicalProperties(ln=LineProperties(noFill=True))
    ch.plot_area.graphicalProperties = GraphicalProperties(noFill=True, ln=LineProperties(noFill=True))
    for ax in (ch.x_axis, ch.y_axis):
        ax.delete = False
        ax.txPr = txt()
        ax.graphicalProperties = GraphicalProperties(ln=LineProperties(solidFill=RULE))
    ch.y_axis.majorGridlines = None
    ch.x_axis.majorTickMark = ch.y_axis.majorTickMark = 'none'
    ch.y_axis.minorTickMark = ch.x_axis.minorTickMark = 'none'


def zone_bars(first_last, keys, fmt, horizontal_axis_max=None):
    ch = BarChart(); ch.type = 'col'; ch.gapWidth = 70
    frame(ch, 13.0, 7.0)
    ch.add_data(Reference(cd, min_col=2, min_row=first_last[0], max_row=first_last[1]), titles_from_data=False)
    ch.set_categories(Reference(cd, min_col=1, min_row=first_last[0], max_row=first_last[1]))
    s = ch.series[0]
    s.graphicalProperties = GraphicalProperties(solidFill=MUTED, ln=LineProperties(noFill=True))
    for k, key in enumerate(keys):
        if key == HIGHLIGHT_ZONE:
            s.dPt.append(DataPoint(idx=k, spPr=GraphicalProperties(solidFill=ACCENT, ln=LineProperties(noFill=True))))
    s.dLbls = DataLabelList(); s.dLbls.showVal = True; s.dLbls.numFmt = fmt; s.dLbls.position = 'outEnd'
    for flag in ('showSerName', 'showCatName', 'showLegendKey', 'showPercent'): setattr(s.dLbls, flag, False)
    s.dLbls.txPr = txt(900, INK, True)
    ch.y_axis.delete = True                      # values sit on the bars instead of an axis
    ch.y_axis.scaling.min = 0                    # bars always start at zero
    if horizontal_axis_max: ch.y_axis.scaling.max = horizontal_axis_max
    ch.x_axis.txPr = txt(850, INK_2)
    return ch


# ---- Dashboard layout ---------------------------------------------------------
NCOL = 21                                   # A = margin, B..T content (19 cols), U = margin
dash.sheet_view.showGridLines = False
dash.sheet_view.zoomScale = 100
dash.column_dimensions['A'].width = 3
for j in range(2, NCOL): dash.column_dimensions[L(j)].width = 7.6
dash.column_dimensions[L(NCOL)].width = 3
for r in range(1, 96):
    dash.row_dimensions[r].height = 15
    for j in range(1, NCOL + 1): dash.cell(r, j).fill = fill(CANVAS)


def paint(r1, c1, r2, c2, color, border=False):
    for r in range(r1, r2 + 1):
        for j in range(c1, c2 + 1):
            c = dash.cell(r, j); c.fill = fill(color)
            if border:
                c.border = Border(left=thin if j == c1 else None, right=thin if j == c2 else None,
                                  top=thin if r == r1 else None, bottom=thin if r == r2 else None)


def put(r, c, value, f, align='left', merge_to=None, valign='center'):
    cell = dash.cell(r, c, value); cell.font = f
    cell.alignment = Alignment(horizontal=align, vertical=valign, wrap_text=False)
    if merge_to: dash.merge_cells(start_row=r, start_column=c, end_row=r, end_column=merge_to)
    return cell


# Header band
paint(2, 2, 5, 20, NAVY)
dash.row_dimensions[2].height = 10; dash.row_dimensions[3].height = 30; dash.row_dimensions[4].height = 18; dash.row_dimensions[5].height = 12
put(3, 2, 'Warehouse Intelligence', font(20, 'FFFFFF', True), merge_to=13).alignment = Alignment(horizontal='left', indent=1, vertical='center')
put(4, 2, 'Picking efficiency & inventory accuracy  ·  5 Jan to 31 Oct 2026', font(10, 'B9C4D6'), merge_to=13).alignment = Alignment(horizontal='left', indent=1, vertical='center')
put(3, 14, 'EXECUTIVE DASHBOARD', font(8, '8FA3C0', True), align='right', merge_to=20).alignment = Alignment(horizontal='right', indent=1, vertical='center')
put(4, 14, 'Simulated WMS data · GOV.UK bank holidays', font(8, '8FA3C0'), align='right', merge_to=20).alignment = Alignment(horizontal='right', indent=1, vertical='center')
dash.row_dimensions[6].height = 14

# KPI cards: 5 cards x 3 cols, gutters at E, I, M, Q
Z = "'Zone KPIs'!"
kpis = [
    ('VALIDATED PICKS', f'=SUM({Z}B2:B6)', '#,##0', f'=TEXT(SUM({Z}J2:J6),"#,##0")&" active pick hours"'),
    ('UNIT FILL RATE', f'=SUM({Z}D2:D6)/SUM({Z}C2:C6)', '0.0%', f'=TEXT(SUM({Z}D2:D6),"#,##0")&" of "&TEXT(SUM({Z}C2:C6),"#,##0")&" units"'),
    ('SLOW PICK RATE', f'=SUM({Z}E2:E6)/SUM({Z}B2:B6)', '0.0%', f'=TEXT(SUM({Z}E2:E6)-{metrics["slow_picks_with_breakdown_share"]}*SUM({Z}E2:E6),"#,##0")&" excl. pallet breakdowns"'),
    ('WRONG-LOCATION SCANS', f'=SUM({Z}F2:F6)/SUM({Z}B2:B6)', '0.00%', f'=TEXT(SUM({Z}F2:F6),"#,##0")&" scans at wrong location"'),
    ('BENCHMARK GAP', f'=SUM({Z}I2:I6)', '0.0" h"', '="Time above per-pick benchmark"'),
]
dash.row_dimensions[7].height = 6; dash.row_dimensions[8].height = 16; dash.row_dimensions[9].height = 34
dash.row_dimensions[10].height = 16; dash.row_dimensions[11].height = 8
for k, (label, formula, fmt, ctx) in enumerate(kpis):
    c1 = 2 + k * 4; c2 = c1 + 2
    paint(7, c1, 11, c2, CARD, border=True)
    for j in range(c1, c2 + 1):
        dash.cell(7, j).border = Border(top=Side(style='medium', color=NAVY_2),
                                         left=thin if j == c1 else None, right=thin if j == c2 else None)
    put(8, c1, label, font(7.5, INK_3, True), merge_to=c2).alignment = Alignment(horizontal='left', indent=1, vertical='bottom')
    v = put(9, c1, formula, font(22, INK, True), merge_to=c2); v.number_format = fmt
    v.alignment = Alignment(horizontal='left', indent=1, vertical='center')
    put(10, c1, ctx, font(8, INK_2), merge_to=c2).alignment = Alignment(horizontal='left', indent=1, vertical='top')
# The slow-pick context needs a whole-number note, so state it as a plain fact line instead.
dash.cell(10, 10).value = f'=TEXT(ROUND(SUM({Z}E2:E6)*(1-{metrics["slow_picks_with_breakdown_share"]}),0),"#,##0")&" without a pallet breakdown"'

dash.row_dimensions[12].height = 14


def card(r1, c1, r2, c2, title, subtitle):
    paint(r1, c1, r2, c2, CARD, border=True)
    dash.row_dimensions[r1].height = 22; dash.row_dimensions[r1 + 1].height = 16
    put(r1, c1, title, font(11, INK, True), merge_to=c2, valign='bottom').alignment = Alignment(horizontal='left', indent=1, vertical='bottom')
    put(r1 + 1, c1, subtitle, font(8.5, INK_3), merge_to=c2, valign='top').alignment = Alignment(horizontal='left', indent=1, vertical='top')


h = lambda key: f'{z.set_index("zone").loc[HIGHLIGHT_ZONE, key]:.0f}'
hb_gap = z.set_index('zone').loc[HIGHLIGHT_ZONE, 'gsp']
hb_slow = z.set_index('zone').loc[HIGHLIGHT_ZONE, 'slow_pick_rate']
st = stock.assign(r=stock.exact_matches / stock.count_events).set_index('zone')
n_hb = int((prio.zone == HIGHLIGHT_ZONE).sum())

# Row 1 of charts
card(13, 2, 30, 10, f'High-Bay loses most time per pick: {hb_gap:.0f}s above benchmark',
     'Benchmark-gap seconds per pick, by zone. Totals favour busy zones; this shows intensity.')
card(13, 12, 30, 20, f'High-Bay has the highest slow-pick rate at {hb_slow:.0%}',
     'Share of picks over 125% of the per-pick benchmark, by zone.')
c = zone_bars(g1, gap_keys, '0.0"s"'); dash.add_chart(c, 'B16')
c = zone_bars(g2, slow_keys, '0%', 0.5); dash.add_chart(c, 'L16')
dash.row_dimensions[31].height = 14

# Row 2 of charts
card(32, 2, 49, 10, f'High-Bay stock records match only {st.loc[HIGHLIGHT_ZONE, "r"]:.0%} of physical counts',
     'Cycle counts where physical quantity equals system quantity. Axis starts at zero.')
card(32, 12, 49, 20, f'{n_hb} of the top 10 recount priorities are High-Bay SKUs',
     'Combined score of wrong-location, short-pick and count-discrepancy rates (1 = worst).')
c = zone_bars(g3, stock_keys, '0%', 1.0); dash.add_chart(c, 'B35')

pc = BarChart(); pc.type = 'bar'; pc.gapWidth = 45
frame(pc, 13.0, 7.0)
pc.add_data(Reference(cd, min_col=2, min_row=g4[0], max_row=g4[1]), titles_from_data=False)
pc.set_categories(Reference(cd, min_col=1, min_row=g4[0], max_row=g4[1]))
ps = pc.series[0]
ps.graphicalProperties = GraphicalProperties(solidFill=MUTED, ln=LineProperties(noFill=True))
for k, r in enumerate(prio.itertuples()):
    if r.zone == HIGHLIGHT_ZONE:
        ps.dPt.append(DataPoint(idx=k, spPr=GraphicalProperties(solidFill=ACCENT, ln=LineProperties(noFill=True))))
ps.dLbls = DataLabelList(); ps.dLbls.showVal = True; ps.dLbls.numFmt = '0.00'; ps.dLbls.position = 'outEnd'
for flag in ('showSerName', 'showCatName', 'showLegendKey', 'showPercent'): setattr(ps.dLbls, flag, False)
ps.dLbls.txPr = txt(800, INK, True)
pc.x_axis.scaling.orientation = 'maxMin'      # highest priority at the top
pc.y_axis.delete = True; pc.y_axis.scaling.min = 0; pc.y_axis.scaling.max = 1.1
pc.x_axis.txPr = txt(800, INK_2)
dash.add_chart(pc, 'L35')
dash.row_dimensions[50].height = 14

# Weekly trend, full width
card(51, 2, 68, 20, f'Slow-pick rate holds steady between {metrics["weekly_slow_rate_min"]:.0%} and {metrics["weekly_slow_rate_max"]:.0%} every week',
     'Weekly share of slow picks against the period average (dashed). No sustained drift across the year.')
lc = LineChart()
frame(lc, 27.6, 7.0)
lc.add_data(Reference(wb['Weekly Trend'], min_col=6, min_row=1, max_row=nweeks + 1), titles_from_data=True)
lc.add_data(Reference(wb['Weekly Trend'], min_col=7, min_row=1, max_row=nweeks + 1), titles_from_data=True)
lc.set_categories(Reference(cd, min_col=1, min_row=37, max_row=36 + nweeks))
main, avg = lc.series
main.graphicalProperties = GraphicalProperties(ln=LineProperties(solidFill=ACCENT, w=28575))
main.smooth = False; main.marker.symbol = 'none'
avg.graphicalProperties = GraphicalProperties(ln=LineProperties(solidFill='8A8F98', w=12700, prstDash='dash'))
avg.smooth = False; avg.marker.symbol = 'none'
lc.y_axis.scaling.min = 0; lc.y_axis.scaling.max = 0.4; lc.y_axis.majorUnit = 0.1
lc.y_axis.numFmt = '0%'
from openpyxl.chart.axis import ChartLines
lc.y_axis.majorGridlines = ChartLines(spPr=GraphicalProperties(ln=LineProperties(solidFill=GRID)))
lc.y_axis.graphicalProperties = GraphicalProperties(ln=LineProperties(noFill=True))
lc.x_axis.tickLblSkip = 1
lc.x_axis.txPr = txt(800, INK_2)
from openpyxl.chart.legend import Legend
lc.legend = Legend(); lc.legend.position = 't'; lc.legend.overlay = False; lc.legend.txPr = txt(800, INK_2)
dash.add_chart(lc, 'B54')
dash.row_dimensions[69].height = 14

# Key findings panel
paint(70, 2, 77, 20, CARD, border=True)
dash.row_dimensions[70].height = 24
put(70, 2, 'Key findings', font(11, INK, True), merge_to=20, valign='bottom').alignment = Alignment(horizontal='left', indent=1, vertical='bottom')
findings = [
    ('High-Bay first.', f'Worst zone on every per-pick measure and lowest stock accuracy; {n_hb} of the top 10 recount SKUs.'),
    ('Pallet breakdowns drive slowness.', f'{metrics["slow_picks_with_breakdown_share"]:.0%} of slow picks involve one; without them the slow rate is {metrics["slow_pick_rate_excluding_breakdowns"]:.1%}.'),
    ('Late shift is slower like for like.', f'{metrics["late_units_per_hour"]:.1f} vs {metrics["early_units_per_hour"]:.1f} units per active hour; only {metrics["shift_gap_explained_by_breakdown_mix_seconds"]:.1f}s of the {metrics["late_minus_early_mean_pick_seconds"]:.1f}s gap is breakdown mix.'),
    ('Plan for pre-holiday peaks.', f'{metrics["preholiday_5d_picks_per_day"]:.0f} picks per day in the 5 days before a bank holiday vs {metrics["other_days_picks_per_day"]:.0f} otherwise.'),
]
for k, (lead, body) in enumerate(findings):
    r = 71 + k
    dash.row_dimensions[r].height = 20
    put(r + 0, 2, f'{k+1}', font(9, ACCENT, True), align='center')
    put(r + 0, 3, lead, font(9, INK, True), merge_to=6).alignment = Alignment(vertical='center')
    put(r + 0, 7, body, font(9, INK_2), merge_to=20).alignment = Alignment(vertical='center')
dash.row_dimensions[75].height = 10
put(76, 2, 'Descriptive associations from simulated data, not proven causes. Benchmark is analyst-defined, not an SLA.',
    font(8, INK_3, italic=True), merge_to=20).alignment = Alignment(horizontal='left', indent=1, vertical='center')
dash.row_dimensions[77].height = 8

# Print setup: one landscape page
dash.print_area = 'A1:U78'
dash.page_setup.orientation = 'landscape'; dash.page_setup.paperSize = dash.PAPERSIZE_A4
dash.sheet_properties.pageSetUpPr.fitToPage = True
dash.page_setup.fitToWidth = 1; dash.page_setup.fitToHeight = 1
dash.print_options.horizontalCentered = True
dash.page_margins.left = dash.page_margins.right = 0.3; dash.page_margins.top = dash.page_margins.bottom = 0.3

wb.move_sheet('Chart Data', offset=0)
DEST.parent.mkdir(exist_ok=True)
wb.save(DEST)
print('Dashboard written:', DEST)
