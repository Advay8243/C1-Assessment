# Databricks notebook source
# MAGIC %md
# MAGIC # 4 / 4 — Gold
# MAGIC
# MAGIC Manual sanity test. Attach a cluster, run Silver first, then **Run All** here.

# COMMAND ----------

# MAGIC %run ./_setup

# COMMAND ----------

from create_gold_tables import run_gold

run_gold(spark)

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT 'sales_by_product' AS table_name, COUNT(*) AS row_count FROM gold.sales_by_product
# MAGIC UNION ALL
# MAGIC SELECT 'revenue_by_customer', COUNT(*) FROM gold.revenue_by_customer
# MAGIC UNION ALL
# MAGIC SELECT 'daily_weekly_trends', COUNT(*) FROM gold.daily_weekly_trends
# MAGIC UNION ALL
# MAGIC SELECT 'customer_segmentation', COUNT(*) FROM gold.customer_segmentation;
# MAGIC
# MAGIC SELECT segment_type, customer_count, total_revenue
# MAGIC FROM gold.customer_segmentation
# MAGIC ORDER BY segment_type;
