from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .paths import STATE


def _safe_id(session_id: str) -> str:
    return hashlib.sha256(session_id.encode()).hexdigest()[:24]


def _private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)


def _atomic_json(path: Path, value: dict) -> None:
    _private_dir(path.parent)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def capture(event: dict) -> Path:
    session_id = str(event.get("session_id") or "")
    if not session_id:
        raise ValueError("Hook omitted session_id")
    key = _safe_id(session_id)
    transcript = Path(str(event.get("transcript_path") or ""))
    snapshot = STATE / "transcripts" / f"{key}.jsonl"
    if transcript.is_file() and transcript.stat().st_size <= 15_000_000:
        _private_dir(snapshot.parent)
        shutil.copyfile(transcript, snapshot)
        snapshot.chmod(0o600)
    item = {
        "session_id": session_id,
        "cwd": str(event.get("cwd") or ""),
        "transcript_path": str(snapshot if snapshot.exists() else transcript),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "reason": str(event.get("hook_event_name") or "unknown"),
    }
    path = STATE / "pending" / f"{key}.json"
    _atomic_json(path, item)
    return path


def pending(limit: int = 3) -> list[Path]:
    directory = STATE / "pending"
    if not directory.exists():
        return []
    return sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]


def mark_done(session_id: str) -> None:
    key = _safe_id(session_id)
    pending_path = STATE / "pending" / f"{key}.json"
    if pending_path.exists():
        done_path = STATE / "done" / pending_path.name
        _private_dir(done_path.parent)
        os.replace(pending_path, done_path)
