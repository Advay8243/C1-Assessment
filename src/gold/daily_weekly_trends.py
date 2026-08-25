"""
Build gold.daily_weekly_trends from Silver.

Daily grain; order_year / order_week support weekly GROUP BY without storing
a second weekly revenue total that could disagree with the daily rows.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from gold_utils import DAILY_WEEKLY_TRENDS_COLUMNS, money, qualifying_orders


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def build_daily_weekly_trends(
    silver_tables: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    orders, _products = qualifying_orders(silver_tables)
    buckets: dict[date, dict[str, Any]] = {}
    for order in orders:
        order_date = _as_date(order["order_date"])
        bucket = buckets.get(order_date)
        if bucket is None:
            iso = order_date.isocalendar()
            bucket = {
                "order_date": order_date,
                "order_year": order_date.year,
                "order_week": iso.week if hasattr(iso, "week") else iso[1],
                "total_orders": 0,
                "total_revenue": money(0),
                "customer_ids": set(),
            }
            buckets[order_date] = bucket
        bucket["total_orders"] += 1
        bucket["total_revenue"] += money(order["total_amount"])
        bucket["customer_ids"].add(order["customer_id"])

    rows = []
    for bucket in buckets.values():
        revenue = money(bucket["total_revenue"])
        orders_n = int(bucket["total_orders"])
        rows.append(
            {
                "order_date": bucket["order_date"],
                "order_year": bucket["order_year"],
                "order_week": bucket["order_week"],
                "total_orders": orders_n,
                "total_revenue": revenue,
                "avg_order_value": money(revenue / orders_n),
                "unique_customers": len(bucket["customer_ids"]),
            }
        )
    rows.sort(key=lambda row: row["order_date"])
    return [{column: row[column] for column in DAILY_WEEKLY_TRENDS_COLUMNS} for row in rows]
