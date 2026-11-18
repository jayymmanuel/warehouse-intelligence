"""Run from project root: python -m unittest discover -s tests -v"""
from pathlib import Path
import unittest,sqlite3,json
ROOT=Path(__file__).resolve().parents[1]
class WarehousePipelineChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db=sqlite3.connect(ROOT/'warehouse_operations.sqlite')
        cls.audit=json.loads((ROOT/'data/quality/quality_audit.json').read_text())
    @classmethod
    def tearDownClass(cls):cls.db.close()
    def scalar(self,sql):return self.db.execute(sql).fetchone()[0]
    def test_unique_cleaned_pick_ids(self):
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM picks_clean'),self.scalar('SELECT COUNT(DISTINCT event_id) FROM picks_clean'))
    def test_no_invalid_picks(self):
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM picks_clean WHERE duration_seconds<=0 OR qty_picked<0 OR qty_picked>qty_requested OR qty_requested<=0'),0)
    def test_no_orphan_skus(self):
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM picks_clean p LEFT JOIN sku_master m ON p.sku_id=m.sku_id WHERE m.sku_id IS NULL'),0)
    def test_fill_rate_bounded(self):
        rate=self.scalar('SELECT SUM(qty_picked)*1.0/SUM(qty_requested) FROM picks_clean')
        self.assertTrue(0<=rate<=1)
    def test_roster_unique(self):
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM shift_roster'),self.scalar('SELECT COUNT(DISTINCT date || shift) FROM shift_roster'))
    def test_summary_reconciliation(self):
        total=self.scalar('SELECT COUNT(*) FROM picks_clean')
        from_view=self.scalar('SELECT SUM(pick_events) FROM v_daily_ops')
        self.assertEqual(total,from_view)
    def test_quality_audit_reconciles(self):
        a=self.audit
        self.assertEqual(a['pick_raw_records']-a['pick_duplicate_exports_removed']-a['pick_rejected_records'],a['pick_clean_records'])
    def test_calendar_source_disclosed(self):
        self.assertIn(self.audit['calendar_source_type'],{'manually_seeded_offline_reference_NOT_live_fetch','live_public_api'})
    def test_preholiday_flag_precedes_holiday(self):
        # Regression test: the flag once marked days AFTER holidays. 2 Jan 2026 follows New Year's Day.
        self.assertEqual(self.scalar("SELECT is_preholiday_3d FROM calendar WHERE date='2026-01-02'"),0)
        self.assertEqual(self.scalar("SELECT is_preholiday_3d FROM calendar WHERE date='2026-04-02'"),1)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM calendar WHERE is_bank_holiday=1 AND (is_preholiday_3d=1 OR is_preholiday_5d=1)'),0)
    def test_weekday_volume_pattern(self):
        # Regression test: generator weekday weights were silently ignored. Saturday should be the quietest day.
        rows=self.db.execute("""SELECT c.day_of_week, COUNT(*)*1.0/COUNT(DISTINCT p.pick_date) FROM picks_clean p
                                JOIN calendar c ON p.pick_date=c.date WHERE c.is_preholiday_5d=0 AND c.is_bank_holiday=0
                                GROUP BY c.day_of_week""").fetchall()
        per_day=dict(rows)
        self.assertEqual(min(per_day,key=per_day.get),'Saturday')
    def test_count_rejections_explained(self):
        self.assertEqual(sum(self.audit['stockcount_rejections_by_reason'].values()),self.audit['stockcount_rejected_records'])
        self.assertEqual(sum(self.audit['pick_rejections_by_reason'].values()),self.audit['pick_rejected_records'])
    def test_count_locations_trimmed(self):
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM cycle_counts_clean WHERE location<>TRIM(location)"),0)
    def test_calendar_covers_all_picks(self):
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM picks_clean p LEFT JOIN calendar c ON p.pick_date=c.date WHERE c.date IS NULL'),0)
if __name__=='__main__':unittest.main()
