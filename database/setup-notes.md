# Setup Notes

How to land the sample CSVs and run Bronze → Silver → Gold on Databricks.

Related: `database/seed-data-notes.md` (row counts and NULL handling)  
Related: `database/schema.sql` (DDL)  
Related: `src/dashboard/DASHBOARD_GUIDE.md` (tiles after Gold exists)

## What each layer does (contract)

**Bronze** — Read the three CSVs, apply types, treat `""` as NULL, add `_source_file` / `_ingest_timestamp` / `_batch_id`, write `bronze.*` and append `bronze.ingestion_log`. No cleaning.

**Silver** — Copy Bronze rows, run five quality checks, flag (do not delete), write `silver.*` and `silver.quality_metrics`.

**Gold** — Aggregate Silver `PASS` + `Completed` orders (PASS customer and product), write the four Gold tables and `gold.quality_metrics`.

If Bronze/Silver counts are 10,000 / 500 / 100,000 instead of **10,010 / 505 / 100,020**, duplicate-key rows were dropped — that is a bug.

## 1. Generate or confirm seed CSVs

From the repository root:

```bash
python src/data_generation/generate_sample_data.py
```

Confirm `data/customers.csv`, `data/products.csv`, `data/orders.csv` exist.

## 2. Auth (never in git)

Use CLI profile `c1-assessment` in `~/.databrickscfg`. Host is also in `databricks.yml`. Do not put a PAT in the repo or in chat logs.

```bash
export DATABRICKS_CONFIG_PROFILE=c1-assessment
databricks bundle validate -t dev
```

Workspace host used for this project: `https://dbc-a6c854d8-1508.cloud.databricks.com`.

## 3. Databricks workspace constraints we hit

- **Serverless only.** Classic job clusters returned `Only serverless compute is supported in the workspace.` The bundle job uses `environments` / `environment_version: "3"` (`resources/jobs.yml`).
- **Jobs create can be disabled** if the Free Edition org is cancelled or quota-blocked (`Organization … has been cancelled or is not active yet` / `Triggering new runs … disabled temporarily`). File upload can still succeed. That is account/workspace state, not a YAML logic error.
- Do not point this assessment at the Tabcorp `DEFAULT` profile.

## 4. Landing files (Workspace, not DBFS FileStore)

This workspace has **public DBFS root disabled**, so `/FileStore/medallion/landing` is blocked.

Default landing path is the repo `data/` folder, which the bundle syncs to:

```
/Workspace/Users/<you>/.bundle/c1-medallion-pipeline/dev/files/data/customers.csv
/Workspace/Users/<you>/.bundle/c1-medallion-pipeline/dev/files/data/products.csv
/Workspace/Users/<you>/.bundle/c1-medallion-pipeline/dev/files/data/orders.csv
```

If those files are missing, upload the three CSVs in the Workspace UI into that `data/` folder. Do not use DBFS FileStore.

S3 is allowed by the brief; this project uses **Workspace files** so the workspace can run without cloud credentials and without public DBFS.

## 5. Create schemas

```sql
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;
```

Tables can come from `database/schema.sql` or from `saveAsTable` on first run (`overwriteSchema` is enabled). Assessment writes should be **Delta**.

## 6. Run the pipeline

### Manual notebooks (sanity test, no Jobs)

Run these four notebooks **one at a time** on an attached cluster. Do not use Jobs.

1. On your laptop, from `C1-Assessment/`:
   ```bash
   python src/data_generation/generate_sample_data.py
   ```
   Keep `data/customers.csv`, `data/products.csv`, `data/orders.csv`.
2. **Workspace → Import** the whole `C1-Assessment` folder (must include `src/` and `data/`).
3. **Compute → Create cluster** → wait until it is running.
4. Attach that cluster and **Run All** on each notebook in order:
   - `src/notebooks/01_copy_landing.py`
   - `src/notebooks/02_bronze.py` → expect 10,010 / 505 / 100,020
   - `src/notebooks/03_silver.py` → same counts (nothing deleted)
   - `src/notebooks/04_gold.py` → four Gold tables + four segment types

If the repo is not at `/Workspace/Users/<your-email>/C1-Assessment`, set the `repo_root` widget on the first notebook (it is reused after that).

Do **not** Run `generate_sample_data.py` or the `src/bronze|silver|gold/*.py` files directly. Use the four notebooks above.

If `data/` is missing in the Workspace folder, upload the three CSVs next to the bundled `src/` directory (`.../files/data/`). Do not use `/FileStore`.

### Preferred when Jobs exist: Asset Bundle job

```bash
export DATABRICKS_CONFIG_PROFILE=c1-assessment
databricks bundle deploy -t dev
# After CSVs are in the bundle files/data folder:
databricks bundle run medallion_pipeline -t dev
```

Task order: `src/bronze/ingest_all.py` → `src/silver/create_silver_tables.py` → `src/gold/create_gold_tables.py`.  
Bronze is passed `--landing-dir ${var.landing_dir}`.

### Notebook fallback (if Jobs API is unavailable)

Attach **serverless** (Connect → Serverless). Put the repo on `sys.path` and run in order:

```python
import sys
base = "/Workspace/Users/<your-email>/C1-Assessment/src"
sys.path.extend([f"{base}/bronze", f"{base}/silver", f"{base}/gold"])

from ingest_all import run_bronze
from create_silver_tables import run_silver
from create_gold_tables import run_gold

run_bronze(landing_dir="/Workspace/Users/<your-email>/.bundle/c1-medallion-pipeline/dev/files/data")
run_silver()
run_gold()
```

Ingest order inside Bronze is **products → customers → orders**. Bronze does not join; this only guarantees parents exist before Silver.

## 7. Local run

CSVs and **tests do not need PySpark**. Bronze/Silver/Gold *Spark* ingest locally does.

```bash
# Logic tests (landing CSVs stand in for Bronze)
python -m unittest tests.test_pipeline_requirements -v
python -m unittest discover -s tests -p 'test_*.py'

# Optional: same engines without Spark writes
python src/silver/create_silver_tables.py --from-landing
python src/gold/create_gold_tables.py --from-landing

# Optional Spark ingest if pyspark is installed:
export BRONZE_LANDING_DIR="$(pwd)/data"
python src/bronze/ingest_all.py --landing-dir data
```

Local write format is Delta when `delta-spark` is present, otherwise Parquet under Spark’s warehouse. Submit on Databricks as Delta.

## 8. Verify

```sql
-- Bronze still dirty
SELECT COUNT(*) FROM bronze.customers;   -- 10010
SELECT COUNT(*) FROM bronze.products;    -- 505
SELECT COUNT(*) FROM bronze.orders;      -- 100020
SELECT COUNT(*) FROM bronze.customers WHERE email IS NULL;        -- 50
SELECT COUNT(*) FROM bronze.orders WHERE customer_id IS NULL;     -- 100

-- Silver kept every row
SELECT COUNT(*) FROM silver.customers;   -- 10010
SELECT COUNT(*) FROM silver.orders;      -- 100020
SELECT quality_check_result, COUNT(*) FROM silver.orders GROUP BY 1;

SELECT table_name, check_name, rows_failed, pass_percentage, threshold_met
FROM silver.quality_metrics
ORDER BY table_name, check_name;

-- Gold
SELECT COUNT(*) FROM gold.sales_by_product;
SELECT COUNT(*) FROM gold.revenue_by_customer;
SELECT segment_type, customer_count, total_revenue FROM gold.customer_segmentation;
```

Dashboard: paste queries from `src/dashboard/dashboard_queries.sql` into SQL Editor (see `DASHBOARD_GUIDE.md`). Warehouse: Free Edition starter / 2X-Small.

## Input validation vs quality checks

Bronze **does** fail if the landing file is missing (local path), the header is wrong, or Spark cannot read the path.

Bronze **does not** fail if emails are NULL, IDs are duplicated, FKs are orphans, amounts do not match, or dates are in the future. Silver flags those. Gold omits FAIL and non-Completed orders from facts.
