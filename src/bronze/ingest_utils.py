"""
Shared Bronze ingest helpers.

Bronze lands CSV files as typed Delta tables. It does not clean data:
no dropna, no dropDuplicates, no FK repair, no status filters, no quality flags.

The only added columns are ingest metadata (_source_file, _ingest_timestamp, _batch_id).
Empty CSV fields are read as NULL. Duplicate keys are kept as extra rows.
"""

from __future__ import annotations

import csv
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BRONZE_SCHEMA = "bronze"
INGESTION_LOG_TABLE = f"{BRONZE_SCHEMA}.ingestion_log"

METADATA_COLUMNS = ("_source_file", "_ingest_timestamp", "_batch_id")

# Physical CSV row counts (header excluded). Logged as reference, never used to drop rows.
EXPECTED_ROW_COUNTS = {
    "customers": 10_010,
    "products": 505,
    "orders": 100_020,
}

# (column_name, spark_type_alias). All fields nullable — Bronze does not enforce keys.
BUSINESS_FIELDS: dict[str, list[tuple[str, str]]] = {
    "customers": [
        ("customer_id", "int"),
        ("customer_name", "string"),
        ("email", "string"),
        ("country", "string"),
        ("signup_date", "date"),
        ("customer_segment", "string"),
        ("lifetime_value", "decimal"),
    ],
    "products": [
        ("product_id", "int"),
        ("product_name", "string"),
        ("category", "string"),
        ("price", "decimal"),
        ("cost", "decimal"),
        ("stock_quantity", "int"),
        ("reorder_level", "int"),
    ],
    "orders": [
        ("order_id", "int"),
        ("customer_id", "int"),
        ("order_date", "date"),
        ("product_id", "int"),
        ("quantity", "int"),
        ("unit_price", "decimal"),
        ("total_amount", "decimal"),
        ("order_status", "string"),
        ("payment_date", "date"),
    ],
}

TABLE_FILES = {
    "customers": "customers.csv",
    "products": "products.csv",
    "orders": "orders.csv",
}

# Parents first so a later Silver run can assume Bronze parents exist. Bronze itself does not join.
DEFAULT_INGEST_ORDER = ("products", "customers", "orders")


def _runtime():
    file_value = globals().get("__file__")
    if file_value:
        src = Path(file_value).resolve().parent.parent
        if str(src) not in sys.path:
            sys.path.insert(0, str(src))
    else:
        cwd = Path.cwd().resolve()
        for root in [cwd, cwd / "src", cwd.parent, cwd.parent / "src"]:
            if (root / "runtime_paths.py").is_file():
                if str(root) not in sys.path:
                    sys.path.insert(0, str(root))
                break
    import runtime_paths

    return runtime_paths, file_value


def repo_root() -> Path:
    runtime_paths, file_value = _runtime()
    return runtime_paths.repo_root(file_value)


def is_databricks() -> bool:
    return "DATABRICKS_RUNTIME_VERSION" in os.environ


def resolve_landing_dir(explicit: str | None = None) -> str:
    """Default landing is the repo data/ folder (Workspace files on Databricks).

    Public DBFS root (/FileStore) is disabled in this workspace, so we do not
    copy CSVs to dbfs:/FileStore.
    """
    if explicit:
        cleaned = explicit.rstrip("/")
        if not _is_disabled_filestore(cleaned):
            return cleaned
    env_dir = os.environ.get("BRONZE_LANDING_DIR")
    if env_dir and not _is_disabled_filestore(env_dir):
        return env_dir.rstrip("/")
    return str(repo_root() / "data")


def _is_disabled_filestore(path: str) -> bool:
    normalized = path.replace("dbfs:", "").rstrip("/")
    return normalized.startswith("/FileStore") or normalized.startswith("FileStore")


def to_spark_path(path: str) -> str:
    """Spark Connect path for Workspace files.

    Do not use file:/...@... URIs: '@' in the user email is parsed as URI userinfo
    and Spark Connect fails with KD001.
    """
    raw = path.removeprefix("file:")
    if raw.startswith("/Users/") and not raw.startswith("/Workspace/"):
        raw = "/Workspace" + raw
    if raw.startswith("/Workspace/"):
        return raw
    return path


def _as_utc_naive(ingest_ts: datetime) -> datetime:
    """Spark timestamps are timezone-naive; store UTC without tzinfo."""
    if ingest_ts.tzinfo is not None:
        return ingest_ts.astimezone(timezone.utc).replace(tzinfo=None)
    return ingest_ts


def new_batch_context() -> tuple[str, datetime]:
    ingest_ts = _as_utc_naive(datetime.now(timezone.utc).replace(microsecond=0))
    batch_id = f"{ingest_ts.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    return batch_id, ingest_ts


def source_path(landing_dir: str, table_name: str) -> str:
    filename = TABLE_FILES[table_name]
    landing_dir = landing_dir.rstrip("/")
    return f"{landing_dir}/{filename}"


def _is_local_path(path: str) -> bool:
    return not path.startswith(("dbfs:", "s3:", "s3a:", "abfss:", "/Volumes/"))


def _local_filesystem_path(path: str) -> Path:
    return Path(path.removeprefix("file:"))


def assert_source_readable(path: str, table_name: str) -> None:
    """Input validation only: file exists and header has required columns. Not a quality check."""
    required = [name for name, _type in BUSINESS_FIELDS[table_name]]
    if not _is_local_path(path):
        return
    local_path = _local_filesystem_path(path)
    if not local_path.is_file():
        raise FileNotFoundError(
            f"Bronze source file not found: {local_path}. "
            "Generate CSVs or upload them to the landing path. "
            "See database/setup-notes.md."
        )
    with local_path.open(newline="", encoding="utf-8") as handle:
        header = next(csv.reader(handle), [])
    missing = [column for column in required if column not in header]
    if missing:
        raise ValueError(
            f"Source {local_path} is missing required columns {missing}. "
            f"Found header: {header}"
        )


def get_spark():
    try:
        from pyspark.sql import SparkSession
    except ImportError as exc:
        raise RuntimeError(
            "PySpark is required for Bronze ingest. Run this on a Databricks cluster "
            "(Spark is preinstalled) or install pyspark locally."
        ) from exc

    existing = SparkSession.getActiveSession()
    if existing is not None:
        return existing

    builder = (
        SparkSession.builder.appName("bronze-ingest")
        .master("local[*]")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.warehouse.dir", str(repo_root() / ".local_spark" / "warehouse"))
        .config("spark.driver.host", "127.0.0.1")
    )
    try:
        from delta import configure_spark_with_delta_pip

        builder = configure_spark_with_delta_pip(
            builder.config(
                "spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension"
            ).config(
                "spark.sql.catalog.spark_catalog",
                "org.apache.spark.sql.delta.catalog.DeltaCatalog",
            )
        )
    except ImportError:
        pass
    return builder.getOrCreate()


def table_schema(table_name: str):
    from pyspark.sql.types import (
        DateType,
        DecimalType,
        IntegerType,
        StringType,
        StructField,
        StructType,
    )

    type_map = {
        "int": IntegerType(),
        "string": StringType(),
        "date": DateType(),
        "decimal": DecimalType(18, 2),
    }
    return StructType(
        [
            StructField(name, type_map[type_alias], nullable=True)
            for name, type_alias in BUSINESS_FIELDS[table_name]
        ]
    )


def write_format() -> str:
    if is_databricks():
        return "delta"
    try:
        import delta  # noqa: F401

        return "delta"
    except ImportError:
        return "parquet"


def ensure_bronze_schema(spark) -> None:
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {BRONZE_SCHEMA}")


def _add_ingest_metadata(df, path: str, batch_id: str, ingest_ts: datetime):
    from pyspark.sql.functions import lit

    return (
        df.withColumn("_source_file", lit(path))
        .withColumn("_ingest_timestamp", lit(ingest_ts.isoformat()).cast("timestamp"))
        .withColumn("_batch_id", lit(batch_id))
    )


def _write_table(df, full_table_name: str) -> None:
    (
        df.write.format(write_format())
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(full_table_name)
    )


def _log_ingestion(
    spark,
    *,
    table_name: str,
    path: str,
    batch_id: str,
    ingest_ts: datetime,
    row_count: int | None,
    status: str,
    error_message: str | None = None,
) -> None:
    from pyspark.sql.types import IntegerType, StringType, StructField, StructType, TimestampType

    log_schema = StructType(
        [
            StructField("table_name", StringType(), False),
            StructField("source_path", StringType(), False),
            StructField("row_count", IntegerType(), True),
            StructField("expected_row_count", IntegerType(), True),
            StructField("ingest_timestamp", TimestampType(), False),
            StructField("batch_id", StringType(), False),
            StructField("status", StringType(), False),
            StructField("error_message", StringType(), True),
            StructField("write_format", StringType(), False),
        ]
    )
    log_row = [
        (
            table_name,
            path,
            row_count,
            EXPECTED_ROW_COUNTS[table_name],
            ingest_ts,
            batch_id,
            status,
            error_message,
            write_format(),
        )
    ]
    log_df = spark.createDataFrame(log_row, schema=log_schema)
    (
        log_df.write.format(write_format())
        .mode("append")
        .option("mergeSchema", "true")
        .saveAsTable(INGESTION_LOG_TABLE)
    )


def read_csv_raw(spark, path: str, table_name: str):
    """Read the landing CSV with types applied. Does not filter or repair values."""
    from pyspark.sql.utils import AnalysisException

    try:
        return (
            spark.read.format("csv")
            .schema(table_schema(table_name))
            .option("header", "true")
            .option("nullValue", "")
            .option("emptyValue", "")
            .option("dateFormat", "yyyy-MM-dd")
            .option("mode", "PERMISSIVE")
            .option("enforceSchema", "true")
            .load(to_spark_path(path))
        )
    except AnalysisException as exc:
        raise FileNotFoundError(
            f"Bronze source not readable: {path}. "
            "Put CSVs in the repo data/ folder (Workspace files). See database/setup-notes.md."
        ) from exc


def ingest_table(
    spark,
    table_name: str,
    landing_dir: str,
    batch_id: str,
    ingest_ts: datetime,
) -> dict[str, Any]:
    if table_name not in BUSINESS_FIELDS:
        raise KeyError(f"Unknown Bronze table '{table_name}'. Known: {list(BUSINESS_FIELDS)}")

    path = source_path(landing_dir, table_name)
    full_table_name = f"{BRONZE_SCHEMA}.{table_name}"
    row_count: int | None = None

    try:
        assert_source_readable(path, table_name)
        raw_df = read_csv_raw(spark, path, table_name)
        bronze_df = _add_ingest_metadata(raw_df, path, batch_id, ingest_ts)
        # Intentionally no .dropDuplicates(), .na.drop(), or business filters.
        _write_table(bronze_df, full_table_name)
        row_count = spark.table(full_table_name).count()
        _log_ingestion(
            spark,
            table_name=table_name,
            path=path,
            batch_id=batch_id,
            ingest_ts=ingest_ts,
            row_count=row_count,
            status="SUCCESS",
        )
    except Exception as exc:
        try:
            _log_ingestion(
                spark,
                table_name=table_name,
                path=path,
                batch_id=batch_id,
                ingest_ts=ingest_ts,
                row_count=row_count,
                status="FAILED",
                error_message=str(exc)[:2000],
            )
        except Exception:
            pass
        raise

    return {
        "table_name": table_name,
        "full_table_name": full_table_name,
        "source_path": path,
        "row_count": row_count,
        "expected_row_count": EXPECTED_ROW_COUNTS[table_name],
        "batch_id": batch_id,
        "status": "SUCCESS",
    }
