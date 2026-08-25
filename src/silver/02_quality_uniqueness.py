"""
Silver uniqueness check.

Fail every row whose natural key appears more than once. NULL keys are not
treated as duplicates (completeness owns those). Rows are flagged, not dropped.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
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

CHECK_NAME = "uniqueness"

KEY_FIELDS = {
    "customers": ("customer_id", "DUPLICATE_CUSTOMER_ID"),
    "products": ("product_id", "DUPLICATE_PRODUCT_ID"),
    "orders": ("order_id", "DUPLICATE_ORDER_ID"),
}


def flag_python(
    rows: list[dict[str, Any]],
    table_name: str,
    ctx: SilverContext | None = None,
) -> list[dict[str, Any]]:
    key_field, reason = KEY_FIELDS[table_name]
    counts = Counter(row.get(key_field) for row in rows if row.get(key_field) is not None)
    flagged = copy_rows(rows)
    for row in flagged:
        key = row.get(key_field)
        reasons = [reason] if key is not None and counts[key] > 1 else []
        set_check_result(row, CHECK_NAME, reasons)
    return flagged


def apply_spark(df, table_name: str, ctx: SilverContext | None = None):
    from pyspark.sql.functions import col, count, lit, when, array, size
    from pyspark.sql.window import Window

    key_field, reason = KEY_FIELDS[table_name]
    window = Window.partitionBy(key_field)
    with_counts = df.withColumn("_key_count", count(lit(1)).over(window))
    is_dup = col(key_field).isNotNull() & (col("_key_count") > 1)
    return (
        with_counts.withColumn(
            "_uniqueness_reasons",
            when(is_dup, array(lit(reason))).otherwise(array()),
        )
        .withColumn(
            "uniqueness_flag",
            when(size(col("_uniqueness_reasons")) == 0, lit(PASS)).otherwise(lit(FAIL)),
        )
        .drop("_key_count")
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Silver uniqueness check on Bronze tables")
    parser.add_argument("--table", choices=sorted(KEY_FIELDS), default=None)
    return parser.parse_known_args()[0]


def main() -> None:
    from pyspark.sql.functions import col

    args = parse_args()
    spark = get_spark()
    tables = [args.table] if args.table else list(KEY_FIELDS)
    for table_name in tables:
        df = apply_spark(spark.table(f"bronze.{table_name}"), table_name)
        failed = df.filter(col("uniqueness_flag") == FAIL).count()
        print(f"{table_name}: uniqueness FAIL={failed} / {df.count()}")


if __name__ == "__main__":
    main()
