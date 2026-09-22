"""Canonical FTS5 recall before Jev's relation decision."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tomllib
from pathlib import Path

from .deps import verify_runtime
from .paths import dataweave_python
from .privacy import has_obvious_secret


def vault_path() -> Path:
    runtime = verify_runtime()
    cfg = tomllib.loads((runtime / "config.toml").read_text(encoding="utf-8"))
    return Path(cfg["vault"]["vault_path"]).resolve()


def _search(query: str, *, folder: str = "") -> list[dict]:
    runtime = verify_runtime()
    cmd = [str(dataweave_python()), "scripts/memory_index.py", "search", query,
           "--limit", "5", "--json"]
    if folder:
        cmd.extend(["--folder", folder])
    result = subprocess.run(cmd, cwd=runtime, text=True, capture_output=True, timeout=30)
    if result.returncode:
        raise RuntimeError("DataWeave FTS5 search failed; canonical relation requires review")
    data = json.loads(result.stdout)
    if not isinstance(data, list):
        raise RuntimeError("DataWeave FTS5 returned an invalid match list")
    return data


def _terms(candidate: dict) -> list[str]:
    title = str(candidate.get("title", ""))
    words = re.findall(r"[\w-]{4,}", title, flags=re.UNICODE)
    # Search short combinations as well as one distinctive word. FTS5's
    # default expression joins all query terms, which can miss useful notes.
    terms = list(dict.fromkeys(words))
    return [" ".join(terms[:3]), *terms[:3]] if terms else [title[:100]]


def retrieve(candidate: dict) -> tuple[list[dict], list[dict]]:
    root = vault_path()
    runtime = verify_runtime()
    cfg = tomllib.loads((runtime / "config.toml").read_text(encoding="utf-8"))
    folders = [cfg["vault"].get("notes_folder", "Research & Insights"), cfg.get("wiki", {}).get("wiki_folder", "LLM Wiki")]
    refreshed = subprocess.run([str(dataweave_python()), "scripts/memory_index.py", "update"],
                               cwd=runtime, text=True, capture_output=True, timeout=60)
    if refreshed.returncode:
        raise RuntimeError("DataWeave FTS5 index refresh failed; canonical relation requires review")
    found: dict[str, dict] = {}
    for query in _terms(candidate):
        if not query.strip():
            continue
        for folder in folders:
            for hit in _search(query, folder=folder):
                path = hit.get("path")
                if isinstance(path, str) and path not in found:
                    found[path] = hit
    matches: list[dict] = []
    wiki: list[dict] = []
    for relative, hit in list(found.items())[:12]:
        file = (root / relative).resolve()
        if not file.is_relative_to(root) or not file.is_file():
            continue
        content = file.read_text(encoding="utf-8", errors="replace")
        excerpt = content.split("---", 2)[-1].strip()[:1600]
        if has_obvious_secret(excerpt) or has_obvious_secret(str(hit.get("title", ""))):
            raise RuntimeError("Retrieved canonical context may contain a credential; review locally")
        item = {
            "id": relative, "path": relative, "title": str(hit.get("title", "")),
            "type": "WIKI" if relative.startswith("LLM Wiki/") else "ATOMIC",
            "excerpt": excerpt, "sha256": hashlib.sha256(content.encode()).hexdigest(),
        }
        (wiki if item["type"] == "WIKI" else matches).append(item)
    return matches[:6], wiki[:6]
