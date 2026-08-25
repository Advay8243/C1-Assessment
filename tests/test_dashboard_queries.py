"""Dashboard SQL must read Gold only and match the three brief visualizations."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src" / "gold"))

from gold_harness import gold_bundle  # noqa: E402
from gold_utils import SEGMENT_TYPES, money  # noqa: E402

SQL_PATH = ROOT / "src" / "dashboard" / "dashboard_queries.sql"


def _strip_comments(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


class DashboardQueryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = SQL_PATH.read_text(encoding="utf-8")
        cls.body = _strip_comments(cls.sql)

    def test_three_required_visualizations_are_documented(self):
        self.assertIn("Bar", self.sql)
        self.assertIn("Histogram", self.sql)
        self.assertIn("Pie", self.sql)
        self.assertIn("Top 10 products by revenue", self.sql)
        self.assertIn("Customer revenue distribution", self.sql)
        self.assertIn("Customer segmentation", self.sql)

    def test_queries_read_gold_not_silver_or_bronze(self):
        self.assertIn("gold.sales_by_product", self.body)
        self.assertIn("gold.revenue_by_customer", self.body)
        self.assertIn("gold.customer_segmentation", self.body)
        self.assertNotIn("silver.", self.body)
        self.assertNotIn("bronze.", self.body)

    def test_top_ten_is_a_limit_not_a_new_aggregation(self):
        self.assertIn("LIMIT 10", self.body)
        self.assertNotRegex(self.body, r"SUM\s*\(\s*total_amount\s*\)")

    def test_segmentation_tile_does_not_rebuild_case_logic(self):
        self.assertNotRegex(
            self.body,
            r"WHEN total_orders >= 2 AND total_revenue >= 1000 THEN 'High-Value'",
        )


class DashboardResultTests(unittest.TestCase):
    """Same ranking / slices the Databricks tiles will show, from Gold Python."""

    @classmethod
    def setUpClass(cls):
        cls.bundle = gold_bundle()

    def test_top_10_products_are_unique_and_descending(self):
        ranked = sorted(
            self.bundle["sales_by_product"],
            key=lambda row: money(row["total_revenue"]),
            reverse=True,
        )[:10]
        self.assertEqual(len(ranked), 10)
        ids = [row["product_id"] for row in ranked]
        self.assertEqual(len(ids), len(set(ids)))
        labels = [f"{row['product_id']} — {row['product_name']}" for row in ranked]
        self.assertEqual(len(labels), len(set(labels)))
        revenues = [money(row["total_revenue"]) for row in ranked]
        self.assertEqual(revenues, sorted(revenues, reverse=True))

    def test_histogram_source_is_one_revenue_per_customer(self):
        values = [
            money(row["total_revenue"])
            for row in self.bundle["revenue_by_customer"]
            if money(row["total_revenue"]) > 0
        ]
        self.assertTrue(values)
        self.assertEqual(
            len(values),
            len(
                [
                    row
                    for row in self.bundle["revenue_by_customer"]
                    if int(row["total_orders"]) > 0
                ]
            ),
        )

    def test_pie_has_four_brief_segments_once(self):
        rows = self.bundle["customer_segmentation"]
        types = [row["segment_type"] for row in rows]
        self.assertEqual(len(types), 4)
        self.assertEqual(len(set(types)), 4)
        self.assertEqual(set(types), set(SEGMENT_TYPES))


if __name__ == "__main__":
    unittest.main()
