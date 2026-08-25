# Dashboard Guide — Databricks SQL

Build a Databricks SQL dashboard from Gold tables. Queries live in
`src/dashboard/dashboard_queries.sql`. Do not point tiles at Bronze or Silver
and do not re-code Gold aggregations in the SQL editor.

## What you should see

| Tile | Databricks viz type | Gold table | Fields |
|---|---|---|---|
| Top 10 products by revenue | **Bar** | `gold.sales_by_product` | X = `product_label`, Y = `total_revenue` |
| Customer revenue distribution | **Histogram** | `gold.revenue_by_customer` | Values = `total_revenue` |
| Customer segmentation | **Pie** | `gold.customer_segmentation` | Label = `segment_type`, Angle = `customer_count` |
| Daily revenue (4th tile) | **Line** | `gold.daily_weekly_trends` | X = `order_date`, Y = `total_revenue` |

Gold already applied PASS + Completed + de-duplication. Dashboard SQL only
filters, sorts, and limits.

## Prerequisites

1. Bronze → Silver → Gold have been run (`create_gold_tables.run_gold()`).
2. A SQL warehouse is running (Community Edition: the starter warehouse).
3. You can `SELECT` from `gold.sales_by_product`, `gold.revenue_by_customer`,
   `gold.customer_segmentation`, and `gold.daily_weekly_trends`.

## Create the four queries

For each block in `dashboard_queries.sql` (Query 1 through Query 4):

1. Open **SQL Editor** → **Create** → **Query**.
2. Paste **one** query only (from its `QUERY n` header through the semicolon).
3. Name it exactly:
   - `Top 10 products by revenue`
   - `Customer revenue distribution`
   - `Customer segmentation`
   - `Daily revenue`
4. **Run**. You should get rows (Top 10 = 10 rows; Segmentation = 4 rows).
5. Click **+** / **Visualization** and set the type in the table above.
6. Save the query.

### Visualization settings (Databricks SQL)

**Bar (Top 10)**  
- Type: Bar  
- X: `product_label` (id + name; unique so duplicate product names do not merge)  
- Y: `total_revenue`  
- Leave the query `ORDER BY total_revenue DESC` — do not switch the viz to
  A–Z on the name axis (that would hide the ranking).  
- If labels clip, set orientation to horizontal.

**Histogram (Customer revenue)**  
- Type: Histogram  
- Column: `total_revenue`  
- Bins: 20  
- The query returns one numeric column per customer with revenue. Databricks
  bins it. Do not `GROUP BY` in SQL for this tile.  
- If Community Edition has no Histogram type, use Bar on a **temporary** binned
  query (see fallback below). Do not keep both Histogram and binned-bar tiles.

**Pie (Segmentation)**  
- Type: Pie  
- Label / Group by: `segment_type`  
- Value: `customer_count`  
- Do not set value to `total_revenue` (that would be a second segmentation
  chart of the same four slices).

**Line (Daily revenue)**  
- Type: Line  
- X: `order_date`  
- Y: `total_revenue`  
- Missing dates are days with no qualifying orders; do not fill zeros in SQL.

## Create the dashboard

1. **Dashboards** → **Create dashboard** (SQL dashboard).  
2. Name it `E-commerce Gold — Sales overview`.  
3. **Add** → each saved query visualization as a tile.  
4. Layout: Top 10 bar and pie on the first row; histogram full width; line chart
   full width at the bottom.

## Filters (optional, dashboard level)

Add filters that map to columns already on the query result — do not add new
joins.

| Filter | Applies to | Column |
|---|---|---|
| Category | Top 10 products | `category` |
| Date range | Daily revenue | `order_date` |
| Customer segment (Premium / Standard / Basic) | Histogram only if you add `customer_segment` to Query 2 | `customer_segment` |

Query 2 as shipped returns only `total_revenue` (what Histogram needs). To
filter by source segment, add `customer_segment` to that SELECT, then attach a
dashboard dropdown. Still do not re-aggregate.

Date filters **do not** apply to Top 10, histogram, or pie: those Gold tables
are all-time snapshots. Date belongs on the daily line tile.

## Fallback if Histogram is missing

Use this **instead of** Query 2, not in addition to it:

```sql
SELECT
  CASE
    WHEN total_revenue < 250 THEN '0–250'
    WHEN total_revenue < 500 THEN '250–500'
    WHEN total_revenue < 1000 THEN '500–1,000'
    WHEN total_revenue < 2500 THEN '1,000–2,500'
    WHEN total_revenue < 5000 THEN '2,500–5,000'
    ELSE '5,000+'
  END AS revenue_band,
  COUNT(*) AS customer_count
FROM gold.revenue_by_customer
WHERE total_revenue > 0
GROUP BY 1;
```

Visualization: Bar, X = `revenue_band`, Y = `customer_count`.  
This is display binning only. Gold customer revenue is unchanged.

## What not to do

- Do not `SELECT` from `silver.*` or `bronze.*` for these tiles.
- Do not `SUM(total_amount)` from orders to “rebuild” Top 10 or segmentation.
- Do not plot `lifetime_value_actual` and `total_revenue` as two histograms.
- Do not add a weekly-revenue tile that re-sums `gold.daily_weekly_trends`
  while the daily line is already on the dashboard.
- Do not add a second pie using `total_revenue` for the same four segments.

## Sanity checks after the tiles load

- Top 10: exactly 10 bars, descending revenue.
- Histogram: spread of customer revenue, not a single bar of order count.
- Pie: four slices — High-Value, Repeat, One-Time, Inactive.
- Line: dates match `gold.daily_weekly_trends` (about 2,300 days on this sample).
