# AI Prompts — Documentation, Design, and Testing

## Prompt 1: Analyse the Brief (No Code)

**PROMPT SENT:**
"@DE_C1_Coding_Evaluation.txt
I have created this repo for a new data pipeline which is my assessment also this is a medallion architecture pipeline that I need to create on databricks

before starting go through the document and analyze it and provide me the following

what all would be required for the sample data
in three different steps explain me what needs to be ingested at bronze what all transformations that needs to be applied on silver and then finally how will data be produced at gold along with I would needed for dashboards
provide details about testing and evaluations
and how would documentation work as according to given in the txt file it should be like that only
Dont create code right away first provide details about above"

**AI RESPONSE SUMMARY:**
Cursor read the evaluation file and mapped sample volumes, planted issues, Bronze (raw), Silver (flag, five modules), Gold (aggregations, Completed filter), dashboard tiles, tests, and the required markdown set. No files were generated in that turn.

**YOUR EVALUATION:**

✓ **What you accepted (and why):**
- Design before code — the brief scores artifacts as well as a working pipeline
- Do not grow pipeline complexity at the expense of docs

✗ **What you changed (and why):**
- Nothing in the repo (analysis only)

△ **What you rejected (and why):**
- Generating scripts in the same turn — the prompt said not to

**FINAL DECISION:** Use that map as the build order. Code starts only after the next design prompt.

---

## Prompt 2: Folder Structure and Layer I/O

**PROMPT SENT:**
"provide me a folder structure level details styarting from sample data to the final gold and dashboards and also the complete details about input processing and output at each layer

dont code still just provide me the design"

**AI RESPONSE SUMMARY:**
Cursor wrote the layer contract: folders, tables, flags, Gold grains, dashboard inputs/outputs. Still no code.

**YOUR EVALUATION:**

✓ **What you accepted (and why):**
- Required tree from the brief, plus `tests/` for the mandatory test tier

✗ **What you changed (and why):**
- Nothing in git yet — this was still a design reply

△ **What you rejected (and why):**
- Coding in that turn

**FINAL DECISION:** Implement against this contract, starting with the generator.

---

## Prompt 3: Are Databricks Pipelines Required?

**PROMPT SENT:**
"Do we need to create pipelines in databricks is there something writtenn any thing like that in the document"

**AI RESPONSE SUMMARY:**
The brief does not require DLT / Lakeflow Pipelines. “Pipeline” means Bronze → Silver → Gold → Dashboard. A Job is optional. A bundle job was added later only because a separate prompt asked for CLI bundles.

**YOUR EVALUATION:**

✓ **What you accepted (and why):**
- DLT is not in the evaluation checklist
- Do not spend Core hours on product Pipelines instead of artifacts

✗ **What you changed (and why):**
- Later (Prompt: Asset Bundle) we still added a Job — that was a tooling choice, not a brief mandate

△ **What you rejected (and why):**
- Building Lakeflow Pipelines as if they were required

**FINAL DECISION:** Medallion code is the pipeline. Bundle job is optional orchestration.

---

## Prompt 4: Requirements Test Tier

**PROMPT SENT:**
"okay lets get back to the project
the pipeliine and dashboard looks fine now I want to add the test tier required by the evaluation
instead of focusing on the testing each line of code try to test the actual requirements try to cover the following
check the sample data for intentional quality issues
the bronze has preserved the issues
then at the silver all the issues are handled evidently and correctly addressed
then check that gold aggregations are inlined with the silver
and finally perform qulaity checks on the dashboard"

(First sent 16 Aug 2026; same text sent again 25 Aug 2026 when work resumed.)

**AI RESPONSE SUMMARY:**
Cursor added `tests/test_pipeline_requirements.py` and `tests/pipeline_harness.py`: planted issues → Bronze unchanged → Silver flags → Gold reconciles to Silver PASS+Completed → dashboard on Gold. Existing per-check tests were kept.

**YOUR EVALUATION:**

✓ **What you accepted (and why):**
- One meaningful tier against requirements, not line-by-line coverage of every helper
- Extra Silver FAIL orders explained as `ORDER_BEFORE_SIGNUP` on future-signup customers — that is correct handling, not a generator bug

✗ **What you changed (and why):**
- First test run: NULL FK RI asserted as `NOT_APPLICABLE` but Silver sets PASS (completeness owns blanks) — assertion updated to match the real contract
- Bronze source test: `dropDuplicates` appears in a comment, not as a call — test checks the “Intentionally no .dropDuplicates()” line

△ **What you rejected (and why):**
- Weakening tests so planted IDs no longer need to FAIL
- Deleting the older per-check tests

**FINAL DECISION:** Requirements tier is the evaluation test layer (23 OK). Full suite 117 OK.

---

## Prompt 5: Review Test Results

**PROMPT SENT:**
"I have run the tests these are the results these are the test results
[23 tests, all OK]
could you please review them and anlyze them and tell me if there is any failures or any where he pipeline is breaking"

**AI RESPONSE SUMMARY:**
All 23 passed. No failure in that run. Caveat: local Python path, not Databricks Jobs.

**YOUR EVALUATION:**

✓ **What you accepted (and why):**
- `OK` means the requirements contract held on the laptop

✗ **What you changed (and why):**
- No code change

△ **What you rejected (and why):**
- Treating this run as proof that `bundle run` works (Jobs API was still blocked on the org)

**FINAL DECISION:** Pipeline logic is intact; deploy remains a workspace issue.

---

## Prompt 6: Repo Structure So Far

**PROMPT SENT:**
"provide me a repo structure for this project up untill. now"

**AI RESPONSE SUMMARY:**
Cursor listed the repo as it then existed and named missing lifecycle files (README, candidate-info, ai-prompts, and the other brief docs).

**YOUR EVALUATION:**

✓ **What you accepted (and why):**
- Honest gap list — those files were still missing at that moment

✗ **What you changed (and why):**
- No code; listing only

△ **What you rejected (and why):**
- Inventing folders that were not in the tree

**FINAL DECISION:** Fill the missing docs next (later prompts).

---

## Prompt 7: Lifecycle Documents

**PROMPT SENT:**
"the pipeline seems to be completed and valdiated now I need you to work on the documents
these are the documents listed in the document
- requirements-analysis.md
- design-notes.md
- data-model.md
- data-quality-strategy.md
- database/setup-notes.md
- database/seed-data-notes.md

keep the document based on what we have used in the project specific to the decisions that we took
dont change any pipeline code and for any assumptions that we made during the working at broze silver or gold document them as well"

**AI RESPONSE SUMMARY:**
Those six files were written or updated from decisions actually used (Completed-only Gold, High-Value cut, serverless, flag-not-delete, DBFS, knock-on ORDER_BEFORE_SIGNUP). No pipeline code changed.

**YOUR EVALUATION:**

✓ **What you accepted (and why):**
- Docs describe this repo, not a generic medallion template
- Assumptions written down instead of left implicit

✗ **What you changed (and why):**
- `setup-notes.md` expanded from Bronze-only to the full run path (bundle + serverless)

△ **What you rejected (and why):**
- Changing generator / Silver / Gold to match a prettier document

**FINAL DECISION:** Those files are the design/DQ pack for submission.

---

## Prompt 8: README

**PROMPT SENT:**
"update the readme file and all the details which are needed in a readme file about the project and dont make it too long or too short a but decent enough to provide a good understanding of the project"

**AI RESPONSE SUMMARY:**
`README.md` added at the project root: what the pipeline is, how to run locally and on Databricks, a few locked design choices, links to longer docs.

**YOUR EVALUATION:**

✓ **What you accepted (and why):**
- Enough to run and understand without repeating `data-quality-strategy.md`

✗ **What you changed (and why):**
- Length kept in the middle — not a one-liner, not the full issue catalog

△ **What you rejected (and why):**
- Dumping every planted ID into the README

**FINAL DECISION:** Use this README as the setup entry point.

---

## Prompt 9: candidate-info.md and tool-workflow.md

**PROMPT SENT:**
"complete the candidate info.md file and tool-workflow.md files with the correct details look up in the de c1 assessment that i provided in there are the details what needs to be added and not along with that also add the necessary details for both of these files"

**AI RESPONSE SUMMARY:**
Filled the Part A templates: name, Cursor, dates 14–25 Aug 2026, serverless Free Edition, how Cursor was used, what not to share. Role recorded as Data Engineer because SE/SSE/ATL was not in the repo.

**YOUR EVALUATION:**

✓ **What you accepted (and why):**
- Every Part A bullet from the brief is covered in `tool-workflow.md`
- Honest about the pasted token (rotate; never in git)

✗ **What you changed (and why):**
- Did not invent an SE/SSE/ATL band

△ **What you rejected (and why):**
- Claiming DLT or a published Databricks dashboard that we did not build

**FINAL DECISION:** Use these files for Part A. Edit the grade band if HR differs.
