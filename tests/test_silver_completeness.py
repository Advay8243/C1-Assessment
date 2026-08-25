"""Tests for Silver completeness — planted NULLs must be flagged, rows kept."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src" / "data_generation"))

import generate_sample_data as gen  # noqa: E402
from silver_harness import failed, flag, records  # noqa: E402


class CompletenessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.customers = flag("01_quality_completeness.py", "customers")
        cls.products = flag("01_quality_completeness.py", "products")
        cls.orders = flag("01_quality_completeness.py", "orders")

    def test_row_counts_unchanged(self):
        source = records()
        self.assertEqual(len(self.customers), len(source["customers"]))
        self.assertEqual(len(self.products), len(source["products"]))
        self.assertEqual(len(self.orders), len(source["orders"]))

    def test_customers_null_email(self):
        bad = failed(self.customers, "completeness_flag")
        self.assertEqual(len(bad), gen.N_NULL_EMAIL)
        self.assertEqual({row["customer_id"] for row in bad}, set(gen.NULL_EMAIL_IDS))
        for row in bad:
            self.assertIn("NULL_EMAIL", row["_completeness_reasons"])

    def test_products_null_name_and_category(self):
        bad = failed(self.products, "completeness_flag")
        self.assertEqual(len(bad), gen.N_NULL_PRODUCT_NAME + gen.N_NULL_CATEGORY)
        names = {row["product_id"] for row in bad if "NULL_PRODUCT_NAME" in row["_completeness_reasons"]}
        cats = {row["product_id"] for row in bad if "NULL_CATEGORY" in row["_completeness_reasons"]}
        self.assertEqual(names, set(gen.NULL_PRODUCT_NAME_IDS))
        self.assertEqual(cats, set(gen.NULL_CATEGORY_IDS))

    def test_orders_null_foreign_keys(self):
        bad = failed(self.orders, "completeness_flag")
        self.assertEqual(len(bad), gen.N_NULL_ORDER_CUSTOMER_ID + gen.N_NULL_ORDER_PRODUCT_ID)
        null_cust = {row["order_id"] for row in bad if "NULL_CUSTOMER_ID" in row["_completeness_reasons"]}
        null_prod = {row["order_id"] for row in bad if "NULL_PRODUCT_ID" in row["_completeness_reasons"]}
        self.assertEqual(null_cust, set(gen.NULL_ORDER_CUSTOMER_IDS))
        self.assertEqual(null_prod, set(gen.NULL_ORDER_PRODUCT_IDS))

    def test_clean_customer_passes(self):
        row = next(r for r in self.customers if r["customer_id"] == 51)
        self.assertEqual(row["completeness_flag"], "PASS")


if __name__ == "__main__":
    unittest.main()
