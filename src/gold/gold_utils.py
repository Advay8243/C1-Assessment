"""
Shared Gold helpers.

Gold reads Silver only. Qualifying facts are PASS rows with Completed orders,
joined to PASS customers and PASS products. Dimension lookups are de-duplicated
on the business key so a leftover Silver duplicate cannot fan out revenue.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

GOLD_SCHEMA = "gold"
SILVER_SCHEMA = "silver"
SALES_BY_PRODUCT_TABLE = f"{GOLD_SCHEMA}.sales_by_product"
REVENUE_BY_CUSTOMER_TABLE = f"{GOLD_SCHEMA}.revenue_by_customer"
DAILY_WEEKLY_TRENDS_TABLE = f"{GOLD_SCHEMA}.daily_weekly_trends"
CUSTOMER_SEGMENTATION_TABLE = f"{GOLD_SCHEMA}.customer_segmentation"
QUALITY_METRICS_TABLE = f"{GOLD_SCHEMA}.quality_metrics"

PASS = "PASS"
COMPLETED = "Completed"
MONEY = Decimal("0.01")
AOV_TOLERANCE = Decimal("0.01")

# Brief names High-Value / Repeat / One-Time / Inactive but does not define cuts.
# High-Value is evaluated before Repeat so the four types cannot overlap.
HIGH_VALUE_MIN_ORDERS = 2
HIGH_VALUE_MIN_REVENUE = Decimal("1000.00")
SEGMENT_TYPES = ("High-Value", "Repeat", "One-Time", "Inactive")

SALES_BY_PRODUCT_COLUMNS = (
    "product_id",
    "product_name",
    "category",
    "total_orders",
    "total_revenue",
    "avg_order_value",
)
REVENUE_BY_CUSTOMER_COLUMNS = (
    "customer_id",
    "customer_name",
    "customer_segment",
    "total_orders",
    "total_revenue",
    "avg_order_value",
    "lifetime_value_actual",
)
DAILY_WEEKLY_TRENDS_COLUMNS = (
    "order_date",
    "order_year",
    "order_week",
    "total_orders",
    "total_revenue",
    "avg_order_value",
    "unique_customers",
)
CUSTOMER_SEGMENTATION_COLUMNS = (
    "segment_type",
    "customer_count",
    "avg_revenue",
    "total_revenue",
)


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


def gold_dir() -> Path:
    runtime_paths, file_value = _runtime()
    return runtime_paths.layer_dir(file_value, "gold")


def repo_root() -> Path:
    runtime_paths, file_value = _runtime()
    return runtime_paths.repo_root(file_value)


def ensure_src_on_path() -> None:
    runtime_paths, file_value = _runtime()
    for layer in ("gold", "silver", "bronze"):
        runtime_paths.add_layer_to_path(file_value, layer)


def get_spark():
    ensure_src_on_path()
    from silver_utils import get_spark as _get_spark

    return _get_spark()


def write_format() -> str:
    ensure_src_on_path()
    from silver_utils import write_format as _write_format

    return _write_format()


def ensure_gold_schema(spark) -> None:
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {GOLD_SCHEMA}")


def new_gold_batch() -> tuple[str, datetime]:
    processed_at = datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)
    batch_id = processed_at.strftime("%Y%m%dT%H%M%SZ")
    return batch_id, processed_at


def money(value: Decimal | int | float) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def read_sql(filename: str) -> str:
    from runtime_paths import read_workspace_text

    return read_workspace_text(gold_dir() / filename)


def write_gold_table(df, table_name: str) -> None:
    (
        df.write.format(write_format())
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(f"{GOLD_SCHEMA}.{table_name}")
    )


def pass_product_dims(products: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """First PASS row per product_id — blocks accidental duplicate-dimension joins."""
    dims: dict[int, dict[str, Any]] = {}
    for row in products:
        if row.get("quality_check_result") != PASS:
            continue
        product_id = row.get("product_id")
        if product_id is None or product_id in dims:
            continue
        dims[product_id] = row
    return dims


def pass_customer_dims(customers: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """First PASS row per customer_id — blocks accidental duplicate-dimension joins."""
    dims: dict[int, dict[str, Any]] = {}
    for row in customers:
        if row.get("quality_check_result") != PASS:
            continue
        customer_id = row.get("customer_id")
        if customer_id is None or customer_id in dims:
            continue
        dims[customer_id] = row
    return dims


def pass_customer_ids(customers: list[dict[str, Any]]) -> set[int]:
    return set(pass_customer_dims(customers).keys())


def qualifying_orders(
    silver_tables: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    """
    Orders that are allowed into Gold sales facts.

    Dedupes on order_id so a Silver uniqueness miss cannot double-count.
    """
    products = pass_product_dims(silver_tables["products"])
    customers = pass_customer_ids(silver_tables["customers"])
    seen_order_ids: set[int] = set()
    selected: list[dict[str, Any]] = []
    for order in silver_tables["orders"]:
        if order.get("quality_check_result") != PASS:
            continue
        if order.get("order_status") != COMPLETED:
            continue
        if order.get("customer_id") not in customers:
            continue
        if order.get("product_id") not in products:
            continue
        order_id = order.get("order_id")
        if order_id is None or order_id in seen_order_ids:
            continue
        seen_order_ids.add(order_id)
        selected.append(order)
    return selected, products


def assign_segment_type(total_orders: int, total_revenue: Decimal) -> str:
    """Map a customer to one brief segment_type. Order matters: High-Value before Repeat."""
    if total_orders <= 0:
        return "Inactive"
    if total_orders == 1:
        return "One-Time"
    if total_orders >= HIGH_VALUE_MIN_ORDERS and total_revenue >= HIGH_VALUE_MIN_REVENUE:
        return "High-Value"
    return "Repeat"
