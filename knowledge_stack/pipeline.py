"""Evidence-backed Jev decisions, canonical retrieval and guarded writes."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tomllib
from datetime import date
from pathlib import Path

import yaml

from .catalog import set_bucket
from .decisions.typesafe import JevResult, TypeSafeJevProvider
from .deps import verify_runtime
from .paths import RUNTIME, STATE, dataweave_python
from .privacy import has_obvious_secret
from .retrieval import retrieve, vault_path
from .state import _atomic_json, mark_done


KINDS = {"decision", "correction", "lesson", "preference", "verified_result", "open_thread"}
BUCKETS = {"NONE", "CURRENT_CONTEXT", "PROJECTS", "DECISIONS", "EXPERIMENTS", "RESEARCH_INSIGHTS", "PEOPLE", "LESSONS_LEARNED"}
VALID_COMBINATIONS = {
    ("DUPLICATE", "NONE"), ("NEW", "ATOMIC"), ("NEW", "WIKI"),
    ("UPDATE_EXISTING", "ATOMIC"), ("UPDATE_EXISTING", "WIKI"),
    ("CONFLICT", "REVIEW"), ("UNCERTAIN", "REVIEW"),
}


def _candidate_error(item: dict) -> str | None:
    if not isinstance(item, dict):
        return "Candidate is not an object"
    if not isinstance(item.get("candidate_id"), str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", item["candidate_id"]):
        return "Missing or unsafe candidate_id"
    if item.get("kind") not in KINDS:
        return "Invalid candidate kind"
    if not isinstance(item.get("title"), str) or not item["title"].strip():
        return "Missing title"
    if not isinstance(item.get("body"), str) or not item["body"].strip():
        return "Missing body"
    evidence = item.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return "Candidate needs transcript evidence"
    for entry in evidence:
        if not isinstance(entry, dict) or entry.get("source") != "transcript" or not all(isinstance(entry.get(k), str) and entry[k].strip() for k in ("locator", "excerpt")):
            return "Evidence needs transcript source, locator and excerpt"
    if not isinstance(item.get("scope"), dict):
        return "Candidate needs scope"
    if type(item.get("jev_safe")) is not bool or type(item.get("cloud_safe")) is not bool:
        return "Candidate needs explicit jev_safe and cloud_safe flags"
    return None


def _telemetry(result: JevResult) -> dict:
    return {"model": result.model, "answers": {
        name: {"choice": value.choice, "confidence": value.confidence, "probabilities": value.probabilities}
        for name, value in result.answers.items()
    }}


def _review(item: dict, reason: str) -> None:
    item["status"] = "REVIEW"
    item["decision_reason"] = reason


def classify(input_path: Path, output_path: Path) -> dict:
    source = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(source.get("candidates"), list) or not isinstance(source.get("session_id"), str) or not source["session_id"]:
        raise ValueError("Candidate file needs session_id and candidates list")
    if any(not isinstance(item, dict) for item in source["candidates"]):
        raise ValueError("Every candidate must be an object")
    ids = [item.get("candidate_id") for item in source["candidates"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Candidate IDs must be unique")
    provider: TypeSafeJevProvider | None = None
    provider_error = ""
    try:
        if any(isinstance(item, dict) and item.get("jev_safe") is True for item in source["candidates"]):
            provider = TypeSafeJevProvider()
    except RuntimeError as exc:
        provider_error = str(exc)
    for item in source["candidates"]:
        error = _candidate_error(item)
        if error:
            _review(item, error)
            continue
        payload_text = json.dumps({k: item[k] for k in ("title", "body", "evidence")}, ensure_ascii=False)
        if not item["jev_safe"] or has_obvious_secret(payload_text):
            _review(item, "Candidate is not approved for the external Jev API")
            continue
        if provider is None:
            _review(item, provider_error or "Official Jev API unavailable")
            continue
        try:
            a = provider.pass_a({k: item[k] for k in ("candidate_id", "kind", "title", "body", "evidence", "scope")})
            item["pass_a"] = _telemetry(a)
            support = a.answers["evidence_support"].choice
            retention = a.answers["retention"].choice
            if support == "UNSUPPORTED" or (support == "SUPPORTED" and retention == "DROP"):
                item["status"] = "DROP"
                continue
            if support != "SUPPORTED" or retention != "KEEP":
                _review(item, "Evidence or retention is uncertain")
                continue
            matches, wiki = retrieve(item)
            item["canonical_matches"] = matches
            item["wiki_candidates"] = wiki
            b = provider.pass_b(
                {k: item[k] for k in ("candidate_id", "kind", "title", "body", "scope", "cloud_safe")},
                matches, wiki,
            )
            item["pass_b"] = _telemetry(b)
            relation = b.answers["canonical_relation"].choice
            representation = b.answers["canonical_representation"].choice
            bucket = b.answers["ai_brain_bucket"].choice
            item.update({"canonical_relation": relation, "canonical_representation": representation, "ai_brain_bucket": bucket})
            if (relation, representation) not in VALID_COMBINATIONS or bucket == "REVIEW" or (not item["cloud_safe"] and bucket != "NONE"):
                _review(item, "Inconsistent or unresolved PASS B choices")
            elif relation == "DUPLICATE":
                item["status"] = "DUPLICATE"
            elif relation in {"CONFLICT", "UNCERTAIN"}:
                _review(item, "Canonical relation requires semantic reconciliation")
            elif relation == "NEW" and representation == "ATOMIC":
                item["status"] = "READY"
            else:
                item["status"] = "NEEDS_SEMANTIC_WORK"
        except (RuntimeError, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
            _review(item, str(exc))
    for item in source["candidates"]:
        item["classified_status"] = item["status"]
    _atomic_json(output_path, source)
    return source


def _note_metadata(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        raise ValueError("Canonical note lacks YAML frontmatter")
    parts = text.split("---", 2)
    if len(parts) != 3:
        raise ValueError("Canonical note has malformed YAML frontmatter")
    frontmatter = yaml.safe_load(parts[1])
    if not isinstance(frontmatter, dict):
        raise ValueError("Canonical note frontmatter is malformed")
    return frontmatter, parts[2].lstrip("\n")


def _write_atomic(item: dict, session_id: str, staging: Path, *, target: Path | None = None) -> str:
    runtime = verify_runtime()
    root = vault_path()
    config = tomllib.loads((runtime / "config.toml").read_text(encoding="utf-8"))
    notes_dir = root / config["vault"].get("notes_folder", "Notes")
    if target is None:
        title = item["title"].strip()
        if not title or "/" in title or "\\" in title or title in {".", ".."}:
            raise ValueError("Unsafe atomic note title")
        source_doc = "codex:" + hashlib.sha256((session_id + item["candidate_id"]).encode()).hexdigest()[:20]
        tags = ["codex-wrapup"]
        body = item["body"].strip()
    else:
        if target.parent != notes_dir.resolve():
            raise ValueError("Atomic update target is outside the notes folder")
        fm, old_body = _note_metadata(target.read_text(encoding="utf-8"))
        title = target.stem
        source_doc = str(fm.get("source_doc", ""))
        tags = fm.get("tags", ["codex-wrapup"])
        body = item["mutation"]["merged_body"].strip()
        if not source_doc or not body:
            raise ValueError("Atomic update needs source_doc and merged body")
        old_links = set(re.findall(r"\[\[([^\]]+)\]\]", old_body))
        new_links = set(re.findall(r"\[\[([^\]]+)\]\]", body))
        if not old_links.issubset(new_links):
            raise ValueError("Atomic merge would remove existing wikilinks")
    atom_plan = staging / "atom-plan.json"
    atom_plan.parent.mkdir(parents=True, exist_ok=True)
    atom_plan.write_text(json.dumps({"notes": [{
        "title": title, "tags": tags, "date": date.today().isoformat(),
        "source_doc": source_doc, "note_type": "atomic", "body": body,
    }]}, ensure_ascii=False), encoding="utf-8")
    staged_dir = staging / "notes"
    subprocess.run([str(dataweave_python()), "scripts/generate_notes.py", str(atom_plan),
                    "--staging-dir", str(staged_dir)], cwd=runtime, check=True, capture_output=True)
    staged_files = list(staged_dir.glob("*.md"))
    if len(staged_files) != 1:
        raise RuntimeError("DataWeave did not stage exactly one atomic note")
    staged = staged_files[0]
    canonical = notes_dir / staged.name
    if target is None and canonical.exists():
        if canonical.read_bytes() != staged.read_bytes():
            raise RuntimeError("NEW atomic title collides with existing canonical note")
        return str(canonical.relative_to(root))
    if target is not None and canonical.resolve() != target.resolve():
        raise RuntimeError("DataWeave changed the target filename during update")
    subprocess.run([str(dataweave_python()), "scripts/vault_writer.py", "--staging", str(staged_dir),
                    "--atom-plan", str(atom_plan), "--non-interactive", "--on-conflict",
                    "overwrite" if target is not None else "skip"], cwd=runtime, check=True, capture_output=True)
    if not canonical.is_file() or canonical.read_bytes() != staged.read_bytes():
        raise RuntimeError("DataWeave writer did not leave the intended canonical note")
    return str(canonical.relative_to(root))


def _resolve_target(item: dict) -> Path:
    mutation = item["mutation"]
    relative = mutation.get("target_path")
    expected = mutation.get("expected_sha256")
    retrieved = item.get("canonical_matches", []) + item.get("wiki_candidates", [])
    if not isinstance(relative, str) or not any(m.get("path") == relative and m.get("sha256") == expected for m in retrieved):
        raise ValueError("Mutation target does not match retrieved canonical context")
    root = vault_path()
    target = (root / relative).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise ValueError("Mutation target is missing or outside the vault")
    if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
        raise RuntimeError("Canonical target changed after retrieval; reclassify")
    return target


def apply(plan_path: Path) -> dict:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    session_id = plan.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("Plan needs session_id")
    items = plan.get("candidates")
    if not isinstance(items, list):
        raise ValueError("Plan needs candidates")
    for item in items:
        if _candidate_error(item):
            raise ValueError(f"Invalid candidate in plan: {_candidate_error(item)}")
        original = item.get("classified_status")
        if original not in {"DROP", "DUPLICATE", "READY", "NEEDS_SEMANTIC_WORK", "REVIEW"}:
            raise ValueError("Plan is missing the Jev classification record")
        changed = original != item.get("status")
        b = item.get("pass_b", {}).get("answers", {})
        for name, field in (("canonical_relation", "canonical_relation"), ("canonical_representation", "canonical_representation"), ("ai_brain_bucket", "ai_brain_bucket")):
            if name in b and item.get(field) != b[name].get("choice"):
                changed = True
        if changed:
            resolution = item.get("agent_resolution")
            if not isinstance(resolution, dict) or not isinstance(resolution.get("reason"), str) or len(resolution["reason"].strip()) < 20:
                raise ValueError("Changed Jev decision needs an explicit agent_resolution reason")
    unresolved = [i.get("candidate_id") for i in items if i.get("status") == "REVIEW" or
                  (i.get("status") == "NEEDS_SEMANTIC_WORK" and not isinstance(i.get("mutation"), dict))]
    if unresolved:
        return {"status": "needs_semantic_work", "candidate_ids": unresolved}
    if any(i.get("status") not in {"DROP", "DUPLICATE", "READY", "NEEDS_SEMANTIC_WORK"} for i in items):
        raise ValueError("Plan has invalid candidate statuses")
    key = hashlib.sha256(session_id.encode()).hexdigest()[:16]
    root = vault_path()
    written = 0
    duplicates = 0
    for item in items:
        if item["status"] == "DROP":
            continue
        if item["status"] == "DUPLICATE":
            duplicates += 1
            continue
        if item.get("ai_brain_bucket") not in BUCKETS or (not item.get("cloud_safe") and item.get("ai_brain_bucket") != "NONE"):
            raise ValueError("Plan has invalid AI Brain bucket")
        ledger = STATE / "applied" / key / f"{item['candidate_id']}.json"
        digest = hashlib.sha256(json.dumps(item, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if ledger.exists():
            previous = json.loads(ledger.read_text(encoding="utf-8"))
            if previous.get("digest") != digest:
                raise RuntimeError("Applied candidate changed; reconcile before retry")
            continue
        staging = RUNTIME / "staging" / key / item["candidate_id"]
        relation = item.get("canonical_relation")
        representation = item.get("canonical_representation")
        if relation == "NEW" and representation == "ATOMIC" and item["status"] == "READY":
            relative = _write_atomic(item, session_id, staging)
        elif relation == "UPDATE_EXISTING" and representation == "ATOMIC":
            if item["mutation"].get("type") != "atomic_update":
                raise ValueError("Atomic update requires atomic_update mutation")
            target = _resolve_target(item)
            relative = _write_atomic(item, session_id, staging, target=target)
        elif representation == "WIKI":
            from .wiki_adapter import apply_changeset
            relative = apply_changeset(item, staging)
        else:
            raise ValueError("Unresolved canonical action")
        set_bucket(relative, item["ai_brain_bucket"], kind=item["kind"], project=str(item["scope"].get("project", "")))
        _atomic_json(ledger, {"digest": digest, "canonical_path": relative})
        written += 1
    mark_done(session_id, plan.get("transcript_revision"))
    return {"status": "applied", "written": written, "duplicates": duplicates}
