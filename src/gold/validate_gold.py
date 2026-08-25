"""
Gold-layer data quality.

Run after each Gold table is built. Checks catch join fan-out, duplicate grains,
and measures that were calculated independently of the stored totals.
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Any

from gold_utils import (
    AOV_TOLERANCE,
    CUSTOMER_SEGMENTATION_COLUMNS,
    DAILY_WEEKLY_TRENDS_COLUMNS,
    HIGH_VALUE_MIN_ORDERS,
    HIGH_VALUE_MIN_REVENUE,
    PASS,
    REVENUE_BY_CUSTOMER_COLUMNS,
    SALES_BY_PRODUCT_COLUMNS,
    SEGMENT_TYPES,
    assign_segment_type,
    money,
    pass_customer_dims,
    qualifying_orders,
)

PASS_STATUS = "PASS"
FAIL_STATUS = "FAIL"


def _check(
    table_name: str,
    name: str,
    passed: bool,
    rows_failed: int,
    rows_evaluated: int,
    detail: str,
) -> dict[str, Any]:
    return {
        "table_name": table_name,
        "check_name": name,
        "status": PASS_STATUS if passed else FAIL_STATUS,
        "rows_evaluated": rows_evaluated,
        "rows_failed": rows_failed,
        "detail": detail,
    }


def _missing_columns(rows: list[dict[str, Any]], columns: tuple[str, ...], key: str) -> list:
    missing = []
    for row in rows:
        for column in columns:
            if row.get(column) is None or row.get(column) == "":
                missing.append((row.get(key), column))
    return missing


def _aov_mismatches(rows: list[dict[str, Any]], id_key: str, orders_key: str = "total_orders") -> list:
    mismatches = []
    for row in rows:
        orders = Decimal(str(row[orders_key]))
        if orders == 0:
            if money(row["avg_order_value"]) != money(0):
                mismatches.append(row[id_key])
            continue
        expected = money(money(row["total_revenue"]) / orders)
        if abs(money(row["avg_order_value"]) - expected) > AOV_TOLERANCE:
            mismatches.append(row[id_key])
    return mismatches


def validate_sales_by_product(
    gold_rows: list[dict[str, Any]],
    silver_tables: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    table = "sales_by_product"
    expected_orders, pass_products = qualifying_orders(silver_tables)
    checks = []
    n = len(gold_rows)

    ids = [row.get("product_id") for row in gold_rows]
    dup_ids = [key for key, count in Counter(ids).items() if key is not None and count > 1]
    checks.append(
        _check(
            table,
            "grain_uniqueness",
            len(dup_ids) == 0 and None not in ids,
            sum(Counter(ids)[key] for key in dup_ids),
            n,
            "product_id must be unique and not null (one Gold row per product)",
        )
    )

    missing = _missing_columns(gold_rows, SALES_BY_PRODUCT_COLUMNS, "product_id")
    checks.append(
        _check(
            table,
            "completeness",
            len(missing) == 0,
            len({item[0] for item in missing}),
            n,
            "required Gold columns must be populated",
        )
    )

    bad_measures = [
        row
        for row in gold_rows
        if int(row["total_orders"]) < 1
        or Decimal(str(row["total_revenue"])) < 0
        or Decimal(str(row["avg_order_value"])) < 0
    ]
    checks.append(
        _check(
            table,
            "positive_measures",
            len(bad_measures) == 0,
            len(bad_measures),
            n,
            "sold products only: total_orders >= 1 and amounts >= 0",
        )
    )

    aov_mismatch = _aov_mismatches(gold_rows, "product_id")
    checks.append(
        _check(
            table,
            "derived_avg_order_value",
            len(aov_mismatch) == 0,
            len(aov_mismatch),
            n,
            "avg_order_value must equal total_revenue / total_orders (not a separate AVG)",
        )
    )

    gold_order_sum = sum(int(row["total_orders"]) for row in gold_rows)
    gold_revenue_sum = sum((money(row["total_revenue"]) for row in gold_rows), money(0))
    source_revenue = sum((money(order["total_amount"]) for order in expected_orders), money(0))
    checks.append(
        _check(
            table,
            "order_count_reconciles",
            gold_order_sum == len(expected_orders),
            abs(gold_order_sum - len(expected_orders)),
            len(expected_orders),
            "sum(total_orders) must equal distinct qualifying Silver orders",
        )
    )
    checks.append(
        _check(
            table,
            "revenue_reconciles",
            abs(gold_revenue_sum - source_revenue) <= AOV_TOLERANCE,
            0 if abs(gold_revenue_sum - source_revenue) <= AOV_TOLERANCE else 1,
            len(expected_orders),
            "sum(total_revenue) must equal sum(total_amount) of qualifying orders",
        )
    )

    unknown = [row["product_id"] for row in gold_rows if row["product_id"] not in pass_products]
    checks.append(
        _check(
            table,
            "dimension_referential_integrity",
            len(unknown) == 0,
            len(unknown),
            n,
            "every Gold product_id must exist in Silver PASS products",
        )
    )

    dim_mismatch = []
    for row in gold_rows:
        product = pass_products.get(row["product_id"])
        if product is None:
            continue
        if row["product_name"] != product["product_name"] or row["category"] != product["category"]:
            dim_mismatch.append(row["product_id"])
    checks.append(
        _check(
            table,
            "dimension_matches_silver",
            len(dim_mismatch) == 0,
            len(dim_mismatch),
            n,
            "product_name and category must come from the PASS product row",
        )
    )

    gold_ids = {row["product_id"] for row in gold_rows}
    fail_products = {
        row["product_id"]
        for row in silver_tables["products"]
        if row.get("quality_check_result") != PASS and row.get("product_id") is not None
    }
    leaked = [pid for pid in gold_ids if pid in fail_products]
    checks.append(
        _check(
            table,
            "excludes_failed_products",
            len(leaked) == 0,
            len(leaked),
            n,
            "Silver FAIL products must not appear on Gold",
        )
    )
    return checks


def validate_revenue_by_customer(
    gold_rows: list[dict[str, Any]],
    silver_tables: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    table = "revenue_by_customer"
    expected_orders, _products = qualifying_orders(silver_tables)
    pass_customers = pass_customer_dims(silver_tables["customers"])
    checks = []
    n = len(gold_rows)

    ids = [row.get("customer_id") for row in gold_rows]
    dup_ids = [key for key, count in Counter(ids).items() if key is not None and count > 1]
    checks.append(
        _check(
            table,
            "grain_uniqueness",
            len(dup_ids) == 0 and None not in ids,
            sum(Counter(ids)[key] for key in dup_ids),
            n,
            "customer_id must be unique and not null (one Gold row per PASS customer)",
        )
    )

    missing = _missing_columns(gold_rows, REVENUE_BY_CUSTOMER_COLUMNS, "customer_id")
    checks.append(
        _check(
            table,
            "completeness",
            len(missing) == 0,
            len({item[0] for item in missing}),
            n,
            "required brief columns must be populated",
        )
    )

    checks.append(
        _check(
            table,
            "covers_all_pass_customers",
            set(ids) == set(pass_customers),
            abs(n - len(pass_customers)),
            len(pass_customers),
            "every PASS customer must appear, including Inactive (zero orders)",
        )
    )

    aov_mismatch = _aov_mismatches(gold_rows, "customer_id")
    checks.append(
        _check(
            table,
            "derived_avg_order_value",
            len(aov_mismatch) == 0,
            len(aov_mismatch),
            n,
            "avg_order_value must equal total_revenue / total_orders (0 when no orders)",
        )
    )

    ltv_mismatch = [
        row["customer_id"]
        for row in gold_rows
        if money(row["lifetime_value_actual"]) != money(row["total_revenue"])
    ]
    checks.append(
        _check(
            table,
            "lifetime_value_matches_revenue",
            len(ltv_mismatch) == 0,
            len(ltv_mismatch),
            n,
            "lifetime_value_actual must equal total_revenue (not source lifetime_value)",
        )
    )

    gold_order_sum = sum(int(row["total_orders"]) for row in gold_rows)
    gold_revenue_sum = sum((money(row["total_revenue"]) for row in gold_rows), money(0))
    source_revenue = sum((money(order["total_amount"]) for order in expected_orders), money(0))
    checks.append(
        _check(
            table,
            "order_count_reconciles",
            gold_order_sum == len(expected_orders),
            abs(gold_order_sum - len(expected_orders)),
            len(expected_orders),
            "sum(total_orders) must equal distinct qualifying Silver orders",
        )
    )
    checks.append(
        _check(
            table,
            "revenue_reconciles",
            abs(gold_revenue_sum - source_revenue) <= AOV_TOLERANCE,
            0 if abs(gold_revenue_sum - source_revenue) <= AOV_TOLERANCE else 1,
            len(expected_orders),
            "sum(total_revenue) must equal sum(total_amount) of qualifying orders",
        )
    )

    dim_mismatch = []
    for row in gold_rows:
        customer = pass_customers.get(row["customer_id"])
        if customer is None:
            continue
        if (
            row["customer_name"] != customer["customer_name"]
            or row["customer_segment"] != customer["customer_segment"]
        ):
            dim_mismatch.append(row["customer_id"])
    checks.append(
        _check(
            table,
            "dimension_matches_silver",
            len(dim_mismatch) == 0,
            len(dim_mismatch),
            n,
            "customer_name and customer_segment must come from the PASS customer row",
        )
    )

    fail_customers = {
        row["customer_id"]
        for row in silver_tables["customers"]
        if row.get("quality_check_result") != PASS and row.get("customer_id") is not None
    }
    leaked = [cid for cid in ids if cid in fail_customers]
    checks.append(
        _check(
            table,
            "excludes_failed_customers",
            len(leaked) == 0,
            len(leaked),
            n,
            "Silver FAIL customers must not appear on Gold",
        )
    )
    return checks


def validate_daily_weekly_trends(
    gold_rows: list[dict[str, Any]],
    silver_tables: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    table = "daily_weekly_trends"
    expected_orders, _products = qualifying_orders(silver_tables)
    checks = []
    n = len(gold_rows)

    dates = [row.get("order_date") for row in gold_rows]
    dup_dates = [key for key, count in Counter(dates).items() if key is not None and count > 1]
    checks.append(
        _check(
            table,
            "grain_uniqueness",
            len(dup_dates) == 0 and None not in dates,
            sum(Counter(dates)[key] for key in dup_dates),
            n,
            "order_date must be unique and not null (one Gold row per day)",
        )
    )

    missing = _missing_columns(gold_rows, DAILY_WEEKLY_TRENDS_COLUMNS, "order_date")
    checks.append(
        _check(
            table,
            "completeness",
            len(missing) == 0,
            len({item[0] for item in missing}),
            n,
            "required trend columns must be populated",
        )
    )

    aov_mismatch = _aov_mismatches(gold_rows, "order_date")
    checks.append(
        _check(
            table,
            "derived_avg_order_value",
            len(aov_mismatch) == 0,
            len(aov_mismatch),
            n,
            "avg_order_value must equal total_revenue / total_orders",
        )
    )

    unique_bad = [
        row
        for row in gold_rows
        if int(row["unique_customers"]) < 1
        or int(row["unique_customers"]) > int(row["total_orders"])
    ]
    checks.append(
        _check(
            table,
            "unique_customers_bounded",
            len(unique_bad) == 0,
            len(unique_bad),
            n,
            "unique_customers must be between 1 and total_orders on each day",
        )
    )

    gold_order_sum = sum(int(row["total_orders"]) for row in gold_rows)
    gold_revenue_sum = sum((money(row["total_revenue"]) for row in gold_rows), money(0))
    source_revenue = sum((money(order["total_amount"]) for order in expected_orders), money(0))
    checks.append(
        _check(
            table,
            "order_count_reconciles",
            gold_order_sum == len(expected_orders),
            abs(gold_order_sum - len(expected_orders)),
            len(expected_orders),
            "sum(daily total_orders) must equal distinct qualifying Silver orders",
        )
    )
    checks.append(
        _check(
            table,
            "revenue_reconciles",
            abs(gold_revenue_sum - source_revenue) <= AOV_TOLERANCE,
            0 if abs(gold_revenue_sum - source_revenue) <= AOV_TOLERANCE else 1,
            len(expected_orders),
            "sum(daily total_revenue) must equal sum(total_amount) of qualifying orders",
        )
    )
    return checks


def validate_customer_segmentation(
    gold_rows: list[dict[str, Any]],
    revenue_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    table = "customer_segmentation"
    checks = []
    n = len(gold_rows)
    by_type = {row.get("segment_type"): row for row in gold_rows}

    checks.append(
        _check(
            table,
            "four_brief_segments",
            set(by_type) == set(SEGMENT_TYPES) and n == 4,
            abs(n - 4),
            4,
            "table must have exactly High-Value, Repeat, One-Time, Inactive",
        )
    )

    missing = _missing_columns(gold_rows, CUSTOMER_SEGMENTATION_COLUMNS, "segment_type")
    checks.append(
        _check(
            table,
            "completeness",
            len(missing) == 0,
            len({item[0] for item in missing}),
            n,
            "required brief columns must be populated",
        )
    )

    expected_counts: dict[str, int] = {segment: 0 for segment in SEGMENT_TYPES}
    expected_revenue = {segment: money(0) for segment in SEGMENT_TYPES}
    for row in revenue_rows:
        segment = assign_segment_type(int(row["total_orders"]), money(row["total_revenue"]))
        expected_counts[segment] += 1
        expected_revenue[segment] += money(row["total_revenue"])

    count_mismatch = [
        segment
        for segment in SEGMENT_TYPES
        if int(by_type.get(segment, {}).get("customer_count", -1)) != expected_counts[segment]
        or abs(
            money(by_type.get(segment, {}).get("total_revenue", 0))
            - money(expected_revenue[segment])
        )
        > AOV_TOLERANCE
    ]
    checks.append(
        _check(
            table,
            "counts_match_revenue_table",
            len(count_mismatch) == 0,
            len(count_mismatch),
            4,
            "customer_count and total_revenue must come from gold.revenue_by_customer",
        )
    )

    gold_customers = sum(int(row["customer_count"]) for row in gold_rows)
    gold_revenue = sum((money(row["total_revenue"]) for row in gold_rows), money(0))
    source_revenue = sum((money(row["total_revenue"]) for row in revenue_rows), money(0))
    checks.append(
        _check(
            table,
            "covers_all_revenue_customers",
            gold_customers == len(revenue_rows),
            abs(gold_customers - len(revenue_rows)),
            len(revenue_rows),
            "segment customer_count must sum to PASS customers in revenue_by_customer",
        )
    )
    checks.append(
        _check(
            table,
            "revenue_reconciles",
            abs(gold_revenue - source_revenue) <= AOV_TOLERANCE,
            0 if abs(gold_revenue - source_revenue) <= AOV_TOLERANCE else 1,
            len(revenue_rows),
            "segment total_revenue must sum to revenue_by_customer total_revenue",
        )
    )

    avg_mismatch = []
    for row in gold_rows:
        count = int(row["customer_count"])
        expected_avg = money(0) if count == 0 else money(money(row["total_revenue"]) / count)
        if abs(money(row["avg_revenue"]) - expected_avg) > AOV_TOLERANCE:
            avg_mismatch.append(row["segment_type"])
    checks.append(
        _check(
            table,
            "derived_avg_revenue",
            len(avg_mismatch) == 0,
            len(avg_mismatch),
            n,
            "avg_revenue must equal total_revenue / customer_count",
        )
    )

    rule_break = []
    for row in revenue_rows:
        segment = assign_segment_type(int(row["total_orders"]), money(row["total_revenue"]))
        orders_n = int(row["total_orders"])
        revenue = money(row["total_revenue"])
        if segment == "Inactive" and orders_n != 0:
            rule_break.append(row["customer_id"])
        if segment == "One-Time" and orders_n != 1:
            rule_break.append(row["customer_id"])
        if segment == "High-Value" and (
            orders_n < HIGH_VALUE_MIN_ORDERS or revenue < HIGH_VALUE_MIN_REVENUE
        ):
            rule_break.append(row["customer_id"])
        if segment == "Repeat" and (
            orders_n < HIGH_VALUE_MIN_ORDERS or revenue >= HIGH_VALUE_MIN_REVENUE
        ):
            rule_break.append(row["customer_id"])
    checks.append(
        _check(
            table,
            "segment_rules_exclusive",
            len(rule_break) == 0,
            len(rule_break),
            len(revenue_rows),
            "High-Value / Repeat / One-Time / Inactive must be mutually exclusive",
        )
    )
    return checks


def all_checks_passed(checks: list[dict[str, Any]]) -> bool:
    return all(row["status"] == PASS_STATUS for row in checks)


def print_gold_quality_report(checks: list[dict[str, Any]]) -> None:
    print("Gold quality report")
    print(f"{'table':<24} {'check':<34} {'status':<6} {'failed':>8} {'evaluated':>10}")
    for row in checks:
        print(
            f"{row['table_name']:<24} {row['check_name']:<34} {row['status']:<6} "
            f"{row['rows_failed']:>8} {row['rows_evaluated']:>10}"
        )
        print(f"    {row['detail']}")
