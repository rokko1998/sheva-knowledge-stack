"""Apply an agent-authored ChangeSet through pinned DataWeave's validator/writer."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .deps import verify_runtime
from .paths import ROOT, dataweave_python
from .state import _atomic_json


def apply_changeset(item: dict, staging: Path) -> str:
    mutation = item.get("mutation", {})
    if mutation.get("type") != "wiki_changeset":
        raise ValueError("Wiki route requires an agent-authored wiki_changeset mutation")
    data = mutation.get("changeset")
    if not isinstance(data, dict) or not isinstance(mutation.get("expected_sha256"), dict):
        raise ValueError("Wiki mutation needs ChangeSet and expected page hashes")
    creates = data.get("creates", [])
    updates = data.get("updates", [])
    if not any(str(c.get("rel_path", "")).startswith("raw/") for c in creates):
        raise ValueError("Wiki ChangeSet needs a durable raw/ input")
    primary = mutation.get("primary_path")
    if primary not in [p.get("rel_path") for p in creates + updates] or str(primary).startswith("raw/"):
        raise ValueError("Wiki primary_path must name a changed compiled page")
    _atomic_json(staging / "wiki-mutation.json", mutation)
    runtime = verify_runtime()
    result = subprocess.run(
        [str(dataweave_python()), str(ROOT / "scripts/apply_wiki_changeset.py"),
         str(runtime), str(staging / "wiki-mutation.json"), str(staging / "wiki-notes")],
        cwd=runtime, text=True, capture_output=True, timeout=120,
    )
    if result.returncode:
        raise RuntimeError(f"Pinned DataWeave rejected wiki ChangeSet (exit {result.returncode}): {result.stderr.strip()[-500:]}")
    output = json.loads(result.stdout.strip().splitlines()[-1])
    return str(output["primary_canonical_path"])
