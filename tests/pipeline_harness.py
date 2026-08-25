"""One pipeline snapshot for the requirements test tier.

Landing CSVs stand in for Spark Bronze (same contract: empty field = NULL,
every row kept, metadata only). Silver and Gold reuse gold_bundle().
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src" / "bronze"))
sys.path.insert(0, str(ROOT / "src" / "silver"))

import ingest_utils  # noqa: E402
from gold_harness import gold_bundle  # noqa: E402
from silver_utils import build_context, build_metrics, load_landing_records  # noqa: E402

_CACHE: dict | None = None
SQL_PATH = ROOT / "src" / "dashboard" / "dashboard_queries.sql"
BUSINESS_COLUMNS = {
    table: [name for name, _type in fields]
    for table, fields in ingest_utils.BUSINESS_FIELDS.items()
}


def simulate_bronze(data_dir: Path | None = None) -> dict[str, list[dict]]:
    """Local stand-in for Bronze ingest: typed rows + ingest metadata, no cleaning."""
    data_dir = data_dir or (ROOT / "data")
    batch_id, ingest_ts = ingest_utils.new_batch_context()
    landing = load_landing_records(data_dir)
    bronze: dict[str, list[dict]] = {}
    for table_name, rows in landing.items():
        path = ingest_utils.source_path(str(data_dir), table_name)
        ingest_utils.assert_source_readable(path, table_name)
        bronze[table_name] = [
            {
                **dict(row),
                "_source_file": path,
                "_ingest_timestamp": ingest_ts,
                "_batch_id": batch_id,
            }
            for row in rows
        ]
    return bronze


def pipeline_bundle() -> dict:
    global _CACHE
    if _CACHE is None:
        gold = gold_bundle()
        landing = load_landing_records(ROOT / "data")
        bronze = simulate_bronze(ROOT / "data")
        ctx = build_context(landing["customers"], landing["products"])
        _CACHE = {
            "landing": landing,
            "bronze": bronze,
            "silver": gold["silver"],
            "metrics": build_metrics(gold["silver"], ctx),
            "sales_by_product": gold["sales_by_product"],
            "revenue_by_customer": gold["revenue_by_customer"],
            "daily_weekly_trends": gold["daily_weekly_trends"],
            "customer_segmentation": gold["customer_segmentation"],
            "gold_checks": gold["checks"],
            "dashboard_sql": SQL_PATH.read_text(encoding="utf-8"),
        }
    return _CACHE
