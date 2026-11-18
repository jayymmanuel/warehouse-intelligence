"""Clean raw data, document rejected records, enrich calendar and load portable SQLite."""
import json, sqlite3
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
RAW=ROOT/'data'/'raw'; OUT=ROOT/'data'/'processed'; QA=ROOT/'data'/'quality'
DB=ROOT/'warehouse_operations.sqlite'
OUT.mkdir(exist_ok=True,parents=True); QA.mkdir(exist_ok=True,parents=True)

skus=pd.read_csv(RAW/'sku_master.csv',dtype={'sku_id':str,'expected_location':str})
skus['zone']=skus['zone'].str.strip()
sku_map=skus.set_index('sku_id')
raw=pd.read_csv(RAW/'picks_raw.csv',dtype={'event_id':str,'sku_id':str,'expected_location':str,'scanned_location':str})
audit={'pick_raw_records':int(len(raw))}
raw=raw.drop_duplicates(subset=['event_id'],keep='first').copy()
audit['pick_duplicate_exports_removed']=audit['pick_raw_records']-len(raw)
for name in ['zone','expected_location','scanned_location','sku_id','shift','pallet_breakdown']:
    raw[name]=raw[name].astype('string').str.strip()
raw['zone']=raw['zone'].str.lower().replace({k.lower():k for k in skus.zone.unique()})
for name in ['expected_location','scanned_location']:
    raw[name]=raw[name].str.upper()
for name in ['qty_requested','qty_picked','duration_seconds']:
    raw[name]=pd.to_numeric(raw[name],errors='coerce')
raw['pick_date']=pd.to_datetime(raw['pick_date'],errors='coerce')
raw['rejection_reason']=''
checks=[('invalid_or_missing_date',raw.pick_date.isna()),
        ('unknown_sku',~raw.sku_id.isin(skus.sku_id)),
        ('invalid_requested_quantity',raw.qty_requested.isna()|(raw.qty_requested<=0)),
        ('invalid_picked_quantity',raw.qty_picked.isna()|(raw.qty_picked<0)|(raw.qty_picked>raw.qty_requested)),
        ('invalid_duration',raw.duration_seconds.isna()|(raw.duration_seconds<=0)|(raw.duration_seconds>1800))]
for label, mask in checks:
    raw.loc[mask & (raw.rejection_reason==''),'rejection_reason']=label
rejected=raw[raw.rejection_reason!=''].copy()
rejected.to_csv(QA/'rejected_picks.csv',index=False)
p=raw[raw.rejection_reason==''].drop(columns=['rejection_reason']).copy()
p=p.merge(skus[['sku_id','category','abc_class','zone','expected_location','unit_weight_kg','unit_cost_gbp']].rename(columns={'zone':'master_zone','expected_location':'master_location'}),on='sku_id',how='left',validate='many_to_one')
p['zone_corrected_from_master']=(p['zone']!=p['master_zone']).astype(int)
p['zone']=p['master_zone']
p['expected_location']=p['master_location']
p['location_mismatch']=(p['scanned_location']!=p['expected_location']).astype(int)
p['is_short_pick']=(p['qty_picked']<p['qty_requested']).astype(int)
p['pallet_breakdown']=(p['pallet_breakdown'].str.upper()=='Y').astype(int)
p['target_seconds']=43+5.9*p.qty_requested + 9*(p.unit_weight_kg>5).astype(int)+4*(p.zone=='High-Bay').astype(int)
p['benchmark_gap_seconds']=(p.duration_seconds-p.target_seconds).clip(lower=0)
p['slow_pick']=(p.duration_seconds>p.target_seconds*1.25).astype(int)
p['pick_date']=p.pick_date.dt.strftime('%Y-%m-%d')
p['qty_requested']=p.qty_requested.astype(int);p['qty_picked']=p.qty_picked.astype(int)
p['duration_seconds']=p.duration_seconds.astype(float)
p['picked_weight_kg']=(p.qty_picked * p.unit_weight_kg).round(2)
p=p.drop(columns=['master_zone','master_location'])

cc=pd.read_csv(RAW/'cycle_counts_raw.csv')
audit['stockcount_raw_records']=int(len(cc))
cc=cc.drop_duplicates('count_id').copy()
audit['stockcount_duplicate_exports_removed']=audit['stockcount_raw_records']-len(cc)
cc['count_date']=pd.to_datetime(cc.count_date,errors='coerce')
for name in ['physical_qty','system_qty']:
    cc[name]=pd.to_numeric(cc[name],errors='coerce')
cc['sku_id']=cc.sku_id.astype(str).str.strip()
cc['location']=cc.location.astype(str).str.strip().str.upper()
# Same first-failing-reason approach as picks, so every rejected count is explained.
cc['rejection_reason']=''
count_checks=[('invalid_or_missing_date',cc.count_date.isna()),
              ('unknown_sku',~cc.sku_id.isin(skus.sku_id)),
              ('missing_physical_qty',cc.physical_qty.isna()),
              ('missing_system_qty',cc.system_qty.isna()),
              ('negative_quantity',(cc.physical_qty<0)|(cc.system_qty<0))]
for label,mask in count_checks:
    cc.loc[mask&(cc.rejection_reason==''),'rejection_reason']=label
valid=cc.rejection_reason==''
cc[~valid].to_csv(QA/'rejected_counts.csv',index=False)
cc=cc.drop(columns=['rejection_reason'])
cc=cc[valid].merge(skus[['sku_id','zone','category','abc_class']],on='sku_id',how='left',validate='many_to_one').copy()
cc['count_date']=cc.count_date.dt.strftime('%Y-%m-%d')
cc['system_qty']=cc.system_qty.astype(int);cc['physical_qty']=cc.physical_qty.astype(int)
cc['absolute_variance_units']=(cc.physical_qty-cc.system_qty).abs()
cc['exact_match']=(cc.physical_qty==cc.system_qty).astype(int)
cc['count_discrepancy']=(cc.physical_qty!=cc.system_qty).astype(int)

roster=pd.read_csv(RAW/'shift_roster.csv')
assert not roster[['date','shift']].duplicated().any(), 'Roster must be one row per day/shift'

with (ROOT/'data/external/uk_bank_holidays.json').open(encoding='utf-8') as f:
    hol=json.load(f)
hol_dates=pd.to_datetime([e['date'] for e in hol['events']])
holidays={e['date']:e['title'] for e in hol['events']}
days=pd.date_range('2026-01-01','2026-11-04')
cal=pd.DataFrame({'date':days.strftime('%Y-%m-%d')})
cal['day_of_week']=days.day_name()
cal['is_weekend']=(days.weekday>=5).astype(int)
cal['is_bank_holiday']=cal.date.isin(holidays.keys()).astype(int)
cal['bank_holiday_name']=cal.date.map(holidays).fillna('')
cal['is_preholiday_3d']=[int(any(0<(d-dt).days<=3 for d in hol_dates)) for dt in days]
# A 3 calendar-day window before a Monday holiday covers only Fri-Sun (one full working day).
# The 5-day window captures the working week before the holiday. Holidays themselves are excluded.
cal['is_preholiday_5d']=[int(any(0<(d-dt).days<=5 for d in hol_dates)) for dt in days]
cal.loc[cal.is_bank_holiday==1,['is_preholiday_3d','is_preholiday_5d']]=0
cal['month']=days.strftime('%Y-%m')
cal['calendar_source_type']=hol['source_type']

# Store SQLite and accessible processed CSV extracts. Roster preserves its own daily/shift grain.
with sqlite3.connect(DB) as con:
    for table,frame in [('sku_master',skus),('picks_clean',p),('cycle_counts_clean',cc),('shift_roster',roster),('calendar',cal)]:
        frame.to_sql(table,con,if_exists='replace',index=False)
    con.executescript('''
CREATE INDEX IF NOT EXISTS idx_pick_day ON picks_clean(pick_date);
CREATE INDEX IF NOT EXISTS idx_pick_zone ON picks_clean(zone);
CREATE INDEX IF NOT EXISTS idx_pick_sku ON picks_clean(sku_id);
CREATE INDEX IF NOT EXISTS idx_count_sku ON cycle_counts_clean(sku_id);
CREATE INDEX IF NOT EXISTS idx_calendar_day ON calendar(date);
DROP VIEW IF EXISTS v_daily_ops;
DROP VIEW IF EXISTS v_picks_enriched;
CREATE VIEW v_picks_enriched AS
SELECT p.*, c.day_of_week, c.month, c.is_bank_holiday, c.is_preholiday_3d, c.is_preholiday_5d,
       r.planned_headcount, r.actual_headcount, r.absent_headcount
FROM picks_clean p LEFT JOIN calendar c ON p.pick_date=c.date
LEFT JOIN shift_roster r ON p.pick_date=r.date AND p.shift=r.shift;
CREATE VIEW v_daily_ops AS
SELECT p.pick_date, p.shift, p.zone, COUNT(*) AS pick_events,
       SUM(p.qty_requested) AS units_requested, SUM(p.qty_picked) AS units_picked,
       ROUND(SUM(p.qty_picked)*1.0/NULLIF(SUM(p.qty_requested),0),4) AS fill_rate,
       ROUND(AVG(p.duration_seconds),2) AS avg_pick_seconds,
       ROUND(SUM(p.duration_seconds)/3600.0,2) AS measured_pick_hours,
       ROUND(SUM(p.benchmark_gap_seconds)/3600.0,2) AS benchmark_gap_hours,
       ROUND(AVG(p.slow_pick),4) AS slow_pick_rate,
       ROUND(AVG(p.location_mismatch),4) AS location_mismatch_rate,
       ROUND(AVG(p.pallet_breakdown),4) AS breakdown_rate,
       ROUND(AVG(p.is_short_pick),4) AS short_pick_rate,
       MAX(p.is_preholiday_3d) AS is_preholiday_3d,
       MAX(p.planned_headcount) AS planned_headcount,
       MAX(p.actual_headcount) AS actual_headcount
FROM v_picks_enriched p GROUP BY p.pick_date,p.shift,p.zone;
''')
    daily=pd.read_sql_query('SELECT * FROM v_daily_ops ORDER BY pick_date,shift,zone',con)

for name,df in [('picks_clean',p),('cycle_counts_clean',cc),('daily_operations',daily),('calendar',cal)]:
    df.to_csv(OUT/(name+'.csv'),index=False)
audit.update({'pick_rejections_by_reason':rejected.rejection_reason.value_counts().to_dict(),
              'stockcount_rejections_by_reason':pd.read_csv(QA/'rejected_counts.csv').rejection_reason.value_counts().to_dict(),
              'pick_clean_records':int(len(p)),'pick_rejected_records':int(len(rejected)),
              'stockcount_clean_records':int(len(cc)),'stockcount_rejected_records':int((~valid).sum()),
              'zone_corrected_from_sku_master':int(p.zone_corrected_from_master.sum()),
              'calendar_source_type':hol['source_type'], 'bank_holiday_source_url':hol['source']})
(QA/'quality_audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
assert p.event_id.is_unique and cc.count_id.is_unique
assert p.duration_seconds.gt(0).all() and p.qty_requested.ge(p.qty_picked).all()
assert len(daily)>0 and daily.fill_rate.between(0,1).all()
print('SQLite and processed CSV datasets created:',DB)
print('Quality audit:',json.dumps(audit,indent=2))
