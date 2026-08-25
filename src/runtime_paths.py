"""
Resolve repo / layer directories when Databricks does not set __file__.

Serverless spark_python_task and Workspace "Run file" often execute code
without a __file__ global. Fall back to cwd and known folder markers.

Do not copy Workspace files to /tmp or /local_disk0 — this workspace rejects
non-/Workspace local paths (LocalFilesystemAccessDeniedException).
"""

from __future__ import annotations

import argparse
import sys
import time
import types
from pathlib import Path

_LAYER_MARKERS = {
    "bronze": "ingest_utils.py",
    "silver": "silver_utils.py",
    "gold": "gold_utils.py",
    "data_generation": "generate_sample_data.py",
}


def _roots_from(file_value: str | None) -> list[Path]:
    roots: list[Path] = []
    if file_value:
        path = Path(file_value).resolve()
        roots.append(path.parent)
        roots.extend(list(path.parents)[:8])
    cwd = Path.cwd().resolve()
    roots.append(cwd)
    roots.append(cwd / "src")
    roots.extend(list(cwd.parents)[:8])
    roots.extend(parent / "src" for parent in list(cwd.parents)[:8])
    seen: set[Path] = set()
    ordered: list[Path] = []
    for root in roots:
        if root not in seen:
            seen.add(root)
            ordered.append(root)
    return ordered


def find_src_dir(file_value: str | None = None) -> Path | None:
    for root in _roots_from(file_value):
        if (root / "runtime_paths.py").is_file():
            return root
    return None


def repo_root(file_value: str | None = None) -> Path:
    for root in _roots_from(file_value):
        if (root / "databricks.yml").is_file():
            return root
        if (root / "src" / "bronze" / "ingest_utils.py").is_file():
            return root
        if root.name == "src" and (root / "bronze" / "ingest_utils.py").is_file():
            return root.parent
    return Path.cwd().resolve()


def layer_dir(file_value: str | None, layer: str) -> Path:
    marker = _LAYER_MARKERS[layer]
    if file_value:
        here = Path(file_value).resolve().parent
        if (here / marker).is_file():
            return here
    root = repo_root(file_value)
    nested = root / "src" / layer
    if (nested / marker).is_file():
        return nested
    cwd = Path.cwd().resolve()
    for candidate in (cwd, cwd / layer, cwd / "src" / layer):
        if (candidate / marker).is_file():
            return candidate
    return nested if nested.is_dir() else cwd


def add_layer_to_path(file_value: str | None, layer: str) -> Path:
    src = find_src_dir(file_value)
    if src is not None and str(src) not in sys.path:
        sys.path.insert(0, str(src))
    directory = layer_dir(file_value, layer)
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))
    return directory


def materialize_src(src_dir: Path) -> Path:
    """Identity. Copying to /tmp or /local_disk0 is blocked on this workspace."""
    return src_dir.resolve()


def _active_spark():
    try:
        from pyspark.sql import SparkSession

        return SparkSession.getActiveSession()
    except Exception:
        return None


def _path_variants(path: Path | str) -> list[str]:
    raw = str(path).removeprefix("file:")
    variants = [raw]
    if raw.startswith("/Users/") and not raw.startswith("/Workspace/"):
        variants.append("/Workspace" + raw)
    if raw.startswith("/Workspace/"):
        variants.append(raw[len("/Workspace") :])
    # Unique, keep order
    seen: set[str] = set()
    ordered: list[str] = []
    for item in variants:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _get_dbutils():
    try:
        import IPython

        ipython = IPython.get_ipython()
        if ipython is not None:
            dbutils = ipython.user_ns.get("dbutils")
            if dbutils is not None:
                return dbutils
    except Exception:
        pass
    try:
        from pyspark.dbutils import DBUtils

        spark = _active_spark()
        if spark is not None:
            return DBUtils(spark)
    except Exception:
        return None
    return None


def _read_via_dbutils(path: Path) -> str | None:
    dbutils = _get_dbutils()
    if dbutils is None:
        return None
    for variant in _path_variants(path):
        try:
            return dbutils.fs.head(variant, 1024 * 1024)
        except Exception:
            continue
    return None


def _read_via_sdk(path: Path) -> str | None:
    try:
        from databricks.sdk import WorkspaceClient
    except Exception:
        return None
    try:
        client = WorkspaceClient()
        for variant in _path_variants(path):
            ws_path = variant[len("/Workspace") :] if variant.startswith("/Workspace/") else variant
            try:
                payload = client.workspace.download(ws_path)
                data = payload.read() if hasattr(payload, "read") else payload
                if isinstance(data, bytes):
                    return data.decode("utf-8")
                return str(data)
            except Exception:
                continue
    except Exception:
        return None
    return None


def read_workspace_text(path: Path, spark=None, attempts: int = 6) -> str:
    """Read a Workspace file on the driver.

    Do not use spark.read.text(file:...). Spark Connect cannot read those paths,
    and '@' in a user email is parsed as a URI userinfo component.
    """
    last: OSError | None = None
    for variant in _path_variants(path):
        candidate = Path(variant)
        for attempt in range(attempts):
            try:
                return candidate.read_text(encoding="utf-8")
            except OSError as exc:
                last = exc
                time.sleep(0.2 * (attempt + 1))
    text = _read_via_dbutils(path)
    if text is not None:
        return text
    text = _read_via_sdk(path)
    if text is not None:
        return text
    raise OSError(f"Cannot read Workspace file {path}: {last}") from last


def load_workspace_module(name: str, path: Path, spark=None):
    """Import a .py module from Workspace without Spark Connect file reads."""
    if name in sys.modules:
        return sys.modules[name]
    try:
        __import__(name)
        return sys.modules[name]
    except OSError:
        pass
    except Exception as exc:
        msg = str(exc).lower()
        if "input/output error" not in msg and "kd001" not in msg:
            raise
    source = read_workspace_text(path)
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module


# Back-compat alias used by older notebooks/scripts.
import_with_spark_fallback = load_workspace_module


def parse_cli_args(
    parser: argparse.ArgumentParser, args: list[str] | None = None
) -> argparse.Namespace:
    """Parse job flags and ignore Databricks/IPython kernel args.

    Workspace "Run file" launches via db_ipykernel_launcher with
    `-f /local_disk0/sandboxapi/.../connection.json`. Job parameters such as
    --landing-dir are still parsed.
    """
    parsed, _unknown = parser.parse_known_args(args)
    return parsed
