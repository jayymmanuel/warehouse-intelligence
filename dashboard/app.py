"""Interactive dashboard:  streamlit run dashboard/app.py"""
import json
import sqlite3
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / 'warehouse_operations.sqlite'
NAVY, ACCENT, MUTED, INK_2 = '#0B1F3A', '#2A78D6', '#C3C7CE', '#52514E'
FOCUS_ZONE = 'High-Bay'

st.set_page_config(page_title='Warehouse Intelligence', page_icon='📦', layout='wide')
st.markdown(f"""
<style>
  .block-container {{padding-top: 3.6rem; max-width: 1300px;}}
  .hero {{background:{NAVY}; color:#fff; padding:22px 28px; border-radius:6px; margin-bottom:18px;}}
  .hero h1 {{color:#fff; font-size:1.9rem; margin:0; padding:0;}}
  .hero p {{color:#B9C4D6; margin:4px 0 0 0; font-size:0.95rem;}}
  div[data-testid="stMetric"] {{background:#fff; border:1px solid #E3E5E9; border-top:3px solid #1C3354;
                                 border-radius:6px; padding:14px 16px;}}
  div[data-testid="stMetricLabel"] p {{font-size:0.75rem; letter-spacing:.04em; text-transform:uppercase; color:#8A8F98;}}
  .note {{color:#8A8F98; font-size:0.8rem; font-style:italic;}}
</style>
<div class="hero"><h1>Warehouse Intelligence</h1>
<p>Picking efficiency &amp; inventory accuracy · simulated WMS data · GOV.UK bank holiday calendar</p></div>
""", unsafe_allow_html=True)

if not DB.exists():
    st.error('Database missing. From the project root run: python3 src/generate_data.py && python3 src/clean_and_load.py')
    st.stop()


@st.cache_data
def load():
    with sqlite3.connect(DB) as con:
        p = pd.read_sql_query('SELECT * FROM v_picks_enriched', con)
        c = pd.read_sql_query('SELECT * FROM cycle_counts_clean', con)
    p['pick_date'] = pd.to_datetime(p.pick_date)
    c['count_date'] = pd.to_datetime(c.count_date)
    return p, c


picks_all, counts_all = load()

# ---- Filters -----------------------------------------------------------------
with st.sidebar:
    st.header('Filters')
    lo, hi = picks_all.pick_date.min().date(), picks_all.pick_date.max().date()
    period = st.date_input('Date range', (lo, hi), min_value=lo, max_value=hi)
    zones = st.multiselect('Zones', sorted(picks_all.zone.unique()), default=sorted(picks_all.zone.unique()))
    shifts = st.multiselect('Shifts', sorted(picks_all['shift'].unique()), default=sorted(picks_all['shift'].unique()))
    st.caption('Stock counts filter by date and zone only; counts are not recorded per shift.')
if not isinstance(period, (list, tuple)) or len(period) != 2:
    st.info('Select a start and end date.'); st.stop()

p = picks_all[picks_all.pick_date.dt.date.between(*period) & picks_all.zone.isin(zones) & picks_all['shift'].isin(shifts)]
counts = counts_all[counts_all.count_date.dt.date.between(*period) & counts_all.zone.isin(zones)]
if p.empty:
    st.info('No picks match these filters.'); st.stop()

# ---- KPI row -------------------------------------------------------------------
k = st.columns(5)
k[0].metric('Validated picks', f'{len(p):,}')
k[1].metric('Unit fill rate', f'{p.qty_picked.sum() / p.qty_requested.sum():.1%}')
k[2].metric('Slow pick rate', f'{p.slow_pick.mean():.1%}',
            help='Picks taking over 125% of the per-pick benchmark.')
k[3].metric('Wrong-location scans', f'{p.location_mismatch.mean():.2%}')
k[4].metric('Benchmark gap', f'{p.benchmark_gap_seconds.sum() / 3600:,.1f} h',
            help='Time above the per-pick benchmark. An opportunity signal, not proven recoverable time.')


def bars(df, x, y, fmt, title, horizontal=False, sort='-y', domain_max=None):
    """Grey bars with the focus zone in the accent colour and values printed on the bars."""
    color = alt.condition(alt.datum.zone == FOCUS_ZONE, alt.value(ACCENT), alt.value(MUTED))
    scale = alt.Scale(domain=[0, domain_max]) if domain_max else alt.Scale(zero=True)
    if horizontal:
        base = alt.Chart(df).encode(y=alt.Y(f'{x}:N', sort=sort, title=None),
                                    x=alt.X(f'{y}:Q', axis=None, scale=scale))
        text = base.mark_text(align='left', dx=4, fontWeight='bold', color=NAVY).encode(text=alt.Text(f'{y}:Q', format=fmt))
    else:
        base = alt.Chart(df).encode(x=alt.X(f'{x}:N', sort=sort, title=None, axis=alt.Axis(labelAngle=0)),
                                    y=alt.Y(f'{y}:Q', axis=None, scale=scale))
        text = base.mark_text(dy=-8, fontWeight='bold', color=NAVY).encode(text=alt.Text(f'{y}:Q', format=fmt))
    chart = (base.mark_bar(cornerRadiusEnd=3).encode(color=color, tooltip=[x, alt.Tooltip(y, format=fmt)]) + text)
    return chart.properties(title=alt.TitleParams(title, anchor='start', fontSize=15, color=NAVY), height=300)\
                .configure_view(strokeWidth=0).configure_axis(labelColor=INK_2, domainColor='#E3E5E9', tickColor='#E3E5E9')


zone = p.groupby('zone').agg(picks=('event_id', 'size'), gap=('benchmark_gap_seconds', 'mean'),
                             slow=('slow_pick', 'mean'), wrong=('location_mismatch', 'mean'),
                             short=('is_short_pick', 'mean'), breakdown=('pallet_breakdown', 'mean'),
                             gap_hours=('benchmark_gap_seconds', lambda s: s.sum() / 3600)).reset_index()

t1, t2, t3, t4, t5 = st.tabs(['Zones', 'Inventory', 'Shifts', 'Demand', 'Data quality'])

with t1:
    a, b = st.columns(2)
    worst = zone.sort_values('gap', ascending=False).iloc[0]
    a.altair_chart(bars(zone, 'zone', 'gap', '.1f', f'{worst.zone} loses most time per pick: {worst.gap:.0f}s above benchmark'),
                   width='stretch')
    worst = zone.sort_values('slow', ascending=False).iloc[0]
    b.altair_chart(bars(zone, 'zone', 'slow', '.0%', f'{worst.zone} has the highest slow-pick rate at {worst.slow:.0%}'),
                   width='stretch')
    share = p.loc[p.slow_pick == 1, 'pallet_breakdown'].mean()
    st.markdown(f'**{share:.0%} of slow picks involve a pallet breakdown.** Without breakdowns the slow-pick rate is '
                f'{p.loc[p.pallet_breakdown == 0, "slow_pick"].mean():.1%}. The benchmark has no breakdown allowance, '
                'so breakdowns are reported separately below.')
    show = zone.rename(columns={'zone': 'Zone', 'picks': 'Picks', 'gap': 'Gap sec per pick', 'slow': 'Slow %',
                                'wrong': 'Wrong location %', 'short': 'Short pick %', 'breakdown': 'Breakdown %',
                                'gap_hours': 'Total gap (h)'}).sort_values('Gap sec per pick', ascending=False)
    st.dataframe(show.style.format({'Picks': '{:,}', 'Gap sec per pick': '{:.1f}', 'Slow %': '{:.1%}', 'Wrong location %': '{:.2%}',
                                    'Short pick %': '{:.2%}', 'Breakdown %': '{:.1%}', 'Total gap (h)': '{:.1f}'}),
                 hide_index=True, width='stretch')

with t2:
    if counts.empty:
        st.info('No stock counts in this selection.')
    else:
        a, b = st.columns(2)
        acc = counts.groupby('zone').agg(counts=('count_id', 'size'), match=('exact_match', 'mean')).reset_index()
        low = acc.sort_values('match').iloc[0]
        a.altair_chart(bars(acc, 'zone', 'match', '.0%', f'{low.zone} stock records match only {low.match:.0%} of counts',
                            sort='y', domain_max=1.05), width='stretch')
        # Recount priority (SQL query 08): aggregate each source to one row per SKU before joining.
        ps = p.groupby(['sku_id', 'zone']).agg(n=('event_id', 'size'), mis=('location_mismatch', 'mean'),
                                               sh=('is_short_pick', 'mean')).reset_index().query('n >= 60')
        cs = counts.groupby('sku_id').agg(c=('count_id', 'size'), disc=('count_discrepancy', 'mean')).reset_index().query('c >= 8')
        sku = ps.merge(cs, on='sku_id')
        if sku.empty:
            b.info('Not enough picks and counts in this selection to score SKUs.')
        else:
            sku['score'] = (sku.mis.rank(pct=True, method='min') + sku.sh.rank(pct=True, method='min')
                            + sku.disc.rank(pct=True, method='min')) / 3
            top = sku.nlargest(10, 'score').assign(label=lambda d: d.sku_id + ' · ' + d.zone)
            n_focus = int((top.zone == FOCUS_ZONE).sum())
            b.altair_chart(bars(top, 'label', 'score', '.2f', f'{n_focus} of the top {len(top)} recount priorities are {FOCUS_ZONE}',
                                horizontal=True, sort='-x', domain_max=1.15), width='stretch')
        st.caption('Priority score = average percentile rank of wrong-location, short-pick and count-discrepancy rates '
                   '(1 = worst). Minimum 60 picks and 8 counts per SKU.')

with t3:
    sh = p.groupby('shift').agg(picks=('event_id', 'size'), units=('qty_picked', 'sum'),
                                secs=('duration_seconds', 'sum'), slow=('slow_pick', 'mean'),
                                breakdown=('pallet_breakdown', 'mean')).reset_index()
    sh['uph'] = sh.units / (sh.secs / 3600)
    cols = st.columns(len(sh))
    for col, r in zip(cols, sh.itertuples()):
        col.metric(f'{r.shift} · units per active hour', f'{r.uph:.1f}', help='Recorded picking time only, not paid hours.')
    like = (p.assign(vs_target=p.duration_seconds - p.target_seconds)
              .groupby(['pallet_breakdown', 'shift']).agg(picks=('event_id', 'size'), mean_sec=('duration_seconds', 'mean'),
                                                          vs_target=('vs_target', 'mean'), slow=('slow_pick', 'mean')).reset_index())
    like['pallet_breakdown'] = like.pallet_breakdown.map({0: 'No breakdown', 1: 'Breakdown'})
    st.markdown('**Like-for-like comparison.** Splitting by pallet breakdown shows whether one shift is slower only '
                'because it breaks down more pallets.')
    st.dataframe(like.rename(columns={'pallet_breakdown': 'Pick type', 'shift': 'Shift', 'picks': 'Picks', 'mean_sec': 'Mean seconds',
                                      'vs_target': 'Seconds vs benchmark', 'slow': 'Slow %'})
                 .style.format({'Picks': '{:,}', 'Mean seconds': '{:.1f}', 'Seconds vs benchmark': '{:+.1f}', 'Slow %': '{:.1%}'}),
                 hide_index=True, width='stretch')

with t4:
    daily = p[p.is_bank_holiday == 0].groupby('pick_date').agg(picks=('event_id', 'size'),
                                                               pre=('is_preholiday_5d', 'max')).reset_index()
    daily['Period'] = daily.pre.map({0: 'Normal day', 1: '5 days before a bank holiday'})
    pre, norm = daily.loc[daily.pre == 1, 'picks'].mean(), daily.loc[daily.pre == 0, 'picks'].mean()
    title = (f'Picks per day rise to {pre:.0f} before bank holidays vs {norm:.0f} normally'
             if daily.pre.any() else 'Picks per operating day')
    line = alt.Chart(daily).mark_bar(width=2).encode(
        x=alt.X('pick_date:T', title=None), y=alt.Y('picks:Q', title='Picks per day'),
        color=alt.Color('Period:N', scale=alt.Scale(domain=['Normal day', '5 days before a bank holiday'], range=[MUTED, ACCENT]),
                        legend=alt.Legend(orient="top", title=None, labelLimit=0)),
        tooltip=[alt.Tooltip('pick_date:T', title='Date'), 'picks', 'Period'])
    st.altair_chart(line.properties(title=alt.TitleParams(title, anchor='start', fontSize=15, color=NAVY), height=300)
                    .configure_view(strokeWidth=0), width='stretch')
    dow = (p[(p.is_bank_holiday == 0) & (p.is_preholiday_5d == 0)].groupby('day_of_week')
           .agg(picks=('event_id', 'size'), days=('pick_date', 'nunique')).reset_index())
    dow['per_day'] = dow.picks / dow.days
    order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    st.altair_chart(alt.Chart(dow).mark_bar(cornerRadiusEnd=3, color=MUTED).encode(
        x=alt.X('day_of_week:N', sort=order, title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y('per_day:Q', title='Picks per day'), tooltip=['day_of_week', alt.Tooltip('per_day', format='.0f')])
        .properties(title=alt.TitleParams('Normal-week demand by day', anchor='start', fontSize=15, color=NAVY), height=240)
        .configure_view(strokeWidth=0), width='stretch')

with t5:
    audit = json.loads((ROOT / 'data/quality/quality_audit.json').read_text())
    a, b = st.columns(2)
    a.subheader('Pick events')
    a.dataframe(pd.DataFrame({'Step': ['Raw records', 'Duplicates removed', *[f'Rejected: {k.replace("_", " ")}' for k in audit['pick_rejections_by_reason']], 'Validated'],
                              'Rows': [audit['pick_raw_records'], -audit['pick_duplicate_exports_removed'],
                                       *[-v for v in audit['pick_rejections_by_reason'].values()], audit['pick_clean_records']]}),
                hide_index=True, width='stretch')
    b.subheader('Stock counts')
    b.dataframe(pd.DataFrame({'Step': ['Raw records', 'Duplicates removed', *[f'Rejected: {k.replace("_", " ")}' for k in audit['stockcount_rejections_by_reason']], 'Validated'],
                              'Rows': [audit['stockcount_raw_records'], -audit['stockcount_duplicate_exports_removed'],
                                       *[-v for v in audit['stockcount_rejections_by_reason'].values()], audit['stockcount_clean_records']]}),
                hide_index=True, width='stretch')
    src = 'live GOV.UK API' if audit['calendar_source_type'] == 'live_public_api' else 'offline copy of GOV.UK API data'
    st.caption(f'Bank holiday calendar: {src}. Every rejected record is logged with its reason in data/quality/.')

st.markdown('<p class="note">Descriptive associations from simulated data, not proven causes. '
            'The per-pick benchmark is analyst-defined, not an SLA.</p>', unsafe_allow_html=True)
