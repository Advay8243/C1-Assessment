-- Databricks SQL dashboard queries
-- Source: Gold tables only. Do not re-aggregate Silver/Bronze — that would
-- repeat (and could disagree with) Gold business logic.
--
-- Required tiles (brief):
--   1. Top 10 products by revenue     -> Bar
--   2. Customer revenue distribution  -> Histogram
--   3. Customer segmentation          -> Pie
-- Extra tile (3+):
--   4. Daily revenue                  -> Line  (gold.daily_weekly_trends)
--
-- How to use: SQL editor -> New query -> paste one block -> Run ->
-- Visualization -> type listed in the header -> Add to dashboard.
-- Widget/filter steps: src/dashboard/DASHBOARD_GUIDE.md

-- =============================================================================
-- QUERY 1 — Top 10 products by revenue
-- Databricks visualization: Bar
--   X axis: product_label  (id + name so two products with the same name
--            do not merge into one bar)
--   Y axis: total_revenue
--   Group by: none (already one row per product in Gold)
--   Sort: use query order (total_revenue DESC) — do not re-sort in the viz
--   Orientation: horizontal bar if names overflow
-- Optional dashboard filter: category (same column name)
-- =============================================================================
SELECT
  CONCAT(CAST(product_id AS STRING), ' — ', product_name) AS product_label,
  product_id,
  product_name,
  category,
  total_revenue,
  total_orders,
  avg_order_value
FROM gold.sales_by_product
ORDER BY total_revenue DESC
LIMIT 10;


-- =============================================================================
-- QUERY 2 — Customer revenue distribution
-- Databricks visualization: Histogram
--   Column (Values): total_revenue
--   Number of bins: 20 (adjust in viz settings)
--   X axis title: Customer revenue
--   Y axis title: Customers
--
-- Gold already stores one revenue figure per PASS customer.
-- Histogram bins that column — it does not SUM again.
-- lifetime_value_actual is the same number as total_revenue on Gold; do not
-- plot both (that would duplicate the same distribution).
-- total_revenue > 0 drops Inactive zeros so the chart is not a spike at 0.
-- =============================================================================
SELECT
  total_revenue
FROM gold.revenue_by_customer
WHERE total_revenue > 0;


-- =============================================================================
-- QUERY 3 — Customer segmentation
-- Databricks visualization: Pie
--   Label (Values / Group by): segment_type
--   Angle (Y / Values): customer_count
--
-- Reads gold.customer_segmentation (four brief types). Do not rebuild
-- High-Value / Repeat / One-Time / Inactive with CASE on revenue_by_customer —
-- that would repeat Gold segment logic and can drift.
-- Use customer_count (headcount mix), not total_revenue, on this pie.
-- A revenue-mix pie of the same four slices would duplicate this tile.
-- =============================================================================
SELECT
  segment_type,
  customer_count,
  total_revenue,
  avg_revenue
FROM gold.customer_segmentation
ORDER BY
  CASE segment_type
    WHEN 'High-Value' THEN 1
    WHEN 'Repeat' THEN 2
    WHEN 'One-Time' THEN 3
    WHEN 'Inactive' THEN 4
    ELSE 5
  END;


-- =============================================================================
-- QUERY 4 — Daily revenue (extra tile, not a repeat of 1–3)
-- Databricks visualization: Line
--   X axis: order_date
--   Y axis: total_revenue
-- Optional dashboard date-range filter on order_date
--
-- Daily grain already exists in Gold. Do not add a second weekly-revenue tile
-- that re-sums the same days (weekly = GROUP BY order_year, order_week in the
-- viz if needed, not a separate query).
-- =============================================================================
SELECT
  order_date,
  order_year,
  order_week,
  total_revenue,
  total_orders,
  unique_customers,
  avg_order_value
FROM gold.daily_weekly_trends
ORDER BY order_date;
