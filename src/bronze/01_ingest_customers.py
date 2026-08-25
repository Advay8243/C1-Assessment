"""
Bronze ingest: customers.csv → bronze.customers

Raw landing only. Duplicate customer_id rows and NULL emails are kept
so Silver can flag them. No quality checks are applied here.
"""

from __future__ import annotations

import argparse
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
    ensure_bronze_schema,
    get_spark,
    ingest_table,
    new_batch_context,
    resolve_landing_dir,
)


def ingest_customers(spark, landing_dir: str, batch_id: str, ingest_ts):
    return ingest_table(spark, "customers", landing_dir, batch_id, ingest_ts)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest customers.csv into bronze.customers")
    parser.add_argument("--landing-dir", default=None, help="CSV landing directory (DBFS or local)")
    return parser.parse_known_args()[0]


def main() -> None:
    args = parse_args()
    spark = get_spark()
    ensure_bronze_schema(spark)
    landing_dir = resolve_landing_dir(args.landing_dir)
    batch_id, ingest_ts = new_batch_context()
    result = ingest_customers(spark, landing_dir, batch_id, ingest_ts)
    print(result)


if __name__ == "__main__":
    main()
