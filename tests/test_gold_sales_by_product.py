"""Gold sales_by_product: aggregation correctness and post-build quality checks."""

from __future__ import annotations

import copy
import sys
import unittest
from collections import Counter
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "gold"))
sys.path.insert(0, str(ROOT / "src" / "silver"))
sys.path.insert(0, str(ROOT / "src" / "data_generation"))

import generate_sample_data as gen  # noqa: E402
from gold_utils import COMPLETED, PASS, money, qualifying_orders  # noqa: E402
from sales_by_product import build_sales_by_product  # noqa: E402
from silver_utils import apply_all_python, build_context, load_landing_records  # noqa: E402
from validate_gold import all_checks_passed, validate_sales_by_product  # noqa: E402


class SalesByProductTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = load_landing_records(ROOT / "data")
        ctx = build_context(source["customers"], source["products"])
        cls.silver = apply_all_python(
            source["customers"], source["products"], source["orders"], ctx
        )
        cls.gold = build_sales_by_product(cls.silver)
        cls.checks = validate_sales_by_product(cls.gold, cls.silver)
        cls.checks_by_name = {row["check_name"]: row for row in cls.checks}
        cls.qualifying, cls.pass_products = qualifying_orders(cls.silver)
        cls.gold_by_id = {row["product_id"]: row for row in cls.gold}

    def test_grain_is_one_row_per_product(self):
        ids = [row["product_id"] for row in self.gold]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(pid is not None for pid in ids))

    def test_avg_order_value_is_derived_from_totals(self):
        for row in self.gold:
            expected = money(Decimal(str(row["total_revenue"])) / int(row["total_orders"]))
            self.assertEqual(money(row["avg_order_value"]), expected)

    def test_totals_reconcile_to_qualifying_silver_orders(self):
        self.assertEqual(
            sum(int(row["total_orders"]) for row in self.gold),
            len(self.qualifying),
        )
        gold_revenue = sum((money(row["total_revenue"]) for row in self.gold), money(0))
        source_revenue = sum(
            (money(order["total_amount"]) for order in self.qualifying), money(0)
        )
        self.assertEqual(gold_revenue, source_revenue)

    def test_failed_products_are_excluded(self):
        failed_ids = (
            set(gen.NULL_PRODUCT_NAME_IDS)
            | set(gen.NULL_CATEGORY_IDS)
            | set(gen.COST_GT_PRICE_IDS)
            | set(gen.NEGATIVE_STOCK_IDS)
            | set(gen.DUP_PRODUCT_SOURCE_IDS)
        )
        gold_ids = set(self.gold_by_id)
        self.assertTrue(failed_ids.isdisjoint(gold_ids))

    def test_pending_and_cancelled_orders_are_excluded(self):
        open_orders = [
            order
            for order in self.silver["orders"]
            if order["quality_check_result"] == PASS
            and order["order_status"] != COMPLETED
            and order["product_id"] in self.pass_products
        ]
        self.assertTrue(open_orders)
        by_product = Counter(order["product_id"] for order in self.qualifying)
        for order in open_orders:
            product_id = order["product_id"]
            if product_id not in self.gold_by_id:
                continue
            self.assertEqual(
                int(self.gold_by_id[product_id]["total_orders"]),
                by_product[product_id],
            )

    def test_fail_silver_orders_do_not_contribute(self):
        fail_completed = [
            order
            for order in self.silver["orders"]
            if order["quality_check_result"] != PASS and order["order_status"] == COMPLETED
        ]
        self.assertTrue(fail_completed)
        qualifying_ids = {order["order_id"] for order in self.qualifying}
        leaked = [order["order_id"] for order in fail_completed if order["order_id"] in qualifying_ids]
        self.assertEqual(leaked, [])

    def test_required_brief_columns_present(self):
        required = {
            "product_id",
            "product_name",
            "category",
            "total_orders",
            "total_revenue",
            "avg_order_value",
        }
        self.assertTrue(required.issubset(self.gold[0].keys()))

    def test_only_products_that_sold(self):
        self.assertTrue(all(int(row["total_orders"]) >= 1 for row in self.gold))
        self.assertLessEqual(len(self.gold), len(self.pass_products))


class SalesByProductQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = load_landing_records(ROOT / "data")
        ctx = build_context(source["customers"], source["products"])
        cls.silver = apply_all_python(
            source["customers"], source["products"], source["orders"], ctx
        )
        cls.gold = build_sales_by_product(cls.silver)
        cls.checks = validate_sales_by_product(cls.gold, cls.silver)

    def test_all_gold_quality_checks_pass(self):
        self.assertTrue(all_checks_passed(self.checks), self.checks)
        expected = {
            "grain_uniqueness",
            "completeness",
            "positive_measures",
            "derived_avg_order_value",
            "order_count_reconciles",
            "revenue_reconciles",
            "dimension_referential_integrity",
            "dimension_matches_silver",
            "excludes_failed_products",
        }
        self.assertEqual({row["check_name"] for row in self.checks}, expected)
        self.assertTrue(all(row["rows_failed"] == 0 for row in self.checks))

    def test_duplicate_grain_is_detected(self):
        tainted = copy.deepcopy(self.gold)
        tainted.append(copy.deepcopy(tainted[0]))
        checks = {
            row["check_name"]: row
            for row in validate_sales_by_product(tainted, self.silver)
        }
        self.assertEqual(checks["grain_uniqueness"]["status"], "FAIL")
        self.assertEqual(checks["order_count_reconciles"]["status"], "FAIL")

    def test_independent_avg_calculation_is_detected(self):
        tainted = copy.deepcopy(self.gold)
        tainted[0]["avg_order_value"] = money(
            Decimal(str(tainted[0]["avg_order_value"])) + Decimal("5.00")
        )
        checks = {
            row["check_name"]: row
            for row in validate_sales_by_product(tainted, self.silver)
        }
        self.assertEqual(checks["derived_avg_order_value"]["status"], "FAIL")

    def test_join_fanout_is_detected(self):
        tainted = copy.deepcopy(self.gold)
        tainted[0]["total_orders"] = int(tainted[0]["total_orders"]) * 2
        tainted[0]["total_revenue"] = money(Decimal(str(tainted[0]["total_revenue"])) * 2)
        tainted[0]["avg_order_value"] = money(
            Decimal(str(tainted[0]["total_revenue"])) / int(tainted[0]["total_orders"])
        )
        checks = {
            row["check_name"]: row
            for row in validate_sales_by_product(tainted, self.silver)
        }
        self.assertEqual(checks["order_count_reconciles"]["status"], "FAIL")
        self.assertEqual(checks["revenue_reconciles"]["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
