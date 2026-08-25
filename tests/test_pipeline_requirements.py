"""Requirements test tier for the medallion pipeline.

This is the evaluation's meaningful test layer: planted sample-data issues,
Bronze preserving them, Silver flagging (not deleting) them, Gold lining up
with Silver PASS+Completed facts, and dashboard queries staying on Gold.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src" / "bronze"))
sys.path.insert(0, str(ROOT / "src" / "gold"))
sys.path.insert(0, str(ROOT / "src" / "data_generation"))

import generate_sample_data as gen  # noqa: E402
import ingest_utils  # noqa: E402
from gold_utils import COMPLETED, PASS, SEGMENT_TYPES, money, qualifying_orders  # noqa: E402
from pipeline_harness import BUSINESS_COLUMNS, pipeline_bundle  # noqa: E402
from validate_gold import all_checks_passed  # noqa: E402

FAIL = "FAIL"

FAIL_CUSTOMER_IDS = (
    set(gen.NULL_EMAIL_IDS)
    | set(gen.INVALID_SEGMENT_IDS)
    | set(gen.MALFORMED_EMAIL_IDS)
    | set(gen.FUTURE_SIGNUP_IDS)
    | set(gen.DUP_CUSTOMER_SOURCE_IDS)
)
FAIL_PRODUCT_IDS = (
    set(gen.NULL_PRODUCT_NAME_IDS)
    | set(gen.NULL_CATEGORY_IDS)
    | set(gen.COST_GT_PRICE_IDS)
    | set(gen.NEGATIVE_STOCK_IDS)
    | set(gen.DUP_PRODUCT_SOURCE_IDS)
)
FAIL_ORDER_IDS = (
    set(gen.NULL_ORDER_CUSTOMER_IDS)
    | set(gen.NULL_ORDER_PRODUCT_IDS)
    | set(gen.ORPHAN_CUSTOMER_ORDER_IDS)
    | set(gen.ORPHAN_PRODUCT_ORDER_IDS)
    | set(gen.DUP_ORDER_SOURCE_IDS)
    | set(gen.WRONG_TOTAL_ORDER_IDS)
    | set(gen.COMPLETED_NO_PAY_IDS)
    | set(gen.PENDING_WITH_PAY_IDS)
)

# Duplicate keys produce two physical rows each.
EXPECTED_FAIL_CUSTOMER_ROWS = (
    gen.N_NULL_EMAIL
    + gen.N_INVALID_SEGMENT
    + gen.N_MALFORMED_EMAIL
    + gen.N_FUTURE_SIGNUP
    + gen.N_DUP_CUSTOMER_ID * 2
)
EXPECTED_FAIL_PRODUCT_ROWS = (
    gen.N_NULL_PRODUCT_NAME
    + gen.N_NULL_CATEGORY
    + gen.N_COST_GT_PRICE
    + gen.N_NEGATIVE_STOCK
    + gen.N_DUP_PRODUCT_ID * 2
)
EXPECTED_FAIL_ORDER_ROWS = (
    gen.N_NULL_ORDER_CUSTOMER_ID
    + gen.N_NULL_ORDER_PRODUCT_ID
    + gen.N_ORPHAN_CUSTOMER_ID
    + gen.N_ORPHAN_PRODUCT_ID
    + gen.N_DUP_ORDER_ID * 2
    + gen.N_WRONG_TOTAL_AMOUNT
    + gen.N_COMPLETED_WITHOUT_PAYMENT
    + gen.N_PENDING_WITH_PAYMENT
)


def _failed(rows: list[dict], key: str) -> list[dict]:
    return [row for row in rows if row.get("quality_check_result") == FAIL]


def _strip_sql_comments(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


def _select_statements(sql: str) -> list[str]:
    body = _strip_sql_comments(sql)
    parts = re.split(r"(?i)(?=\bSELECT\b)", body)
    return [part.strip().rstrip(";") for part in parts if part.strip().upper().startswith("SELECT")]


class SampleDataQualityIssuesTests(unittest.TestCase):
    """Landing CSVs must contain the brief's intentional defects at known IDs."""

    @classmethod
    def setUpClass(cls):
        cls.bundle = pipeline_bundle()
        cls.landing = cls.bundle["landing"]
        cls.stats = gen.verify(
            cls.landing["customers"],
            cls.landing["products"],
            cls.landing["orders"],
        )

    def test_volumes_match_the_brief_plus_duplicate_rows(self):
        self.assertEqual(self.stats["customer_rows"], 10_010)
        self.assertEqual(self.stats["product_rows"], 505)
        self.assertEqual(self.stats["order_rows"], 100_020)
        self.assertEqual(self.stats["null_email"], gen.N_NULL_EMAIL)
        self.assertEqual(self.stats["null_order_customer_id"], gen.N_NULL_ORDER_CUSTOMER_ID)
        self.assertEqual(self.stats["null_order_product_id"], gen.N_NULL_ORDER_PRODUCT_ID)
        self.assertEqual(self.stats["orphan_customer_id"], gen.N_ORPHAN_CUSTOMER_ID)
        self.assertEqual(self.stats["orphan_product_id"], gen.N_ORPHAN_PRODUCT_ID)
        self.assertEqual(self.stats["duplicate_customer_id_extra_rows"], gen.N_DUP_CUSTOMER_ID)
        self.assertEqual(self.stats["duplicate_order_id_extra_rows"], gen.N_DUP_ORDER_ID)

    def test_brief_issues_sit_on_the_planted_ids(self):
        customers = {row["customer_id"]: row for row in self.landing["customers"]}
        orders = {row["order_id"]: row for row in self.landing["orders"]}
        for customer_id in gen.NULL_EMAIL_IDS:
            self.assertIsNone(customers[customer_id]["email"])
        for order_id in gen.NULL_ORDER_CUSTOMER_IDS:
            self.assertIsNone(orders[order_id]["customer_id"])
        for order_id in gen.NULL_ORDER_PRODUCT_IDS:
            self.assertIsNone(orders[order_id]["product_id"])
        for order_id in gen.ORPHAN_CUSTOMER_ORDER_IDS:
            self.assertNotIn(orders[order_id]["customer_id"], customers)
        product_ids = {row["product_id"] for row in self.landing["products"]}
        for order_id in gen.ORPHAN_PRODUCT_ORDER_IDS:
            self.assertNotIn(orders[order_id]["product_id"], product_ids)

    def test_inactive_customers_have_no_orders(self):
        ordered = {
            row["customer_id"]
            for row in self.landing["orders"]
            if row["customer_id"] is not None
        }
        inactive_ids = set(range(gen.INACTIVE_CUSTOMER_ID_START, gen.N_CUSTOMERS + 1))
        self.assertTrue(inactive_ids.isdisjoint(ordered))
        self.assertEqual(len(inactive_ids), 301)


class BronzePreservesIssuesTests(unittest.TestCase):
    """Bronze is raw ingest: same rows and defects as landing, metadata only."""

    @classmethod
    def setUpClass(cls):
        cls.bundle = pipeline_bundle()
        cls.landing = cls.bundle["landing"]
        cls.bronze = cls.bundle["bronze"]

    def test_bronze_keeps_every_landing_row(self):
        for table_name in ("customers", "products", "orders"):
            self.assertEqual(len(self.bronze[table_name]), len(self.landing[table_name]))
            self.assertEqual(
                len(self.bronze[table_name]),
                ingest_utils.EXPECTED_ROW_COUNTS[table_name],
            )

    def test_business_columns_are_unchanged(self):
        for table_name, columns in BUSINESS_COLUMNS.items():
            landing_rows = self.landing[table_name]
            bronze_rows = self.bronze[table_name]
            self.assertEqual(len(landing_rows), len(bronze_rows))
            for landing_row, bronze_row in zip(landing_rows, bronze_rows):
                for column in columns:
                    self.assertEqual(
                        bronze_row[column],
                        landing_row[column],
                        f"{table_name}.{column} changed during Bronze ingest",
                    )

    def test_planted_defects_still_present(self):
        stats = gen.verify(
            self.bronze["customers"],
            self.bronze["products"],
            self.bronze["orders"],
        )
        self.assertEqual(stats["null_email"], gen.N_NULL_EMAIL)
        self.assertEqual(stats["null_order_customer_id"], gen.N_NULL_ORDER_CUSTOMER_ID)
        self.assertEqual(stats["orphan_customer_id"], gen.N_ORPHAN_CUSTOMER_ID)
        self.assertEqual(stats["duplicate_order_id_extra_rows"], gen.N_DUP_ORDER_ID)

    def test_ingest_adds_metadata_only_and_does_not_flag_quality(self):
        sample = self.bronze["orders"][0]
        for column in ingest_utils.METADATA_COLUMNS:
            self.assertIn(column, sample)
            self.assertIsNotNone(sample[column])
        self.assertNotIn("quality_check_result", sample)
        self.assertNotIn("completeness_flag", sample)
        batch_ids = {row["_batch_id"] for row in self.bronze["orders"]}
        self.assertEqual(len(batch_ids), 1)

    def test_spark_ingest_keeps_nulls_and_duplicates(self):
        source = (ROOT / "src" / "bronze" / "ingest_utils.py").read_text(encoding="utf-8")
        self.assertIn('option("nullValue", "")', source)
        self.assertIn("Intentionally no .dropDuplicates()", source)


class SilverHandlesIssuesTests(unittest.TestCase):
    """Silver flags every planted defect, keeps the row, and reports the checks."""

    @classmethod
    def setUpClass(cls):
        cls.bundle = pipeline_bundle()
        cls.bronze = cls.bundle["bronze"]
        cls.silver = cls.bundle["silver"]
        cls.metrics = {
            (row["table_name"], row["check_name"]): row for row in cls.bundle["metrics"]
        }

    def test_silver_does_not_delete_bronze_rows(self):
        for table_name in ("customers", "products", "orders"):
            self.assertEqual(len(self.silver[table_name]), len(self.bronze[table_name]))

    def test_every_planted_issue_fails_overall(self):
        failed_customers = _failed(self.silver["customers"], "customer_id")
        failed_products = _failed(self.silver["products"], "product_id")
        failed_orders = _failed(self.silver["orders"], "order_id")
        self.assertEqual(len(failed_customers), EXPECTED_FAIL_CUSTOMER_ROWS)
        self.assertEqual(len(failed_products), EXPECTED_FAIL_PRODUCT_ROWS)
        self.assertEqual(
            {row["customer_id"] for row in failed_customers}, FAIL_CUSTOMER_IDS
        )
        self.assertEqual({row["product_id"] for row in failed_products}, FAIL_PRODUCT_IDS)
        self.assertTrue(FAIL_ORDER_IDS.issubset({row["order_id"] for row in failed_orders}))
        self.assertGreaterEqual(len(failed_orders), EXPECTED_FAIL_ORDER_ROWS)

        extra_orders = [
            row for row in failed_orders if row["order_id"] not in FAIL_ORDER_IDS
        ]
        future_customers = set(gen.FUTURE_SIGNUP_IDS)
        self.assertTrue(extra_orders)
        self.assertTrue(
            all(
                row["customer_id"] in future_customers
                and "ORDER_BEFORE_SIGNUP" in row["failure_reasons"]
                for row in extra_orders
            )
        )

    def test_issues_are_mapped_to_the_correct_check(self):
        customers = self.silver["customers"]
        products = self.silver["products"]
        orders = {row["order_id"]: row for row in self.silver["orders"]}

        null_email = next(row for row in customers if row["customer_id"] == 1)
        self.assertEqual(null_email["completeness_flag"], FAIL)
        self.assertIn("NULL_EMAIL", null_email["failure_reasons"])

        dup_customer = [row for row in customers if row["customer_id"] == 991]
        self.assertEqual(len(dup_customer), 2)
        self.assertTrue(all(row["uniqueness_flag"] == FAIL for row in dup_customer))

        invalid_segment = next(row for row in customers if row["customer_id"] == 201)
        self.assertEqual(invalid_segment["type_validation_flag"], FAIL)

        future_signup = next(row for row in customers if row["customer_id"] == 221)
        self.assertEqual(future_signup["business_logic_flag"], FAIL)

        null_fk = orders[1]
        self.assertEqual(null_fk["completeness_flag"], FAIL)
        self.assertNotEqual(null_fk["referential_integrity_flag"], FAIL)
        self.assertNotIn("ORPHAN_CUSTOMER_ID", null_fk["failure_reasons"])

        orphan = orders[next(iter(gen.ORPHAN_CUSTOMER_ORDER_IDS))]
        self.assertEqual(orphan["completeness_flag"], PASS)
        self.assertEqual(orphan["referential_integrity_flag"], FAIL)
        self.assertIn("ORPHAN_CUSTOMER_ID", orphan["failure_reasons"])

        null_name = next(row for row in products if row["product_id"] == 1)
        self.assertEqual(null_name["completeness_flag"], FAIL)

    def test_clean_control_rows_pass(self):
        customer = next(row for row in self.silver["customers"] if row["customer_id"] == 51)
        product = next(row for row in self.silver["products"] if row["product_id"] == 50)
        self.assertEqual(customer["quality_check_result"], PASS)
        self.assertEqual(product["quality_check_result"], PASS)
        self.assertEqual(customer["failure_reasons"], "")
        self.assertEqual(product["failure_reasons"], "")

    def test_quality_metrics_cover_the_required_checks(self):
        order_checks = {check for table, check in self.metrics if table == "orders"}
        self.assertGreaterEqual(
            order_checks,
            {
                "completeness",
                "uniqueness",
                "type_validation",
                "referential_integrity",
                "business_logic",
            },
        )
        completeness = self.metrics[("orders", "completeness")]
        uniqueness = self.metrics[("customers", "uniqueness")]
        ri = self.metrics[("orders", "referential_integrity")]
        self.assertEqual(
            completeness["rows_failed"],
            gen.N_NULL_ORDER_CUSTOMER_ID + gen.N_NULL_ORDER_PRODUCT_ID,
        )
        self.assertEqual(uniqueness["rows_failed"], gen.N_DUP_CUSTOMER_ID * 2)
        self.assertEqual(
            ri["rows_failed"],
            gen.N_ORPHAN_CUSTOMER_ID + gen.N_ORPHAN_PRODUCT_ID,
        )
        self.assertIn("pass_percentage", completeness)
        self.assertFalse(uniqueness["threshold_met"])


class GoldAlignedWithSilverTests(unittest.TestCase):
    """Gold facts are PASS + Completed Silver only, and the three aggs agree."""

    @classmethod
    def setUpClass(cls):
        cls.bundle = pipeline_bundle()
        cls.silver = cls.bundle["silver"]
        cls.sales = cls.bundle["sales_by_product"]
        cls.revenue = cls.bundle["revenue_by_customer"]
        cls.trends = cls.bundle["daily_weekly_trends"]
        cls.segments = cls.bundle["customer_segmentation"]
        cls.qualifying, cls.pass_products = qualifying_orders(cls.silver)
        cls.qualifying_revenue = sum(
            (money(order["total_amount"]) for order in cls.qualifying), money(0)
        )

    def test_failed_and_open_orders_never_enter_gold(self):
        gold_product_ids = {row["product_id"] for row in self.sales}
        gold_customer_ids = {row["customer_id"] for row in self.revenue}
        self.assertTrue(FAIL_PRODUCT_IDS.isdisjoint(gold_product_ids))
        self.assertTrue(FAIL_CUSTOMER_IDS.isdisjoint(gold_customer_ids))
        leaked = [
            order["order_id"]
            for order in self.qualifying
            if order["order_id"] in FAIL_ORDER_IDS
        ]
        self.assertEqual(leaked, [])
        self.assertTrue(
            all(order["order_status"] == COMPLETED for order in self.qualifying)
        )
        self.assertTrue(
            all(order["quality_check_result"] == PASS for order in self.qualifying)
        )

    def test_aggregations_reconcile_to_the_same_silver_facts(self):
        sales_orders = sum(int(row["total_orders"]) for row in self.sales)
        sales_revenue = sum((money(row["total_revenue"]) for row in self.sales), money(0))
        customer_orders = sum(int(row["total_orders"]) for row in self.revenue)
        customer_revenue = sum(
            (money(row["total_revenue"]) for row in self.revenue), money(0)
        )
        trend_orders = sum(int(row["total_orders"]) for row in self.trends)
        trend_revenue = sum((money(row["total_revenue"]) for row in self.trends), money(0))
        segment_revenue = sum(
            (money(row["total_revenue"]) for row in self.segments), money(0)
        )
        expected_n = len(self.qualifying)
        self.assertEqual(sales_orders, expected_n)
        self.assertEqual(customer_orders, expected_n)
        self.assertEqual(trend_orders, expected_n)
        self.assertEqual(sales_revenue, self.qualifying_revenue)
        self.assertEqual(customer_revenue, self.qualifying_revenue)
        self.assertEqual(trend_revenue, self.qualifying_revenue)
        self.assertEqual(segment_revenue, self.qualifying_revenue)

    def test_brief_gold_tables_and_measures(self):
        self.assertTrue(self.sales)
        self.assertTrue(self.revenue)
        self.assertEqual({row["segment_type"] for row in self.segments}, set(SEGMENT_TYPES))
        for row in self.sales:
            self.assertEqual(
                money(row["avg_order_value"]),
                money(money(row["total_revenue"]) / int(row["total_orders"])),
            )
        for row in self.revenue:
            self.assertEqual(money(row["lifetime_value_actual"]), money(row["total_revenue"]))
        inactive = [
            row
            for row in self.revenue
            if gen.INACTIVE_CUSTOMER_ID_START <= int(row["customer_id"]) <= gen.N_CUSTOMERS
        ]
        self.assertEqual(len(inactive), 301)
        self.assertTrue(all(int(row["total_orders"]) == 0 for row in inactive))
        self.assertEqual(
            sum(int(row["customer_count"]) for row in self.segments),
            len(self.revenue),
        )

    def test_gold_quality_checks_pass(self):
        for table_name, checks in self.bundle["gold_checks"].items():
            self.assertTrue(
                all_checks_passed(checks),
                f"Gold quality checks failed for {table_name}: {checks}",
            )


class DashboardQualityTests(unittest.TestCase):
    """Dashboard tiles read Gold only and show the same numbers the Gold tables hold."""

    @classmethod
    def setUpClass(cls):
        cls.bundle = pipeline_bundle()
        cls.sql = cls.bundle["dashboard_sql"]
        cls.body = _strip_sql_comments(cls.sql)
        cls.statements = _select_statements(cls.sql)
        cls.sales = cls.bundle["sales_by_product"]
        cls.revenue = cls.bundle["revenue_by_customer"]
        cls.segments = cls.bundle["customer_segmentation"]
        cls.trends = cls.bundle["daily_weekly_trends"]
        cls.top10 = sorted(
            cls.sales, key=lambda row: money(row["total_revenue"]), reverse=True
        )[:10]
        cls.histogram = [
            row for row in cls.revenue if money(row["total_revenue"]) > 0
        ]

    def test_required_visualizations_are_gold_only(self):
        self.assertGreaterEqual(len(self.statements), 4)
        self.assertIn("Top 10 products by revenue", self.sql)
        self.assertIn("Customer revenue distribution", self.sql)
        self.assertIn("Customer segmentation", self.sql)
        self.assertIn("Bar", self.sql)
        self.assertIn("Histogram", self.sql)
        self.assertIn("Pie", self.sql)
        self.assertNotIn("silver.", self.body)
        self.assertNotIn("bronze.", self.body)
        self.assertNotRegex(self.body, r"(?i)from\s+(customers|orders|products)\b")
        for statement in self.statements:
            self.assertRegex(statement, r"(?i)\bfrom\s+gold\.")

    def test_tiles_do_not_reaggregate_silver_facts(self):
        self.assertNotRegex(self.body, r"(?i)sum\s*\(\s*total_amount\s*\)")
        self.assertNotRegex(
            self.body,
            r"WHEN total_orders >= 2 AND total_revenue >= 1000 THEN 'High-Value'",
        )
        self.assertIn("LIMIT 10", self.body)

    def test_bar_tile_is_top_ten_gold_products(self):
        self.assertEqual(len(self.top10), 10)
        labels = [
            f"{row['product_id']} — {row['product_name']}" for row in self.top10
        ]
        self.assertEqual(len(labels), len(set(labels)))
        revenues = [money(row["total_revenue"]) for row in self.top10]
        self.assertEqual(revenues, sorted(revenues, reverse=True))
        self.assertTrue(
            set(row["product_id"] for row in self.top10).isdisjoint(FAIL_PRODUCT_IDS)
        )

    def test_histogram_is_one_positive_revenue_per_customer(self):
        self.assertTrue(self.histogram)
        self.assertEqual(
            len(self.histogram),
            len({row["customer_id"] for row in self.histogram}),
        )
        self.assertTrue(all(money(row["total_revenue"]) > 0 for row in self.histogram))
        zeros = [row for row in self.revenue if money(row["total_revenue"]) == 0]
        self.assertTrue(zeros)
        self.assertEqual(len(self.histogram) + len(zeros), len(self.revenue))

    def test_pie_matches_gold_segmentation(self):
        types = [row["segment_type"] for row in self.segments]
        self.assertEqual(types, list(SEGMENT_TYPES))
        self.assertEqual(
            sum(int(row["customer_count"]) for row in self.segments),
            len(self.revenue),
        )
        self.assertTrue(all(int(row["customer_count"]) > 0 for row in self.segments))

    def test_line_tile_matches_gold_daily_trends(self):
        dates = [row["order_date"] for row in self.trends]
        self.assertEqual(dates, sorted(dates))
        self.assertEqual(len(dates), len(set(dates)))
        self.assertEqual(
            sum((money(row["total_revenue"]) for row in self.trends), money(0)),
            sum((money(row["total_revenue"]) for row in self.sales), money(0)),
        )


if __name__ == "__main__":
    unittest.main()
