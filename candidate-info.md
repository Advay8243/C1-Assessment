# Candidate Information

**Name:** Advay Rawat  
**Role:** Data Engineer  
**Organisation / email:** To The New (`advay.rawat@tothenew.com`)  
**Primary Technology Stack:** Python / PySpark, SQL, Databricks  
**Primary AI Tool Used:** Cursor  
**Project Option Selected:** Data Pipeline (Medallion Architecture)  
**Assessment Start Date:** 14 August 2026  
**Submission Date:** 25 August 2026  

If the form needs a grade band (SE / SSE / ATL / TL), use the band on your HR record — it was not specified in the repo.

## Tools & Environment

- Databricks: Free Edition workspace (`dbc-a6c854d8-1508.cloud.databricks.com`), serverless compute only (classic job clusters are rejected)
- Languages: Python 3.9+, Spark SQL
- Libraries: Python standard library for generation and local tests; PySpark + Delta on Databricks; `unittest` (no pandas / Faker in the pipeline)
- Orchestration: Databricks Asset Bundles (`databricks.yml`, `resources/jobs.yml`), CLI profile `c1-assessment`
- AI tool: Cursor (this repository was designed and built in Cursor against `DE_C1_Coding_Evaluation.txt`)

## Setup Summary

Full steps: `README.md` and `database/setup-notes.md`.

```bash
python src/data_generation/generate_sample_data.py
python -m unittest tests.test_pipeline_requirements -v

export DATABRICKS_CONFIG_PROFILE=c1-assessment
# After data/*.csv are in the bundle files/data folder (not DBFS FileStore)
databricks bundle deploy -t dev
databricks bundle run medallion_pipeline -t dev
```

Do not store PATs in git or in `databricks.yml`. Local tests do not need Spark; they use landing CSVs as Bronze.
