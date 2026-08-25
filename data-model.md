# Data Model

Physical tables are declared in `database/schema.sql`. This file explains grains, keys, and how layers relate. All business columns on Bronze/Silver are nullable: the model must store the planted defects.

## Source files (landing)

Empty CSV field = NULL.

### customers.csv → bronze.customers / silver.customers

| Column | Type | Role |
|---|---|---|
| customer_id | INT | Natural key (not unique in the file) |
| customer_name | STRING | |
| email | STRING | Completeness + type (format) |
| country | STRING | |
| signup_date | DATE | Business logic (not after 2026-08-14) |
| customer_segment | STRING | Domain: Premium / Standard / Basic |
| lifetime_value | DECIMAL(18,2) | Source placeholder only |

Physical rows: **10,010** (10,000 IDs + 10 duplicate-key rows). IDs `1`–`10000`. IDs `9700`–`10000` have no orders.

### products.csv → bronze.products / silver.products

| Column | Type | Role |
|---|---|---|
| product_id | INT | Natural key (not unique in the file) |
| product_name | STRING | Completeness |
| category | STRING | Completeness |
| price | DECIMAL(18,2) | |
| cost | DECIMAL(18,2) | Business logic vs price |
| stock_quantity | INT | Type: not negative |
| reorder_level | INT | |

Physical rows: **505** (500 IDs + 5 duplicate-key rows). IDs `1`–`500`.

### orders.csv → bronze.orders / silver.orders

| Column | Type | Role |
|---|---|---|
| order_id | INT | Natural key (not unique in the file) |
| customer_id | INT | FK → customers (NULL and orphans planted) |
| order_date | DATE | Completeness; vs signup |
| product_id | INT | FK → products (NULL and orphans planted) |
| quantity | INT | Type: positive |
| unit_price | DECIMAL(18,2) | |
| total_amount | DECIMAL(18,2) | Business logic vs qty × price |
| order_status | STRING | Pending / Completed / Cancelled |
| payment_date | DATE | Nullable; status rules in Silver |

Physical rows: **100,020** (100,000 IDs + 20 duplicate-key rows). IDs `1`–`100000`.

Relationships (when keys are populated and valid):

```text
customers.customer_id  1 ──*  orders.customer_id
products.product_id    1 ──*  orders.product_id
```

Bronze does not enforce these. Silver flags violations. Gold inner-joins PASS parents.

## Bronze technical columns

Added on every business table; not in the CSV.

| Column | Meaning |
|---|---|
| _source_file | Landing path |
| _ingest_timestamp | UTC ingest time |
| _batch_id | Shared across the three tables in one `run_bronze()` |

`bronze.ingestion_log` is append-only: one row per table per attempt (`status` SUCCESS/FAILED, `row_count`, `expected_row_count`).

## Silver quality columns

Same business + Bronze metadata, plus:

| Column | Values |
|---|---|
| completeness_flag | PASS / FAIL |
| uniqueness_flag | PASS / FAIL |
| type_validation_flag | PASS / FAIL |
| referential_integrity_flag | PASS / FAIL / NOT_APPLICABLE |
| business_logic_flag | PASS / FAIL |
| quality_check_result | PASS if no FAIL flags; else FAIL |
| failure_reasons | `; `-joined reason codes |
| _silver_processed_at | |
| _silver_batch_id | |

`silver.quality_metrics`: one row per `(table_name, check_name)` with `rows_evaluated`, `rows_passed`, `rows_failed`, `pass_percentage`, `threshold`, `threshold_met`.

**Assumption:** `NOT_APPLICABLE` on customer/product RI is not a FAIL. Overall result ignores it.

## Gold tables

Facts used in all four tables: Silver orders with `quality_check_result = PASS` and `order_status = Completed`, customer PASS, product PASS, keys de-duplicated.

### gold.sales_by_product

Grain: one row per `product_id` that sold at least once.

| Column | Rule |
|---|---|
| total_orders | COUNT of qualifying orders |
| total_revenue | SUM(total_amount) |
| avg_order_value | total_revenue / total_orders |

FAIL products do not appear, even if Bronze FKs existed.

### gold.revenue_by_customer

Grain: one row per PASS `customer_id` (including zero orders).

| Column | Rule |
|---|---|
| customer_segment | From Silver (Premium / Standard / Basic), not Gold segment_type |
| total_orders / total_revenue | Qualifying orders only |
| avg_order_value | 0 when total_orders = 0; else revenue / orders |
| lifetime_value_actual | Same figure as total_revenue |

**Assumption:** source `lifetime_value` is not copied into Gold.

### gold.daily_weekly_trends

Grain: one row per `order_date`.

| Column | Rule |
|---|---|
| order_year, order_week | ISO week attributes on that date |
| unique_customers | Distinct customer_id that day |
| avg_order_value | That day’s revenue / orders |

No second weekly fact table.

### gold.customer_segmentation

Grain: one row per `segment_type` (always four rows).

| segment_type | Rule (from revenue_by_customer) |
|---|---|
| Inactive | total_orders = 0 |
| One-Time | total_orders = 1 |
| High-Value | total_orders ≥ 2 and total_revenue ≥ 1000 |
| Repeat | total_orders ≥ 2 and total_revenue < 1000 |

`avg_revenue` = segment total_revenue / customer_count. Built from Gold revenue, not Silver.

### gold.quality_metrics

Post-build checks (grain uniqueness, reconcile to Silver, derived AOV, no FAIL product leak, exclusive segments). Different shape from Silver metrics (`status` / `detail` rather than pass %).

## What is not in the model

- Surrogate keys / SCD2.
- Constraints (`PRIMARY KEY`, `FOREIGN KEY`) on Delta tables — they would reject the sample.
- Loading CSVs directly into Silver or Gold.
