"""Seven stable NotebookLM sources rendered from current canonical Obsidian state."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

from . import drive
from .catalog import load as load_catalog
from .paths import NOTEBOOK_CLI, ROOT, STATE
from .privacy import has_obvious_secret
from .retrieval import vault_path
from .state import _atomic_json


def _run(*args: str, input_text: str | None = None, timeout: int = 60) -> dict | list:
    result = subprocess.run([str(NOTEBOOK_CLI), *args], input=input_text, text=True,
                            capture_output=True, timeout=timeout)
    if result.returncode:
        try:
            error = json.loads(result.stdout)
            message = str(error.get("message", "")) if isinstance(error, dict) else ""
        except json.JSONDecodeError:
            message = ""
        raise RuntimeError(f"NotebookLM command failed ({args[0]}): {(message or result.stderr.strip())[:500]}")
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


def projections() -> dict[str, tuple[str, str]]:
    """Read complete live notes; the catalog contains only routing metadata."""
    cfg = _config()
    root = vault_path()
    groups: dict[str, list[str]] = {bucket: [] for bucket in cfg["buckets"]}
    for relative, meta in sorted(load_catalog().items()):
        bucket = meta.get("bucket")
        if bucket not in groups or meta.get("status") != "active":
            continue
        note = (root / relative).resolve()
        if not note.is_relative_to(root) or not note.is_file():
            raise RuntimeError(f"Catalog points to missing/outside canonical note: {relative}")
        body = note.read_text(encoding="utf-8")
        if has_obvious_secret(body):
            raise ValueError(f"Potential secret in canonical projection item: {relative}")
        groups[bucket].append(f"## {note.stem}\n\n{body.strip()}\n")
    result = {}
    for bucket, entries in groups.items():
        content = f"# AI Brain — {bucket}\n\n" + "\n".join(entries)
        result[bucket] = (content, hashlib.sha256(content.encode()).hexdigest())
    return result


def projection(bucket: str | None = None) -> tuple[str, str]:
    all_buckets = projections()
    if bucket is None:
        combined = "\n\n".join(v[0] for v in all_buckets.values())
        return combined, hashlib.sha256(combined.encode()).hexdigest()
    return all_buckets[bucket]


def _live_sources(notebook_id: str) -> list[dict]:
    data = _run("source", "list", "--notebook", notebook_id, "--json")
    if isinstance(data, dict) and data.get("notebook_id") not in (None, notebook_id):
        raise RuntimeError("NotebookLM source list identified a different notebook")
    return _items(data, "sources")


def _one_live(sources: list[dict], *, title: str, source_id: str | None, drive_id: str | None) -> dict | None:
    titled = [s for s in sources if s.get("title") == title]
    if len(titled) > 1:
        raise RuntimeError(f"Duplicate managed NotebookLM title: {title}")
    source = titled[0] if titled else None
    if source_id:
        if not source or source.get("id") != source_id or source.get("drive_document_id") != drive_id:
            raise RuntimeError(f"Managed source registry disagrees with live source: {title}")
    elif source:
        if not drive_id or source.get("drive_document_id") != drive_id:
            raise RuntimeError(f"Unowned NotebookLM source uses managed title: {title}")
    return source


def _publish_bucket(cfg: dict, bucket: str, content: str, digest: str, registry: dict, path: Path) -> dict:
    spec = cfg["buckets"][bucket]
    entry = registry.setdefault("sources", {}).setdefault(bucket, {})
    if entry.get("drive_path") not in (None, spec["drive_path"]):
        raise RuntimeError(f"Managed Drive path changed for {bucket}")
    sources = _live_sources(cfg["id"])
    live = _one_live(sources, title=spec["title"], source_id=entry.get("source_id"), drive_id=entry.get("drive_file_id"))
    if live and not entry.get("source_id"):
        entry["source_id"] = live["id"]  # Recover after add succeeded but registry write failed.
        _atomic_json(path, registry)
    if live and live.get("status") == "ready" and entry.get("content_hash") == digest:
        return {"status": "unchanged", "source_id": live["id"]}
    if entry.get("drive_file_id") and digest == entry.get("content_hash") and live and live.get("status") == "processing":
        pass  # Recovery waits for an in-flight add/refresh.
    else:
        expected_id = entry.get("drive_file_id")
        if not expected_id:
            intent = entry.get("creation_intent")
            if intent and intent != digest:
                raise RuntimeError(f"{bucket} projection changed during an incomplete Drive creation")
            if not intent:
                if drive.file_id(spec["drive_path"], create_folder=True):
                    raise RuntimeError(f"An unmanaged Drive document already occupies {bucket} path")
                entry.update({"creation_intent": digest, "drive_path": spec["drive_path"], "title": spec["title"]})
                _atomic_json(path, registry)
            expected_id = drive.file_id(spec["drive_path"])
            if expected_id and not drive.content_matches(spec["drive_path"], content):
                raise RuntimeError(f"Existing Drive document for {bucket} differs from the recorded creation intent")
        projection_dir = STATE / "projection"
        projection_dir.mkdir(parents=True, exist_ok=True)
        projection_dir.chmod(0o700)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".txt", prefix=f"{bucket}-", dir=projection_dir, delete=False) as tmp:
            tmp.write(content)
            local_file = Path(tmp.name)
        local_file.chmod(0o600)
        try:
            drive_id = drive.upload(local_file, spec["drive_path"], expected_id=expected_id)
        finally:
            local_file.unlink(missing_ok=True)
        entry.update({"drive_file_id": drive_id, "drive_path": spec["drive_path"], "title": spec["title"]})
        entry.pop("creation_intent", None)
        _atomic_json(path, registry)
        preflight()
        sources = _live_sources(cfg["id"])
        live = _one_live(sources, title=spec["title"], source_id=entry.get("source_id"), drive_id=drive_id)
        if not live:
            added = _run("source", "add-drive", drive_id, spec["title"], "--mime-type", "google-doc", "--notebook", cfg["id"], "--json", timeout=90)
            source_id = added.get("source", {}).get("id") if isinstance(added, dict) else None
            if not source_id:
                raise RuntimeError("NotebookLM did not return a source ID")
            entry["source_id"] = source_id
            _atomic_json(path, registry)
        else:
            entry["source_id"] = live["id"]
            _atomic_json(path, registry)
            _run("source", "refresh", live["id"], "--notebook", cfg["id"], "--json", timeout=90)
    source_id = entry["source_id"]
    _run("source", "wait", source_id, "--notebook", cfg["id"], "--timeout", "600", "--json", timeout=630)
    live = _one_live(_live_sources(cfg["id"]), title=spec["title"], source_id=source_id, drive_id=entry["drive_file_id"])
    if not live or str(live.get("status", "")).lower() != "ready":
        raise RuntimeError(f"NotebookLM bucket did not become ready: {bucket}")
    entry["content_hash"] = digest
    _atomic_json(path, registry)
    return {"status": "ready", "source_id": source_id}


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
    contents = projections()
    registry_path = STATE / "publication.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8")) if registry_path.exists() else {}
    if "legacy" not in registry and registry.get("source_id"):
        registry["legacy"] = {k: registry[k] for k in ("source_id", "drive_file_id", "drive_path", "title", "content_hash") if k in registry}
        _atomic_json(registry_path, registry)
    outcomes = {}
    for bucket, (content, digest) in contents.items():
        outcomes[bucket] = _publish_bucket(cfg, bucket, content, digest, registry, registry_path)
    for bucket, (_, digest) in contents.items():
        if registry["sources"][bucket].get("content_hash") != digest:
            raise RuntimeError("Cannot activate incomplete seven-source projection")
    registry["active_schema"] = "seven-buckets-v1"
    _atomic_json(registry_path, registry)
    legacy = registry.get("legacy", {})
    if legacy.get("source_id") and not legacy.get("retired"):
        candidates = [s for s in _live_sources(cfg["id"]) if s.get("title") == legacy["title"] or s.get("id") == legacy["source_id"]]
        if candidates and (len(candidates) != 1 or candidates[0].get("id") != legacy["source_id"] or
                           candidates[0].get("title") != legacy["title"] or
                           candidates[0].get("drive_document_id") != legacy.get("drive_file_id")):
            raise RuntimeError("Legacy source identity changed during migration")
        live = candidates[0] if candidates else None
        if live:
            preflight()
            _one_live(_live_sources(cfg["id"]), title=legacy["title"], source_id=legacy["source_id"], drive_id=legacy.get("drive_file_id"))
            _run("source", "delete", legacy["source_id"], "--notebook", cfg["id"], "--yes", "--json", timeout=90)
        legacy["retired"] = True
        _atomic_json(registry_path, registry)
    return {"status": "ready", "active_schema": registry["active_schema"], "buckets": outcomes, "legacy_retired": bool(legacy.get("retired"))}
