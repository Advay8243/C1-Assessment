# Tool Workflow (Part A)

How Cursor was used on this medallion pipeline. This is the AI-workflow artifact the evaluation asks for — not a second copy of the code comments.

## Primary AI tool

**Cursor**, in Agent mode, against the local `C1-Assessment` repo. The evaluation brief (`DE_C1_Coding_Evaluation.txt`) was attached or opened so prompts could refer to required volumes, quality issues, and the repo tree. No second LLM was used as the system of record.

## How project context is provided

Context was loaded in this order, on purpose:

1. The evaluation text (what “complete” means, folder names, four vs five quality checks)
2. The empty (then growing) repo — `src/`, `data/`, `database/`, `tests/`
3. Decisions written back into markdown (`requirements-analysis.md`, `design-notes.md`, `data-quality-strategy.md`) so later prompts did not re-invent Gold filters
4. Open files and test failures, not one-line “write a pipeline” prompts

Standing rules that were repeated in prompts (and now live in those docs):

- Bronze keeps every row
- Silver flags, does not delete
- Gold uses Silver `PASS` + `Completed` only
- No secrets in git
- Do not expand scope at the expense of artifacts

## Requirement analysis

The first Cursor session was **read-only**: parse the brief, list sample-data volumes, Bronze/Silver/Gold contracts, dashboard tiles, and the documentation set. Code was explicitly deferred until that map existed.

Gaps the brief left open were named as assumptions (not guessed silently later): High-Value cut, Completed-only facts, `lifetime_value_actual` vs source LTV, DBFS instead of S3, five Silver modules because the required tree has five files, four Gold tables because `03_daily_weekly_trends.sql` is in the tree. Those landed in `requirements-analysis.md`.

## Pipeline design (Bronze / Silver / Gold)

Design was a separate Cursor turn: folder layout, inputs → processing → outputs per layer, then implementation by slice (generator → Bronze → Silver checks → Gold tables → dashboard → tests → docs).

What was accepted from Cursor:

- Flag-not-delete Silver model
- Dual engine: Spark/SQL on Databricks, Python builders for laptop tests (PySpark is not installed locally)
- Serverless job after classic clusters were rejected
- Dashboard SQL on Gold only

What was changed or rejected:

- Products left “clean” — rejected after the request to plant defects in all three CSVs
- A second stored weekly-revenue table — rejected (week is an attribute on daily grain)
- Rebuilding High-Value logic in dashboard SQL — rejected
- Putting a PAT in `databricks.yml` — rejected
- Using the Tabcorp `DEFAULT` CLI workspace for this assessment — rejected

## Code generation (Python / PySpark / SQL)

Typical prompt shape: “implement this layer against the contract we already wrote; do not clean in Bronze; plant IDs X–Y.” Cursor generated `generate_sample_data.py`, ingest helpers, five Silver modules, Gold SQL + Python, and `unittest` files.

I did not treat first-pass code as done. Examples of edits after generation:

- Generator `verify()` so planted counts cannot silently drift
- Gold `ROW_NUMBER` de-dupe so a leftover Silver duplicate cannot fan out revenue
- AOV as `total_revenue / total_orders`, not a second `AVG()`
- Bar chart `product_label` = id + name so duplicate product names do not merge

## How AI-generated code is validated

1. Read the generated file against the layer contract (would Bronze drop dups? would Gold include Pending?)
2. Run `unittest` locally
3. For Gold, reconcile `SUM(total_orders)` / `SUM(total_revenue)` across sales, customer, daily, and segmentation tables — they must match the same qualifying Silver facts
4. Requirements tier (`tests/test_pipeline_requirements.py`) walks planted issues through every layer

Last local results: requirements tier **23 OK**; full suite **117 OK**. That is the validation for logic. Databricks Jobs create later failed on org/quota (`Organization … cancelled`); that was treated as workspace state, not a reason to change Gold SQL.

## Testing and validation with AI

Cursor wrote per-check tests first (completeness, uniqueness, RI, type, business logic, each Gold table). Those are useful while building.

The evaluation asked for **one meaningful test tier**, not line-by-line coverage. A later prompt asked to test requirements instead of each function. That produced `test_pipeline_requirements.py`:

- Sample CSVs still contain planted defects
- Bronze preserves them
- Silver maps them to the right check and does not delete rows
- Gold matches Silver PASS + Completed
- Dashboard queries stay on Gold

When a test failed, the failure was treated as a contract question (e.g. extra order FAILs were `ORDER_BEFORE_SIGNUP` on future-signup customers), not as “make the test weaker until it passes” unless the assertion was actually wrong (NULL FKs are completeness, RI stays PASS rather than `NOT_APPLICABLE` on orders).

## Debugging with AI

Cursor was used to read the error, name the layer, and propose a fix — then the fix was run.

| Symptom | Root cause | Outcome |
|---|---|---|
| `Only serverless compute is supported` | Classic `job_clusters` on a Free Edition workspace | Job switched to `environments` / `environment_version: "3"` |
| `Organization … cancelled or is not active yet` | Workspace/org lifecycle; Jobs create disabled | Documented; file sync still worked; no fake “code fix” |
| Requirements test: 559 FAIL orders vs 470 planted | Knock-on `ORDER_BEFORE_SIGNUP` for customers 221–230 | Assertion updated to require planted IDs plus that knock-on |
| `dropDuplicates` found in Bronze source | String appeared in a **comment** (“Intentionally no .dropDuplicates”) | Test now checks that comment, not a naive substring ban |

## Data quality checks with AI

Cursor helped design the planted catalog (brief-mandated ~700-class issues plus extra product/type/business rows) and the Silver reason codes. Quality is not “ask the model if the data looks fine.” It is:

- Deterministic IDs in the generator
- Silver flags + `silver.quality_metrics` % passed
- Tests that those IDs FAIL and do not appear in Gold

## What is not shared with AI tools

- **Personal access tokens / passwords.** A PAT was pasted in chat during CLI setup; it must be rotated and must never live in git. `databricks.yml` holds host + profile name only.
- **Real customer PII.** This project uses synthetic `shopmail.com` emails and invented names. Production would keep real extracts out of the prompt and out of git.
- **Tabcorp non-prod credentials / the DEFAULT workspace profile.** Assessment work stays on the `c1-assessment` profile.

## How this would be reused in production

Same loop, stricter gates:

1. Write the contract (grain, PASS/FAIL, fact filter) before generating Spark
2. Keep Bronze raw; put repairs in an explicit, audited step if the business wants them
3. Test with planted defects or production-like fixtures, not only “job succeeded”
4. Secrets in a secret store / CLI profile, never in prompts or bundle YAML
5. Keep dashboard SQL as a thin read of Gold so BI cannot fork the metric definitions

## Lessons learned

**Worked:** design-before-code; one contract repeated in docs, SQL, and tests; Python test engine when Spark was unavailable locally; requirements-tier tests after the pipeline existed.

**Did not work / would not repeat:** pasting a workspace token into chat; assuming Community Edition classic clusters; assuming Jobs API is available because `bundle validate` and file upload succeeded; treating the first Gold `AVG()` as correct without reconciling to Silver.

**Would do earlier next time:** fill `candidate-info.md` / `tool-workflow.md` as the work happens, and log prompts into `ai-prompts/` in the same session instead of reconstructing them at the end.
