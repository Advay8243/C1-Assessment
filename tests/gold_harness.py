"""Shared Gold table builders for tests (landing CSVs → Silver engine → Gold)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "gold"))
sys.path.insert(0, str(ROOT / "src" / "silver"))

from customer_segmentation import build_customer_segmentation  # noqa: E402
from daily_weekly_trends import build_daily_weekly_trends  # noqa: E402
from revenue_by_customer import build_revenue_by_customer  # noqa: E402
from sales_by_product import build_sales_by_product  # noqa: E402
from silver_utils import apply_all_python, build_context, load_landing_records  # noqa: E402
from validate_gold import (  # noqa: E402
    validate_customer_segmentation,
    validate_daily_weekly_trends,
    validate_revenue_by_customer,
    validate_sales_by_product,
)

_CACHE: dict | None = None


def gold_bundle() -> dict:
    global _CACHE
    if _CACHE is None:
        source = load_landing_records(ROOT / "data")
        ctx = build_context(source["customers"], source["products"])
        silver = apply_all_python(
            source["customers"], source["products"], source["orders"], ctx
        )
        sales = build_sales_by_product(silver)
        revenue = build_revenue_by_customer(silver)
        trends = build_daily_weekly_trends(silver)
        segments = build_customer_segmentation(revenue)
        _CACHE = {
            "silver": silver,
            "sales_by_product": sales,
            "revenue_by_customer": revenue,
            "daily_weekly_trends": trends,
            "customer_segmentation": segments,
            "checks": {
                "sales_by_product": validate_sales_by_product(sales, silver),
                "revenue_by_customer": validate_revenue_by_customer(revenue, silver),
                "daily_weekly_trends": validate_daily_weekly_trends(trends, silver),
                "customer_segmentation": validate_customer_segmentation(segments, revenue),
            },
        }
    return _CACHE
