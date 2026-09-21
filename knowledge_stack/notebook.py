from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from .paths import NOTEBOOK_CLI, ROOT, STATE
from .privacy import has_obvious_secret


def _run(*args: str, input_text: str | None = None, timeout: int = 60) -> dict | list:
    result = subprocess.run(
        [str(NOTEBOOK_CLI), *args],
        input=input_text,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError(f"NotebookLM command failed ({args[0]}): {result.stderr.strip()[:500]}")
    return json.loads(result.stdout)


def _items(data: dict | list, key: str) -> list[dict]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        found = data.get(key, [])
        return found if isinstance(found, list) else []
    return []


def _config() -> dict:
    return json.loads((ROOT / "notebooks.json").read_text(encoding="utf-8"))["ai-brain"]


def preflight() -> dict:
    auth = _run("auth", "check", "--test", "--json", timeout=30)
    if not isinstance(auth, dict) or auth.get("status") != "ok" or auth.get("checks", {}).get("token_fetch") is not True:
        raise RuntimeError("NotebookLM authentication or network validation failed")
    cfg = _config()
    notebooks = _items(_run("list", "--json"), "notebooks")
    if not any(n.get("id") == cfg["id"] and n.get("title") == cfg["title"] for n in notebooks):
        raise RuntimeError("Configured AI Brain notebook ID and title were not both found")
    return cfg


def persona_apply() -> dict:
    cfg = preflight()
    prompt = (ROOT / cfg["persona"]).read_text(encoding="utf-8").strip()
    if len(prompt) > 10_000:
        raise ValueError("NotebookLM persona exceeds CLI limit")
    return _run("configure", "--persona", prompt, "--notebook", cfg["id"], "--json")


def projection() -> tuple[str, str]:
    outbox = STATE / "outbox"
    entries = []
    for path in sorted(outbox.glob("*.json")) if outbox.exists() else []:
        entry = json.loads(path.read_text(encoding="utf-8"))
        body = str(entry.get("body", ""))
        if has_obvious_secret(str(entry.get("title", "")) + "\n" + body):
            raise ValueError(f"Potential secret in queued item {path.name}; review it before publishing")
        entries.append(f"## {entry['title']}\n\n{body.strip()}\n")
    content = "# AI Brain — curated context\n\n" + "\n".join(entries)
    return content, hashlib.sha256(content.encode()).hexdigest()


def publish() -> dict:
    cfg = preflight()
    content, digest = projection()
    if content.strip() == "# AI Brain — curated context":
        return {"status": "empty"}
    registry_path = STATE / "publication.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8")) if registry_path.exists() else {}
    sources = _items(_run("source", "list", "--notebook", cfg["id"], "--json"), "sources")
    source_id = registry.get("source_id")
    matching = [s for s in sources if s.get("title") == cfg["managed_source_title"]]
    if source_id:
        if not any(s.get("id") == source_id for s in matching):
            raise RuntimeError("Managed source registry disagrees with live notebook; reconcile manually")
        if digest == registry.get("content_hash"):
            return {"status": "unchanged", "source_id": source_id}
        return {"status": "needs_refresh", "reason": "Text sources are snapshots; configure a Drive or URL source before replacing the managed source", "source_id": source_id}
    if matching:
        raise RuntimeError("Managed title exists without a registry entry; reconcile before adding")
    added = _run(
        "source", "add", "-", "--type", "text", "--title", cfg["managed_source_title"],
        "--notebook", cfg["id"], "--json", input_text=content, timeout=90,
    )
    source_id = added.get("source", {}).get("id") if isinstance(added, dict) else None
    if not source_id:
        raise RuntimeError("NotebookLM did not return a source ID")
    _run("source", "wait", source_id, "--notebook", cfg["id"], "--timeout", "600", "--json", timeout=630)
    sources = _items(_run("source", "list", "--notebook", cfg["id"], "--json"), "sources")
    if not any(s.get("id") == source_id and str(s.get("status", "")).lower() == "ready" for s in sources):
        raise RuntimeError("NotebookLM accepted the source but it is not ready")
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps({"source_id": source_id, "content_hash": digest, "title": cfg["managed_source_title"]}, indent=2), encoding="utf-8")
    registry_path.chmod(0o600)
    return {"status": "ready", "source_id": source_id}
