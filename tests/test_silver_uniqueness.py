"""Tests for Silver uniqueness — every duplicate-key row is flagged, none dropped."""

from __future__ import annotations

import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src" / "data_generation"))

import generate_sample_data as gen  # noqa: E402
from silver_harness import failed, flag, records  # noqa: E402


class UniquenessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.customers = flag("02_quality_uniqueness.py", "customers")
        cls.products = flag("02_quality_uniqueness.py", "products")
        cls.orders = flag("02_quality_uniqueness.py", "orders")

    def test_row_counts_unchanged(self):
        source = records()
        self.assertEqual(len(self.customers), len(source["customers"]))
        self.assertEqual(len(self.products), len(source["products"]))
        self.assertEqual(len(self.orders), len(source["orders"]))

    def test_duplicate_customer_ids(self):
        bad = failed(self.customers, "uniqueness_flag")
        # 10 extra rows → 10 IDs appear twice → 20 failing rows
        self.assertEqual(len(bad), gen.N_DUP_CUSTOMER_ID * 2)
        self.assertEqual({row["customer_id"] for row in bad}, set(gen.DUP_CUSTOMER_SOURCE_IDS))
        counts = Counter(row["customer_id"] for row in self.customers)
        extra = sum(n - 1 for n in counts.values() if n > 1)
        self.assertEqual(extra, gen.N_DUP_CUSTOMER_ID)

    def test_duplicate_product_ids(self):
        bad = failed(self.products, "uniqueness_flag")
        self.assertEqual(len(bad), gen.N_DUP_PRODUCT_ID * 2)
        self.assertEqual({row["product_id"] for row in bad}, set(gen.DUP_PRODUCT_SOURCE_IDS))

    def test_duplicate_order_ids(self):
        bad = failed(self.orders, "uniqueness_flag")
        self.assertEqual(len(bad), gen.N_DUP_ORDER_ID * 2)
        self.assertEqual({row["order_id"] for row in bad}, set(gen.DUP_ORDER_SOURCE_IDS))

    def test_unique_customer_passes(self):
        row = next(r for r in self.customers if r["customer_id"] == 51)
        self.assertEqual(row["uniqueness_flag"], "PASS")

    def test_null_order_keys_are_not_duplicates(self):
        """NULL FKs/IDs are completeness issues; uniqueness ignores null keys."""
        null_fk_orders = [
            row
            for row in self.orders
            if row["order_id"] in set(gen.NULL_ORDER_CUSTOMER_IDS)
        ]
        self.assertTrue(null_fk_orders)
        self.assertTrue(all(row["uniqueness_flag"] == "PASS" for row in null_fk_orders))


if __name__ == "__main__":
    unittest.main()
