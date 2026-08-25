"""
Silver type / domain validation.

Catch values that are the wrong domain even when the column is populated:
invalid segment/status, malformed email, negative amounts/stock, non-positive
quantity. NULL critical fields are left to completeness.
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
    ALLOWED_SEGMENTS,
    ALLOWED_STATUSES,
    EMAIL_RE,
    FAIL,
    PASS,
    SilverContext,
    copy_rows,
    get_spark,
    set_check_result,
)

CHECK_NAME = "type_validation"


def _negative_number(value: Any) -> bool:
    return value is not None and value < 0


def type_reasons(row: dict[str, Any], table_name: str) -> list[str]:
    reasons: list[str] = []
    if table_name == "customers":
        if _negative_number(row.get("customer_id")):
            reasons.append("NEGATIVE_CUSTOMER_ID")
        segment = row.get("customer_segment")
        if segment is not None and segment not in ALLOWED_SEGMENTS:
            reasons.append("INVALID_CUSTOMER_SEGMENT")
        email = row.get("email")
        if email is not None and EMAIL_RE.match(str(email)) is None:
            reasons.append("MALFORMED_EMAIL")
        if _negative_number(row.get("lifetime_value")):
            reasons.append("NEGATIVE_LIFETIME_VALUE")
    elif table_name == "products":
        if _negative_number(row.get("product_id")):
            reasons.append("NEGATIVE_PRODUCT_ID")
        if _negative_number(row.get("price")):
            reasons.append("NEGATIVE_PRICE")
        if _negative_number(row.get("cost")):
            reasons.append("NEGATIVE_COST")
        stock = row.get("stock_quantity")
        if stock is not None and stock < 0:
            reasons.append("NEGATIVE_STOCK")
        if _negative_number(row.get("reorder_level")):
            reasons.append("NEGATIVE_REORDER_LEVEL")
    elif table_name == "orders":
        if _negative_number(row.get("order_id")):
            reasons.append("NEGATIVE_ORDER_ID")
        if _negative_number(row.get("customer_id")):
            reasons.append("NEGATIVE_CUSTOMER_ID")
        if _negative_number(row.get("product_id")):
            reasons.append("NEGATIVE_PRODUCT_ID")
        quantity = row.get("quantity")
        if quantity is None or quantity <= 0:
            reasons.append("QUANTITY_NOT_POSITIVE")
        if _negative_number(row.get("unit_price")):
            reasons.append("NEGATIVE_UNIT_PRICE")
        if _negative_number(row.get("total_amount")):
            reasons.append("NEGATIVE_TOTAL_AMOUNT")
        status = row.get("order_status")
        if status is not None and status not in ALLOWED_STATUSES:
            reasons.append("INVALID_ORDER_STATUS")
    return reasons


def flag_python(
    rows: list[dict[str, Any]],
    table_name: str,
    ctx: SilverContext | None = None,
) -> list[dict[str, Any]]:
    flagged = copy_rows(rows)
    for row in flagged:
        set_check_result(row, CHECK_NAME, type_reasons(row, table_name))
    return flagged


def apply_spark(df, table_name: str, ctx: SilverContext | None = None):
    from pyspark.sql.functions import array, col, lit, size, when
    from pyspark.sql.functions import filter as spark_filter

    email_pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    if table_name == "customers":
        items = [
            when(col("customer_id") < 0, lit("NEGATIVE_CUSTOMER_ID")),
            when(
                col("customer_segment").isNotNull()
                & ~col("customer_segment").isin("Premium", "Standard", "Basic"),
                lit("INVALID_CUSTOMER_SEGMENT"),
            ),
            when(
                col("email").isNotNull() & ~col("email").rlike(email_pattern),
                lit("MALFORMED_EMAIL"),
            ),
            when(col("lifetime_value") < 0, lit("NEGATIVE_LIFETIME_VALUE")),
        ]
    elif table_name == "products":
        items = [
            when(col("product_id") < 0, lit("NEGATIVE_PRODUCT_ID")),
            when(col("price") < 0, lit("NEGATIVE_PRICE")),
            when(col("cost") < 0, lit("NEGATIVE_COST")),
            when(col("stock_quantity") < 0, lit("NEGATIVE_STOCK")),
            when(col("reorder_level") < 0, lit("NEGATIVE_REORDER_LEVEL")),
        ]
    else:
        items = [
            when(col("order_id") < 0, lit("NEGATIVE_ORDER_ID")),
            when(col("customer_id") < 0, lit("NEGATIVE_CUSTOMER_ID")),
            when(col("product_id") < 0, lit("NEGATIVE_PRODUCT_ID")),
            when(col("quantity").isNull() | (col("quantity") <= 0), lit("QUANTITY_NOT_POSITIVE")),
            when(col("unit_price") < 0, lit("NEGATIVE_UNIT_PRICE")),
            when(col("total_amount") < 0, lit("NEGATIVE_TOTAL_AMOUNT")),
            when(
                col("order_status").isNotNull()
                & ~col("order_status").isin("Pending", "Completed", "Cancelled"),
                lit("INVALID_ORDER_STATUS"),
            ),
        ]
    reasons = spark_filter(array(*items), lambda x: x.isNotNull())
    return df.withColumn("_type_validation_reasons", reasons).withColumn(
        "type_validation_flag",
        when(size(col("_type_validation_reasons")) == 0, lit(PASS)).otherwise(lit(FAIL)),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Silver type validation on Bronze tables")
    parser.add_argument("--table", choices=["customers", "products", "orders"], default=None)
    return parser.parse_known_args()[0]


def main() -> None:
    from pyspark.sql.functions import col

    args = parse_args()
    spark = get_spark()
    tables = [args.table] if args.table else ["customers", "products", "orders"]
    for table_name in tables:
        df = apply_spark(spark.table(f"bronze.{table_name}"), table_name)
        failed = df.filter(col("type_validation_flag") == FAIL).count()
        print(f"{table_name}: type_validation FAIL={failed} / {df.count()}")


if __name__ == "__main__":
    main()
