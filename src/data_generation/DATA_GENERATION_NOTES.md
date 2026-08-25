# Data Generation Notes

This document describes how the three landing CSVs are produced, why quality issues exist, and how to regenerate them.

## Purpose

The generator creates **realistic e-commerce data with planted defects**. Bronze must ingest every row unchanged. Silver must detect the defects. Gold must ignore failed rows.

Script: `src/data_generation/generate_sample_data.py`  
Outputs: `data/customers.csv`, `data/products.csv`, `data/orders.csv`  
Dependencies: Python 3.9+ standard library only (no Faker, pandas, or Spark).  
Reproducibility: `random.Random(seed=42)` and **fixed ID ranges** for every injected issue.

## How to regenerate

From the repository root:

```bash
python src/data_generation/generate_sample_data.py
```

Optional:

```bash
python src/data_generation/generate_sample_data.py --output-dir data --seed 42
```

The script recounts every planted issue before writing files and **exits with an error** if a count does not match the contract below.

## Volumes

| File | Unique IDs (brief) | Physical rows | Extra rows | Approx. size |
|---|---|---|---|---|
| `customers.csv` | 10,000 | 10,010 | 10 duplicate `customer_id` | ~500 KB |
| `products.csv` | 500 | 505 | 5 duplicate `product_id` | ~50 KB |
| `orders.csv` | 100,000 | 100,020 | 20 duplicate `order_id` | ~2–3 MB |

Unique ID ranges:

- Customers: `1`–`10000`
- Products: `1`–`500`
- Orders: `1`–`100000`

Customers `9700`–`10000` (301 people) receive **no orders** so Gold can form an Inactive segment.

## Schemas

NULL is stored as an **empty CSV field**.

### customers.csv

| Column | Type | Notes |
|---|---|---|
| `customer_id` | INT | PK |
| `customer_name` | STRING | First + last name |
| `email` | STRING | `{first}.{last}{id}@shopmail.com` when valid |
| `country` | STRING | Weighted toward Australia |
| `signup_date` | DATE | `2020-01-01` to `2026-08-14` except planted future dates |
| `customer_segment` | STRING | Premium (`1`–`1500`), Standard (`1501`–`7000`), Basic (`7001`–`10000`) unless overwritten |
| `lifetime_value` | DECIMAL | Placeholder source LTV; Gold computes `lifetime_value_actual` from orders |

### products.csv

| Column | Type | Notes |
|---|---|---|
| `product_id` | INT | PK |
| `product_name` | STRING | `{brand} {item}` |
| `category` | STRING | Electronics, Clothing, Home, Sports, Beauty, Books, Toys, Grocery |
| `price` | DECIMAL | Selling price |
| `cost` | DECIMAL | Below price except planted cost>price rows |
| `stock_quantity` | INT | Positive except planted negatives |
| `reorder_level` | INT | At most stock on clean rows |

### orders.csv

| Column | Type | Notes |
|---|---|---|
| `order_id` | INT | PK |
| `customer_id` | INT | FK → customers (except NULL / orphan rows) |
| `order_date` | DATE | On or after the customer's signup, through `2026-08-14` |
| `product_id` | INT | FK → products (except NULL / orphan rows) |
| `quantity` | INT | 1–6 (Premium up to 8) |
| `unit_price` | DECIMAL | Copied from product `price` on clean rows |
| `total_amount` | DECIMAL | `quantity * unit_price` on clean rows |
| `order_status` | STRING | Completed / Pending / Cancelled (~80 / 12 / 8) |
| `payment_date` | DATE, nullable | Set for Completed; empty for Pending/Cancelled, except planted mismatches |

## Why quality issues exist

They are **not** accidental. Each one maps to a Silver check so tests can assert exact counts.

Empty email, duplicate keys, null FKs, and orphan FKs are required by the assessment brief (~700 problematic order/customer rows, about 0.7% of order volume). Extra issues were added so **products** also have defects (requested) and so type-validation and business-logic checks have known rows to catch.

## Issue catalog — customers.csv

| Issue | Silver check | Count | How it is planted |
|---|---|---|---|
| NULL `email` | Completeness | 50 | `customer_id` **1–50**, email blank |
| Duplicate `customer_id` | Uniqueness | 10 extra rows | Append copies of `customer_id` **991–1000** |
| Invalid `customer_segment` | Type / domain | 10 | `customer_id` **201–210** set to VIP / Gold / Enterprise |
| Malformed `email` | Type / domain | 10 | `customer_id` **211–220**, value like `customer211 at shopmail` (not NULL) |
| Future `signup_date` | Business logic | 10 | `customer_id` **221–230**, date `2027-03-01` |

Uniqueness: 10 extra rows means **10 IDs appear twice** (20 physical rows share those IDs). Silver should flag **all** rows for a duplicated key.

## Issue catalog — products.csv

The brief left products clean. Issues were added so all three sources exercise Silver.

| Issue | Silver check | Count | How it is planted |
|---|---|---|---|
| NULL `product_name` | Completeness | 10 | `product_id` **1–10** |
| NULL `category` | Completeness | 5 | `product_id` **11–15** |
| `cost` > `price` | Business logic | 8 | `product_id` **16–23**, cost = 1.25 × price |
| Negative `stock_quantity` | Type / domain | 5 | `product_id` **24–28** |
| Duplicate `product_id` | Uniqueness | 5 extra rows | Append copies of `product_id` **491–495** |

Orders that reference products `1`–`500` remain valid FKs even if that product later fails Silver. Gold inner-joins to **PASS** products only.

## Issue catalog — orders.csv

| Issue | Silver check | Count | How it is planted |
|---|---|---|---|
| NULL `customer_id` | Completeness | 100 | `order_id` **1–100** |
| NULL `product_id` | Completeness | 200 | `order_id` **101–300** |
| `customer_id` not in customers | Referential integrity | 50 | `order_id` **301–350**, `customer_id` **20001–20050** |
| `product_id` not in products | Referential integrity | 30 | `order_id` **351–380**, `product_id` **9001–9030** |
| Duplicate `order_id` | Uniqueness | 20 extra rows | Append copies of `order_id` **1001–1020** |
| Wrong `total_amount` | Business logic | 25 | `order_id` **601–625**, amount = qty × price + 17.50 |
| Completed with no `payment_date` | Business logic | 15 | `order_id` **626–640** |
| Pending with `payment_date` | Business logic | 10 | `order_id` **641–650** |

NULL FKs are completeness failures, not orphans. Orphan IDs are non-null and outside the parent key space.

## Count summary (what verify() asserts)

**Brief-mandated (~700-class issues)**

- 50 NULL emails
- 10 extra duplicate customer rows
- 100 NULL order `customer_id`
- 200 NULL order `product_id`
- 50 orphan customer FKs
- 30 orphan product FKs
- 20 extra duplicate order rows

**Additional (all three files, extra Silver coverage)**

- Customers: 10 invalid segment + 10 malformed email + 10 future signup
- Products: 10 NULL name + 5 NULL category + 8 cost>price + 5 negative stock + 5 extra duplicate rows
- Orders: 25 wrong totals + 15 completed-without-payment + 10 pending-with-payment

Issue ID ranges do not overlap, so a row is planted for **one primary defect** (duplicate copies are otherwise clean).

## Clean-row rules (everything else)

- `total_amount = quantity * unit_price`
- Completed orders have `payment_date` on or after `order_date`
- Pending / Cancelled have blank `payment_date`
- `order_date` ≥ customer `signup_date` when the signup is not in the future
- Product `cost` < `price` and `stock_quantity` ≥ 0
- Customer emails contain `@` and segments are Premium / Standard / Basic

## What this file is not

- Not Bronze ingestion (no Delta, no Databricks)
- Not a quality report (Silver produces `% passed`)
- Not seed SQL (`database/seed-data-notes.md` covers landing the CSVs on DBFS)
