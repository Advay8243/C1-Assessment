"""Gold revenue_by_customer: brief table B plus post-build quality checks."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src" / "gold"))
sys.path.insert(0, str(ROOT / "src" / "data_generation"))

import generate_sample_data as gen  # noqa: E402
from gold_harness import gold_bundle  # noqa: E402
from gold_utils import PASS, money, pass_customer_dims, qualifying_orders  # noqa: E402
from validate_gold import all_checks_passed, validate_revenue_by_customer  # noqa: E402


class RevenueByCustomerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = gold_bundle()
        cls.silver = cls.bundle["silver"]
        cls.gold = cls.bundle["revenue_by_customer"]
        cls.checks = cls.bundle["checks"]["revenue_by_customer"]
        cls.pass_customers = pass_customer_dims(cls.silver["customers"])
        cls.qualifying, _ = qualifying_orders(cls.silver)
        cls.by_id = {row["customer_id"]: row for row in cls.gold}

    def test_brief_columns_present(self):
        required = {
            "customer_id",
            "customer_name",
            "customer_segment",
            "total_orders",
            "total_revenue",
            "avg_order_value",
            "lifetime_value_actual",
        }
        self.assertTrue(required.issubset(self.gold[0].keys()))

    def test_one_row_per_pass_customer(self):
        ids = [row["customer_id"] for row in self.gold]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), set(self.pass_customers))

    def test_lifetime_value_is_order_revenue_not_source_column(self):
        for row in self.gold:
            self.assertEqual(money(row["lifetime_value_actual"]), money(row["total_revenue"]))
        sample = next(row for row in self.gold if int(row["total_orders"]) > 0)
        source_ltv = self.pass_customers[sample["customer_id"]]["lifetime_value"]
        # Source lifetime_value is a generator placeholder; Gold must not copy it blindly.
        self.assertEqual(money(sample["lifetime_value_actual"]), money(sample["total_revenue"]))
        self.assertIsNotNone(source_ltv)

    def test_avg_order_value_derived(self):
        for row in self.gold:
            orders_n = int(row["total_orders"])
            if orders_n == 0:
                self.assertEqual(money(row["avg_order_value"]), money(0))
            else:
                self.assertEqual(
                    money(row["avg_order_value"]),
                    money(money(row["total_revenue"]) / orders_n),
                )

    def test_failed_customers_excluded(self):
        failed_ids = (
            set(gen.NULL_EMAIL_IDS)
            | set(gen.INVALID_SEGMENT_IDS)
            | set(gen.MALFORMED_EMAIL_IDS)
            | set(gen.FUTURE_SIGNUP_IDS)
            | set(gen.DUP_CUSTOMER_SOURCE_IDS)
        )
        self.assertTrue(failed_ids.isdisjoint(self.by_id))

    def test_inactive_customers_have_zero_orders(self):
        inactive_ids = [
            customer_id
            for customer_id in range(gen.INACTIVE_CUSTOMER_ID_START, gen.N_CUSTOMERS + 1)
            if customer_id in self.by_id
        ]
        self.assertTrue(inactive_ids)
        self.assertTrue(
            all(int(self.by_id[customer_id]["total_orders"]) == 0 for customer_id in inactive_ids)
        )

    def test_totals_reconcile_to_qualifying_orders(self):
        self.assertEqual(
            sum(int(row["total_orders"]) for row in self.gold),
            len(self.qualifying),
        )


class RevenueByCustomerQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = gold_bundle()
        cls.gold = cls.bundle["revenue_by_customer"]
        cls.silver = cls.bundle["silver"]
        cls.checks = cls.bundle["checks"]["revenue_by_customer"]

    def test_all_gold_quality_checks_pass(self):
        self.assertTrue(all_checks_passed(self.checks), self.checks)
        self.assertTrue(all(row["rows_failed"] == 0 for row in self.checks))

    def test_duplicate_customer_is_detected(self):
        tainted = copy.deepcopy(self.gold)
        tainted.append(copy.deepcopy(tainted[0]))
        checks = {
            row["check_name"]: row
            for row in validate_revenue_by_customer(tainted, self.silver)
        }
        self.assertEqual(checks["grain_uniqueness"]["status"], "FAIL")

    def test_ltv_drift_is_detected(self):
        tainted = copy.deepcopy(self.gold)
        tainted[0]["lifetime_value_actual"] = money(
            money(tainted[0]["lifetime_value_actual"]) + 10
        )
        checks = {
            row["check_name"]: row
            for row in validate_revenue_by_customer(tainted, self.silver)
        }
        self.assertEqual(checks["lifetime_value_matches_revenue"]["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
