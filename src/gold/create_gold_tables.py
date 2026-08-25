"""
Create Gold tables from Silver.

Build order matches the brief plus the required repo SQL files:
  01 sales_by_product
  02 revenue_by_customer
  03 daily_weekly_trends
  04 customer_segmentation (reads gold.revenue_by_customer)

Each table is quality-checked after it is written. Segmentation is not rebuilt
from Silver, so revenue cannot drift from revenue_by_customer.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

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

from runtime_paths import add_layer_to_path, load_workspace_module  # noqa: E402

_GOLD_DIR = add_layer_to_path(_FILE, "gold")

from customer_segmentation import build_customer_segmentation  # noqa: E402
from daily_weekly_trends import build_daily_weekly_trends  # noqa: E402
from gold_utils import (  # noqa: E402
    CUSTOMER_SEGMENTATION_TABLE,
    DAILY_WEEKLY_TRENDS_TABLE,
    QUALITY_METRICS_TABLE,
    REVENUE_BY_CUSTOMER_TABLE,
    SALES_BY_PRODUCT_TABLE,
    ensure_gold_schema,
    ensure_src_on_path,
    get_spark,
    new_gold_batch,
    read_sql,
    write_format,
    write_gold_table,
)
from revenue_by_customer import build_revenue_by_customer  # noqa: E402
from sales_by_product import build_sales_by_product  # noqa: E402


def _validate_gold():
    return load_workspace_module("validate_gold", _GOLD_DIR / "validate_gold.py")

ensure_src_on_path()

SPARK_BUILDS = (
    ("sales_by_product", "01_sales_by_product.sql", SALES_BY_PRODUCT_TABLE),
    ("revenue_by_customer", "02_revenue_by_customer.sql", REVENUE_BY_CUSTOMER_TABLE),
    ("daily_weekly_trends", "03_daily_weekly_trends.sql", DAILY_WEEKLY_TRENDS_TABLE),
    ("customer_segmentation", "04_customer_segmentation.sql", CUSTOMER_SEGMENTATION_TABLE),
)


def add_gold_metadata(df, batch_id: str, processed_at):
    from pyspark.sql.functions import lit

    return (
        df.withColumn(
            "_gold_processed_at",
            lit(processed_at.isoformat()).cast("timestamp"),
        ).withColumn("_gold_batch_id", lit(batch_id))
    )


def write_quality_metrics(spark, checks: list[dict], batch_id: str, processed_at) -> None:
    from pyspark.sql.types import (
        IntegerType,
        StringType,
        StructField,
        StructType,
        TimestampType,
    )

    schema = StructType(
        [
            StructField("table_name", StringType(), False),
            StructField("check_name", StringType(), False),
            StructField("status", StringType(), False),
            StructField("rows_evaluated", IntegerType(), False),
            StructField("rows_failed", IntegerType(), False),
            StructField("detail", StringType(), False),
            StructField("batch_id", StringType(), False),
            StructField("processed_at", TimestampType(), False),
        ]
    )
    rows = [
        (
            row["table_name"],
            row["check_name"],
            row["status"],
            row["rows_evaluated"],
            row["rows_failed"],
            row["detail"],
            batch_id,
            processed_at,
        )
        for row in checks
    ]
    log_df = spark.createDataFrame(rows, schema=schema)
    (
        log_df.write.format(write_format())
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(QUALITY_METRICS_TABLE)
    )


def _collect_table(spark, full_name: str) -> list[dict]:
    return [row.asDict(recursive=True) for row in spark.table(full_name).collect()]


def _raise_if_failed(checks: list[dict]) -> None:
    vg = _validate_gold()
    if not vg.all_checks_passed(checks):
        failed = [
            f"{row['table_name']}.{row['check_name']}"
            for row in checks
            if row["status"] != "PASS"
        ]
        raise RuntimeError(f"Gold quality checks failed: {failed}")


def run_gold(spark=None) -> dict:
    spark = spark or get_spark()
    ensure_gold_schema(spark)
    batch_id, processed_at = new_gold_batch()
    print(f"Gold batch_id={batch_id}")

    table_counts = []
    for table_name, sql_file, full_name in SPARK_BUILDS:
        gold_df = add_gold_metadata(spark.sql(read_sql(sql_file)), batch_id, processed_at)
        write_gold_table(gold_df, table_name)
        row_count = spark.table(full_name).count()
        print(f"  {full_name}: {row_count} rows")
        table_counts.append({"table_name": table_name, "row_count": row_count})

    silver_tables = {
        "customers": _collect_table(spark, "silver.customers"),
        "products": _collect_table(spark, "silver.products"),
        "orders": _collect_table(spark, "silver.orders"),
    }
    sales_rows = _collect_table(spark, SALES_BY_PRODUCT_TABLE)
    revenue_rows = _collect_table(spark, REVENUE_BY_CUSTOMER_TABLE)
    trend_rows = _collect_table(spark, DAILY_WEEKLY_TRENDS_TABLE)
    segment_rows = _collect_table(spark, CUSTOMER_SEGMENTATION_TABLE)

    vg = _validate_gold()
    checks = []
    checks.extend(vg.validate_sales_by_product(sales_rows, silver_tables))
    checks.extend(vg.validate_revenue_by_customer(revenue_rows, silver_tables))
    checks.extend(vg.validate_daily_weekly_trends(trend_rows, silver_tables))
    checks.extend(vg.validate_customer_segmentation(segment_rows, revenue_rows))
    write_quality_metrics(spark, checks, batch_id, processed_at)
    vg.print_gold_quality_report(checks)
    _raise_if_failed(checks)
    return {"batch_id": batch_id, "tables": table_counts, "checks": checks}


def run_gold_from_landing() -> dict:
    from silver_utils import apply_all_python, build_context, load_landing_records

    source = load_landing_records()
    ctx = build_context(source["customers"], source["products"])
    silver_tables = apply_all_python(
        source["customers"], source["products"], source["orders"], ctx
    )
    gold_tables = {
        "sales_by_product": build_sales_by_product(silver_tables),
        "revenue_by_customer": build_revenue_by_customer(silver_tables),
        "daily_weekly_trends": build_daily_weekly_trends(silver_tables),
    }
    gold_tables["customer_segmentation"] = build_customer_segmentation(
        gold_tables["revenue_by_customer"]
    )
    vg = _validate_gold()
    checks = []
    checks.extend(vg.validate_sales_by_product(gold_tables["sales_by_product"], silver_tables))
    checks.extend(vg.validate_revenue_by_customer(gold_tables["revenue_by_customer"], silver_tables))
    checks.extend(vg.validate_daily_weekly_trends(gold_tables["daily_weekly_trends"], silver_tables))
    checks.extend(
        vg.validate_customer_segmentation(
            gold_tables["customer_segmentation"],
            gold_tables["revenue_by_customer"],
        )
    )
    for name, rows in gold_tables.items():
        print(f"gold.{name}: {len(rows)} rows (from landing/Silver engine)")
    vg.print_gold_quality_report(checks)
    _raise_if_failed(checks)
    return {"tables": gold_tables, "checks": checks, "silver_tables": silver_tables}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create Gold tables from Silver")
    parser.add_argument(
        "--from-landing",
        action="store_true",
        help="Build from data/*.csv via the Silver Python engine (no Spark write)",
    )
    return parser.parse_known_args()[0]


def main() -> None:
    args = parse_args()
    if args.from_landing:
        result = run_gold_from_landing()
        print(
            json.dumps(
                {
                    "tables": {
                        name: len(rows) for name, rows in result["tables"].items()
                    },
                    "checks": result["checks"],
                },
                indent=2,
                default=str,
            )
        )
        return
    result = run_gold()
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
