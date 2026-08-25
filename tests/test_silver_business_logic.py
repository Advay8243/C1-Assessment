"""Tests for Silver business-logic checks."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src" / "data_generation"))

import generate_sample_data as gen  # noqa: E402
from silver_harness import failed, flag  # noqa: E402


class BusinessLogicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.customers = flag("05_quality_business_logic.py", "customers")
        cls.products = flag("05_quality_business_logic.py", "products")
        cls.orders = flag("05_quality_business_logic.py", "orders")

    def test_future_signup_date(self):
        bad = [
            row
            for row in failed(self.customers, "business_logic_flag")
            if "FUTURE_SIGNUP_DATE" in row["_business_logic_reasons"]
        ]
        self.assertEqual(len(bad), gen.N_FUTURE_SIGNUP)
        self.assertEqual({row["customer_id"] for row in bad}, set(gen.FUTURE_SIGNUP_IDS))

    def test_cost_greater_than_price(self):
        bad = [
            row
            for row in failed(self.products, "business_logic_flag")
            if "COST_GT_PRICE" in row["_business_logic_reasons"]
        ]
        self.assertEqual(len(bad), gen.N_COST_GT_PRICE)
        self.assertEqual({row["product_id"] for row in bad}, set(gen.COST_GT_PRICE_IDS))

    def test_wrong_total_amount(self):
        bad = [
            row
            for row in failed(self.orders, "business_logic_flag")
            if "TOTAL_AMOUNT_MISMATCH" in row["_business_logic_reasons"]
        ]
        self.assertEqual(len(bad), gen.N_WRONG_TOTAL_AMOUNT)
        self.assertEqual({row["order_id"] for row in bad}, set(gen.WRONG_TOTAL_ORDER_IDS))

    def test_completed_without_payment(self):
        bad = [
            row
            for row in failed(self.orders, "business_logic_flag")
            if "COMPLETED_WITHOUT_PAYMENT" in row["_business_logic_reasons"]
        ]
        self.assertEqual(len(bad), gen.N_COMPLETED_WITHOUT_PAYMENT)
        self.assertEqual({row["order_id"] for row in bad}, set(gen.COMPLETED_NO_PAY_IDS))

    def test_pending_with_payment(self):
        bad = [
            row
            for row in failed(self.orders, "business_logic_flag")
            if "PAYMENT_ON_OPEN_ORDER" in row["_business_logic_reasons"]
        ]
        self.assertEqual(len(bad), gen.N_PENDING_WITH_PAYMENT)
        self.assertEqual({row["order_id"] for row in bad}, set(gen.PENDING_WITH_PAY_IDS))

    def test_negative_stock_is_not_business_logic(self):
        rows = [
            row for row in self.products if row["product_id"] in set(gen.NEGATIVE_STOCK_IDS)
        ]
        self.assertTrue(all(row["business_logic_flag"] == "PASS" for row in rows))

    def test_clean_customer_passes(self):
        row = next(r for r in self.customers if r["customer_id"] == 51)
        self.assertEqual(row["business_logic_flag"], "PASS")


if __name__ == "__main__":
    unittest.main()
