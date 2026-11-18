"""Generate repeatable SYNTHETIC warehouse records. Not company data."""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data' / 'raw'
RAW.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(20261118)

ZONES = ['Ambient-A', 'Ambient-B', 'Chilled', 'Bulk', 'High-Bay']
CATEGORIES = ['Grocery', 'Beverages', 'Household', 'Health & Beauty', 'Pet Care', 'Seasonal']
N_SKUS = 180
skus = []
for i in range(N_SKUS):
    zone = rng.choice(ZONES, p=[.28,.22,.17,.21,.12])
    cat = rng.choice(CATEGORIES, p=[.29,.18,.18,.13,.12,.10])
    weight = round(float(rng.lognormal(.15,.85)), 2)
    weight = min(weight, 17.5)
    skus.append(dict(sku_id=f'SKU{i+1:04d}', category=cat, abc_class=rng.choice(['A','B','C'], p=[.25,.38,.37]),
                     zone=zone, expected_location=f'{ZONES.index(zone)+1:02d}-{rng.integers(1,15):02d}-{rng.integers(1,8):02d}',
                     unit_weight_kg=weight, unit_cost_gbp=round(float(rng.uniform(1.1,22.5)),2)))
items = pd.DataFrame(skus)
items.to_csv(RAW / 'sku_master.csv', index=False)

all_days = pd.date_range('2026-01-05','2026-10-31',freq='D')
active_days = all_days[all_days.weekday < 6]
# Mon/Fri busier, Saturday quieter. Note weekday() must be CALLED: a bare d.weekday is a method object and never matches.
weights = np.array([1.28 if d.weekday() in (0,4) else 0.72 if d.weekday() == 5 else 1.0 for d in active_days],dtype=float)
# Modelled pick volume increases for pre-holiday and promotion periods; these are synthetic assumptions.
peak_days = pd.to_datetime(['2026-04-01','2026-04-02','2026-05-01','2026-05-22','2026-08-28','2026-10-29','2026-10-30'])
weights = weights * np.array([1.72 if any(0 <= (p-d).days <= 2 for p in peak_days) else 1.0 for d in active_days])
weights /= weights.sum()

N_PICKS = 32200
row_dates = rng.choice(active_days, size=N_PICKS, p=weights)
sku_ind = rng.choice(N_SKUS,size=N_PICKS,p=(np.array([3.0 if c=='A' else 1.35 if c=='B' else 0.55 for c in items.abc_class]) / sum(3.0 if c=='A' else 1.35 if c=='B' else .55 for c in items.abc_class)))
sku_rows = items.iloc[sku_ind].reset_index(drop=True)
qty_requested = rng.choice([1,2,3,4,5,6,8,10,12],size=N_PICKS,p=[.11,.19,.21,.19,.10,.08,.06,.04,.02])
shifts = rng.choice(['Early','Late'],size=N_PICKS,p=[.56,.44])
zone_arr = sku_rows.zone.to_numpy()
heavy = sku_rows.unit_weight_kg.to_numpy() > 5
breakdown = rng.random(N_PICKS) < (0.105 + .105*(zone_arr=='Bulk') + .07*(zone_arr=='High-Bay') + .04*(shifts=='Late'))
stockout = rng.random(N_PICKS) < (.017 + .027*(zone_arr=='High-Bay') + .020*(zone_arr=='Chilled'))
wrong = rng.random(N_PICKS) < (.012 + .026*(zone_arr=='High-Bay') + .012*(zone_arr=='Bulk'))
qty_picked = qty_requested.copy()
shorts = np.maximum(1, (qty_requested[stockout]*rng.uniform(.3,.75,stockout.sum())).astype(int))
qty_picked[stockout] = np.maximum(0,qty_requested[stockout]-shorts)
location = sku_rows.expected_location.to_numpy().copy()
location[wrong] = np.array([f'99-{n%13+1:02d}-{n%7+1:02d}' for n in np.where(wrong)[0]])
target = 43.0 + 5.9 * qty_requested + 9.0 * heavy.astype(int) + 4.0*(zone_arr=='High-Bay')
duration = target * rng.lognormal(-.07,.21,N_PICKS) + 67*breakdown + 87*wrong + 42*stockout + 7*(shifts=='Late') + 7*(zone_arr=='High-Bay')
duration = np.maximum(duration,12).round(0)
pickers = rng.integers(1,50,N_PICKS)
raw = pd.DataFrame({'event_id':[f'P{i+1:07d}' for i in range(N_PICKS)], 'pick_date':pd.to_datetime(row_dates).strftime('%Y-%m-%d'),
        'shift':shifts, 'picker_code':[f'OP{x:03d}' for x in pickers], 'sku_id':sku_rows.sku_id.values,
        'zone':zone_arr, 'expected_location':sku_rows.expected_location.values, 'scanned_location':location,
        'qty_requested':qty_requested.astype(object), 'qty_picked':qty_picked.astype(object),
        'duration_seconds':duration.astype(object), 'pallet_breakdown':np.where(breakdown,'Y','N'),
        'exception_code':np.where(stockout,'SHORT',np.where(wrong,'MISLOC','NONE')),
        'pallet_id':[f'PAL{n:06d}' for n in rng.integers(1,3700,N_PICKS)]})
# Introduce deliberately imperfect WMS data. Never inject multiple issues into same chosen row.
chosen = rng.choice(len(raw),size=880,replace=False)
for ind in chosen[:210]: raw.loc[ind,'zone'] = ' '+str(raw.loc[ind,'zone']).lower()+' '
for ind in chosen[210:360]: raw.loc[ind,'scanned_location'] = ' '+str(raw.loc[ind,'scanned_location']).lower()+' '
for ind in chosen[360:510]: raw.loc[ind,'qty_requested'] = ' '+str(raw.loc[ind,'qty_requested'])+' '
for ind in chosen[510:680]: raw.loc[ind,'duration_seconds'] = None
for ind in chosen[680:785]: raw.loc[ind,'duration_seconds'] = -4
for ind in chosen[785:850]: raw.loc[ind,'qty_picked'] = -2
for ind in chosen[850:880]: raw.loc[ind,'sku_id'] = 'NOT_IN_MASTER'
# Duplicate event IDs represent a common re-export issue.
raw = pd.concat([raw,raw.iloc[rng.choice(len(raw),size=135,replace=False)]],ignore_index=True)
raw = raw.sample(frac=1, random_state=331).reset_index(drop=True)
raw.to_csv(RAW/'picks_raw.csv',index=False)

# Cycle counts sample inventory snapshots and contain errors to be reconciled, not real records.
N_COUNTS=2600
count_dates=rng.choice(active_days,N_COUNTS)
idx=rng.choice(N_SKUS,N_COUNTS)
counts=items.iloc[idx].reset_index(drop=True)
system_qty=rng.integers(12,320,N_COUNTS)
prob = .09 + .13*(counts.zone.to_numpy()=='High-Bay') + .09*(counts.zone.to_numpy()=='Bulk')
variance = rng.random(N_COUNTS) < prob
noise = np.where(variance,rng.choice([-12,-8,-5,-3,2,4,9],N_COUNTS),0)
physical_qty=np.maximum(system_qty+noise,0)
cc=pd.DataFrame({'count_id':[f'C{i+1:06d}' for i in range(N_COUNTS)],'count_date':pd.to_datetime(count_dates).strftime('%Y-%m-%d'),
                 'sku_id':counts.sku_id.values, 'system_qty':system_qty.astype(object), 'physical_qty':physical_qty.astype(object),
                 'location':counts.expected_location.values, 'count_method':rng.choice(['Routine','Spot Check'],N_COUNTS,p=[.7,.3])})
bad=rng.choice(len(cc),size=40,replace=False)
cc.loc[bad[:17],'physical_qty']=None
cc.loc[bad[17:27],'system_qty']=-1
cc.loc[bad[27:],'location']=' '+cc.loc[bad[27:],'location'].astype(str)+' '
cc=pd.concat([cc,cc.iloc[rng.choice(len(cc),size=18,replace=False)]],ignore_index=True)
cc.to_csv(RAW/'cycle_counts_raw.csv',index=False)

# Staffing is a separate file with a different grain: one roster row per day/shift.
roster=[]
for dt in active_days:
    for shift in ['Early','Late']:
        planned=int(rng.integers(13,24))
        absent=int(rng.binomial(planned,.045 + (.02 if dt.weekday()==5 else 0)))
        roster.append({'date':dt.strftime('%Y-%m-%d'), 'shift':shift, 'planned_headcount':planned, 'absent_headcount':absent,
                       'actual_headcount':planned-absent})
pd.DataFrame(roster).to_csv(RAW/'shift_roster.csv',index=False)
print(f'Created {len(raw):,} raw picks, {len(cc):,} raw stock counts, {len(roster)} roster records, {len(items)} SKUs.')
