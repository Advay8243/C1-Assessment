# Databricks notebook source
# MAGIC %md
# MAGIC # 3 / 4 — Silver
# MAGIC
# MAGIC Manual sanity test. Attach a cluster, run Bronze first, then **Run All** here.
# MAGIC Row counts must match Bronze (nothing deleted). Next: `04_gold`.

# COMMAND ----------

# MAGIC %run ./_setup

# COMMAND ----------

from create_silver_tables import run_silver

run_silver(spark)

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT 'customers' AS table_name, COUNT(*) AS row_count FROM silver.customers
# MAGIC UNION ALL
# MAGIC SELECT 'products', COUNT(*) FROM silver.products
# MAGIC UNION ALL
# MAGIC SELECT 'orders', COUNT(*) FROM silver.orders;
# MAGIC
# MAGIC SELECT table_name, check_name, rows_failed, pass_percentage, threshold_met
# MAGIC FROM silver.quality_metrics
# MAGIC ORDER BY table_name, check_name;
