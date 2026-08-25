"""Path helpers must work when Databricks does not set __file__."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from runtime_paths import add_layer_to_path, layer_dir, materialize_src, parse_cli_args, repo_root  # noqa: E402

ENTRY_SCRIPTS = (
    ROOT / "src" / "bronze" / "ingest_all.py",
    ROOT / "src" / "silver" / "create_silver_tables.py",
    ROOT / "src" / "gold" / "create_gold_tables.py",
)


class RuntimePathTests(unittest.TestCase):
    def test_repo_root_from_file(self):
        root = repo_root(str(Path(__file__)))
        self.assertTrue((root / "databricks.yml").is_file())

    def test_materialize_src_is_noop_outside_workspace(self):
        src = ROOT / "src"
        self.assertEqual(materialize_src(src), src.resolve())

    def test_path_variants_include_workspace_prefix(self):
        from runtime_paths import _path_variants

        variants = _path_variants(
            "/Workspace/Users/a@b.com/.bundle/c1-medallion-pipeline/dev/files/src/gold/validate_gold.py"
        )
        self.assertTrue(any(v.startswith("/Workspace/") for v in variants))
        self.assertTrue(any(v.startswith("/Users/") for v in variants))

    def test_read_workspace_text_local_file(self):
        from runtime_paths import read_workspace_text

        path = ROOT / "src" / "gold" / "01_sales_by_product.sql"
        text = read_workspace_text(path)
        self.assertIn("pass_products", text)

    def test_repo_root_without_file(self):
        root = repo_root(None)
        self.assertTrue((root / "databricks.yml").is_file())

    def test_layer_dirs_without_file(self):
        self.assertTrue((layer_dir(None, "bronze") / "ingest_utils.py").is_file())
        self.assertTrue((layer_dir(None, "silver") / "silver_utils.py").is_file())
        self.assertTrue((layer_dir(None, "gold") / "gold_utils.py").is_file())

    def test_add_layer_to_path_without_file(self):
        bronze = add_layer_to_path(None, "bronze")
        self.assertTrue((bronze / "ingest_utils.py").is_file())

    def test_job_entry_scripts_import_without_file(self):
        for path in ENTRY_SCRIPTS:
            with self.subTest(script=path.name):
                namespace = {"__name__": "databricks_exec_test"}
                exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), namespace)
                self.assertNotIn("__file__", namespace)

    def test_parse_cli_args_ignores_ipython_kernel_flag(self):
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--output-dir", default=None)
        parser.add_argument("--seed", type=int, default=42)
        parsed = parse_cli_args(
            parser,
            ["-f", "/local_disk0/sandboxapi/123_2/connection.json", "--seed", "7"],
        )
        self.assertEqual(parsed.seed, 7)
        self.assertIsNone(parsed.output_dir)

    def test_sample_data_parser_ignores_ipython_kernel_flag(self):
        import unittest.mock

        sys.path.insert(0, str(ROOT / "src" / "data_generation"))
        import generate_sample_data as gen

        with unittest.mock.patch.object(
            sys,
            "argv",
            [
                "db_ipykernel_launcher.py",
                "-f",
                "/local_disk0/sandboxapi/123_2/connection.json",
            ],
        ):
            args = gen.parse_args()
        self.assertEqual(args.seed, 42)
        self.assertIsNone(args.output_dir)


if __name__ == "__main__":
    unittest.main()
