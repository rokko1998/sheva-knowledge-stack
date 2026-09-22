"""Small, explicit rclone boundary for one managed Google Doc."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


def _run(*args: str, timeout: int = 120) -> str:
    result = subprocess.run(["rclone", *args], text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"rclone {args[0]} failed (exit {result.returncode})")
    return result.stdout


def _location(remote_path: str) -> tuple[str, str]:
    if not remote_path.startswith("gdrive:") or not remote_path.endswith(".txt"):
        raise ValueError("Managed Drive path must be a gdrive: .txt document")
    rest = remote_path.removeprefix("gdrive:")
    parts = rest.split("/")
    if len(parts) < 2 or any(p in ("", ".", "..") for p in parts):
        raise ValueError("Invalid managed Drive path")
    return "gdrive:" + "/".join(parts[:-1]), parts[-1]


def file_id(remote_path: str, *, create_folder: bool = False) -> str | None:
    parent, name = _location(remote_path)
    if create_folder:
        _run("mkdir", parent)
    entries = json.loads(_run("lsjson", parent, "--files-only", "--drive-export-formats", "txt"))
    matches = [item for item in entries if item.get("Path") == name]
    if len(matches) > 1:
        raise RuntimeError("Multiple Drive files have the managed name")
    return str(matches[0]["ID"]) if matches else None


def upload(local_file: Path, remote_path: str, *, expected_id: str | None) -> str:
    prior = file_id(remote_path, create_folder=True)
    if prior != expected_id:
        raise RuntimeError("Managed Drive document does not match the local registry")
    _run(
        "copyto", str(local_file), remote_path,
        "--drive-import-formats", "txt", "--drive-export-formats", "txt",
        timeout=180,
    )
    actual = file_id(remote_path)
    if not actual or (expected_id and actual != expected_id):
        raise RuntimeError("Drive upload changed or lost the managed document ID")
    return actual


def content_matches(remote_path: str, expected: str) -> bool:
    """Google Docs text export may add BOM/paragraph breaks; compare its text tokens."""
    _location(remote_path)
    actual = _run("cat", remote_path, "--drive-export-formats", "txt", timeout=120)
    normalize = lambda value: re.sub(r"\s+", " ", value.lstrip("\ufeff")).strip()
    return normalize(actual) == normalize(expected)
