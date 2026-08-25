"""
Silver referential integrity check.

Orders fail when a non-null customer_id / product_id does not exist in the
parent Bronze table. NULL FKs are completeness failures, not RI failures.
Customers and products are marked NOT_APPLICABLE.
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
    NOT_APPLICABLE,
    PASS,
    SilverContext,
    copy_rows,
    get_spark,
    set_check_result,
)

CHECK_NAME = "referential_integrity"


def referential_reasons(row: dict[str, Any], ctx: SilverContext) -> list[str]:
    reasons: list[str] = []
    customer_id = row.get("customer_id")
    product_id = row.get("product_id")
    if customer_id is not None and customer_id not in ctx.customer_ids:
        reasons.append("ORPHAN_CUSTOMER_ID")
    if product_id is not None and product_id not in ctx.product_ids:
        reasons.append("ORPHAN_PRODUCT_ID")
    return reasons


def flag_python(
    rows: list[dict[str, Any]],
    table_name: str,
    ctx: SilverContext,
) -> list[dict[str, Any]]:
    flagged = copy_rows(rows)
    for row in flagged:
        if table_name != "orders":
            set_check_result(row, CHECK_NAME, [], na=True)
        else:
            set_check_result(row, CHECK_NAME, referential_reasons(row, ctx))
    return flagged


def apply_spark(df, table_name: str, ctx: SilverContext | None = None, spark=None):
    from pyspark.sql.functions import array, col, lit, size, when

    if table_name != "orders":
        return (
            df.withColumn("_referential_integrity_reasons", array())
            .withColumn("referential_integrity_flag", lit(NOT_APPLICABLE))
        )

    if spark is None:
        spark = df.sparkSession

    customer_keys = (
        spark.table("bronze.customers")
        .select(col("customer_id").alias("_valid_customer_id"))
        .where(col("_valid_customer_id").isNotNull())
        .distinct()
    )
    product_keys = (
        spark.table("bronze.products")
        .select(col("product_id").alias("_valid_product_id"))
        .where(col("_valid_product_id").isNotNull())
        .distinct()
    )
    joined = (
        df.join(customer_keys, df["customer_id"] == col("_valid_customer_id"), "left")
        .join(product_keys, df["product_id"] == col("_valid_product_id"), "left")
    )
    orphan_customer = col("customer_id").isNotNull() & col("_valid_customer_id").isNull()
    orphan_product = col("product_id").isNotNull() & col("_valid_product_id").isNull()
    reasons = expr_reasons(orphan_customer, orphan_product)
    return (
        joined.withColumn("_referential_integrity_reasons", reasons)
        .withColumn(
            "referential_integrity_flag",
            when(size(col("_referential_integrity_reasons")) == 0, lit(PASS)).otherwise(
                lit(FAIL)
            ),
        )
        .drop("_valid_customer_id", "_valid_product_id")
    )


def expr_reasons(orphan_customer, orphan_product):
    from pyspark.sql.functions import array, filter as spark_filter, lit, when

    return spark_filter(
        array(
            when(orphan_customer, lit("ORPHAN_CUSTOMER_ID")),
            when(orphan_product, lit("ORPHAN_PRODUCT_ID")),
        ),
        lambda x: x.isNotNull(),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Silver referential integrity check on Bronze tables"
    )
    parser.add_argument("--table", choices=["customers", "products", "orders"], default=None)
    return parser.parse_known_args()[0]


def main() -> None:
    from pyspark.sql.functions import col

    args = parse_args()
    spark = get_spark()
    tables = [args.table] if args.table else ["customers", "products", "orders"]
    for table_name in tables:
        df = apply_spark(spark.table(f"bronze.{table_name}"), table_name, spark=spark)
        failed = df.filter(col("referential_integrity_flag") == FAIL).count()
        print(f"{table_name}: referential_integrity FAIL={failed} / {df.count()}")


if __name__ == "__main__":
    main()
