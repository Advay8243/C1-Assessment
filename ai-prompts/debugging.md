# AI Prompts — Debugging

Databricks setup and deploy errors. Medallion logic was not rewritten to “fix” a 403.

## Prompt 1: Asset Bundle and CLI

**PROMPT SENT:**
"before I continue further I want to start setting up my databricks. I would be using databricks CLI bundle approach i want you to create a databricks.yml file with suitable confirgurations that we would need in our project and then dont hard code any credentials or my personal access token also try to configure the databricks CLI and I will provide you with the access token as well as the workspace link
and also create the YML according to the structure that we have in our current repo

workspace link : https://dbc-3d6b5aec-582e.cloud.databricks.com/?o=3093091232302096
peronal access token : [REDACTED — never committed; rotate if still active]"

**AI RESPONSE SUMMARY:**
Cursor created `databricks.yml` and `resources/jobs.yml` with host and profile `c1-assessment` only. Token stored in local `~/.databrickscfg`, not in git. Existing Tabcorp DEFAULT profile left intact. Instruction to rotate the token because it had been pasted in chat.

**YOUR EVALUATION:**

✓ **What you accepted (and why):**
- Bundle syncs `src/`, `data/`, `database/`, `tests/`
- Landing path as a variable: `dbfs:/FileStore/medallion/landing`
- Prompt already said not to hard-code the token

✗ **What you changed (and why):**
- Named profile `c1-assessment` so the Tabcorp DEFAULT CLI profile was not overwritten

△ **What you rejected (and why):**
- Writing the PAT into `databricks.yml` or any committed file

**FINAL DECISION:** Auth stays in the CLI profile. Rotate any token that appeared in chat.

---

## Iteration 1: Serverless-Only Workspace

**PROMPT SENT:**
"@terminals/2.txt (databricks bundle deploy)

Error: cannot create resources.jobs.medallion_pipeline: Only serverless compute is supported in the workspace. (400 INVALID_PARAMETER_VALUE)"

**AI RESPONSE SUMMARY:**
Job definition switched from classic `job_clusters` / `new_cluster` to serverless `environments` (`environment_version: "3"`, `environment_key` on each task).

**YOUR EVALUATION:**

✓ **What you accepted (and why):**
- This workspace only allows serverless — the API message is explicit

✗ **What you changed (and why):**
- Removed classic `spark_version` / `node_type_id` from the job cluster

△ **What you rejected (and why):**
- Keeping a classic cluster because “jobs usually need one”

**FINAL DECISION:** `resources/jobs.yml` stays serverless.

---

## Iteration 2: Organization Cancelled

**PROMPT SENT:**
"@terminals/2.txt

still facing the error

Error: cannot create resources.jobs.medallion_pipeline: Organization 3093091232302096 has been cancelled or is not active yet. (403 PERMISSION_DENIED)"

**AI RESPONSE SUMMARY:**
File upload still worked; `jobs create` / `jobs submit` were blocked at org level. Diagnosed as workspace lifecycle / quota, not a bundle YAML bug. Documented in `database/setup-notes.md`. No Gold/Silver code change.

**YOUR EVALUATION:**

✓ **What you accepted (and why):**
- CLI showed current-user active, jobs list empty, create/submit disabled — that is the org, not the medallion code

✗ **What you changed (and why):**
- Nothing in pipeline code — a 403 cannot be fixed by rewriting aggregations

△ **What you rejected (and why):**
- Using the Tabcorp DEFAULT workspace for this assessment
- Pretending a YAML tweak would activate a cancelled org

**FINAL DECISION:** Validate logic locally (117 tests). Job create waits on an active Databricks org.
