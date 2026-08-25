-- Bronze / Silver / Gold DDL for the e-commerce medallion pipeline.
-- Bronze is implemented now. Silver and Gold tables are added with those layers.
--
-- Run on Databricks:
--   %sql
--   -- paste this file, or:
--   -- spark.sql(open("database/schema.sql").read()) is not valid for multi-statement
--   -- unless split. Prefer running CREATE SCHEMA then letting ingest saveAsTable
--   -- create tables, or execute statements from database/setup-notes.md.

CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

-- ---------------------------------------------------------------------------
-- Bronze: raw landing. All business columns are nullable. Duplicate keys allowed.
-- Quality issues from the CSVs must survive ingest unchanged.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS bronze.customers (
  customer_id INT,
  customer_name STRING,
  email STRING,
  country STRING,
  signup_date DATE,
  customer_segment STRING,
  lifetime_value DECIMAL(18, 2),
  _source_file STRING,
  _ingest_timestamp TIMESTAMP,
  _batch_id STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS bronze.products (
  product_id INT,
  product_name STRING,
  category STRING,
  price DECIMAL(18, 2),
  cost DECIMAL(18, 2),
  stock_quantity INT,
  reorder_level INT,
  _source_file STRING,
  _ingest_timestamp TIMESTAMP,
  _batch_id STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS bronze.orders (
  order_id INT,
  customer_id INT,
  order_date DATE,
  product_id INT,
  quantity INT,
  unit_price DECIMAL(18, 2),
  total_amount DECIMAL(18, 2),
  order_status STRING,
  payment_date DATE,
  _source_file STRING,
  _ingest_timestamp TIMESTAMP,
  _batch_id STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS bronze.ingestion_log (
  table_name STRING,
  source_path STRING,
  row_count INT,
  expected_row_count INT,
  ingest_timestamp TIMESTAMP,
  batch_id STRING,
  status STRING,
  error_message STRING,
  write_format STRING
) USING DELTA;

-- ---------------------------------------------------------------------------
-- Silver: Bronze rows plus quality flags. Duplicate keys and NULLs are kept.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS silver.customers (
  customer_id INT,
  customer_name STRING,
  email STRING,
  country STRING,
  signup_date DATE,
  customer_segment STRING,
  lifetime_value DECIMAL(18, 2),
  _source_file STRING,
  _ingest_timestamp TIMESTAMP,
  _batch_id STRING,
  completeness_flag STRING,
  uniqueness_flag STRING,
  type_validation_flag STRING,
  referential_integrity_flag STRING,
  business_logic_flag STRING,
  quality_check_result STRING,
  failure_reasons STRING,
  _silver_processed_at TIMESTAMP,
  _silver_batch_id STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS silver.products (
  product_id INT,
  product_name STRING,
  category STRING,
  price DECIMAL(18, 2),
  cost DECIMAL(18, 2),
  stock_quantity INT,
  reorder_level INT,
  _source_file STRING,
  _ingest_timestamp TIMESTAMP,
  _batch_id STRING,
  completeness_flag STRING,
  uniqueness_flag STRING,
  type_validation_flag STRING,
  referential_integrity_flag STRING,
  business_logic_flag STRING,
  quality_check_result STRING,
  failure_reasons STRING,
  _silver_processed_at TIMESTAMP,
  _silver_batch_id STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS silver.orders (
  order_id INT,
  customer_id INT,
  order_date DATE,
  product_id INT,
  quantity INT,
  unit_price DECIMAL(18, 2),
  total_amount DECIMAL(18, 2),
  order_status STRING,
  payment_date DATE,
  _source_file STRING,
  _ingest_timestamp TIMESTAMP,
  _batch_id STRING,
  completeness_flag STRING,
  uniqueness_flag STRING,
  type_validation_flag STRING,
  referential_integrity_flag STRING,
  business_logic_flag STRING,
  quality_check_result STRING,
  failure_reasons STRING,
  _silver_processed_at TIMESTAMP,
  _silver_batch_id STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS silver.quality_metrics (
  table_name STRING,
  check_name STRING,
  rows_evaluated INT,
  rows_passed INT,
  rows_failed INT,
  pass_percentage DECIMAL(8, 4),
  threshold DECIMAL(5, 1),
  threshold_met BOOLEAN,
  batch_id STRING,
  processed_at TIMESTAMP
) USING DELTA;

-- Gold: business aggregations. Facts come from Silver PASS + Completed orders.

CREATE TABLE IF NOT EXISTS gold.sales_by_product (
  product_id INT,
  product_name STRING,
  category STRING,
  total_orders BIGINT,
  total_revenue DECIMAL(18, 2),
  avg_order_value DECIMAL(18, 2),
  _gold_processed_at TIMESTAMP,
  _gold_batch_id STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS gold.quality_metrics (
  table_name STRING,
  check_name STRING,
  status STRING,
  rows_evaluated INT,
  rows_failed INT,
  detail STRING,
  batch_id STRING,
  processed_at TIMESTAMP
) USING DELTA;

CREATE TABLE IF NOT EXISTS gold.revenue_by_customer (
  customer_id INT,
  customer_name STRING,
  customer_segment STRING,
  total_orders BIGINT,
  total_revenue DECIMAL(18, 2),
  avg_order_value DECIMAL(18, 2),
  lifetime_value_actual DECIMAL(18, 2),
  _gold_processed_at TIMESTAMP,
  _gold_batch_id STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS gold.daily_weekly_trends (
  order_date DATE,
  order_year INT,
  order_week INT,
  total_orders BIGINT,
  total_revenue DECIMAL(18, 2),
  avg_order_value DECIMAL(18, 2),
  unique_customers BIGINT,
  _gold_processed_at TIMESTAMP,
  _gold_batch_id STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS gold.customer_segmentation (
  segment_type STRING,
  customer_count BIGINT,
  avg_revenue DECIMAL(18, 2),
  total_revenue DECIMAL(18, 2),
  _gold_processed_at TIMESTAMP,
  _gold_batch_id STRING
) USING DELTA;

-- Do not load landing CSVs directly into silver or gold.
