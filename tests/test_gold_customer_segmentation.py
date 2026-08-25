"""Gold customer_segmentation: brief table C plus post-build quality checks."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src" / "gold"))

from gold_harness import gold_bundle  # noqa: E402
from gold_utils import (  # noqa: E402
    HIGH_VALUE_MIN_ORDERS,
    HIGH_VALUE_MIN_REVENUE,
    SEGMENT_TYPES,
    assign_segment_type,
    money,
)
from validate_gold import all_checks_passed, validate_customer_segmentation  # noqa: E402


class CustomerSegmentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = gold_bundle()
        cls.gold = cls.bundle["customer_segmentation"]
        cls.revenue = cls.bundle["revenue_by_customer"]
        cls.checks = cls.bundle["checks"]["customer_segmentation"]
        cls.by_type = {row["segment_type"]: row for row in cls.gold}

    def test_brief_columns_and_four_types(self):
        required = {"segment_type", "customer_count", "avg_revenue", "total_revenue"}
        self.assertTrue(required.issubset(self.gold[0].keys()))
        self.assertEqual(len(self.gold), 4)
        self.assertEqual(tuple(row["segment_type"] for row in self.gold), SEGMENT_TYPES)

    def test_segments_are_mutually_exclusive_and_complete(self):
        assigned = [assign_segment_type(int(row["total_orders"]), money(row["total_revenue"])) for row in self.revenue]
        self.assertEqual(len(assigned), len(self.revenue))
        self.assertEqual(
            sum(int(row["customer_count"]) for row in self.gold),
            len(self.revenue),
        )
        for segment in SEGMENT_TYPES:
            self.assertEqual(
                int(self.by_type[segment]["customer_count"]),
                assigned.count(segment),
            )

    def test_high_value_rule(self):
        high = [
            row
            for row in self.revenue
            if assign_segment_type(int(row["total_orders"]), money(row["total_revenue"]))
            == "High-Value"
        ]
        self.assertTrue(high)
        self.assertTrue(
            all(
                int(row["total_orders"]) >= HIGH_VALUE_MIN_ORDERS
                and money(row["total_revenue"]) >= HIGH_VALUE_MIN_REVENUE
                for row in high
            )
        )

    def test_inactive_is_zero_orders_only(self):
        inactive = [
            row
            for row in self.revenue
            if assign_segment_type(int(row["total_orders"]), money(row["total_revenue"]))
            == "Inactive"
        ]
        self.assertTrue(inactive)
        self.assertTrue(all(int(row["total_orders"]) == 0 for row in inactive))
        self.assertEqual(int(self.by_type["Inactive"]["customer_count"]), len(inactive))

    def test_avg_revenue_derived(self):
        for row in self.gold:
            count = int(row["customer_count"])
            if count == 0:
                self.assertEqual(money(row["avg_revenue"]), money(0))
            else:
                self.assertEqual(
                    money(row["avg_revenue"]),
                    money(money(row["total_revenue"]) / count),
                )

    def test_segment_revenue_sums_to_customer_revenue(self):
        self.assertEqual(
            sum((money(row["total_revenue"]) for row in self.gold), money(0)),
            sum((money(row["total_revenue"]) for row in self.revenue), money(0)),
        )


class CustomerSegmentationQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = gold_bundle()
        cls.gold = cls.bundle["customer_segmentation"]
        cls.revenue = cls.bundle["revenue_by_customer"]
        cls.checks = cls.bundle["checks"]["customer_segmentation"]

    def test_all_gold_quality_checks_pass(self):
        self.assertTrue(all_checks_passed(self.checks), self.checks)
        self.assertTrue(all(row["rows_failed"] == 0 for row in self.checks))

    def test_missing_segment_is_detected(self):
        tainted = [row for row in copy.deepcopy(self.gold) if row["segment_type"] != "Inactive"]
        checks = {
            row["check_name"]: row
            for row in validate_customer_segmentation(tainted, self.revenue)
        }
        self.assertEqual(checks["four_brief_segments"]["status"], "FAIL")

    def test_count_drift_is_detected(self):
        tainted = copy.deepcopy(self.gold)
        tainted[0]["customer_count"] = int(tainted[0]["customer_count"]) + 5
        checks = {
            row["check_name"]: row
            for row in validate_customer_segmentation(tainted, self.revenue)
        }
        self.assertEqual(checks["counts_match_revenue_table"]["status"], "FAIL")
        self.assertEqual(checks["covers_all_revenue_customers"]["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
