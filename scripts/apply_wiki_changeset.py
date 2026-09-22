#!/usr/bin/env python3
"""Run the pinned DataWeave ChangeSet validator and writer without another LLM call."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path


def main() -> None:
    runtime, mutation_file, staging = map(Path, sys.argv[1:4])
    sys.path.insert(0, str(runtime))
    from scripts.config import load_config  # type: ignore
    from scripts.wiki_models import parse_changeset  # type: ignore
    from scripts.wiki_compile import (  # type: ignore
        _append_log_to_staging, materialize_to_staging, regenerate_index_to_staging,
        snapshot_wiki_space, validate_changeset, write_to_vault,
    )

    mutation = json.loads(mutation_file.read_text(encoding="utf-8"))
    data = mutation["changeset"]
    cs = parse_changeset(data)
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", cs.project):
        raise ValueError("Wiki project slug is unsafe")
    if cs.renames:
        raise ValueError("Wiki renames require separate reviewed migration")
    cfg = load_config(strict=True)
    root = Path(cfg["vault"]["vault_path"]).resolve()
    wiki_folder = cfg.get("wiki", {}).get("wiki_folder", "LLM Wiki")
    wiki_root = (root / wiki_folder / cs.project).resolve()
    if not wiki_root.is_relative_to(root):
        raise ValueError("Wiki project is outside the vault")
    if not (wiki_root / "SCHEMA.md").is_file():
        raise ValueError("Wiki project is not initialized in pinned DataWeave")
    snapshot = snapshot_wiki_space(wiki_root)
    expected = mutation["expected_sha256"]
    actual_targets = {u.rel_path for u in cs.updates}
    if set(expected) != actual_targets:
        raise ValueError("Wiki update hashes must cover every updated page exactly")
    for rel in actual_targets:
        file = (wiki_root / rel).resolve()
        if not file.is_relative_to(wiki_root) or not file.is_file():
            raise ValueError("Wiki update target is missing or outside project")
        if hashlib.sha256(file.read_bytes()).hexdigest() != expected[rel]:
            raise ValueError("Wiki page changed after semantic merge; reclassify")
    validate_changeset(cs, snapshot)
    staging.mkdir(parents=True, exist_ok=True)
    materialize_to_staging(cs, staging)
    _append_log_to_staging(staging, cs.project, snapshot, cs, "current-agent", 0.0)
    regenerate_index_to_staging(staging, cs.project, snapshot, cs, snapshot.get("mode", "project"))
    writer_result = write_to_vault(staging, on_conflict="overwrite")
    if writer_result:
        raise RuntimeError("DataWeave vault writer failed")
    primary = mutation["primary_path"]
    page = (wiki_root / primary).resolve()
    if not page.is_relative_to(wiki_root) or not page.is_file():
        raise RuntimeError("DataWeave did not write the primary wiki page")
    print(json.dumps({"primary_canonical_path": str(page.relative_to(root))}))


if __name__ == "__main__":
    main()
