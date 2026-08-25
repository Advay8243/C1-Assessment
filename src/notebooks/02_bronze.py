# Databricks notebook source
# MAGIC %md
# MAGIC # 2 / 4 — Bronze
# MAGIC
# MAGIC Manual sanity test. Attach a cluster, run `01_copy_landing` first, then **Run All** here.
# MAGIC Reads CSVs from Workspace `data/` (not DBFS FileStore).
# MAGIC Expect 10,010 / 505 / 100,020 rows. Next: `03_silver`.

# COMMAND ----------

# MAGIC %run ./_setup

# COMMAND ----------

from ingest_all import run_bronze

run_bronze(spark, landing_dir=LANDING_DIR)

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT 'customers' AS table_name, COUNT(*) AS row_count FROM bronze.customers
# MAGIC UNION ALL
# MAGIC SELECT 'products', COUNT(*) FROM bronze.products
# MAGIC UNION ALL
# MAGIC SELECT 'orders', COUNT(*) FROM bronze.orders;
