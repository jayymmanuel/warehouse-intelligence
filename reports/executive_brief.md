# Warehouse Intelligence: Management Decision Brief

**Prepared for:** Distribution Centre Operations Manager  
**Period analysed:** 5 January to 31 October 2026  
**Data:** 31,830 validated picking events and 2,573 stock counts from a simulated WMS, enriched with the GOV.UK bank holiday calendar.

## The decision
Where should a warehouse operations manager focus a targeted improvement pilot to reduce slow picks, stock inaccuracies and re-handling?

## Executive scorecard
- **31,830 valid pick events**, after removing 135 duplicated exports and excluding 370 invalid raw picks.
- **98.93% unit-fill rate** (125,217 of 126,577 requested units).
- **29.2% slow-pick rate** (pick duration more than 125% of a simplified per-item benchmark).
- **1.72% mismatched location-scans** after normalization against SKU master locations.
- **157.5 benchmark-gap hours**, the sum of positive differences between recorded pick durations and the benchmark. This is *not* proven recoverable labour time.

## Findings and possible actions

### 1. Prioritise High-Bay for stock-location verification
High-Bay is the worst zone on every per-pick measure: **77.1% exact stock-count match** (195/253 counts, lowest of five zones), **3.50% wrong-location scans**, **4.62% short picks** and **27 seconds above benchmark per pick**. It ranks last on *total* benchmark-gap hours only because it handles the fewest picks. **8 of the top 10 SKUs** on the combined recount priority score (`sku_recount_priority.csv`) are High-Bay. **Pilot:** recount those SKUs and check their location labels, then compare exact-match and mismatch rates before and after.

### 2. Review the pallet-breakdown workflow, starting in Bulk
Bulk has the largest total benchmark gap (**42.0 hours**), partly because it is a high-volume zone, and the highest breakdown share (**22.4%** of picks). Across the site, **53% of all slow picks involve a pallet breakdown**; without breakdowns the slow-pick rate falls from 29.2% to 16.3%. The benchmark gives no time allowance for breakdowns, so the slow-pick KPI is largely a breakdown counter. Heavy or complex picks may also be more likely to need breakdown, so this is association, not proof of cause. **Pilot:** review stock presentation for the 20 highest-frequency Bulk SKUs; compare median time for comparable SKUs, shifts and quantities before and after.

### 3. Investigate the late-shift performance difference
Early processed **185.5 picked units per active picking hour**, Late **164.1**. Late picks average **9.6 seconds** longer. About **2.7 seconds** of that comes from Late doing more pallet breakdowns; the rest persists within like-for-like picks (see SQL query 09). SKU mix, zone mix and quantities are near-identical between shifts. This is active picking time, not paid hours. **Pilot:** observe congestion, replenishment timing and handovers on Late before changing headcount.

### 4. Plan labour for the week before bank holidays
Operating days in the five days before a bank holiday averaged **181 picks**, versus **119** on other days. Slow-pick rates barely moved, so the site absorbed the volume, but this is a staffing signal. Mondays and Fridays are also busier than mid-week and Saturdays are quietest. This is observational context and, with synthetic data, not evidence of a real holiday effect.

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
