# Design Notes

## Architecture Overview

```text
generate_sample_data.py
        │
        ▼
data/*.csv  →  Workspace .../files/data  (not dbfs:/FileStore)
        │
        ▼
BRONZE   types + ingest metadata only
         bronze.customers | bronze.products | bronze.orders
         bronze.ingestion_log
        │
        ▼
SILVER   five quality checks, flag, do not delete
         silver.customers | silver.products | silver.orders
         silver.quality_metrics
        │
        ▼
GOLD     PASS + Completed facts, de-duped keys
         gold.sales_by_product
         gold.revenue_by_customer
         gold.daily_weekly_trends
         gold.customer_segmentation
         gold.quality_metrics
        │
        ▼
DASHBOARD   Databricks SQL tiles on Gold (queries in src/dashboard/)
```

**Rule that does not change:** Bronze keeps every raw row. Silver flags it. Gold filters it.

Orchestration on Databricks is one Asset Bundle job (`resources/jobs.yml`): `ingest_all.py` → `create_silver_tables.py` → `create_gold_tables.py`. Compute is serverless (`environment_version: "3"`) because this workspace rejected classic job clusters.

## Two execution paths (same contracts)

| Path | Where | Engine |
|---|---|---|
| Databricks | CE / Free Edition workspace | Spark read/write + Gold `.sql` files |
| Laptop tests | `python -m unittest` | Python builders (`apply_all_python`, `build_*`) against `data/*.csv` |

PySpark is not installed locally. Tests therefore treat landing CSVs as Bronze and assert the same business rules the Spark path encodes in SQL. That was a deliberate split, not an incomplete Silver layer.

## Data Model & Schema

See `data-model.md` for grains and columns. Short version:

- Source grain is one CSV row (duplicate keys are extra rows, not updates).
- Silver grain is the same as Bronze plus flags.
- Gold grains are product, customer, day, and segment_type.

## Bronze Layer Design

**Input:** three landing CSVs.  
**Output:** three typed tables + `bronze.ingestion_log`.

Choices:

- Explicit schema (`BUSINESS_FIELDS` in `ingest_utils.py`), not schema-on-read guesswork.
- `nullValue=""` / `emptyValue=""` so planted blanks become NULL.
- `PERMISSIVE` read; no `dropDuplicates`, no `na.drop`, no status filter.
- Input validation is “file exists and header has required columns,” not data quality.
- One `batch_id` shared across the three tables in `run_bronze()`.

Why: the brief’s Silver tests only work if Bronze did not “help” by cleaning.

## Silver Layer Design

**Input:** Bronze tables (Databricks) or landing records (tests).  
**Output:** same rows with five flags + `quality_check_result` + `silver.quality_metrics`.

Choices:

- One module per check (`01`–`05`) plus `create_silver_tables.py` to combine them.
- Overall FAIL if any applicable check is FAIL. `NOT_APPLICABLE` (parent RI) does not fail the row.
- Reason codes (`NULL_EMAIL`, `ORPHAN_CUSTOMER_ID`, …) are stored in `failure_reasons` so a FAIL is explainable.
- Metrics evaluate rows where the flag is not `NOT_APPLICABLE`. Thresholds are documented in `data-quality-strategy.md`; they never delete rows.

Why flag-not-delete: deleting would hide the planted issues and make the quality report lie. Gold is the layer that excludes FAIL rows.

## Gold Layer Design

**Input:** Silver tables.  
**Output:** four aggregation tables + `gold.quality_metrics`.

Shared fact filter (`qualifying_orders` / the SQL CTEs):

1. Order `quality_check_result = PASS`
2. `order_status = Completed`
3. Customer and product also PASS
4. De-duplicate `order_id`, `customer_id`, `product_id` before join/aggregate

Table-specific choices:

- **sales_by_product** — sold products only (inner join to qualifying orders). AOV derived.
- **revenue_by_customer** — left join from PASS customers so zeros remain. `lifetime_value_actual = total_revenue`.
- **daily_weekly_trends** — one row per `order_date`. Week fields are attributes, not a second fact table.
- **customer_segmentation** — reads Gold revenue, not Silver, so the pie cannot invent a different revenue total.

Post-build checks in `validate_gold.py` catch fan-out, grain duplicates, and AOV that was not derived from the stored totals.

## Dashboard Design

Queries in `src/dashboard/dashboard_queries.sql`. Guide in `DASHBOARD_GUIDE.md`.

| Tile | Viz | Source |
|---|---|---|
| Top 10 products | Bar | `gold.sales_by_product` `LIMIT 10` |
| Customer revenue | Histogram | `gold.revenue_by_customer` where revenue > 0 |
| Segmentation | Pie | `gold.customer_segmentation` (headcount) |
| Daily revenue | Line | `gold.daily_weekly_trends` |

The bundle does not publish a dashboard object. That is a workspace UI step after Gold exists.

## Data Quality Validation Strategy

See `data-quality-strategy.md`. Design intent: each planted defect has a Silver check and a test that names the ID range. Gold tests prove those IDs never appear in aggregations.

## Testing Approach

- Per-check unit tests (`tests/test_silver_*.py`, `tests/test_gold_*.py`) lock the rules while building.
- Requirements tier (`tests/test_pipeline_requirements.py`) is what the brief asked for: sample issues → Bronze preserved → Silver handled → Gold aligned → dashboard on Gold.
- Last full local run: 117 tests OK. Requirements tier alone: 23 OK.

## Debugging Approach

When a count is wrong, walk the contract in order:

1. `wc -l data/*.csv` and `generate_sample_data.verify` — did the seed drift?
2. Bronze counts 10010 / 505 / 100020 — did ingest de-dupe?
3. Silver still has those counts — did someone filter FAIL rows?
4. `silver.quality_metrics` — did the check fire on the planted reason?
5. Gold `SUM(total_orders)` vs qualifying Silver order count — fan-out or status filter?

Do not “fix” a Gold mismatch by changing Silver flags without checking the planted ID first.

## Databricks Runtime Notes (what we hit)

- First `bundle deploy` failed: classic job cluster not allowed. Job YAML was switched to serverless environments.
- Later `bundle deploy` failed: organization `3093091232302096` cancelled / jobs create disabled. File sync still worked; Jobs API did not. That is a workspace lifecycle issue, not a medallion logic bug.
- Tokens stay in `~/.databrickscfg` profile `c1-assessment`, never in `databricks.yml`.

## What We Explicitly Did Not Build

- Lakeflow / DLT pipelines (not required; bundle jobs were enough).
- Classic clusters.
- Cleaning or upserting in Bronze.
- A second weekly revenue table.
- Re-aggregation of Silver inside dashboard SQL.
