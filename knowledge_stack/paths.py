from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / ".runtime"
STATE = RUNTIME / "state"
DATAWEAVE = RUNTIME / "active" / "ObsidianDataWeave"
LOCK = ROOT / "deps.lock.json"
NOTEBOOK_ID = "6a1e477f-2de0-4051-9fbc-5916140aabb6"
NOTEBOOK_CLI = Path("/Users/sheva/bin/notebooklm")
JEV_ROOT = Path("/Users/sheva/Developer/jev-lab")
JEV_URL = "http://127.0.0.1:4319"


def lockfile() -> dict:
    return json.loads(LOCK.read_text(encoding="utf-8"))


def dataweave_python() -> Path:
    source = Path(lockfile()["obsidian_dataweave"]["source"])
    return source / ".venv/bin/python"
