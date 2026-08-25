# Databricks notebook source
# MAGIC %md
# MAGIC Shared setup for manual sanity notebooks. Other notebooks `%run` this first.
# MAGIC Sets `REPO_ROOT`, `LANDING_DIR`, and `sys.path`. Attach a cluster before running.

# COMMAND ----------

import sys
from pathlib import Path

dbutils.widgets.text("repo_root", "", "Repo root (blank = auto-detect)")
dbutils.widgets.text("landing_dir", "", "CSV landing dir (blank = <repo>/data)")


def _current_user() -> str:
    return spark.sql("SELECT current_user()").collect()[0][0]


def _notebook_parents() -> list[Path]:
    try:
        raw = (
            dbutils.notebook.entry_point.getDbutils()
            .notebook()
            .getContext()
            .notebookPath()
            .get()
        )
    except Exception:
        return []
    if not raw:
        return []
    paths = [Path(raw), Path("/Workspace") / str(raw).lstrip("/")]
    parents: list[Path] = []
    for path in paths:
        parents.extend([path, *list(path.parents)[:10]])
    return parents


def _is_repo_root(root: Path) -> bool:
    return (root / "src" / "bronze" / "ingest_all.py").is_file()


def find_repo_root() -> Path:
    typed = dbutils.widgets.get("repo_root").strip()
    user = _current_user()
    candidates: list[Path] = []
    if typed:
        candidates.append(Path(typed))
    candidates.extend(_notebook_parents())
    candidates.extend(
        [
            Path(f"/Workspace/Users/{user}/.bundle/c1-medallion-pipeline/dev/files"),
            Path(f"/Users/{user}/.bundle/c1-medallion-pipeline/dev/files"),
            Path(f"/Workspace/Users/{user}/C1-Assessment"),
            Path(f"/Users/{user}/C1-Assessment"),
            Path(f"/Workspace/Users/{user}/c1-assessment/C1-Assessment"),
            Path("/Workspace/C1-Assessment"),
        ]
    )
    cwd = Path.cwd().resolve()
    candidates.extend([cwd, cwd.parent, cwd.parent.parent])
    seen: set[Path] = set()
    for root in candidates:
        if root in seen:
            continue
        seen.add(root)
        if _is_repo_root(root):
            return root
    raise FileNotFoundError(
        "Cannot find the repo (src/bronze/ingest_all.py). Set repo_root to the folder "
        "that contains src/ and data/ "
        f"(example: /Workspace/Users/{user}/.bundle/c1-medallion-pipeline/dev/files)."
    )


REPO_ROOT = find_repo_root()
src_dir = REPO_ROOT / "src"
for relative in (src_dir, src_dir / "bronze", src_dir / "silver", src_dir / "gold"):
    path = str(relative)
    if path not in sys.path:
        sys.path.insert(0, path)

_widget_landing = dbutils.widgets.get("landing_dir").strip().rstrip("/")
_filestore = _widget_landing.replace("dbfs:", "").startswith("/FileStore") or _widget_landing.replace(
    "dbfs:", ""
).startswith("FileStore")
if (not _widget_landing) or _filestore:
    LANDING_DIR = str(REPO_ROOT / "data")
else:
    LANDING_DIR = _widget_landing

print(f"repo_root={REPO_ROOT}")
print(f"landing_dir={LANDING_DIR}")
