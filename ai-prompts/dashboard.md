# AI Prompts — Dashboard

## Prompt 1: Dashboard Queries (3+ Tiles)

**PROMPT SENT:**
"The gold looks good and validated now lets the start the dashboards and start writing the dashboard queries using the gold tables
I need 3+ tiles visualization
1. Top 10 products by revenue
2. Customer revenue distribution
3. Customer segmentation

for each visualization make sure none is repated after the business logic and make them according to databricks SQL visualization types"

**AI RESPONSE SUMMARY:**
Cursor wrote `src/dashboard/dashboard_queries.sql` and `DASHBOARD_GUIDE.md`. Tiles: Bar (top 10), Histogram (customer revenue), Pie (segmentation), plus a fourth Line on `gold.daily_weekly_trends`. Queries select from Gold only. Bar X-axis is `product_id — product_name`. Tests in `tests/test_dashboard_queries.py`.

**YOUR EVALUATION:**

✓ **What you accepted (and why):**
- Three required visualizations plus one extra (brief asks 3+)
- Databricks viz types documented in SQL comments and the guide
- Gold-only SQL so tiles cannot fork Silver business rules

✗ **What you changed (and why):**
- Histogram `WHERE total_revenue > 0` so Inactive zeros are not a spike at 0 (those customers still appear on the pie)
- `product_label` so two products with the same name do not merge into one bar

△ **What you rejected (and why):**
- `SUM(total_amount)` from orders in dashboard SQL
- Rebuilding High-Value / Repeat with CASE on `revenue_by_customer`
- A second pie using `total_revenue` for the same four slices
- A weekly-revenue tile that re-sums the daily line

**FINAL DECISION:** Use `dashboard_queries.sql` + `DASHBOARD_GUIDE.md`. The bundle does not publish a dashboard object.
