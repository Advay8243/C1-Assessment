-- Gold: daily / weekly trends (repo structure table; supports dashboard time series)
-- Grain: one row per order_date from qualifying orders.
-- order_year / order_week are attributes so weekly charts can GROUP BY them.
-- Weekly totals are not stored a second time (avoids two revenue figures that can drift).
-- avg_order_value = total_revenue / total_orders.

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
  SELECT customer_id
  FROM (
    SELECT
      customer_id,
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
    o.order_date,
    o.total_amount
  FROM silver.orders o
  INNER JOIN pass_customers c
    ON o.customer_id = c.customer_id
  INNER JOIN pass_products p
    ON o.product_id = p.product_id
  WHERE o.quality_check_result = 'PASS'
    AND o.order_status = 'Completed'
    AND o.order_id IS NOT NULL
    AND o.order_date IS NOT NULL
),
deduped_orders AS (
  SELECT
    order_id,
    customer_id,
    order_date,
    total_amount
  FROM (
    SELECT
      order_id,
      customer_id,
      order_date,
      total_amount,
      ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY order_id) AS _rn
    FROM qualifying_orders
  ) ranked
  WHERE _rn = 1
),
aggregated AS (
  SELECT
    order_date,
    YEAR(order_date) AS order_year,
    WEEKOFYEAR(order_date) AS order_week,
    COUNT(*) AS total_orders,
    CAST(SUM(total_amount) AS DECIMAL(18, 2)) AS total_revenue,
    COUNT(DISTINCT customer_id) AS unique_customers
  FROM deduped_orders
  GROUP BY
    order_date,
    YEAR(order_date),
    WEEKOFYEAR(order_date)
)
SELECT
  order_date,
  order_year,
  order_week,
  total_orders,
  total_revenue,
  CAST(total_revenue / total_orders AS DECIMAL(18, 2)) AS avg_order_value,
  unique_customers
FROM aggregated
