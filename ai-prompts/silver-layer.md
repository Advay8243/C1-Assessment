# AI Prompts — Silver Layer

## Prompt 1: Five Quality Checks and Tests

**PROMPT SENT:**
"the validation queries looks good now start the development for the silver

Based on the requirements in the document perform the necessary checks and transformations for bronze to silver
perform the following quality checks :
1. completness
2. uniqueness
3. type validation
4. referntial integrity
5. business logic
and create silver tables accordingly

after each quality check do perform  test to check if each one is working as it should be"

**AI RESPONSE SUMMARY:**
Cursor implemented flag-only Silver: `silver_utils.py`, `01_quality_completeness.py` through `05_quality_business_logic.py`, `create_silver_tables.py`, and `silver.quality_metrics`. Every Bronze row is kept. Per-check tests plus `tests/test_silver_tables.py` assert planted IDs fail the right check.

**YOUR EVALUATION:**

✓ **What you accepted (and why):**
- All five checks (required repo tree has five files; brief also says “all four”)
- `quality_check_result` PASS/FAIL plus per-check flags and `failure_reasons`
- NULL FKs = completeness; orphans = referential integrity (avoids double-counting)
- Every row with a duplicate key fails uniqueness, not only the extra copy

✗ **What you changed (and why):**
- Python engine for laptop tests (PySpark is not installed locally) and Spark/SQL for Databricks — same rules, two runtimes

△ **What you rejected (and why):**
- Deleting or repairing bad rows in Silver — Gold filters `PASS`; the quality report would lie if rows disappeared

**FINAL DECISION:** Use this Silver model. Gold reads `quality_check_result = 'PASS'` only.
