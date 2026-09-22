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


def _transcript_user_state(transcript: Path) -> tuple[set[str], int]:
    if not transcript.is_file():
        return set(), 0
    latest: list[str] = []
    count = 0
    try:
        with transcript.open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                payload = entry.get("payload", {})
                if entry.get("type") == "response_item" and payload.get("type") == "message" and payload.get("role") == "user":
                    count += 1
                    parts = [part.get("text", "") for part in payload.get("content", []) if part.get("type") == "input_text"]
                    if parts:
                        latest = [part.strip() for part in parts if part.strip()]
    except OSError:
        return set(), 0
    revisions = {hashlib.sha256(value.encode()).hexdigest() for value in ["\n".join(latest), *latest]} if latest else set()
    return revisions, count


def transcript_revision(event: dict) -> str | None:
    prompt = event.get("prompt")
    if isinstance(prompt, str) and prompt.strip():
        return hashlib.sha256(prompt.strip().encode()).hexdigest()
    revisions, _ = _transcript_user_state(Path(str(event.get("transcript_path") or "")))
    return next(iter(revisions)) if len(revisions) == 1 else None


def capture(event: dict) -> Path | None:
    session_id = str(event.get("session_id") or "")
    if not session_id:
        raise ValueError("Hook omitted session_id")
    key = _safe_id(session_id)
    revision = transcript_revision(event)
    transcript_revisions, user_count = _transcript_user_state(Path(str(event.get("transcript_path") or "")))
    completed_path = STATE / "completed" / f"{key}.json"
    if revision and completed_path.exists():
        completed = json.loads(completed_path.read_text(encoding="utf-8"))
        allowed_count = completed.get("user_message_count", -1) + (1 if completed.get("reason") == "UserPromptSubmit" else 0)
        same_revision = completed.get("transcript_revision") == revision or completed.get("transcript_revision") in transcript_revisions
        if user_count <= allowed_count and same_revision:
            return None
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
        "transcript_revision": revision,
        "user_message_count": user_count,
    }
    path = STATE / "pending" / f"{key}.json"
    _atomic_json(path, item)
    return path


def pending(limit: int = 3) -> list[Path]:
    directory = STATE / "pending"
    if not directory.exists():
        return []
    return sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]


def mark_done(session_id: str, revision: str | None = None) -> None:
    key = _safe_id(session_id)
    pending_path = STATE / "pending" / f"{key}.json"
    pending_record = json.loads(pending_path.read_text(encoding="utf-8")) if pending_path.exists() else {}
    if not revision:
        revision = pending_record.get("transcript_revision")
    if revision:
        _atomic_json(STATE / "completed" / f"{key}.json", {
            "session_id": session_id, "transcript_revision": revision,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "user_message_count": pending_record.get("user_message_count", -1),
            "reason": pending_record.get("reason", "unknown"),
        })
    if pending_path.exists():
        done_path = STATE / "done" / pending_path.name
        _private_dir(done_path.parent)
        os.replace(pending_path, done_path)
