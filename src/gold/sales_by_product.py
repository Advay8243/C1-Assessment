"""
Build gold.sales_by_product from Silver.

Python path is the test engine. Spark path runs 01_sales_by_product.sql.
"""

from __future__ import annotations

from typing import Any

from gold_utils import (
    SALES_BY_PRODUCT_COLUMNS,
    money,
    qualifying_orders,
)


def build_sales_by_product(
    silver_tables: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    orders, products = qualifying_orders(silver_tables)
    buckets: dict[int, dict[str, Any]] = {}
    for order in orders:
        product_id = order["product_id"]
        product = products[product_id]
        bucket = buckets.get(product_id)
        if bucket is None:
            bucket = {
                "product_id": product_id,
                "product_name": product["product_name"],
                "category": product["category"],
                "total_orders": 0,
                "total_revenue": money(0),
            }
            buckets[product_id] = bucket
        bucket["total_orders"] += 1
        bucket["total_revenue"] += money(order["total_amount"])

    rows = []
    for bucket in buckets.values():
        bucket["total_revenue"] = money(bucket["total_revenue"])
        bucket["avg_order_value"] = money(
            bucket["total_revenue"] / bucket["total_orders"]
        )
        rows.append({column: bucket[column] for column in SALES_BY_PRODUCT_COLUMNS})
    rows.sort(key=lambda row: row["product_id"])
    return rows
