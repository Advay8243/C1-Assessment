-- Gold: customer segmentation (brief table C)
-- Grain: one row per segment_type (always four rows).
-- Built from gold.revenue_by_customer so revenue is not recalculated.
--
-- segment_type (brief): High-Value / Repeat / One-Time / Inactive
--   Inactive  : total_orders = 0
--   One-Time  : total_orders = 1
--   High-Value: total_orders >= 2 AND total_revenue >= 1000
--   Repeat    : total_orders >= 2 AND total_revenue < 1000
-- High-Value is applied before Repeat so the buckets cannot overlap.
-- avg_revenue = total_revenue / customer_count (0 when the bucket is empty).

WITH classified AS (
  SELECT
    customer_id,
    total_revenue,
    CASE
      WHEN total_orders = 0 THEN 'Inactive'
      WHEN total_orders = 1 THEN 'One-Time'
      WHEN total_orders >= 2 AND total_revenue >= 1000 THEN 'High-Value'
      ELSE 'Repeat'
    END AS segment_type
  FROM gold.revenue_by_customer
),
segment_list AS (
  SELECT 'High-Value' AS segment_type, 1 AS sort_order
  UNION ALL
  SELECT 'Repeat', 2
  UNION ALL
  SELECT 'One-Time', 3
  UNION ALL
  SELECT 'Inactive', 4
),
aggregated AS (
  SELECT
    s.segment_type,
    s.sort_order,
    COUNT(c.customer_id) AS customer_count,
    CAST(COALESCE(SUM(c.total_revenue), 0) AS DECIMAL(18, 2)) AS total_revenue
  FROM segment_list s
  LEFT JOIN classified c
    ON s.segment_type = c.segment_type
  GROUP BY
    s.segment_type,
    s.sort_order
)
SELECT
  segment_type,
  customer_count,
  CAST(
    CASE
      WHEN customer_count = 0 THEN 0
      ELSE total_revenue / customer_count
    END AS DECIMAL(18, 2)
  ) AS avg_revenue,
  total_revenue
FROM aggregated
ORDER BY sort_order
