# AI Prompts — Data Generation

Only prompts from this Cursor conversation. The evaluation’s sample (Faker, a second “add 50 NULL emails” prompt) was **not** used — issues were requested in the same message as the generator.

## Prompt 1: Sample Data Generator

**PROMPT SENT:**
"start building the sample data generator you know that you have to create python files according to the volumes that you set earlier and the schemas for products orders and customers looks good to me keep in mind to add the intentional qulatiy issues as well to all thress csv's

Also write DATA_GENERATION_NOTES.md and database/seed-data-notes.md describing counts, issue injection, and how to regenerate."

**AI RESPONSE SUMMARY:**
Cursor generated `src/data_generation/generate_sample_data.py` (Python stdlib, `seed=42`) and wrote `data/customers.csv`, `data/products.csv`, `data/orders.csv`. Volumes: 10,000 / 500 / 100,000 unique IDs plus 10 / 5 / 20 duplicate-key rows. Planted the brief’s issues and extra defects on all three files. Added `verify()` so a bad count aborts the write. Wrote `DATA_GENERATION_NOTES.md` and `database/seed-data-notes.md`.

**YOUR EVALUATION:**

✓ **What you accepted (and why):**
- Deterministic ID ranges so Silver tests can assert exact counts
- Empty CSV field as NULL (matches Bronze `nullValue=""`)
- Customers 9700–10000 with no orders so Gold Inactive is not empty
- Notes that list every planted issue and how to regenerate

✗ **What you changed (and why):**
- Did not use Faker or pandas — stdlib was enough and keeps the generator dependency-free
- Duplicate keys are **appended** copies, not in-place edits, so physical rows stay 10,010 / 505 / 100,020

△ **What you rejected (and why):**
- Leaving products clean — the prompt asked for quality issues in all three CSVs
- Hand-editing CSVs after generation — the generator is the source of truth

**FINAL DECISION:** Use this version as `generate_sample_data.py` and keep the checked-in CSVs as seed.
