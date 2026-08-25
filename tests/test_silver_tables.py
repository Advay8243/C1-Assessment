"""End-to-end Silver table contract: flags combined, rows kept, metrics produced."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "silver"))
sys.path.insert(0, str(ROOT / "src" / "data_generation"))

import generate_sample_data as gen  # noqa: E402
from silver_utils import (  # noqa: E402
    FAIL,
    NOT_APPLICABLE,
    PASS,
    apply_all_python,
    build_context,
    build_metrics,
    load_landing_records,
)


class SilverTablesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = load_landing_records(ROOT / "data")
        cls.ctx = build_context(cls.source["customers"], cls.source["products"])
        cls.tables = apply_all_python(
            cls.source["customers"],
            cls.source["products"],
            cls.source["orders"],
            cls.ctx,
        )
        cls.metrics = build_metrics(cls.tables, cls.ctx)
        cls.metrics_by_key = {
            (row["table_name"], row["check_name"]): row for row in cls.metrics
        }

    def test_silver_keeps_every_bronze_row(self):
        self.assertEqual(len(self.tables["customers"]), 10_010)
        self.assertEqual(len(self.tables["products"]), 505)
        self.assertEqual(len(self.tables["orders"]), 100_020)

    def test_known_bad_customer_fails_overall(self):
        row = next(r for r in self.tables["customers"] if r["customer_id"] == 1)
        self.assertEqual(row["quality_check_result"], FAIL)
        self.assertIn("NULL_EMAIL", row["failure_reasons"])

    def test_clean_customer_passes_overall(self):
        row = next(r for r in self.tables["customers"] if r["customer_id"] == 51)
        self.assertEqual(row["quality_check_result"], PASS)
        self.assertEqual(row["failure_reasons"], "")

    def test_orphan_order_fails_overall(self):
        row = next(
            r
            for r in self.tables["orders"]
            if r["order_id"] == next(iter(gen.ORPHAN_CUSTOMER_ORDER_IDS))
        )
        self.assertEqual(row["quality_check_result"], FAIL)
        self.assertIn("ORPHAN_CUSTOMER_ID", row["failure_reasons"])

    def test_parent_ri_not_applicable_does_not_fail_clean_product(self):
        row = next(r for r in self.tables["products"] if r["product_id"] == 50)
        self.assertEqual(row["referential_integrity_flag"], NOT_APPLICABLE)
        self.assertEqual(row["quality_check_result"], PASS)

    def test_metrics_cover_required_checks(self):
        customer_checks = {check for table, check in self.metrics_by_key if table == "customers"}
        order_checks = {check for table, check in self.metrics_by_key if table == "orders"}
        self.assertEqual(
            customer_checks,
            {"completeness", "uniqueness", "type_validation", "business_logic"},
        )
        self.assertIn("referential_integrity", order_checks)

    def test_metrics_catch_planted_completeness_counts(self):
        customers = self.metrics_by_key[("customers", "completeness")]
        orders = self.metrics_by_key[("orders", "completeness")]
        products = self.metrics_by_key[("products", "completeness")]
        self.assertEqual(customers["rows_failed"], gen.N_NULL_EMAIL)
        self.assertEqual(
            orders["rows_failed"],
            gen.N_NULL_ORDER_CUSTOMER_ID + gen.N_NULL_ORDER_PRODUCT_ID,
        )
        self.assertEqual(
            products["rows_failed"],
            gen.N_NULL_PRODUCT_NAME + gen.N_NULL_CATEGORY,
        )

    def test_uniqueness_threshold_not_met(self):
        metric = self.metrics_by_key[("customers", "uniqueness")]
        self.assertEqual(metric["rows_failed"], gen.N_DUP_CUSTOMER_ID * 2)
        self.assertFalse(metric["threshold_met"])

    def test_ri_metrics_match_orphan_counts(self):
        metric = self.metrics_by_key[("orders", "referential_integrity")]
        self.assertEqual(
            metric["rows_failed"],
            gen.N_ORPHAN_CUSTOMER_ID + gen.N_ORPHAN_PRODUCT_ID,
        )


if __name__ == "__main__":
    unittest.main()
