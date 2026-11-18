-- Reusable portfolio SQL: run in SQLite 3.25+ / DB Browser for SQLite (query 08 uses window functions).
-- 01. Whole-period warehouse KPI summary.
SELECT COUNT(*) AS pick_events,
       SUM(qty_requested) AS requested_units,
       SUM(qty_picked) AS picked_units,
       ROUND(100.0*SUM(qty_picked)/NULLIF(SUM(qty_requested),0),2) AS fill_rate_pct,
       ROUND(SUM(qty_picked)*3600.0/NULLIF(SUM(duration_seconds),0),1) AS units_per_active_pick_hour,
       ROUND(100.0*AVG(location_mismatch),2) AS location_mismatch_pct,
       ROUND(SUM(benchmark_gap_seconds)/3600.0,1) AS benchmark_gap_hours
FROM picks_clean;

-- 02. Zones requiring attention: compare rate and impact, not just a leaderboard.
SELECT zone, COUNT(*) AS pick_events, ROUND(AVG(duration_seconds),1) AS mean_pick_sec,
       ROUND(100.0*AVG(slow_pick),1) AS slow_pick_pct,
       ROUND(100.0*AVG(location_mismatch),2) AS wrong_location_pct,
       ROUND(100.0*AVG(is_short_pick),2) AS short_pick_pct,
       ROUND(100.0*AVG(pallet_breakdown),1) AS breakdown_pct,
       ROUND(SUM(benchmark_gap_seconds)/3600.0,1) AS benchmark_gap_hours,
       -- Per-pick gap removes the volume effect: total hours favour busy zones, per pick shows intensity.
       ROUND(AVG(benchmark_gap_seconds),1) AS gap_seconds_per_pick
FROM picks_clean GROUP BY zone ORDER BY benchmark_gap_hours DESC;

-- 03. Pallet breakdown vs no breakdown: descriptive comparison only, NOT causal impact.
SELECT zone, pallet_breakdown, COUNT(*) AS pick_events,
       ROUND(AVG(duration_seconds),1) AS mean_pick_sec,
       ROUND(100.0*AVG(slow_pick),1) AS slow_pick_pct
FROM picks_clean GROUP BY zone,pallet_breakdown ORDER BY zone,pallet_breakdown;

-- 04. Shift differences with measurable denominator.
SELECT shift, COUNT(*) AS pick_events,
       SUM(qty_picked) AS picked_units,
       ROUND(SUM(qty_picked)*3600.0/NULLIF(SUM(duration_seconds),0),1) AS units_per_active_pick_hour,
       ROUND(100.0*AVG(slow_pick),1) AS slow_pick_pct
FROM picks_clean GROUP BY shift;

-- 05. Inventory accuracy, measured from stock COUNT records, not picks.
SELECT zone, COUNT(*) AS cycle_counts,
       ROUND(100.0*AVG(exact_match),2) AS exact_match_pct,
       SUM(absolute_variance_units) AS absolute_units_reconciled
FROM cycle_counts_clean GROUP BY zone ORDER BY exact_match_pct;

-- 06. Context only: the five days before official England/Wales bank holidays.
-- Volume is measured PER OPERATING DAY: a pick-level count would just reflect how many days are flagged.
-- Avoid treating observational differences as proven holiday causality.
WITH daily AS (
  SELECT pick_date, MAX(is_preholiday_5d) AS is_preholiday_5d, COUNT(*) AS picks,
         AVG(slow_pick) AS slow_rate, AVG(duration_seconds) AS avg_pick_sec
  FROM v_picks_enriched WHERE is_bank_holiday=0 GROUP BY pick_date)
SELECT is_preholiday_5d, COUNT(*) AS operating_days,
       ROUND(AVG(picks),1) AS avg_picks_per_day,
       ROUND(100.0*AVG(slow_rate),1) AS slow_pick_pct,
       ROUND(AVG(avg_pick_sec),1) AS avg_pick_sec
FROM daily GROUP BY is_preholiday_5d;

-- 07. Worst SKU/location clusters for targeted cycle count follow-ups.
SELECT p.zone,p.sku_id,COUNT(*) AS picks,
       SUM(p.location_mismatch) AS mismatched_scans,
       ROUND(100.0*AVG(p.location_mismatch),2) AS mismatch_pct,
       SUM(p.is_short_pick) AS short_pick_events
FROM picks_clean p GROUP BY p.zone,p.sku_id
HAVING COUNT(*)>=60 ORDER BY mismatched_scans DESC,short_pick_events DESC LIMIT 15;

-- 08. SKU recount priority list combining BOTH evidence sources.
-- Each source is aggregated to one row per SKU BEFORE joining, so pick rows never multiply count rows.
-- Score = average percentile rank of three RATES (0 = best, 1 = worst), so high-volume SKUs are not
-- favoured just for having more picks. Minimum samples stop a SKU with 2 counts topping the list by chance.
WITH pick_sku AS (
  SELECT sku_id, zone, COUNT(*) AS picks, AVG(location_mismatch) AS mismatch_rate, AVG(is_short_pick) AS short_rate
  FROM picks_clean GROUP BY sku_id, zone HAVING COUNT(*)>=60),
count_sku AS (
  SELECT sku_id, COUNT(*) AS counts, AVG(count_discrepancy) AS discrepancy_rate
  FROM cycle_counts_clean GROUP BY sku_id HAVING COUNT(*)>=8),
ranked AS (
  SELECT p.*, c.counts, c.discrepancy_rate,
         PERCENT_RANK() OVER (ORDER BY p.mismatch_rate) AS r_mismatch,
         PERCENT_RANK() OVER (ORDER BY p.short_rate) AS r_short,
         PERCENT_RANK() OVER (ORDER BY c.discrepancy_rate) AS r_count
  FROM pick_sku p JOIN count_sku c ON p.sku_id=c.sku_id)
SELECT zone, sku_id, picks, counts,
       ROUND(100.0*mismatch_rate,2) AS mismatch_pct,
       ROUND(100.0*short_rate,2) AS short_pick_pct,
       ROUND(100.0*discrepancy_rate,1) AS count_discrepancy_pct,
       ROUND((r_mismatch+r_short+r_count)/3.0,3) AS priority_score
FROM ranked ORDER BY priority_score DESC LIMIT 10;

-- 09. Like-for-like shift comparison: split by pallet breakdown so the extra breakdowns on Late
-- cannot explain the whole difference. Descriptive, still not causal.
SELECT pallet_breakdown, shift, COUNT(*) AS pick_events,
       ROUND(AVG(duration_seconds),1) AS mean_pick_sec,
       ROUND(AVG(duration_seconds - target_seconds),1) AS mean_sec_vs_target,
       ROUND(100.0*AVG(slow_pick),1) AS slow_pick_pct
FROM picks_clean GROUP BY pallet_breakdown, shift ORDER BY pallet_breakdown, shift;

-- 10. Day-of-week demand pattern (normal weeks only), for staffing context.
SELECT day_of_week, COUNT(DISTINCT pick_date) AS operating_days,
       ROUND(COUNT(*)*1.0/COUNT(DISTINCT pick_date),1) AS avg_picks_per_day
FROM v_picks_enriched WHERE is_bank_holiday=0 AND is_preholiday_5d=0
GROUP BY day_of_week ORDER BY avg_picks_per_day DESC;
