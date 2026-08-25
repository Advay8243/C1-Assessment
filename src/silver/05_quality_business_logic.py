"""
Silver business-logic check.

Cross-field rules that types alone cannot catch: amount = qty * price,
payment_date vs status, signup in the future, cost vs price, order vs signup.
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
    AMOUNT_TOLERANCE,
    AS_OF_DATE,
    FAIL,
    MONEY,
    PASS,
    SilverContext,
    copy_rows,
    get_spark,
    set_check_result,
)

CHECK_NAME = "business_logic"


def business_reasons(row: dict[str, Any], table_name: str, ctx: SilverContext) -> list[str]:
    reasons: list[str] = []
    if table_name == "customers":
        signup = row.get("signup_date")
        if signup is not None and signup > AS_OF_DATE:
            reasons.append("FUTURE_SIGNUP_DATE")
    elif table_name == "products":
        price = row.get("price")
        cost = row.get("cost")
        if price is not None and cost is not None and cost > price:
            reasons.append("COST_GT_PRICE")
    elif table_name == "orders":
        quantity = row.get("quantity")
        unit_price = row.get("unit_price")
        total_amount = row.get("total_amount")
        if quantity is not None and unit_price is not None and total_amount is not None:
            expected = (unit_price * quantity).quantize(MONEY)
            if abs(total_amount - expected) > AMOUNT_TOLERANCE:
                reasons.append("TOTAL_AMOUNT_MISMATCH")
        status = row.get("order_status")
        payment_date = row.get("payment_date")
        order_date = row.get("order_date")
        if status == "Completed" and payment_date is None:
            reasons.append("COMPLETED_WITHOUT_PAYMENT")
        if status in {"Pending", "Cancelled"} and payment_date is not None:
            reasons.append("PAYMENT_ON_OPEN_ORDER")
        if payment_date is not None and order_date is not None and payment_date < order_date:
            reasons.append("PAYMENT_BEFORE_ORDER")
        customer_id = row.get("customer_id")
        signup = ctx.customer_signup.get(customer_id) if customer_id is not None else None
        if order_date is not None and signup is not None and order_date < signup:
            reasons.append("ORDER_BEFORE_SIGNUP")
    return reasons


def flag_python(
    rows: list[dict[str, Any]],
    table_name: str,
    ctx: SilverContext,
) -> list[dict[str, Any]]:
    flagged = copy_rows(rows)
    for row in flagged:
        set_check_result(row, CHECK_NAME, business_reasons(row, table_name, ctx))
    return flagged


def apply_spark(df, table_name: str, ctx: SilverContext | None = None, spark=None):
    from pyspark.sql.functions import abs as spark_abs
    from pyspark.sql.functions import array, col, lit, size, when
    from pyspark.sql.functions import filter as spark_filter

    extra_drop: list[str] = []
    if table_name == "customers":
        as_of = AS_OF_DATE.isoformat()
        reasons = spark_filter(
            array(
                when(col("signup_date") > lit(as_of), lit("FUTURE_SIGNUP_DATE")),
            ),
            lambda x: x.isNotNull(),
        )
    elif table_name == "products":
        reasons = spark_filter(
            array(
                when(
                    col("price").isNotNull()
                    & col("cost").isNotNull()
                    & (col("cost") > col("price")),
                    lit("COST_GT_PRICE"),
                ),
            ),
            lambda x: x.isNotNull(),
        )
    else:
        if spark is None:
            spark = df.sparkSession
        signup = (
            spark.table("bronze.customers")
            .select(
                col("customer_id").alias("_signup_customer_id"),
                col("signup_date").alias("_customer_signup_date"),
            )
            .where(col("_signup_customer_id").isNotNull())
            .dropDuplicates(["_signup_customer_id"])
        )
        df = df.join(
            signup, df["customer_id"] == signup["_signup_customer_id"], "left"
        )
        signup_date = df["_customer_signup_date"]
        mismatch = (
            col("quantity").isNotNull()
            & col("unit_price").isNotNull()
            & col("total_amount").isNotNull()
            & (
                spark_abs(col("total_amount") - (col("unit_price") * col("quantity")))
                > lit(0.01)
            )
        )
        reasons = spark_filter(
            array(
                when(mismatch, lit("TOTAL_AMOUNT_MISMATCH")),
                when(
                    (col("order_status") == lit("Completed")) & col("payment_date").isNull(),
                    lit("COMPLETED_WITHOUT_PAYMENT"),
                ),
                when(
                    col("order_status").isin("Pending", "Cancelled")
                    & col("payment_date").isNotNull(),
                    lit("PAYMENT_ON_OPEN_ORDER"),
                ),
                when(
                    col("payment_date").isNotNull()
                    & col("order_date").isNotNull()
                    & (col("payment_date") < col("order_date")),
                    lit("PAYMENT_BEFORE_ORDER"),
                ),
                when(
                    col("order_date").isNotNull()
                    & signup_date.isNotNull()
                    & (col("order_date") < signup_date),
                    lit("ORDER_BEFORE_SIGNUP"),
                ),
            ),
            lambda x: x.isNotNull(),
        )
        extra_drop = ["_signup_customer_id", "_customer_signup_date"]

    flagged = (
        df.withColumn("_business_logic_reasons", reasons)
        .withColumn(
            "business_logic_flag",
            when(size(col("_business_logic_reasons")) == 0, lit(PASS)).otherwise(lit(FAIL)),
        )
    )
    if extra_drop:
        flagged = flagged.drop(*extra_drop)
    return flagged


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Silver business-logic check on Bronze tables")
    parser.add_argument("--table", choices=["customers", "products", "orders"], default=None)
    return parser.parse_known_args()[0]


def main() -> None:
    from pyspark.sql.functions import col

    args = parse_args()
    spark = get_spark()
    tables = [args.table] if args.table else ["customers", "products", "orders"]
    for table_name in tables:
        df = apply_spark(spark.table(f"bronze.{table_name}"), table_name, spark=spark)
        failed = df.filter(col("business_logic_flag") == FAIL).count()
        print(f"{table_name}: business_logic FAIL={failed} / {df.count()}")


if __name__ == "__main__":
    main()
