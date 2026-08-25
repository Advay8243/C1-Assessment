-- Gold: revenue by customer (brief table B)
-- Grain: one row per PASS customer_id, including customers with zero qualifying orders
-- (required so Customer Segmentation can form Inactive).
--
-- Qualifying order: Silver PASS + Completed, customer PASS, product PASS.
-- avg_order_value = total_revenue / total_orders (0 when there are no orders).
-- lifetime_value_actual is the same total_revenue figure, not the source lifetime_value column.

WITH pass_products AS (
  SELECT product_id
  FROM (
    SELECT
      product_id,
      ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY product_id) AS _rn
    FROM silver.products
    WHERE quality_check_result = 'PASS'
      AND product_id IS NOT NULL
  ) ranked
  WHERE _rn = 1
),
pass_customers AS (
  SELECT
    customer_id,
    customer_name,
    customer_segment
  FROM (
    SELECT
      customer_id,
      customer_name,
      customer_segment,
      ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY customer_id) AS _rn
    FROM silver.customers
    WHERE quality_check_result = 'PASS'
      AND customer_id IS NOT NULL
  ) ranked
  WHERE _rn = 1
),
qualifying_orders AS (
  SELECT
    o.order_id,
    o.customer_id,
    o.total_amount
  FROM silver.orders o
  INNER JOIN pass_customers c
    ON o.customer_id = c.customer_id
  INNER JOIN pass_products p
    ON o.product_id = p.product_id
  WHERE o.quality_check_result = 'PASS'
    AND o.order_status = 'Completed'
    AND o.order_id IS NOT NULL
),
deduped_orders AS (
  SELECT
    order_id,
    customer_id,
    total_amount
  FROM (
    SELECT
      order_id,
      customer_id,
      total_amount,
      ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY order_id) AS _rn
    FROM qualifying_orders
  ) ranked
  WHERE _rn = 1
),
order_totals AS (
  SELECT
    customer_id,
    COUNT(*) AS total_orders,
    CAST(SUM(total_amount) AS DECIMAL(18, 2)) AS total_revenue
  FROM deduped_orders
  GROUP BY customer_id
),
combined AS (
  SELECT
    c.customer_id,
    c.customer_name,
    c.customer_segment,
    CAST(COALESCE(o.total_orders, 0) AS BIGINT) AS total_orders,
    CAST(COALESCE(o.total_revenue, 0) AS DECIMAL(18, 2)) AS total_revenue
  FROM pass_customers c
  LEFT JOIN order_totals o
    ON c.customer_id = o.customer_id
)
SELECT
  customer_id,
  customer_name,
  customer_segment,
  total_orders,
  total_revenue,
  CAST(
    CASE
      WHEN total_orders = 0 THEN 0
      ELSE total_revenue / total_orders
    END AS DECIMAL(18, 2)
  ) AS avg_order_value,
  total_revenue AS lifetime_value_actual
FROM combined
