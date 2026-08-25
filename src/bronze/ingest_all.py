"""
Run all Bronze ingest jobs as one batch.

Order: products → customers → orders (parents first). Bronze does not join
or clean; each CSV is landed unchanged with shared batch metadata.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_FILE = globals().get("__file__")
_CWD = Path.cwd().resolve()
_src_candidates = []
if _FILE:
    _p = Path(_FILE).resolve()
    _src_candidates.extend([_p.parent, _p.parent.parent, _p.parent.parent.parent])
_src_candidates.extend([_CWD, _CWD / "src", _CWD.parent, _CWD.parent / "src"])
_src_candidates.extend(parent / "src" for parent in list(_CWD.parents)[:8])
for _src in _src_candidates:
    if (_src / "runtime_paths.py").is_file():
        if str(_src) not in sys.path:
            sys.path.insert(0, str(_src))
        break

from runtime_paths import add_layer_to_path  # noqa: E402

_BRONZE_DIR = add_layer_to_path(_FILE, "bronze")

from ingest_utils import (  # noqa: E402
    DEFAULT_INGEST_ORDER,
    ensure_bronze_schema,
    get_spark,
    ingest_table,
    new_batch_context,
    resolve_landing_dir,
)


def run_bronze(spark=None, landing_dir: str | None = None) -> list[dict]:
    spark = spark or get_spark()
    ensure_bronze_schema(spark)
    landing_dir = resolve_landing_dir(landing_dir)
    batch_id, ingest_ts = new_batch_context()
    results = []
    print(f"Bronze ingest batch_id={batch_id} landing_dir={landing_dir}")
    for table_name in DEFAULT_INGEST_ORDER:
        result = ingest_table(spark, table_name, landing_dir, batch_id, ingest_ts)
        print(
            f"  {result['full_table_name']}: {result['row_count']} rows "
            f"(seed reference {result['expected_row_count']})"
        )
        results.append(result)
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest all landing CSVs into Bronze")
    parser.add_argument("--landing-dir", default=None, help="CSV landing directory (DBFS or local)")
    return parser.parse_known_args()[0]


def main() -> None:
    args = parse_args()
    results = run_bronze(landing_dir=args.landing_dir)
    print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
