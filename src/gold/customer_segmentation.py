"""
Build gold.customer_segmentation from gold.revenue_by_customer (brief table C).

Always emits the four brief segment types. Does not re-sum Silver orders.
"""

from __future__ import annotations

from typing import Any

from gold_utils import (
    CUSTOMER_SEGMENTATION_COLUMNS,
    SEGMENT_TYPES,
    assign_segment_type,
    money,
)


def build_customer_segmentation(
    revenue_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    buckets = {
        segment: {"customer_count": 0, "total_revenue": money(0)}
        for segment in SEGMENT_TYPES
    }
    for row in revenue_rows:
        segment = assign_segment_type(int(row["total_orders"]), money(row["total_revenue"]))
        buckets[segment]["customer_count"] += 1
        buckets[segment]["total_revenue"] += money(row["total_revenue"])

    rows = []
    for segment in SEGMENT_TYPES:
        count = int(buckets[segment]["customer_count"])
        revenue = money(buckets[segment]["total_revenue"])
        rows.append(
            {
                "segment_type": segment,
                "customer_count": count,
                "avg_revenue": money(0) if count == 0 else money(revenue / count),
                "total_revenue": revenue,
            }
        )
    return [{column: row[column] for column in CUSTOMER_SEGMENTATION_COLUMNS} for row in rows]
