"""Tests for Silver referential integrity — orphans flagged, NULLs left to completeness."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src" / "data_generation"))

import generate_sample_data as gen  # noqa: E402
from silver_harness import failed, flag  # noqa: E402


class ReferentialIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.customers = flag("04_quality_referential_integrity.py", "customers")
        cls.products = flag("04_quality_referential_integrity.py", "products")
        cls.orders = flag("04_quality_referential_integrity.py", "orders")

    def test_parent_tables_are_not_applicable(self):
        self.assertTrue(
            all(row["referential_integrity_flag"] == "NOT_APPLICABLE" for row in self.customers)
        )
        self.assertTrue(
            all(row["referential_integrity_flag"] == "NOT_APPLICABLE" for row in self.products)
        )

    def test_orphan_customer_ids(self):
        bad = [
            row
            for row in failed(self.orders, "referential_integrity_flag")
            if "ORPHAN_CUSTOMER_ID" in row["_referential_integrity_reasons"]
        ]
        self.assertEqual(len(bad), gen.N_ORPHAN_CUSTOMER_ID)
        self.assertEqual({row["order_id"] for row in bad}, set(gen.ORPHAN_CUSTOMER_ORDER_IDS))
        self.assertTrue(
            all(
                gen.ORPHAN_CUSTOMER_ID_START
                <= row["customer_id"]
                < gen.ORPHAN_CUSTOMER_ID_START + gen.N_ORPHAN_CUSTOMER_ID
                for row in bad
            )
        )

    def test_orphan_product_ids(self):
        bad = [
            row
            for row in failed(self.orders, "referential_integrity_flag")
            if "ORPHAN_PRODUCT_ID" in row["_referential_integrity_reasons"]
        ]
        self.assertEqual(len(bad), gen.N_ORPHAN_PRODUCT_ID)
        self.assertEqual({row["order_id"] for row in bad}, set(gen.ORPHAN_PRODUCT_ORDER_IDS))

    def test_null_foreign_keys_are_not_ri_failures(self):
        null_rows = [
            row
            for row in self.orders
            if row["order_id"]
            in set(gen.NULL_ORDER_CUSTOMER_IDS) | set(gen.NULL_ORDER_PRODUCT_IDS)
        ]
        self.assertEqual(
            len(null_rows), gen.N_NULL_ORDER_CUSTOMER_ID + gen.N_NULL_ORDER_PRODUCT_ID
        )
        self.assertTrue(all(row["referential_integrity_flag"] == "PASS" for row in null_rows))

    def test_valid_order_passes(self):
        row = next(r for r in self.orders if r["order_id"] == 5000)
        self.assertEqual(row["referential_integrity_flag"], "PASS")


if __name__ == "__main__":
    unittest.main()
