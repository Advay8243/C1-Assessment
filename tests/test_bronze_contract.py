"""Contract tests for Bronze ingest — no Spark required.

These tests lock: schema alignment with the generator, dirty rows still in
the landing CSVs, and local input validation (missing file / missing columns).
They do not run quality checks on the data.
"""

from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "bronze"))
sys.path.insert(0, str(ROOT / "src" / "data_generation"))

import ingest_utils  # noqa: E402
import generate_sample_data as gen  # noqa: E402


class BronzeSchemaContractTests(unittest.TestCase):
    def test_business_columns_match_generator(self):
        self.assertEqual(
            [name for name, _ in ingest_utils.BUSINESS_FIELDS["customers"]],
            gen.CUSTOMER_COLUMNS,
        )
        self.assertEqual(
            [name for name, _ in ingest_utils.BUSINESS_FIELDS["products"]],
            gen.PRODUCT_COLUMNS,
        )
        self.assertEqual(
            [name for name, _ in ingest_utils.BUSINESS_FIELDS["orders"]],
            gen.ORDER_COLUMNS,
        )

    def test_metadata_columns_are_ingest_only(self):
        self.assertEqual(
            ingest_utils.METADATA_COLUMNS,
            ("_source_file", "_ingest_timestamp", "_batch_id"),
        )

    def test_expected_counts_include_duplicate_rows(self):
        self.assertEqual(ingest_utils.EXPECTED_ROW_COUNTS["customers"], 10_010)
        self.assertEqual(ingest_utils.EXPECTED_ROW_COUNTS["products"], 505)
        self.assertEqual(ingest_utils.EXPECTED_ROW_COUNTS["orders"], 100_020)


class LandingFileStillDirtyTests(unittest.TestCase):
    """Bronze must ingest these defects; if the CSVs were cleaned, ingest is wrong."""

    @classmethod
    def setUpClass(cls):
        cls.customers = _read_csv(ROOT / "data" / "customers.csv")
        cls.products = _read_csv(ROOT / "data" / "products.csv")
        cls.orders = _read_csv(ROOT / "data" / "orders.csv")

    def test_physical_row_counts_keep_duplicates(self):
        self.assertEqual(len(self.customers), 10_010)
        self.assertEqual(len(self.products), 505)
        self.assertEqual(len(self.orders), 100_020)
        self.assertEqual(len({row["customer_id"] for row in self.customers}), 10_000)
        self.assertEqual(len({row["product_id"] for row in self.products}), 500)
        self.assertEqual(len({row["order_id"] for row in self.orders}), 100_000)

    def test_nulls_still_present(self):
        self.assertEqual(sum(1 for row in self.customers if row["email"] == ""), 50)
        self.assertEqual(sum(1 for row in self.orders if row["customer_id"] == ""), 100)
        self.assertEqual(sum(1 for row in self.orders if row["product_id"] == ""), 200)
        self.assertEqual(sum(1 for row in self.products if row["product_name"] == ""), 10)


class SourceValidationTests(unittest.TestCase):
    def test_missing_local_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            ingest_utils.assert_source_readable("/tmp/does-not-exist-customers.csv", "customers")

    def test_missing_header_column_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "customers.csv"
            path.write_text("customer_id,customer_name\n1,Ada\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                ingest_utils.assert_source_readable(str(path), "customers")

    def test_real_landing_files_are_readable(self):
        for table_name in ("customers", "products", "orders"):
            path = ingest_utils.source_path(str(ROOT / "data"), table_name)
            ingest_utils.assert_source_readable(path, table_name)

    def test_dbfs_paths_skip_local_stat(self):
        ingest_utils.assert_source_readable(
            "dbfs:/Volumes/main/landing/customers.csv", "customers"
        )

    def test_filestore_landing_falls_back_to_repo_data(self):
        landing = ingest_utils.resolve_landing_dir("dbfs:/FileStore/medallion/landing")
        self.assertTrue(str(landing).endswith("data"))
        self.assertNotIn("FileStore", landing)

    def test_workspace_paths_use_file_scheme_for_spark(self):
        converted = ingest_utils.to_spark_path(
            "/Workspace/Users/a@b.com/.bundle/c1-medallion-pipeline/dev/files/data/customers.csv"
        )
        self.assertTrue(converted.startswith("/Workspace/"))
        self.assertNotIn("file:", converted)
        self.assertIn("@", converted)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


if __name__ == "__main__":
    unittest.main()
