# Seed Data Notes

How to produce the three landing CSVs, land them for Databricks, and what row counts to expect after Bronze ingest.

Related: `src/data_generation/DATA_GENERATION_NOTES.md` (generation rules and issue catalog)  
Related: `database/setup-notes.md` (cluster, Workspace landing, Bronze ingest)

## Source of truth

Checked-in files under `data/`:

| Local path | Landing name |
|---|---|
| `data/customers.csv` | `customers.csv` |
| `data/products.csv` | `products.csv` |
| `data/orders.csv` | `orders.csv` |

These files **are** the seed. Do not hand-edit them. Change the generator, then regenerate.

## Regenerate locally

From the repository root:

```bash
python src/data_generation/generate_sample_data.py
```

Defaults:

- Output directory: `<repo>/data`
- Seed: `42`

The generator verifies planted-issue counts and refuses to write if they drift.

Confirm after a run:

```bash
wc -l data/customers.csv data/products.csv data/orders.csv
```

Expected line counts (including header):

| File | Lines | Data rows |
|---|---|---|
| `data/customers.csv` | 10,011 | 10,010 |
| `data/products.csv` | 506 | 505 |
| `data/orders.csv` | 100,021 | 100,020 |

## Expected Bronze row counts

After a successful ingest, Delta tables must match CSV data rows (header excluded):

| Bronze table | Rows |
|---|---|
| `bronze.customers` | 10,010 |
| `bronze.products` | 505 |
| `bronze.orders` | 100,020 |

If Bronze has 10,000 / 500 / 100,000 rows, duplicate-key rows were dropped at ingest — that is a bug. Bronze must not de-duplicate.

## NULL representation

Empty CSV fields are NULL. Examples:

- `customers.csv` `customer_id` 1–50: blank `email`
- `orders.csv` `order_id` 1–100: blank `customer_id`
- `orders.csv` `order_id` 101–300: blank `product_id`
- `products.csv` `product_id` 1–10: blank `product_name`

Ingest must treat `""` as null (`nullValue` / empty-string-to-null), not as the string `"None"`.

## Issue counts to expect in Bronze (unchanged)

Brief-mandated:

| Check | Location | Count |
|---|---|---|
| Completeness | customers `email` NULL | 50 |
| Uniqueness | extra customer rows with reused `customer_id` | 10 |
| Completeness | orders `customer_id` NULL | 100 |
| Completeness | orders `product_id` NULL | 200 |
| Referential integrity | orders `customer_id` in `20001`–`20050` | 50 |
| Referential integrity | orders `product_id` in `9001`–`9030` | 30 |
| Uniqueness | extra order rows with reused `order_id` | 20 |

Additional (all three files):

| Check | Location | Count |
|---|---|---|
| Type / domain | customers invalid segment (`201`–`210`) | 10 |
| Type / domain | customers malformed email (`211`–`220`) | 10 |
| Business logic | customers signup `2027-03-01` (`221`–`230`) | 10 |
| Completeness | products NULL name (`1`–`10`) | 10 |
| Completeness | products NULL category (`11`–`15`) | 5 |
| Business logic | products `cost` > `price` (`16`–`23`) | 8 |
| Type / domain | products negative stock (`24`–`28`) | 5 |
| Uniqueness | extra product rows (`491`–`495` copied) | 5 |
| Business logic | orders wrong `total_amount` (`601`–`625`) | 25 |
| Business logic | orders Completed with no payment (`626`–`640`) | 15 |
| Business logic | orders Pending with payment (`641`–`650`) | 10 |

Silver flags these rows. It must not delete them. Seed data therefore stays dirty through Bronze and Silver.

Gold reads only Silver `PASS` + `Completed` orders joined to `PASS` customers and `PASS` products. Planted FAIL IDs must not appear in Gold facts. Customers `9700`–`10000` (301 IDs) have no orders so Inactive is populated.

**Knock-on (not a second planted catalog):** customers `221`–`230` have signup `2027-03-01`. Their orders also FAIL `ORDER_BEFORE_SIGNUP`. Requirements tests treat that as correct Silver handling.

## Land files on Databricks (Workspace files)

Public DBFS `/FileStore` is disabled in this workspace. Keep CSVs in the repo `data/` folder:

```
/Workspace/Users/<you>/.bundle/c1-medallion-pipeline/dev/files/data/customers.csv
/Workspace/Users/<you>/.bundle/c1-medallion-pipeline/dev/files/data/products.csv
/Workspace/Users/<you>/.bundle/c1-medallion-pipeline/dev/files/data/orders.csv
```

Upload there in the Workspace UI if the files are missing. Point Bronze at that folder. Do not point Bronze at Gold or Silver tables.

S3 is allowed by the brief; this project uses **Workspace files** because public DBFS is blocked and there are no cloud bucket credentials.

## What not to do when seeding

- Do not filter cancelled orders before Bronze.
- Do not drop NULL emails or NULL FKs to “help” Silver.
- Do not generate a second unofficial CSV set with a different seed and mix it into `data/`.
- Do not load these CSVs straight into Gold. Gold reads Silver PASS + Completed orders only.

## Quick sanity queries (after Bronze)

These belong in tests later; they are listed here as the seed contract:

- `SELECT COUNT(*) FROM bronze.customers` → 10010
- `SELECT COUNT(*) FROM bronze.products` → 505
- `SELECT COUNT(*) FROM bronze.orders` → 100020
- `SELECT COUNT(*) FROM bronze.customers WHERE email IS NULL` → 50
- `SELECT COUNT(*) FROM bronze.orders WHERE customer_id IS NULL` → 100
- `SELECT COUNT(*) FROM bronze.orders WHERE product_id IS NULL` → 200
- `SELECT COUNT(*) FROM bronze.orders WHERE customer_id BETWEEN 20001 AND 20050` → 50
- `SELECT COUNT(*) FROM bronze.orders WHERE product_id BETWEEN 9001 AND 9030` → 30

After Silver, those counts on the *business* tables stay the same; `quality_check_result` is FAIL on the planted IDs. After Gold, `SUM(total_orders)` on `gold.sales_by_product` equals the count of qualifying Silver orders, not 100,020.
