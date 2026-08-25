# AI Prompts — Bronze Layer

## Prompt 1: Raw Bronze Ingest

**PROMPT SENT:**
"the sample data looks good now please implement the bronze ingestion and keep bronze raw and unchanged keep the duplicates and null and all other quality issues which would be handled at the silver layer and dont apply any other checks if it seems good then apply ingestion metadata as required such as inghestion timestamp"

**AI RESPONSE SUMMARY:**
Cursor added `src/bronze/ingest_utils.py`, `01_ingest_customers.py`, `02_ingest_orders.py`, `03_ingest_products.py`, and `ingest_all.py`. CSVs are read with an explicit schema and empty fields as NULL. Tables `bronze.customers`, `bronze.products`, `bronze.orders` plus `bronze.ingestion_log`. Technical columns only: `_source_file`, `_ingest_timestamp`, `_batch_id`. `tests/test_bronze_contract.py` locks dirty row counts.

**YOUR EVALUATION:**

✓ **What you accepted (and why):**
- Raw landing — duplicates, nulls, and orphans survive so Silver has something to catch
- Shared `batch_id` across the three tables in one `run_bronze()`
- Expected counts 10,010 / 505 / 100,020 (dropping to unique-ID counts would mean Bronze de-duped)

✗ **What you changed (and why):**
- “File exists / header has required columns” only — that is input validation, not a quality check
- Ingest order products → customers → orders so parents exist before Silver (Bronze itself does not join)

△ **What you rejected (and why):**
- `dropDuplicates`, `dropna`, FK repair, status filters, `quality_check_result` — those belong in Silver

**FINAL DECISION:** Keep Bronze as ingest-only; Silver owns quality.
