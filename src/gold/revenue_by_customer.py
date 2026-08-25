"""
Build gold.revenue_by_customer from Silver (brief table B).

Includes every PASS customer. Zero-order customers stay at 0 so Inactive exists.
lifetime_value_actual is total_revenue, not a second sum and not source lifetime_value.
"""

from __future__ import annotations

from typing import Any

from gold_utils import (
    REVENUE_BY_CUSTOMER_COLUMNS,
    money,
    pass_customer_dims,
    qualifying_orders,
)


def build_revenue_by_customer(
    silver_tables: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    orders, _products = qualifying_orders(silver_tables)
    customers = pass_customer_dims(silver_tables["customers"])
    buckets: dict[int, dict[str, Any]] = {}
    for customer_id, customer in customers.items():
        buckets[customer_id] = {
            "customer_id": customer_id,
            "customer_name": customer["customer_name"],
            "customer_segment": customer["customer_segment"],
            "total_orders": 0,
            "total_revenue": money(0),
        }
    for order in orders:
        bucket = buckets[order["customer_id"]]
        bucket["total_orders"] += 1
        bucket["total_revenue"] += money(order["total_amount"])

    rows = []
    for bucket in buckets.values():
        revenue = money(bucket["total_revenue"])
        orders_n = int(bucket["total_orders"])
        bucket["total_revenue"] = revenue
        bucket["lifetime_value_actual"] = revenue
        bucket["avg_order_value"] = money(0) if orders_n == 0 else money(revenue / orders_n)
        rows.append({column: bucket[column] for column in REVENUE_BY_CUSTOMER_COLUMNS})
    rows.sort(key=lambda row: row["customer_id"])
    return rows
