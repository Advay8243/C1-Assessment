# Requirement Analysis

## Problem Statement

An e-commerce company lands daily extracts from three systems — customer master, product catalog, and orders — as CSVs. The company needs a Databricks medallion pipeline that:

1. Lands the files as raw tables (Bronze)
2. Validates the data without silently dropping bad rows (Silver)
3. Publishes business aggregations that analysts can trust (Gold)
4. Feeds a small BI dashboard from those Gold tables only

This is not a generic “clean everything in Silver” job. The sample is deliberately dirty. Bronze must preserve that dirt. Silver must prove it can see it. Gold must not let it into revenue.

## Functional Requirements

Taken from the brief, then narrowed to what this repo actually implements.

### Sample data

- Generate `customers.csv`, `products.csv`, `orders.csv` at the brief volumes (10,000 / 500 / 100,000 unique IDs).
- Plant the mandated quality issues (~700-class order/customer defects).
- Keep generation reproducible (`seed=42`) so tests can assert exact IDs and counts.

### Bronze

- Ingest the three CSVs from a landing path (DBFS FileStore in this project).
- Apply types only. Empty CSV fields become NULL.
- Keep every physical row, including duplicate keys.
- Log ingest metadata (row count, timestamp, batch id, success/fail).
- Do not run quality checks and do not add `quality_check_result`.

### Silver

- Copy Bronze business rows; do not delete or repair them.
- Run five checks (the brief names four; the required repo layout also asks for type and business logic):
  1. Completeness
  2. Uniqueness
  3. Type / domain validation
  4. Referential integrity
  5. Business logic
- Flag each check and set an overall `quality_check_result` (`PASS` / `FAIL`).
- Publish `% passed` per check in `silver.quality_metrics`.

### Gold

- Build the three brief aggregations plus the repo’s fourth SQL file:
  - `gold.sales_by_product`
  - `gold.revenue_by_customer`
  - `gold.customer_segmentation`
  - `gold.daily_weekly_trends` (time series for the extra dashboard tile)
- Facts come from Silver `PASS` + `Completed` orders, joined to `PASS` customers and `PASS` products.
- Dashboard SQL reads Gold only.

### Testing

- One requirements-tier suite that follows planted issues through Bronze → Silver → Gold → dashboard (`tests/test_pipeline_requirements.py`).
- Per-check and per-table tests remain as supporting evidence.

## Non-Functional Requirements

- Python 3.9+ standard library for generation (no Faker, no pandas in the generator).
- Databricks-ready PySpark / Spark SQL for the cluster path; a local Python engine for tests because PySpark is not installed on the laptop.
- No secrets in git. CLI profile `c1-assessment` holds the host/token locally.
- Readable names and comments over extra frameworks.
- Asset Bundle job is serverless because this workspace rejects classic job clusters.

## Assumptions

These are decisions the brief left open. They are implemented in code and tests.

### Shared

- **As-of date is 2026-08-14.** Future-signup and “today” comparisons use this date, not `current_date()`, so the sample stays stable.
- **Landing is Workspace `data/`**, not S3 and not DBFS FileStore. Public DBFS root is disabled in this workspace.
- **Hive-style schemas** `bronze` / `silver` / `gold` (created with `CREATE SCHEMA IF NOT EXISTS`). No custom external location.
- **Empty CSV field = NULL.** Ingest uses `nullValue=""`.
- **Local tests do not start Spark.** Landing CSVs stand in for Bronze; Silver/Gold Python builders are the test engine. Databricks runs the Spark/SQL path in `ingest_all.py`, `create_silver_tables.py`, `create_gold_tables.py`.
- **Databricks Jobs are serverless** (`environment_version: "3"`). Classic `new_cluster` was rejected with “Only serverless compute is supported in the workspace.”

### Bronze

- Bronze **fails the job** if the file is missing or the header lacks required columns (local paths). It does **not** fail because the data is dirty.
- Ingest order is products → customers → orders so parent tables exist before Silver. Bronze itself does not join.
- The only extra columns are `_source_file`, `_ingest_timestamp`, `_batch_id`.
- Duplicate-key extra rows are part of the contract: 10,010 / 505 / 100,020 physical rows. Dropping them to the unique-ID counts is a Bronze bug.

### Silver

- **Flag, do not delete.** Gold filters `quality_check_result = 'PASS'`.
- **NULL foreign keys are completeness, not RI.** Orphans are non-null IDs outside the parent key space (`20001–20050`, `9001–9030`).
- **RI looks up Bronze parent IDs that exist**, not Silver PASS parents. A product can exist and still FAIL Silver (null name, cost > price, …). Gold then excludes FAIL products with an inner join.
- **Customers and products have no FKs**, so `referential_integrity_flag = NOT_APPLICABLE` on those tables. That flag does not fail the row.
- **Every copy of a duplicate key fails uniqueness**, not only the extra row (10 duplicate customer IDs → 20 failing customer rows).
- **NULL keys are not duplicates.** Completeness owns blanks.
- **Any single check FAIL fails the row overall.** `failure_reasons` concatenates reason codes.
- Thresholds are reporting gates, not delete gates: completeness / type / business logic 99%, RI 99.9%, uniqueness 100%. Rows stay either way.
- **Knock-on:** customers `221–230` have signup `2027-03-01`. Their orders also FAIL `ORDER_BEFORE_SIGNUP`. That is intended, not a generator accident.

### Gold

- **Completed orders only.** Pending and Cancelled are valid Silver rows but not sales facts.
- **`avg_order_value = total_revenue / total_orders`**, never a second independent `AVG()`. Zero-order customers get AOV `0`.
- **`lifetime_value_actual` is computed order revenue**, not the source `lifetime_value` column (that column is a placeholder on the CSV).
- **Revenue by customer includes every PASS customer**, including zeros, so Inactive can exist.
- **Segmentation cuts** (brief named the four types but did not define them):
  - Inactive: `total_orders = 0`
  - One-Time: `total_orders = 1`
  - High-Value: `total_orders >= 2` AND `total_revenue >= 1000`
  - Repeat: `total_orders >= 2` AND `total_revenue < 1000`
  - High-Value is applied before Repeat so the types cannot overlap.
- **Daily grain for trends.** `order_year` / `order_week` are attributes. A second stored weekly total is not written (it would be able to disagree with the daily rows).
- **Join fan-out is treated as a defect.** PASS dimensions and qualifying orders are de-duplicated on the business key before aggregation.
- **Segmentation is built from `gold.revenue_by_customer`**, not re-summed from Silver, so the pie cannot drift from the customer table.

### Dashboard

- Tiles **select from Gold**. They must not `SUM(total_amount)` from orders.
- Histogram drops `total_revenue = 0` so Inactive does not become a spike at zero. Those customers still appear on the pie.
- Bar X-axis is `product_id — product_name` so two products with the same name do not merge.
- The dashboard is **queries + a guide**, not a bundle-published Databricks dashboard object.

## Edge Cases

- Duplicate product names with different IDs (dashboard bar labels).
- FAIL products that still have valid FKs from orders (Silver RI passes; Gold inner-join to PASS products excludes them).
- Duplicate Silver keys if uniqueness were ever missed (Gold `ROW_NUMBER` / Python first-seen de-dupe).
- Customers `9700–10000` (301 people) receive no orders so Inactive is not empty.
- Orders that reference future-signup customers fail business logic even when the order row itself was generated “clean.”
- `payment_date` is nullable by design (Pending / Cancelled). Completed-without-payment is a planted FAIL.
- Local Spark write format falls back to Parquet if Delta is missing. Assessment runs on Databricks should be Delta.

## Clarifications We Resolved in the Design

The brief did not define these; we locked them rather than leaving Gold ambiguous:

| Gap in the brief | Decision in this repo |
|---|---|
| Four quality checks vs five files in the repo tree | Implement all five; metrics include all of them |
| Three Gold tables vs `03_daily_weekly_trends.sql` | Build four Gold tables; dashboard uses the fourth as a line chart |
| Products listed as clean | Plant product defects so all three sources exercise Silver (requested during build) |
| When is an order “sold”? | `PASS` + `Completed` only |
| What is High-Value? | ≥ 2 completed PASS orders and ≥ 1000 revenue |
| Source `lifetime_value` vs actual | Gold uses `lifetime_value_actual = total_revenue` |
| S3 vs DBFS | Workspace `data/` files; public DBFS `/FileStore` is disabled |
| Classic cluster vs serverless | Serverless job environment after the workspace rejected classic compute |

## Out of Scope

- Streaming / incremental merge (batch overwrite per layer).
- Unity Catalog grants, SCD2 history, PII tokenization.
- Publishing a Databricks dashboard asset from the bundle.
- Using the Tabcorp `DEFAULT` CLI workspace for this assessment.
