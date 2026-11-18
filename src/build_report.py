"""Write reproducible summary tables and a management brief from the SQLite data."""
from pathlib import Path
import sqlite3, json
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data'/'processed'; REPORT=ROOT/'reports'
REPORT.mkdir(exist_ok=True)
con=sqlite3.connect(ROOT/'warehouse_operations.sqlite')

def query(sql):return pd.read_sql_query(sql,con)
zone=query('''SELECT zone, COUNT(*) AS pick_events, SUM(qty_requested) AS requested_units,
SUM(qty_picked) AS picked_units, SUM(slow_pick) AS slow_picks,
SUM(location_mismatch) AS mismatched_scans, SUM(pallet_breakdown) AS breakdown_events,
SUM(is_short_pick) AS short_picks, ROUND(SUM(benchmark_gap_seconds)/3600.0,2) AS benchmark_gap_hours,
ROUND(SUM(duration_seconds)/3600.0,2) AS active_pick_hours
FROM picks_clean GROUP BY zone ORDER BY benchmark_gap_hours DESC''')
zone['slow_pick_rate']=zone.slow_picks/zone.pick_events
zone['mismatch_rate']=zone.mismatched_scans/zone.pick_events
zone['breakdown_rate']=zone.breakdown_events/zone.pick_events
zone['fill_rate']=zone.picked_units/zone.requested_units
zone.to_csv(OUT/'zone_summary.csv',index=False)
shifts=query('''SELECT shift,COUNT(*) AS pick_events,SUM(qty_picked) AS picked_units,
SUM(slow_pick) AS slow_picks,ROUND(SUM(duration_seconds)/3600.0,2) AS active_pick_hours,
ROUND(SUM(benchmark_gap_seconds)/3600.0,2) AS benchmark_gap_hours
FROM picks_clean GROUP BY shift ORDER BY shift''')
shifts['units_per_active_pick_hour']=shifts.picked_units/shifts.active_pick_hours
shifts['slow_pick_rate']=shifts.slow_picks/shifts.pick_events
shifts.to_csv(OUT/'shift_summary.csv',index=False)
stock=query('''SELECT zone, COUNT(*) AS count_events, SUM(exact_match) AS exact_matches,
SUM(absolute_variance_units) AS abs_variance_units
FROM cycle_counts_clean GROUP BY zone ORDER BY zone''')
stock['exact_match_rate']=stock.exact_matches/stock.count_events
stock.to_csv(OUT/'stock_accuracy_by_zone.csv',index=False)
# Week label = the Monday the week starts on (strftime %w: Sunday=0), clearer than a week number.
weekly=query('''SELECT date(pick_date, '-'||((CAST(strftime('%w',pick_date) AS INT)+6)%7)||' days') AS week_start,
COUNT(*) AS pick_events,SUM(qty_picked) AS picked_units, SUM(slow_pick) AS slow_picks,
ROUND(SUM(benchmark_gap_seconds)/3600.0,2) AS benchmark_gap_hours
FROM picks_clean GROUP BY week_start ORDER BY week_start''')
weekly['slow_pick_rate']=weekly.slow_picks/weekly.pick_events
weekly.to_csv(OUT/'weekly_trend.csv',index=False)

picks=int(zone.pick_events.sum());rq=int(zone.requested_units.sum());picked=int(zone.picked_units.sum())
slow=float(zone.slow_picks.sum()/picks);fill=picked/rq
miss=float(zone.mismatched_scans.sum()/picks)
benchmark_hours=float(zone.benchmark_gap_hours.sum())
late=shifts.set_index('shift').loc['Late'];early=shifts.set_index('shift').loc['Early']
high=stock.set_index('zone').loc['High-Bay']; bulk=zone.set_index('zone').loc['Bulk']
# Extra evidence used in the brief.
zone['gap_seconds_per_pick']=zone.benchmark_gap_hours*3600/zone.pick_events
zone.to_csv(OUT/'zone_summary.csv',index=False)
hb=zone.set_index('zone').loc['High-Bay']
mix=query('''SELECT shift,pallet_breakdown,COUNT(*) AS n,AVG(duration_seconds) AS mean_sec FROM picks_clean GROUP BY shift,pallet_breakdown''').set_index(['shift','pallet_breakdown'])
def mean_sec(shift,mix_shift):
    w=mix.loc[mix_shift,'n']/mix.loc[mix_shift,'n'].sum()
    return float((w*mix.loc[shift,'mean_sec']).sum())
shift_gap=mean_sec('Late','Late')-mean_sec('Early','Early')
mix_part=mean_sec('Late','Late')-mean_sec('Late','Early')   # how much disappears if Late had Early's breakdown share
slow_split=query('SELECT SUM(slow_pick) AS slow, SUM(slow_pick*pallet_breakdown) AS slow_br, AVG(CASE WHEN pallet_breakdown=0 THEN slow_pick END) AS slow_nobr FROM picks_clean').iloc[0]
hol=query('''WITH d AS (SELECT pick_date,MAX(is_preholiday_5d) AS pre,COUNT(*) AS n FROM v_picks_enriched WHERE is_bank_holiday=0 GROUP BY pick_date)
SELECT pre,AVG(n) AS per_day FROM d GROUP BY pre''').set_index('pre').per_day
sql_text=(ROOT/'sql'/'analysis_queries.sql').read_text()
q8=sql_text.split('-- 08.')[1].split('-- 09.')[0].split('\n',1)[1]
priority=query('\n'.join(l for l in q8.splitlines() if not l.strip().startswith('--')).strip().rstrip(';'))
priority.to_csv(OUT/'sku_recount_priority.csv',index=False)
hb_in_top10=int((priority.zone=='High-Bay').sum())
qa=json.loads((ROOT/'data'/'quality'/'quality_audit.json').read_text())

metrics={'pick_events':picks,'requested_units':rq,'picked_units':picked,
         'fill_rate':round(fill,5),'slow_pick_rate':round(slow,5),
         'location_mismatch_rate':round(miss,5),'benchmark_gap_hours':round(benchmark_hours,2),
         'late_units_per_hour':round(float(late.units_per_active_pick_hour),2),
         'early_units_per_hour':round(float(early.units_per_active_pick_hour),2),
         'high_bay_inventory_exact_match_rate':round(float(high.exact_match_rate),5),
         'slow_picks_with_breakdown_share':round(float(slow_split.slow_br/slow_split.slow),4),
         'slow_pick_rate_excluding_breakdowns':round(float(slow_split.slow_nobr),5),
         'late_minus_early_mean_pick_seconds':round(shift_gap,2),'shift_gap_explained_by_breakdown_mix_seconds':round(mix_part,2),
         'preholiday_5d_picks_per_day':round(float(hol.loc[1]),1),'other_days_picks_per_day':round(float(hol.loc[0]),1),
         'high_bay_skus_in_top10_recount_priority':hb_in_top10,
         'weekly_slow_rate_min':round(float(weekly.slow_pick_rate.min()),5),'weekly_slow_rate_max':round(float(weekly.slow_pick_rate.max()),5),
         'bank_holidays_source_type':qa['calendar_source_type']}
(REPORT/'metrics.json').write_text(json.dumps(metrics,indent=2))

brief=f'''# Warehouse Intelligence: Management Decision Brief

**Prepared for:** Distribution Centre Operations Manager  
**Period analysed:** 5 January to 31 October 2026  
**Data:** {picks:,} validated picking events and {int(stock.count_events.sum()):,} stock counts from a simulated WMS, enriched with the GOV.UK bank holiday calendar.

## The decision
Where should a warehouse operations manager focus a targeted improvement pilot to reduce slow picks, stock inaccuracies and re-handling?

## Executive scorecard
- **{picks:,} valid pick events**, after removing {qa['pick_duplicate_exports_removed']} duplicated exports and excluding {qa['pick_rejected_records']} invalid raw picks.
- **{fill*100:.2f}% unit-fill rate** ({picked:,} of {rq:,} requested units).
- **{slow*100:.1f}% slow-pick rate** (pick duration more than 125% of a simplified per-item benchmark).
- **{miss*100:.2f}% mismatched location-scans** after normalization against SKU master locations.
- **{benchmark_hours:.1f} benchmark-gap hours**, the sum of positive differences between recorded pick durations and the benchmark. This is *not* proven recoverable labour time.

## Findings and possible actions

### 1. Prioritise High-Bay for stock-location verification
High-Bay is the worst zone on every per-pick measure: **{high.exact_match_rate*100:.1f}% exact stock-count match** ({int(high.exact_matches):,}/{int(high.count_events):,} counts, lowest of five zones), **{hb.mismatch_rate*100:.2f}% wrong-location scans**, **{hb.short_picks/hb.pick_events*100:.2f}% short picks** and **{hb.gap_seconds_per_pick:.0f} seconds above benchmark per pick**. It ranks last on *total* benchmark-gap hours only because it handles the fewest picks. **{hb_in_top10} of the top 10 SKUs** on the combined recount priority score (`sku_recount_priority.csv`) are High-Bay. **Pilot:** recount those SKUs and check their location labels, then compare exact-match and mismatch rates before and after.

### 2. Review the pallet-breakdown workflow, starting in Bulk
Bulk has the largest total benchmark gap (**{bulk.benchmark_gap_hours:.1f} hours**), partly because it is a high-volume zone, and the highest breakdown share (**{bulk.breakdown_rate*100:.1f}%** of picks). Across the site, **{slow_split.slow_br/slow_split.slow*100:.0f}% of all slow picks involve a pallet breakdown**; without breakdowns the slow-pick rate falls from {slow*100:.1f}% to {slow_split.slow_nobr*100:.1f}%. The benchmark gives no time allowance for breakdowns, so the slow-pick KPI is largely a breakdown counter. Heavy or complex picks may also be more likely to need breakdown, so this is association, not proof of cause. **Pilot:** review stock presentation for the 20 highest-frequency Bulk SKUs; compare median time for comparable SKUs, shifts and quantities before and after.

### 3. Investigate the late-shift performance difference
Early processed **{early.units_per_active_pick_hour:.1f} picked units per active picking hour**, Late **{late.units_per_active_pick_hour:.1f}**. Late picks average **{shift_gap:.1f} seconds** longer. About **{mix_part:.1f} seconds** of that comes from Late doing more pallet breakdowns; the rest persists within like-for-like picks (see SQL query 09). SKU mix, zone mix and quantities are near-identical between shifts. This is active picking time, not paid hours. **Pilot:** observe congestion, replenishment timing and handovers on Late before changing headcount.

### 4. Plan labour for the week before bank holidays
Operating days in the five days before a bank holiday averaged **{hol.loc[1]:.0f} picks**, versus **{hol.loc[0]:.0f}** on other days. Slow-pick rates barely moved, so the site absorbed the volume, but this is a staffing signal. Mondays and Fridays are also busier than mid-week and Saturdays are quietest. This is observational context and, with synthetic data, not evidence of a real holiday effect.

### 5. Introduce measurable process controls
Build a weekly dashboard showing slow-pick %, fill rate, mismatch %, exact stock-count match %, breakdown %, and benchmark-gap hours by zone/shift. Report breakdown picks separately or give them their own target. Set initial alert thresholds *with supervisors* rather than presenting synthetic benchmarks as genuine service-level agreements.

## Caveats and recommended verification
- The operational data is simulated. Findings show what the analysis would surface in a real site, not measured facts about one.
- More average seconds on a breakdown pick does **not** establish breakdown *caused* the whole difference (confounding by SKU size/weight, order quantities and zone).
- The simple duration target is an **illustrative analyst-defined benchmark**, not an existing business target. Recalibrate with business process data.
- The calendar enrichment is a context variable; it is not evidence that bank holidays cause a demand increase.
- A proper evaluation would compare matched items/shifts before and after a pilot, with confidence intervals and capacity constraints.

## Four-week pilot suggestion
**Week 1:** Verify location codes and target definitions with stakeholders.  
**Week 2:** Audit 20 High-Bay/Bulk SKUs and document re-handling reasons.  
**Week 3:** Compare matched picks by SKU, shift and quantity; test a small layout/label change.  
**Week 4:** Measure change in discrepancy rate and per-pick time; scale only if benefits persist.

## Data and calculations
Use `sql/analysis_queries.sql` and the dashboard data exports under `data/processed/`. QA evidence is in `data/quality/quality_audit.json`.
'''
(REPORT/'executive_brief.md').write_text(brief,encoding='utf-8')
print('Built metric extracts and management brief. KPI:',json.dumps(metrics,indent=2))
