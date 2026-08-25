"""Gold daily_weekly_trends: daily grain with week attributes, plus quality checks."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src" / "gold"))

from gold_harness import gold_bundle  # noqa: E402
from gold_utils import money, qualifying_orders  # noqa: E402
from validate_gold import all_checks_passed, validate_daily_weekly_trends  # noqa: E402


class DailyWeeklyTrendsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = gold_bundle()
        cls.gold = cls.bundle["daily_weekly_trends"]
        cls.silver = cls.bundle["silver"]
        cls.checks = cls.bundle["checks"]["daily_weekly_trends"]
        cls.qualifying, _ = qualifying_orders(cls.silver)

    def test_brief_supporting_columns_present(self):
        required = {
            "order_date",
            "order_year",
            "order_week",
            "total_orders",
            "total_revenue",
            "avg_order_value",
            "unique_customers",
        }
        self.assertTrue(required.issubset(self.gold[0].keys()))

    def test_one_row_per_order_date(self):
        dates = [row["order_date"] for row in self.gold]
        self.assertEqual(len(dates), len(set(dates)))

    def test_avg_order_value_derived(self):
        for row in self.gold:
            self.assertEqual(
                money(row["avg_order_value"]),
                money(money(row["total_revenue"]) / int(row["total_orders"])),
            )

    def test_unique_customers_cannot_exceed_orders(self):
        for row in self.gold:
            self.assertGreaterEqual(int(row["unique_customers"]), 1)
            self.assertLessEqual(int(row["unique_customers"]), int(row["total_orders"]))

    def test_week_attributes_present_for_weekly_rollups(self):
        for row in self.gold:
            self.assertGreaterEqual(int(row["order_week"]), 1)
            self.assertLessEqual(int(row["order_week"]), 53)
            self.assertGreaterEqual(int(row["order_year"]), 2020)

    def test_daily_totals_reconcile_to_qualifying_orders(self):
        self.assertEqual(
            sum(int(row["total_orders"]) for row in self.gold),
            len(self.qualifying),
        )
        self.assertEqual(
            sum((money(row["total_revenue"]) for row in self.gold), money(0)),
            sum((money(order["total_amount"]) for order in self.qualifying), money(0)),
        )


class DailyWeeklyTrendsQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = gold_bundle()
        cls.gold = cls.bundle["daily_weekly_trends"]
        cls.silver = cls.bundle["silver"]
        cls.checks = cls.bundle["checks"]["daily_weekly_trends"]

    def test_all_gold_quality_checks_pass(self):
        self.assertTrue(all_checks_passed(self.checks), self.checks)
        self.assertTrue(all(row["rows_failed"] == 0 for row in self.checks))

    def test_duplicate_day_is_detected(self):
        tainted = copy.deepcopy(self.gold)
        tainted.append(copy.deepcopy(tainted[0]))
        checks = {
            row["check_name"]: row
            for row in validate_daily_weekly_trends(tainted, self.silver)
        }
        self.assertEqual(checks["grain_uniqueness"]["status"], "FAIL")
        self.assertEqual(checks["order_count_reconciles"]["status"], "FAIL")

    def test_independent_avg_is_detected(self):
        tainted = copy.deepcopy(self.gold)
        tainted[0]["avg_order_value"] = money(money(tainted[0]["avg_order_value"]) + 3)
        checks = {
            row["check_name"]: row
            for row in validate_daily_weekly_trends(tainted, self.silver)
        }
        self.assertEqual(checks["derived_avg_order_value"]["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
