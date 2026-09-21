from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tomllib
from datetime import date
from pathlib import Path

from .decisions.typesafe import TypeSafeJevProvider
from .deps import verify_runtime
from .paths import ROOT, RUNTIME, STATE, dataweave_python
from .privacy import has_obvious_secret
from .state import mark_done


def _slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "-", value)[:48]


def classify(input_path: Path, output_path: Path) -> dict:
    source = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(source.get("candidates"), list) or not source.get("session_id"):
        raise ValueError("Candidate file needs session_id and candidates list")
    provider = None
    try:
        if any(item.get("jev_safe") for item in source["candidates"]):
            provider = TypeSafeJevProvider()
    except RuntimeError as exc:
        source["classifier_error"] = str(exc)
    for item in source["candidates"]:
        if not item.get("jev_safe") or has_obvious_secret(str(item.get("title", "")) + "\n" + str(item.get("body", ""))):
            item["retention"] = "UNCERTAIN"
            item["route"] = "REVIEW"
            item["decision_reason"] = "Not approved for external Jev API or contains a potential secret"
            continue
        if provider is None:
            item["retention"] = "UNCERTAIN"
            item["route"] = "REVIEW"
            continue
        try:
            answer = provider.evaluate(str(item.get("title", "")), str(item.get("body", "")))
            retention = answer.retention.choice if answer.retention.confidence >= 0.68 else "UNCERTAIN"
            route = answer.route.choice if answer.route.confidence >= 0.60 else "REVIEW"
            if retention != "KEEP":
                route = "DROP" if retention == "DROP" else "REVIEW"
            if route == "LOCAL_AND_AI_BRAIN" and not item.get("cloud_safe"):
                route = "REVIEW"
            item["retention"] = retention
            item["route"] = route
            item["retention_confidence"] = answer.retention.confidence
            item["route_confidence"] = answer.route.confidence
            item["decision_model"] = answer.model
            item["retention_probabilities"] = answer.retention.probabilities
            item["route_probabilities"] = answer.route.probabilities
        except (RuntimeError, OSError, ValueError) as exc:
            item["retention"] = "UNCERTAIN"
            item["route"] = "REVIEW"
            item["decision_reason"] = str(exc)
    source["reviewed_by_agent"] = False
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return source


def _validate_for_apply(plan: dict) -> list[dict]:
    if plan.get("reviewed_by_agent") is not True:
        raise ValueError("Plan needs semantic review and reviewed_by_agent=true")
    if not isinstance(plan.get("session_id"), str) or not plan["session_id"]:
        raise ValueError("Missing session_id")
    accepted = []
    for item in plan.get("candidates", []):
        if item.get("retention") != "KEEP":
            continue
        if item.get("route") not in ("LOCAL_ONLY", "LOCAL_AND_AI_BRAIN"):
            raise ValueError("Unresolved candidate route; review before apply")
        if not item.get("title") or not item.get("body"):
            raise ValueError("Accepted candidate needs title and body")
        if item["route"] == "LOCAL_AND_AI_BRAIN" and not item.get("cloud_safe"):
            raise ValueError("Cloud route requires cloud_safe=true")
        accepted.append(item)
    return accepted


def apply(plan_path: Path) -> dict:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    accepted = _validate_for_apply(plan)
    if not accepted:
        mark_done(plan["session_id"])
        return {"written": 0, "queued": 0}
    runtime = verify_runtime()
    session_key = hashlib.sha256(plan["session_id"].encode()).hexdigest()[:16]
    applied_path = STATE / "applied" / f"{session_key}.json"
    plan_digest = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    if applied_path.exists():
        prior = json.loads(applied_path.read_text(encoding="utf-8"))
        if prior.get("plan_digest") == plan_digest:
            return {"status": "already_applied", **prior["result"]}
        raise RuntimeError("This session already has a different applied plan")
    source_doc = "codex-session-" + session_key
    staging = RUNTIME / "staging" / session_key
    staging.mkdir(parents=True, exist_ok=True)
    date_value = date.today().isoformat()
    notes = []
    for index, item in enumerate(accepted, 1):
        title = f"{item['title'].strip()} [{session_key[:6]}-{index}]"
        notes.append({
            "title": title,
            "tags": ["codex-wrapup"],
            "date": date_value,
            "source_doc": source_doc,
            "note_type": "atomic",
            "body": item["body"].strip(),
        })
    atom_plan = staging / "atom-plan.json"
    atom_plan.write_text(json.dumps({"notes": notes}, ensure_ascii=False, indent=2), encoding="utf-8")
    subprocess.run([str(dataweave_python()), "scripts/generate_notes.py", str(atom_plan), "--staging-dir", str(staging / "notes")], cwd=runtime, check=True)
    subprocess.run([str(dataweave_python()), "scripts/vault_writer.py", "--staging", str(staging / "notes"), "--atom-plan", str(atom_plan), "--non-interactive", "--on-conflict", "skip"], cwd=runtime, check=True)
    config = tomllib.loads((runtime / "config.toml").read_text(encoding="utf-8"))
    vault = Path(config["vault"]["vault_path"])
    notes_dir = vault / config["vault"].get("notes_folder", "Notes")
    for staged in (staging / "notes").glob("*.md"):
        canonical = notes_dir / staged.name
        if not canonical.exists() or canonical.read_bytes() != staged.read_bytes():
            raise RuntimeError(f"Vault writer did not leave the intended canonical content at {canonical}")
    cloud_items = [item for item in accepted if item["route"] == "LOCAL_AND_AI_BRAIN"]
    outbox = STATE / "outbox"
    outbox.mkdir(parents=True, exist_ok=True)
    outbox.chmod(0o700)
    for index, item in enumerate(cloud_items, 1):
        key = hashlib.sha256((plan["session_id"] + item["title"]).encode()).hexdigest()[:24]
        path = outbox / f"{key}.json"
        content = {"title": item["title"], "body": item["body"], "source_doc": source_doc, "queued_at": date_value}
        fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False, indent=2)
    result = {"written": len(notes), "queued": len(cloud_items), "vault_source": source_doc}
    applied_path.parent.mkdir(parents=True, exist_ok=True)
    applied_path.write_text(json.dumps({"plan_digest": plan_digest, "result": result}, ensure_ascii=False, indent=2), encoding="utf-8")
    applied_path.chmod(0o600)
    mark_done(plan["session_id"])
    return result
