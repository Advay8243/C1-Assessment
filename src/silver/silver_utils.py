"""
Shared Silver helpers.

Silver copies Bronze business rows and adds quality flags. It does not delete
or repair rows. Gold is expected to read quality_check_result = 'PASS'.
"""

from __future__ import annotations

import csv
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

SILVER_SCHEMA = "silver"
BRONZE_SCHEMA = "bronze"
QUALITY_METRICS_TABLE = f"{SILVER_SCHEMA}.quality_metrics"

PASS = "PASS"
FAIL = "FAIL"
NOT_APPLICABLE = "NOT_APPLICABLE"

AS_OF_DATE = date(2026, 8, 14)
MONEY = Decimal("0.01")
AMOUNT_TOLERANCE = Decimal("0.01")

ALLOWED_SEGMENTS = frozenset({"Premium", "Standard", "Basic"})
ALLOWED_STATUSES = frozenset({"Pending", "Completed", "Cancelled"})
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

CHECK_NAMES = (
    "completeness",
    "uniqueness",
    "type_validation",
    "referential_integrity",
    "business_logic",
)

FLAG_COLUMNS = {
    "completeness": "completeness_flag",
    "uniqueness": "uniqueness_flag",
    "type_validation": "type_validation_flag",
    "referential_integrity": "referential_integrity_flag",
    "business_logic": "business_logic_flag",
}

REASON_COLUMNS = {
    "completeness": "_completeness_reasons",
    "uniqueness": "_uniqueness_reasons",
    "type_validation": "_type_validation_reasons",
    "referential_integrity": "_referential_integrity_reasons",
    "business_logic": "_business_logic_reasons",
}

THRESHOLDS = {
    "completeness": Decimal("99.0"),
    "uniqueness": Decimal("100.0"),
    "type_validation": Decimal("99.0"),
    "referential_integrity": Decimal("99.9"),
    "business_logic": Decimal("99.0"),
}

EXPECTED_ROW_COUNTS = {
    "customers": 10_010,
    "products": 505,
    "orders": 100_020,
}

INT_FIELDS = {
    "customers": ("customer_id",),
    "products": ("product_id", "stock_quantity", "reorder_level"),
    "orders": ("order_id", "customer_id", "product_id", "quantity"),
}
DATE_FIELDS = {
    "customers": ("signup_date",),
    "products": (),
    "orders": ("order_date", "payment_date"),
}
DECIMAL_FIELDS = {
    "customers": ("lifetime_value",),
    "products": ("price", "cost"),
    "orders": ("unit_price", "total_amount"),
}


@dataclass
class SilverContext:
    customer_ids: set[int]
    product_ids: set[int]
    customer_signup: dict[int, date]
    batch_id: str
    processed_at: datetime
    extra: dict[str, Any] = field(default_factory=dict)


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


def silver_dir() -> Path:
    runtime_paths, file_value = _runtime()
    return runtime_paths.layer_dir(file_value, "silver")


def load_check_module(filename: str):
    from runtime_paths import load_workspace_module

    path = silver_dir() / filename
    return load_workspace_module(path.stem, path)


def _blank_to_none(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def parse_int(value: Any) -> int | None:
    value = _blank_to_none(value)
    if value is None:
        return None
    return int(value)


def parse_date(value: Any) -> date | None:
    value = _blank_to_none(value)
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def parse_decimal(value: Any) -> Decimal | None:
    value = _blank_to_none(value)
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def parse_record(row: dict[str, Any], table_name: str) -> dict[str, Any]:
    parsed = dict(row)
    for column in INT_FIELDS[table_name]:
        parsed[column] = parse_int(row.get(column))
    for column in DATE_FIELDS[table_name]:
        parsed[column] = parse_date(row.get(column))
    for column in DECIMAL_FIELDS[table_name]:
        parsed[column] = parse_decimal(row.get(column))
    for key, value in list(parsed.items()):
        if isinstance(value, str):
            parsed[key] = _blank_to_none(value)
    return parsed


def load_csv_records(path: Path, table_name: str) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [parse_record(row, table_name) for row in csv.DictReader(handle)]


def load_landing_records(data_dir: Path | None = None) -> dict[str, list[dict[str, Any]]]:
    data_dir = data_dir or (repo_root() / "data")
    return {
        "customers": load_csv_records(data_dir / "customers.csv", "customers"),
        "products": load_csv_records(data_dir / "products.csv", "products"),
        "orders": load_csv_records(data_dir / "orders.csv", "orders"),
    }


def build_context(
    customers: Iterable[dict[str, Any]],
    products: Iterable[dict[str, Any]],
    batch_id: str | None = None,
    processed_at: datetime | None = None,
) -> SilverContext:
    customer_ids = {
        row["customer_id"] for row in customers if row.get("customer_id") is not None
    }
    product_ids = {
        row["product_id"] for row in products if row.get("product_id") is not None
    }
    signup: dict[int, date] = {}
    for row in customers:
        customer_id = row.get("customer_id")
        signup_date = row.get("signup_date")
        if customer_id is None or signup_date is None or customer_id in signup:
            continue
        signup[customer_id] = signup_date
    processed_at = processed_at or datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)
    batch_id = batch_id or processed_at.strftime("%Y%m%dT%H%M%SZ")
    return SilverContext(
        customer_ids=customer_ids,
        product_ids=product_ids,
        customer_signup=signup,
        batch_id=batch_id,
        processed_at=processed_at,
    )


def copy_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def set_check_result(row: dict[str, Any], check_name: str, reasons: list[str], na: bool = False) -> None:
    flag_col = FLAG_COLUMNS[check_name]
    reason_col = REASON_COLUMNS[check_name]
    row[reason_col] = reasons
    if na:
        row[flag_col] = NOT_APPLICABLE
    else:
        row[flag_col] = FAIL if reasons else PASS


def finalize_row(row: dict[str, Any], ctx: SilverContext) -> dict[str, Any]:
    reasons: list[str] = []
    failed = False
    for check_name in CHECK_NAMES:
        flag = row.get(FLAG_COLUMNS[check_name], PASS)
        if flag == FAIL:
            failed = True
        reasons.extend(row.get(REASON_COLUMNS[check_name]) or [])
    row["failure_reasons"] = "; ".join(reasons)
    row["quality_check_result"] = FAIL if failed else PASS
    row["_silver_processed_at"] = ctx.processed_at
    row["_silver_batch_id"] = ctx.batch_id
    for reason_col in REASON_COLUMNS.values():
        row.pop(reason_col, None)
    return row


def apply_all_python(
    customers: list[dict[str, Any]],
    products: list[dict[str, Any]],
    orders: list[dict[str, Any]],
    ctx: SilverContext | None = None,
) -> dict[str, list[dict[str, Any]]]:
    customers = copy_rows(customers)
    products = copy_rows(products)
    orders = copy_rows(orders)
    ctx = ctx or build_context(customers, products)

    completeness = load_check_module("01_quality_completeness.py")
    uniqueness = load_check_module("02_quality_uniqueness.py")
    type_validation = load_check_module("03_quality_type_validation.py")
    referential = load_check_module("04_quality_referential_integrity.py")
    business = load_check_module("05_quality_business_logic.py")

    customers = completeness.flag_python(customers, "customers", ctx)
    products = completeness.flag_python(products, "products", ctx)
    orders = completeness.flag_python(orders, "orders", ctx)

    customers = uniqueness.flag_python(customers, "customers", ctx)
    products = uniqueness.flag_python(products, "products", ctx)
    orders = uniqueness.flag_python(orders, "orders", ctx)

    customers = type_validation.flag_python(customers, "customers", ctx)
    products = type_validation.flag_python(products, "products", ctx)
    orders = type_validation.flag_python(orders, "orders", ctx)

    customers = referential.flag_python(customers, "customers", ctx)
    products = referential.flag_python(products, "products", ctx)
    orders = referential.flag_python(orders, "orders", ctx)

    customers = business.flag_python(customers, "customers", ctx)
    products = business.flag_python(products, "products", ctx)
    orders = business.flag_python(orders, "orders", ctx)

    return {
        "customers": [finalize_row(row, ctx) for row in customers],
        "products": [finalize_row(row, ctx) for row in products],
        "orders": [finalize_row(row, ctx) for row in orders],
    }


def metric_from_flags(
    rows: list[dict[str, Any]],
    table_name: str,
    check_name: str,
    ctx: SilverContext,
) -> dict[str, Any] | None:
    flag_col = FLAG_COLUMNS[check_name]
    evaluated_rows = [row for row in rows if row.get(flag_col) != NOT_APPLICABLE]
    if not evaluated_rows:
        return None
    failed = sum(1 for row in evaluated_rows if row.get(flag_col) == FAIL)
    passed = len(evaluated_rows) - failed
    pass_pct = (Decimal(passed) / Decimal(len(evaluated_rows)) * Decimal("100")).quantize(
        Decimal("0.0001")
    )
    threshold = THRESHOLDS[check_name]
    return {
        "table_name": table_name,
        "check_name": check_name,
        "rows_evaluated": len(evaluated_rows),
        "rows_passed": passed,
        "rows_failed": failed,
        "pass_percentage": pass_pct,
        "threshold": threshold,
        "threshold_met": pass_pct >= threshold,
        "batch_id": ctx.batch_id,
        "processed_at": ctx.processed_at,
    }


def build_metrics(
    tables: dict[str, list[dict[str, Any]]],
    ctx: SilverContext,
) -> list[dict[str, Any]]:
    metrics = []
    for table_name, rows in tables.items():
        for check_name in CHECK_NAMES:
            metric = metric_from_flags(rows, table_name, check_name, ctx)
            if metric is not None:
                metrics.append(metric)
    return metrics


def _ensure_bronze_on_path() -> None:
    runtime_paths, file_value = _runtime()
    runtime_paths.add_layer_to_path(file_value, "bronze")


def get_spark():
    _ensure_bronze_on_path()
    import ingest_utils as bronze_ingest

    return bronze_ingest.get_spark()


def write_format() -> str:
    _ensure_bronze_on_path()
    import ingest_utils as bronze_ingest

    return bronze_ingest.write_format()


def ensure_silver_schema(spark) -> None:
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {SILVER_SCHEMA}")


def write_silver_table(df, table_name: str) -> None:
    (
        df.write.format(write_format())
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(f"{SILVER_SCHEMA}.{table_name}")
    )
