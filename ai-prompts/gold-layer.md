# AI Prompts — Gold Layer

## Prompt 1: Sales by Product

**PROMPT SENT:**
"Silver is validated and looks good

Start builiding the gold layer now first start with the gold layer of sales by product
using the business requirements create in the document create the gold layer from the silver tables also maintain data quality at the gold layer like accidental duplication or no reduntant calculations and other checks also include them after completion
perform checks on the tables created on gold"

**AI RESPONSE SUMMARY:**
Cursor built `gold.sales_by_product` from Silver PASS + Completed orders, inner-joined to PASS customers and PASS products. Keys de-duplicated before the join. `avg_order_value = total_revenue / total_orders`. Post-build checks in `validate_gold.py` and `tests/test_gold_sales_by_product.py`.

**YOUR EVALUATION:**

✓ **What you accepted (and why):**
- Completed + PASS only — Pending/Cancelled and FAIL rows must not inflate revenue
- Inner join so FAIL / unsold products do not appear
- Post-build grain uniqueness and reconcile-to-Silver checks

✗ **What you changed (and why):**
- `ROW_NUMBER` / first-seen de-dupe on keys so a leftover Silver duplicate cannot fan out revenue

△ **What you rejected (and why):**
- A second independent `AVG()` — it can disagree with `SUM/COUNT` stored on the same row

**FINAL DECISION:** Keep this fact filter for every later Gold table. Do not change sales-by-product in the next prompt.

---

## Prompt 2: Revenue by Customer, Daily/Weekly Trends, Customer Segmentation

**PROMPT SENT:**
"No start building  and validate Revenue by Customer, Customer Segmentation and daily weekly trends work according to the business logic and make sure that there is no changes in them and the entire development is based on the provided document and also perform validations on the gold tables you perform"

**AI RESPONSE SUMMARY:**
Cursor added `gold.revenue_by_customer` (every PASS customer, including zeros), `gold.daily_weekly_trends` (one row per order_date, year/week as attributes), and `gold.customer_segmentation` from the revenue table (High-Value / Repeat / One-Time / Inactive). Matching `.sql` files and tests. `sales_by_product` was not modified.

**YOUR EVALUATION:**

✓ **What you accepted (and why):**
- `lifetime_value_actual` = computed `total_revenue`, not the CSV `lifetime_value` placeholder
- High-Value = ≥2 orders and revenue ≥ 1000, evaluated before Repeat so types cannot overlap
- Segmentation built from Gold revenue so the pie cannot drift from the customer table
- “No changes in them” = leave sales-by-product as already built

✗ **What you changed (and why):**
- Daily grain only for trends — a stored weekly total would be a second revenue figure that can disagree with the daily rows

△ **What you rejected (and why):**
- Rewriting sales-by-product
- Re-summing Silver inside the segmentation SQL

**FINAL DECISION:** Four Gold tables. Dashboard reads these only.
