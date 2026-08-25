"""Shared loaders for Silver quality tests (landing CSVs stand in for Bronze)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "silver"))
sys.path.insert(0, str(ROOT / "src" / "data_generation"))

from silver_utils import (  # noqa: E402
    SilverContext,
    build_context,
    load_check_module,
    load_landing_records,
)

_RECORDS: dict | None = None
_CTX: SilverContext | None = None


def records() -> dict:
    global _RECORDS, _CTX
    if _RECORDS is None:
        _RECORDS = load_landing_records(ROOT / "data")
        _CTX = build_context(_RECORDS["customers"], _RECORDS["products"])
    return _RECORDS


def context() -> SilverContext:
    records()
    assert _CTX is not None
    return _CTX


def load_check(filename: str):
    return load_check_module(filename)


def flag(filename: str, table_name: str) -> list[dict]:
    module = load_check(filename)
    return module.flag_python(records()[table_name], table_name, context())


def failed(rows: list[dict], flag_col: str) -> list[dict]:
    return [row for row in rows if row.get(flag_col) == "FAIL"]
