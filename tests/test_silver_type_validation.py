"""Tests for Silver type / domain validation."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src" / "data_generation"))

import generate_sample_data as gen  # noqa: E402
from silver_harness import failed, flag  # noqa: E402


class TypeValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.customers = flag("03_quality_type_validation.py", "customers")
        cls.products = flag("03_quality_type_validation.py", "products")
        cls.orders = flag("03_quality_type_validation.py", "orders")

    def test_invalid_customer_segment(self):
        bad = [
            row
            for row in failed(self.customers, "type_validation_flag")
            if "INVALID_CUSTOMER_SEGMENT" in row["_type_validation_reasons"]
        ]
        self.assertEqual(len(bad), gen.N_INVALID_SEGMENT)
        self.assertEqual({row["customer_id"] for row in bad}, set(gen.INVALID_SEGMENT_IDS))

    def test_malformed_email(self):
        bad = [
            row
            for row in failed(self.customers, "type_validation_flag")
            if "MALFORMED_EMAIL" in row["_type_validation_reasons"]
        ]
        self.assertEqual(len(bad), gen.N_MALFORMED_EMAIL)
        self.assertEqual({row["customer_id"] for row in bad}, set(gen.MALFORMED_EMAIL_IDS))

    def test_null_email_is_not_a_type_failure(self):
        null_email_rows = [
            row for row in self.customers if row["customer_id"] in set(gen.NULL_EMAIL_IDS)
        ]
        self.assertEqual(len(null_email_rows), gen.N_NULL_EMAIL)
        self.assertTrue(
            all(row["type_validation_flag"] == "PASS" for row in null_email_rows)
        )

    def test_negative_stock(self):
        bad = [
            row
            for row in failed(self.products, "type_validation_flag")
            if "NEGATIVE_STOCK" in row["_type_validation_reasons"]
        ]
        self.assertEqual(len(bad), gen.N_NEGATIVE_STOCK)
        self.assertEqual({row["product_id"] for row in bad}, set(gen.NEGATIVE_STOCK_IDS))

    def test_cost_gt_price_is_not_a_type_failure(self):
        """cost > price is business logic; both values are still valid decimals."""
        rows = [
            row for row in self.products if row["product_id"] in set(gen.COST_GT_PRICE_IDS)
        ]
        self.assertEqual(len(rows), gen.N_COST_GT_PRICE)
        self.assertTrue(all(row["type_validation_flag"] == "PASS" for row in rows))

    def test_clean_rows_pass(self):
        customer = next(r for r in self.customers if r["customer_id"] == 51)
        product = next(r for r in self.products if r["product_id"] == 50)
        self.assertEqual(customer["type_validation_flag"], "PASS")
        self.assertEqual(product["type_validation_flag"], "PASS")


if __name__ == "__main__":
    unittest.main()
