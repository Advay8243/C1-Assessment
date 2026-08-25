"""
Build Silver tables from Bronze: run all five quality checks, flag rows,
write silver.customers / products / orders plus silver.quality_metrics.

Rows are never deleted. Gold should filter quality_check_result = 'PASS'.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
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

from runtime_paths import add_layer_to_path  # noqa: E402

_SILVER_DIR = add_layer_to_path(_FILE, "silver")

from silver_utils import (  # noqa: E402
    CHECK_NAMES,
    EXPECTED_ROW_COUNTS,
    FAIL,
    FLAG_COLUMNS,
    NOT_APPLICABLE,
    PASS,
    QUALITY_METRICS_TABLE,
    THRESHOLDS,
    SilverContext,
    apply_all_python,
    build_context,
    build_metrics,
    ensure_silver_schema,
    get_spark,
    load_check_module,
    load_landing_records,
    write_format,
    write_silver_table,
)


def new_silver_batch() -> tuple[str, datetime]:
    processed_at = datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)
    batch_id = processed_at.strftime("%Y%m%dT%H%M%SZ")
    return batch_id, processed_at


def finalize_spark(df, ctx: SilverContext):
    from pyspark.sql.functions import col, concat, concat_ws, lit, when

    df = df.withColumn(
        "_all_reasons",
        concat(
            col("_completeness_reasons"),
            col("_uniqueness_reasons"),
            col("_type_validation_reasons"),
            col("_referential_integrity_reasons"),
            col("_business_logic_reasons"),
        ),
    )
    failed = (
        (col("completeness_flag") == FAIL)
        | (col("uniqueness_flag") == FAIL)
        | (col("type_validation_flag") == FAIL)
        | (col("referential_integrity_flag") == FAIL)
        | (col("business_logic_flag") == FAIL)
    )
    return (
        df.withColumn("failure_reasons", concat_ws("; ", col("_all_reasons")))
        .withColumn("quality_check_result", when(failed, lit(FAIL)).otherwise(lit(PASS)))
        .withColumn(
            "_silver_processed_at",
            lit(ctx.processed_at.isoformat()).cast("timestamp"),
        )
        .withColumn("_silver_batch_id", lit(ctx.batch_id))
        .drop(
            "_completeness_reasons",
            "_uniqueness_reasons",
            "_type_validation_reasons",
            "_referential_integrity_reasons",
            "_business_logic_reasons",
            "_all_reasons",
        )
    )


def apply_all_spark(spark, ctx: SilverContext) -> dict:
    completeness = load_check_module("01_quality_completeness.py")
    uniqueness = load_check_module("02_quality_uniqueness.py")
    type_validation = load_check_module("03_quality_type_validation.py")
    referential = load_check_module("04_quality_referential_integrity.py")
    business = load_check_module("05_quality_business_logic.py")

    frames = {}
    for table_name in ("products", "customers", "orders"):
        df = spark.table(f"bronze.{table_name}")
        df = completeness.apply_spark(df, table_name, ctx)
        df = uniqueness.apply_spark(df, table_name, ctx)
        df = type_validation.apply_spark(df, table_name, ctx)
        df = referential.apply_spark(df, table_name, ctx, spark=spark)
        df = business.apply_spark(df, table_name, ctx, spark=spark)
        frames[table_name] = finalize_spark(df, ctx)
    return frames


def spark_metrics(spark, frames: dict, ctx: SilverContext) -> list[dict]:
    from pyspark.sql.functions import col
    from pyspark.sql.types import (
        BooleanType,
        DecimalType,
        IntegerType,
        StringType,
        StructField,
        StructType,
        TimestampType,
    )

    metrics = []
    for table_name, df in frames.items():
        total = df.count()
        for check_name in CHECK_NAMES:
            flag_col = FLAG_COLUMNS[check_name]
            evaluated = df.filter(col(flag_col) != NOT_APPLICABLE)
            evaluated_count = evaluated.count()
            if evaluated_count == 0:
                continue
            failed = evaluated.filter(col(flag_col) == FAIL).count()
            passed = evaluated_count - failed
            pass_pct = (Decimal(passed) / Decimal(evaluated_count) * Decimal("100")).quantize(
                Decimal("0.0001")
            )
            threshold = THRESHOLDS[check_name]
            metrics.append(
                {
                    "table_name": table_name,
                    "check_name": check_name,
                    "rows_evaluated": evaluated_count,
                    "rows_passed": passed,
                    "rows_failed": failed,
                    "pass_percentage": pass_pct,
                    "threshold": threshold,
                    "threshold_met": pass_pct >= threshold,
                    "batch_id": ctx.batch_id,
                    "processed_at": ctx.processed_at,
                }
            )
        if total != EXPECTED_ROW_COUNTS[table_name]:
            print(
                f"  note: silver.{table_name} has {total} rows "
                f"(seed reference {EXPECTED_ROW_COUNTS[table_name]})"
            )

    schema = StructType(
        [
            StructField("table_name", StringType(), False),
            StructField("check_name", StringType(), False),
            StructField("rows_evaluated", IntegerType(), False),
            StructField("rows_passed", IntegerType(), False),
            StructField("rows_failed", IntegerType(), False),
            StructField("pass_percentage", DecimalType(8, 4), False),
            StructField("threshold", DecimalType(5, 1), False),
            StructField("threshold_met", BooleanType(), False),
            StructField("batch_id", StringType(), False),
            StructField("processed_at", TimestampType(), False),
        ]
    )
    log_df = spark.createDataFrame(
        [
            (
                row["table_name"],
                row["check_name"],
                row["rows_evaluated"],
                row["rows_passed"],
                row["rows_failed"],
                row["pass_percentage"],
                row["threshold"],
                row["threshold_met"],
                row["batch_id"],
                row["processed_at"],
            )
            for row in metrics
        ],
        schema=schema,
    )
    (
        log_df.write.format(write_format())
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(QUALITY_METRICS_TABLE)
    )
    return metrics


def print_quality_report(metrics: list[dict]) -> None:
    print("Silver quality report (% passed by check)")
    print(
        f"{'table':<12} {'check':<24} {'failed':>8} {'evaluated':>10} "
        f"{'% pass':>10} {'threshold':>10} {'met':>6}"
    )
    for row in metrics:
        print(
            f"{row['table_name']:<12} {row['check_name']:<24} "
            f"{row['rows_failed']:>8} {row['rows_evaluated']:>10} "
            f"{row['pass_percentage']:>10} {row['threshold']:>10} "
            f"{str(row['threshold_met']):>6}"
        )


def run_silver(spark=None) -> dict:
    spark = spark or get_spark()
    ensure_silver_schema(spark)
    batch_id, processed_at = new_silver_batch()
    ctx = SilverContext(
        customer_ids=set(),
        product_ids=set(),
        customer_signup={},
        batch_id=batch_id,
        processed_at=processed_at,
    )
    print(f"Silver batch_id={batch_id}")
    frames = apply_all_spark(spark, ctx)
    results = []
    for table_name, df in frames.items():
        write_silver_table(df, table_name)
        row_count = spark.table(f"silver.{table_name}").count()
        print(f"  silver.{table_name}: {row_count} rows (flags only, no deletes)")
        results.append({"table_name": table_name, "row_count": row_count})
    metrics = spark_metrics(spark, frames, ctx)
    print_quality_report(metrics)
    return {"tables": results, "metrics": metrics, "batch_id": batch_id}


def run_silver_from_landing() -> dict:
    """Python path used by tests when Spark / Bronze tables are not available."""
    records = load_landing_records()
    ctx = build_context(records["customers"], records["products"])
    tables = apply_all_python(records["customers"], records["products"], records["orders"], ctx)
    metrics = build_metrics(tables, ctx)
    print_quality_report(metrics)
    return {"tables": tables, "metrics": metrics, "context": ctx}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create Silver tables from Bronze")
    parser.add_argument(
        "--from-landing",
        action="store_true",
        help="Run the Python engine on data/*.csv and print the quality report (no Spark write)",
    )
    return parser.parse_known_args()[0]


def main() -> None:
    args = parse_args()
    if args.from_landing:
        result = run_silver_from_landing()
        summary = [
            {"table_name": name, "row_count": len(rows), "fail_count": sum(
                1 for row in rows if row["quality_check_result"] == FAIL
            )}
            for name, rows in result["tables"].items()
        ]
        print(json.dumps(summary, indent=2))
        return
    result = run_silver()
    serializable = {
        "batch_id": result["batch_id"],
        "tables": result["tables"],
        "metrics": [
            {k: (str(v) if isinstance(v, Decimal) else v) for k, v in row.items() if k != "processed_at"}
            for row in result["metrics"]
        ],
    }
    print(json.dumps(serializable, indent=2, default=str))


if __name__ == "__main__":
    main()
