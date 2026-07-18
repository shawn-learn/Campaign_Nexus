"""SRD/licensing filters and index-file helpers for the 5etools data layout."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def is_srd(entry: dict[str, Any]) -> bool:
    """True if the entry is in the open SRD (5.1 ``srd`` or 5.2 ``srd52``).

    5etools stores these as either ``True`` or a string (the entry's renamed SRD name);
    both mean "in the SRD". Everything else is copyrighted and must not be redistributed.
    """
    for key in ("srd", "srd52"):
        val = entry.get(key)
        if val is True or isinstance(val, str):
            return True
    return False


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def load_index(dir_path: Path) -> dict[str, str]:
    """Read a 5etools ``index.json`` (source code -> filename), e.g. ``{"MM": "bestiary-mm.json"}``."""
    index_path = dir_path / "index.json"
    if not index_path.exists():
        return {}
    return load_json(index_path)
