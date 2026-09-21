from __future__ import annotations

import hashlib
import json
import fcntl
import os
import subprocess
import tempfile
from pathlib import Path

from . import drive
from .paths import NOTEBOOK_CLI, ROOT, STATE
from .privacy import has_obvious_secret
from .state import _atomic_json


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


def _config(key: str = "ai-brain") -> dict:
    registry = json.loads((ROOT / "notebooks.json").read_text(encoding="utf-8"))
    if key not in registry:
        raise ValueError(f"Unknown configured notebook: {key}")
    return registry[key]


def preflight(key: str = "ai-brain") -> dict:
    auth = _run("auth", "check", "--test", "--json", timeout=30)
    if not isinstance(auth, dict) or auth.get("status") != "ok" or auth.get("checks", {}).get("token_fetch") is not True:
        raise RuntimeError("NotebookLM authentication or network validation failed")
    cfg = _config(key)
    notebooks = _items(_run("list", "--json"), "notebooks")
    if not any(n.get("id") == cfg["id"] and n.get("title") == cfg["title"] for n in notebooks):
        raise RuntimeError(f"Configured notebook ID and title were not both found for {key}")
    return cfg


def persona_apply(key: str = "ai-brain") -> dict:
    cfg = preflight(key)
    if not cfg.get("persona"):
        return {"status": "no_persona", "notebook_key": key}
    _run("source", "list", "--notebook", cfg["id"], "--json")
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
    STATE.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(STATE / "publish.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        return _publish_locked()
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def _publish_locked() -> dict:
    cfg = preflight()
    content, digest = projection()
    if content.strip() == "# AI Brain — curated context":
        return {"status": "empty"}
    registry_path = STATE / "publication.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8")) if registry_path.exists() else {}
    if registry.get("drive_path") and registry["drive_path"] != cfg["drive_path"]:
        raise RuntimeError("Configured Drive path differs from the managed registry")
    sources = _items(_run("source", "list", "--notebook", cfg["id"], "--json"), "sources")
    source_id = registry.get("source_id")
    matching = [s for s in sources if s.get("title") == cfg["managed_source_title"]]
    if registry and not registry.get("drive_file_id"):
        return {"status": "needs_migration", "reason": "Existing snapshot source needs a reviewed migration to Google Drive"}
    if source_id:
        if not any(s.get("id") == source_id and s.get("drive_document_id") == registry.get("drive_file_id") for s in matching):
            raise RuntimeError("Managed source registry disagrees with live notebook; reconcile manually")
        if digest == registry.get("content_hash"):
            return {"status": "unchanged", "source_id": source_id}
    elif matching and not (len(matching) == 1 and matching[0].get("drive_document_id") == registry.get("drive_file_id")):
        raise RuntimeError("Managed title exists without a registry entry; reconcile before adding")
    if matching and not source_id:
        source_id = matching[0]["id"]
        registry["source_id"] = source_id
        _atomic_json(registry_path, registry)

    projection_dir = STATE / "projection"
    projection_dir.mkdir(parents=True, exist_ok=True)
    projection_dir.chmod(0o700)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".txt", prefix="ai-brain-", dir=projection_dir, delete=False) as tmp:
        tmp.write(content)
        local_file = Path(tmp.name)
    local_file.chmod(0o600)
    try:
        drive_id = drive.upload(local_file, cfg["drive_path"], expected_id=registry.get("drive_file_id"))
    finally:
        local_file.unlink(missing_ok=True)
    registry.update({"drive_file_id": drive_id, "drive_path": cfg["drive_path"], "title": cfg["managed_source_title"]})
    _atomic_json(registry_path, registry)

    if source_id is None:
        # Re-list immediately before the NotebookLM write on the shared account.
        preflight()
        if any(s.get("title") == cfg["managed_source_title"] for s in _items(_run("source", "list", "--notebook", cfg["id"], "--json"), "sources")):
            raise RuntimeError("Managed NotebookLM title appeared during Drive upload; reconcile manually")
        added = _run(
            "source", "add-drive", drive_id, cfg["managed_source_title"],
            "--mime-type", "google-doc", "--notebook", cfg["id"], "--json", timeout=90,
        )
        source_id = added.get("source", {}).get("id") if isinstance(added, dict) else None
        if not source_id:
            raise RuntimeError("NotebookLM did not return a source ID")
        registry["source_id"] = source_id
        _atomic_json(registry_path, registry)
    else:
        preflight()
        live = _items(_run("source", "list", "--notebook", cfg["id"], "--json"), "sources")
        if not any(s.get("id") == source_id and s.get("drive_document_id") == drive_id for s in live):
            raise RuntimeError("Managed NotebookLM source changed before refresh")
        _run("source", "refresh", source_id, "--notebook", cfg["id"], "--json", timeout=90)

    _run("source", "wait", source_id, "--notebook", cfg["id"], "--timeout", "600", "--json", timeout=630)
    sources = _items(_run("source", "list", "--notebook", cfg["id"], "--json"), "sources")
    if not any(s.get("id") == source_id and s.get("drive_document_id") == drive_id and str(s.get("status", "")).lower() == "ready" for s in sources):
        raise RuntimeError("NotebookLM accepted the source but it is not ready")
    registry["content_hash"] = digest
    _atomic_json(registry_path, registry)
    return {"status": "ready", "source_id": source_id, "drive_file_id": drive_id}
