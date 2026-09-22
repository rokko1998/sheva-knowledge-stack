"""Projection metadata only; note text is always read from Obsidian."""
from __future__ import annotations

import json
from pathlib import Path

from .paths import STATE
from .state import _atomic_json


CATALOG = STATE / "catalog.json"


def load() -> dict[str, dict]:
    if not CATALOG.exists():
        return {}
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Canonical projection catalog is malformed")
    return data


def set_bucket(relative_path: str, bucket: str, *, kind: str, project: str = "") -> None:
    catalog = load()
    if bucket == "NONE":
        catalog.pop(relative_path, None)
    else:
        catalog[relative_path] = {"bucket": bucket, "kind": kind, "project": project, "status": "active"}
    _atomic_json(CATALOG, catalog)
