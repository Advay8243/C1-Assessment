# Data Quality Strategy

Quality is layered. Bronze records dirt. Silver names it. Gold refuses it. The dashboard does not invent a fourth copy of the business rules.

## Quality Checks Overview

Implemented in `src/silver/01`–`05`. Combined in `create_silver_tables.py`. Rows are **flagged, never deleted**.

### 1. Completeness

- **What:** Critical fields are not NULL / blank.
- **Customers:** `email`, `customer_id`, `customer_name`
- **Products:** `product_id`, `product_name`, `category`
- **Orders:** `order_id`, `customer_id`, `product_id`, `order_date`
- **How:** empty string counts as NULL (same as CSV blanks).
- **Threshold (report only):** >99% of evaluated rows PASS.
- **Planted:** 50 NULL emails; 10 NULL product names; 5 NULL categories; 100 NULL order `customer_id`; 200 NULL order `product_id`.
- **Assumption:** NULL FKs are completeness failures. They are **not** counted as orphans.

### 2. Uniqueness

- **What:** Natural keys are unique.
- **Keys:** `customer_id`, `product_id`, `order_id`.
- **How:** if a non-null key appears more than once, **every** row with that key FAILs (`DUPLICATE_*`).
- **Threshold:** 100% unique (will not be met on this sample — that is the point).
- **Planted extra rows:** 10 customers, 5 products, 20 orders → 20 / 10 / 40 failing rows.
- **Assumption:** NULL keys are ignored here so completeness can own them.

### 3. Type / domain validation

- **What:** Populated values are in the allowed domain.
- **Customers:** segment in Premium/Standard/Basic; email matches `^[^@\s]+@[^@\s]+\.[^@\s]+$`; no negative id/LTV.
- **Products:** stock/price/cost/reorder not negative.
- **Orders:** quantity > 0; status in Pending/Completed/Cancelled; amounts not negative.
- **Threshold:** >99%.
- **Planted:** invalid segments `201–210`; malformed emails `211–220`; negative stock `24–28`.
- **Assumption:** NULL email is completeness, not `MALFORMED_EMAIL`.

### 4. Referential integrity

- **What:** Non-null order FKs exist in the parent **Bronze** key set.
- **How:** `customer_id` in bronze customer ids; `product_id` in bronze product ids.
- **Threshold:** >99.9%.
- **Planted:** 50 orders with `customer_id` `20001–20050`; 30 with `product_id` `9001–9030`.
- **Assumption:** parents (customers, products) are `NOT_APPLICABLE`. Existence in Bronze is enough for RI; Gold still requires the parent row to be Silver PASS. A FAIL product can be a valid FK and still be excluded from revenue.

### 5. Business logic

- **What:** Cross-field rules types cannot catch.
- **Customers:** `signup_date` ≤ 2026-08-14.
- **Products:** `cost` ≤ `price`.
- **Orders:** `total_amount ≈ quantity * unit_price` (tolerance 0.01); Completed requires `payment_date`; Pending/Cancelled must not have `payment_date`; payment not before order date; `order_date` ≥ customer signup.
- **Threshold:** >99%.
- **Planted:** future signups `221–230`; cost > price `16–23`; wrong totals `601–625`; Completed without payment `626–640`; Pending with payment `641–650`.
- **Knock-on (documented, tested):** orders for future-signup customers also FAIL `ORDER_BEFORE_SIGNUP`.

### Overall row result

`quality_check_result = FAIL` if any of the five flags is FAIL. Gold reads PASS only.

## Quality Metrics Report

`silver.quality_metrics` stores, per table and check:

- `rows_evaluated` (excludes `NOT_APPLICABLE`)
- `rows_passed` / `rows_failed`
- `pass_percentage`
- `threshold` / `threshold_met`

Uniqueness on this sample is expected **not** to meet the 100% threshold (duplicate keys are planted). Completeness on orders still clears 99%: 300 NULL FK rows in 100,020 is about 0.3% fail. Tests lock **failed row counts** to the planted catalog rather than requiring every `threshold_met` flag to be true.

## Sample Data Quality Issues

Full ID catalog: `src/data_generation/DATA_GENERATION_NOTES.md` and `database/seed-data-notes.md`.

**Brief-mandated (~700-class):**

| Issue | Count |
|---|---|
| NULL customer email | 50 |
| Extra duplicate customer rows | 10 |
| NULL order customer_id | 100 |
| NULL order product_id | 200 |
| Orphan customer_id | 50 |
| Orphan product_id | 30 |
| Extra duplicate order rows | 20 |

**Added so products and the extra Silver files have known fails:** invalid segment, malformed email, future signup, NULL product name/category, cost > price, negative stock, duplicate products, wrong totals, payment/status mismatches.

Issue ID ranges do not overlap. Duplicate copies are otherwise clean so uniqueness is the only fail on those extra rows.

## Gold-layer quality

After each Gold table is built, `validate_gold.py` checks:

- Grain uniqueness (one product, one customer, one date, four segments)
- Required columns populated
- AOV / avg_revenue derived from stored totals
- `SUM(total_orders)` and `SUM(total_revenue)` match qualifying Silver orders
- FAIL products/customers do not leak
- Segmentation rules are exclusive and reconcile to `revenue_by_customer`

Sales, customer revenue, daily trends, and segmentation **must share the same qualifying revenue**. That is how we know Gold is aligned with Silver rather than each SQL file inventing a filter.

## Dashboard quality

`tests/test_pipeline_requirements.py` `DashboardQualityTests`:

- SQL reads `gold.*` only
- No `SUM(total_amount)` and no rebuilt High-Value CASE
- Top 10 ranking matches Gold
- Histogram is one positive revenue per PASS customer
- Pie is the four Gold segments; headcount sums to `revenue_by_customer`
- Line totals match Gold daily trends / sales revenue

## How we know the pipeline is not “cleaning away” the exercise

1. Generator `verify()` refuses to write CSVs if planted counts drift.
2. Bronze row counts stay 10,010 / 505 / 100,020.
3. Silver row counts stay the same; planted IDs are FAIL with the right reason.
4. Those IDs are absent from Gold facts.
5. Requirements-tier tests (23) passed locally; full suite 117 OK.

## What we do not do

- Auto-repair emails, FKs, or amounts in Silver.
- Drop Cancelled/Pending in Silver (Gold excludes them from facts).
- Treat threshold_met = false as a job-killing error. The job still writes Silver; the report shows the miss.
- Re-run quality in the dashboard SQL.
