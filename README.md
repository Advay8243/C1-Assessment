# C1 Assessment — E-commerce Medallion Pipeline

Databricks medallion pipeline for e-commerce sales: **Bronze → Silver → Gold → Dashboard**.

Sample CSVs are generated with planted quality issues. Bronze lands them unchanged. Silver flags bad rows (it does not delete them). Gold aggregates only Silver `PASS` + `Completed` orders. Dashboard SQL reads Gold only.

This is the coding exercise for the competency AI-capability assessment, not a production deployment.

## How it fits together

```text
data/*.csv
    → bronze.customers | products | orders     (raw + ingest metadata)
    → silver.* + silver.quality_metrics        (five checks, flags only)
    → gold.sales_by_product
      gold.revenue_by_customer
      gold.daily_weekly_trends
      gold.customer_segmentation
    → src/dashboard/dashboard_queries.sql
```

| Layer | Contract |
|---|---|
| Seed | 10,010 / 505 / 100,020 physical rows (unique IDs 10,000 / 500 / 100,000 plus duplicate-key extras) |
| Bronze | Types + `_source_file`, `_ingest_timestamp`, `_batch_id`. Empty CSV fields → NULL. No cleaning. |
| Silver | Completeness, uniqueness, type, referential integrity, business logic. `quality_check_result` = PASS/FAIL. |
| Gold | PASS customers/products, Completed orders only. AOV = revenue / orders. `lifetime_value_actual` = computed revenue, not the CSV LTV column. |
| Dashboard | Four tiles from Gold: top 10 bar, revenue histogram, segment pie, daily line. |

Details of checks, grains, and assumptions: `requirements-analysis.md`, `design-notes.md`, `data-model.md`, `data-quality-strategy.md`.

## Repository layout

```text
src/data_generation/   generate_sample_data.py (seed=42, stdlib only)
src/bronze/            CSV ingest
src/silver/            quality checks + create_silver_tables.py
src/gold/              aggregations + SQL + validate_gold.py
src/dashboard/         dashboard_queries.sql + DASHBOARD_GUIDE.md
data/                  checked-in seed CSVs
database/              schema.sql, setup-notes.md, seed-data-notes.md
tests/                 unit tests + requirements tier
databricks.yml         Asset Bundle (serverless job)
```

## Prerequisites

- Python 3.9+
- Databricks workspace (this project used Free Edition / serverless-only compute)
- Databricks CLI, profile `c1-assessment` in `~/.databrickscfg` — **do not put tokens in the repo**

PySpark is not required to generate data or run tests. It is required to write Delta tables on Databricks.

## Run locally

From this directory (`C1-Assessment`):

```bash
# Regenerate seed CSVs (already in data/)
python src/data_generation/generate_sample_data.py

# Requirements tier (planted issues → Bronze preserved → Silver → Gold → dashboard)
python -m unittest tests.test_pipeline_requirements -v

# Full suite
python -m unittest discover -s tests -p 'test_*.py'

# Optional: Silver/Gold engines without Spark writes
python src/silver/create_silver_tables.py --from-landing
python src/gold/create_gold_tables.py --from-landing
```

Landing CSVs stand in for Bronze in tests. Last full local run: **117 tests OK**.

## Run on Databricks (manual notebooks)

No Jobs. Attach a cluster and Run All, in order:

1. `src/notebooks/01_copy_landing.py`
2. `src/notebooks/02_bronze.py`
3. `src/notebooks/03_silver.py`
4. `src/notebooks/04_gold.py`

Details: `database/setup-notes.md`.

## Run on Databricks (Jobs / Asset Bundle)

1. Confirm `data/*.csv` are in the synced Workspace folder (`.../files/data/`). Public DBFS `/FileStore` is disabled.
2. Deploy and run the bundle job (serverless — this workspace does not allow classic job clusters):

```bash
export DATABRICKS_CONFIG_PROFILE=c1-assessment
databricks bundle validate -t dev
databricks bundle deploy -t dev
databricks bundle run medallion_pipeline -t dev
```

Job order: `ingest_all.py` → `create_silver_tables.py` → `create_gold_tables.py`.

If Jobs API is blocked (org cancelled / quota), run the same three `run_bronze()` / `run_silver()` / `run_gold()` calls on **serverless** in a notebook.

### Quick checks after a run

```sql
SELECT COUNT(*) FROM bronze.customers;              -- 10010
SELECT COUNT(*) FROM bronze.orders WHERE customer_id IS NULL;  -- 100
SELECT COUNT(*) FROM silver.orders;                 -- 100020 (nothing deleted)
SELECT table_name, check_name, rows_failed, pass_percentage
FROM silver.quality_metrics;
SELECT segment_type, customer_count FROM gold.customer_segmentation;
```

Then paste the four queries in `src/dashboard/dashboard_queries.sql` into SQL Editor. Visualization settings: `src/dashboard/DASHBOARD_GUIDE.md`.

## Design choices worth knowing

- **Flag, don’t delete** in Silver. Gold filters `quality_check_result = 'PASS'`.
- **NULL FKs are completeness**, not orphans. Orphans are IDs `20001–20050` / `9001–9030`.
- **High-Value** = ≥ 2 completed PASS orders and revenue ≥ 1000; **Inactive** = PASS customers with zero such orders (IDs `9700–10000` have no orders in the seed).
- Products were given planted defects as well (the brief left the catalog clean).
- Dashboard SQL must not `SUM(total_amount)` from orders or rebuild segment CASE logic.

## Further reading

| File | Contents |
|---|---|
| `requirements-analysis.md` | Requirements, assumptions, edge cases |
| `design-notes.md` | Layer design and Databricks runtime notes |
| `data-model.md` | Tables, grains, keys |
| `data-quality-strategy.md` | Checks, thresholds, planted issues |
| `database/setup-notes.md` | Cluster/DBFS/bundle setup |
| `src/data_generation/DATA_GENERATION_NOTES.md` | Issue catalog and ID ranges |
| `ai-prompts/` | Actual Cursor prompts from this project (not invented) |
