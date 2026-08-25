"""
Silver completeness check.

Fail a row when a critical field is NULL / blank. Do not delete the row.
NULL foreign keys on orders are completeness failures, not referential ones.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

_FILE = globals().get("__file__")
_CWD = Path.cwd().resolve()
_src_candidates = []
if _FILE:
    _p = Path(_FILE).resolve()
    _src_candidates.extend([_p.parent, _p.parent.parent, _p.parent.parent.parent])
_src_candidates.extend([_CWD, _CWD / "src", _CWD.parent, _CWD.parent / "src"])
_src_candidates.extend(parent / "src" for parent in list(_CWD.parents)[:8])
for _src in _src_candidates:
    if (_src / "runtime_paths.py").is_file():
        if str(_src) not in sys.path:
            sys.path.insert(0, str(_src))
        break

from runtime_paths import add_layer_to_path  # noqa: E402

_SILVER_DIR = add_layer_to_path(_FILE, "silver")

from silver_utils import (  # noqa: E402
    FAIL,
    PASS,
    SilverContext,
    copy_rows,
    get_spark,
    set_check_result,
)

CHECK_NAME = "completeness"

# (field, reason_code) — empty string is treated as NULL.
CRITICAL_FIELDS = {
    "customers": [
        ("email", "NULL_EMAIL"),
        ("customer_id", "NULL_CUSTOMER_ID"),
        ("customer_name", "NULL_CUSTOMER_NAME"),
    ],
    "products": [
        ("product_id", "NULL_PRODUCT_ID"),
        ("product_name", "NULL_PRODUCT_NAME"),
        ("category", "NULL_CATEGORY"),
    ],
    "orders": [
        ("order_id", "NULL_ORDER_ID"),
        ("customer_id", "NULL_CUSTOMER_ID"),
        ("product_id", "NULL_PRODUCT_ID"),
        ("order_date", "NULL_ORDER_DATE"),
    ],
}


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def completeness_reasons(row: dict[str, Any], table_name: str) -> list[str]:
    return [
        reason
        for field_name, reason in CRITICAL_FIELDS[table_name]
        if _is_missing(row.get(field_name))
    ]


def flag_python(
    rows: list[dict[str, Any]],
    table_name: str,
    ctx: SilverContext | None = None,
) -> list[dict[str, Any]]:
    flagged = copy_rows(rows)
    for row in flagged:
        set_check_result(row, CHECK_NAME, completeness_reasons(row, table_name))
    return flagged


def apply_spark(df, table_name: str, ctx: SilverContext | None = None):
    from pyspark.sql.functions import col, expr, lit, size, when

    case_items = ", ".join(
        f"CASE WHEN {field_name} IS NULL OR trim(cast({field_name} AS string)) = '' "
        f"THEN '{reason}' END"
        for field_name, reason in CRITICAL_FIELDS[table_name]
    )
    reasons_expr = f"filter(array({case_items}), x -> x IS NOT NULL)"
    return (
        df.withColumn("_completeness_reasons", expr(reasons_expr))
        .withColumn(
            "completeness_flag",
            when(size(col("_completeness_reasons")) == 0, lit(PASS)).otherwise(lit(FAIL)),
        )
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Silver completeness check on Bronze tables")
    parser.add_argument("--table", choices=sorted(CRITICAL_FIELDS), default=None)
    return parser.parse_known_args()[0]


def main() -> None:
    args = parse_args()
    spark = get_spark()
    tables = [args.table] if args.table else list(CRITICAL_FIELDS)
    for table_name in tables:
        df = apply_spark(spark.table(f"bronze.{table_name}"), table_name)
        failed = df.filter(col_flag_fail(df)).count()
        print(f"{table_name}: completeness FAIL={failed} / {df.count()}")


def col_flag_fail(df):
    from pyspark.sql.functions import col

    return col("completeness_flag") == FAIL


if __name__ == "__main__":
    main()
