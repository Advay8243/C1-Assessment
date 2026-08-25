# Databricks notebook source
# MAGIC %md
# MAGIC # 1 / 4 — Check landing CSVs
# MAGIC
# MAGIC This workspace has **public DBFS disabled**, so CSVs stay in the repo `data/` folder
# MAGIC (Workspace files). No copy to `/FileStore`.
# MAGIC
# MAGIC Attach a cluster, then **Run All**. Next: `02_bronze`.

# COMMAND ----------

# MAGIC %run ./_setup

# COMMAND ----------

from pathlib import Path

FILES = ("customers.csv", "products.csv", "orders.csv")
data_dir = Path(LANDING_DIR)
missing = [name for name in FILES if not (data_dir / name).is_file()]

print(f"Landing dir: {data_dir}")
if data_dir.is_dir():
    for path in sorted(data_dir.glob("*.csv")):
        print(f"  {path.name}: {path.stat().st_size} bytes")

if missing:
    raise FileNotFoundError(
        "Missing CSVs: "
        + ", ".join(missing)
        + f". Put customers.csv, products.csv, and orders.csv in {data_dir} "
        "(Workspace → the bundle files/data folder, or import the repo data/ folder)."
    )

print("Landing CSVs are present. Run 02_bronze next.")
