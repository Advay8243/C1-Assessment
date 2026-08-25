-- Gold: sales by product
-- Grain: one row per product_id that has at least one qualifying order.
--
-- Qualifying order:
--   silver.orders.quality_check_result = 'PASS'
--   silver.orders.order_status = 'Completed'
--   customer and product also PASS (inner join)
--
-- Dimension tables are de-duplicated on the business key before the join so a
-- leftover Silver duplicate cannot fan out and double-count revenue.
-- avg_order_value is derived from total_revenue / total_orders (not a second AVG).

WITH pass_products AS (
  SELECT
    product_id,
    product_name,
    category
  FROM (
    SELECT
      product_id,
      product_name,
      category,
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
    o.product_id,
    o.quantity,
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
    product_id,
    quantity,
    total_amount
  FROM (
    SELECT
      order_id,
      product_id,
      quantity,
      total_amount,
      ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY order_id) AS _rn
    FROM qualifying_orders
  ) ranked
  WHERE _rn = 1
),
aggregated AS (
  SELECT
    p.product_id,
    p.product_name,
    p.category,
    COUNT(*) AS total_orders,
    CAST(SUM(o.total_amount) AS DECIMAL(18, 2)) AS total_revenue
  FROM deduped_orders o
  INNER JOIN pass_products p
    ON o.product_id = p.product_id
  GROUP BY
    p.product_id,
    p.product_name,
    p.category
)
SELECT
  product_id,
  product_name,
  category,
  total_orders,
  total_revenue,
  CAST(total_revenue / total_orders AS DECIMAL(18, 2)) AS avg_order_value
FROM aggregated
