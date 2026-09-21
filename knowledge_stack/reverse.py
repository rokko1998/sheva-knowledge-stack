"""Explicit import of curated AI Brain notes into the canonical vault."""
from __future__ import annotations

import subprocess

from .deps import verify_runtime
from .notebook import _run, preflight
from .paths import dataweave_python


def import_notes() -> dict:
    cfg = preflight()
    listed = _run("note", "list", "--notebook", cfg["id"], "--json")
    if not isinstance(listed, dict) or listed.get("notebook_id") != cfg["id"]:
        raise RuntimeError("NotebookLM note list did not identify the configured AI Brain")
    notes = listed.get("notes")
    if not isinstance(notes, list):
        raise RuntimeError("NotebookLM note list is malformed")
    if not notes:
        return {"status": "no_curated_notes", "notes": 0}

    runtime = verify_runtime()
    # DataWeave fetches notebook *notes* by default. Sources and mind maps are
    # intentionally excluded so the managed projection cannot loop back in.
    result = subprocess.run(
        [str(dataweave_python()), "scripts/process_notebook.py", cfg["id"],
         "--profile", cfg.get("profile", "default"), "--backend", "codex", "--non-interactive",
         "--on-conflict", "skip"],
        cwd=runtime, text=True, capture_output=True, timeout=900,
    )
    if result.returncode:
        raise RuntimeError(f"DataWeave notebook import failed (exit {result.returncode})")
    return {"status": "imported", "notes": len(notes), "writer_summary": result.stdout.strip()[-500:]}
