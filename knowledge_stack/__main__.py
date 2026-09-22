from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from .deps import install_runtime, promote_runtime, verify_runtime
from .credentials import typesafe_key_available
from .decisions.typesafe import TypeSafeJevProvider
from .notebook import persona_apply, projections, publish
from .paths import NOTEBOOK_CLI, ROOT, STATE, lockfile
from .pipeline import apply, classify
from .reverse import import_notes
from .state import mark_done, pending


def _status() -> dict:
    result = {"repository": str(ROOT), "pending": len(pending(1000)), "legacy_outbox_snapshots_ignored": len(list((STATE / "outbox").glob("*.json"))) if (STATE / "outbox").exists() else 0}
    try:
        result["dataweave_runtime"] = str(verify_runtime())
        result["dataweave_pinned"] = True
    except RuntimeError as exc:
        result["dataweave_pinned"] = False
        result["dataweave_error"] = str(exc)
    result["jev_provider"] = "typesafe_api"
    result["jev_api_key_configured"] = typesafe_key_available()
    result["local_jev"] = "adapter reserved; not active"
    result["notebooklm_cli_present"] = NOTEBOOK_CLI.exists()
    result["notebooklm_mcp_present"] = Path("/Users/sheva/.notebooklm-venv/bin/notebooklm-mcp").exists()
    result["notebooklm_live_auth"] = "run notebooklm auth check --test --json"
    registry_path = STATE / "publication.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8")) if registry_path.exists() else {}
    result["publication_schema"] = registry.get("active_schema", "legacy-single-source")
    result["managed_buckets"] = {k: {"source_id": v.get("source_id"), "ready_hash": bool(v.get("content_hash"))} for k, v in registry.get("sources", {}).items()}
    try:
        rendered = projections()
        result["publication_pending"] = [k for k, (_, digest) in rendered.items() if registry.get("sources", {}).get(k, {}).get("content_hash") != digest]
    except (ValueError, RuntimeError) as exc:
        result["publication_pending"] = True
        result["publication_error"] = str(exc)
    return result


def _check_updates() -> dict:
    dep = lockfile()["obsidian_dataweave"]
    source = Path(dep["source"])
    subprocess.run(["git", "fetch", "origin"], cwd=source, check=True)
    latest = subprocess.check_output(["git", "rev-parse", "origin/main"], cwd=source, text=True).strip()
    return {"dependency": "ObsidianDataWeave", "active": dep["commit"], "available": latest, "update_available": latest != dep["commit"], "promoted": False}


def main() -> None:
    parser = argparse.ArgumentParser(prog="knowledge-stack")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("setup", help="Install pinned DataWeave runtime worktree")
    sub.add_parser("status", help="Inspect local pipeline without calling Google")
    sub.add_parser("check-updates", help="Fetch upstream DataWeave without activating it")
    promote_parser = sub.add_parser("promote", help="Test and activate a fetched DataWeave commit")
    promote_parser.add_argument("revision")
    sub.add_parser("pending", help="List pending session records")
    done = sub.add_parser("done", help="Mark a session completed after local write")
    done.add_argument("session_id")
    classify_parser = sub.add_parser("classify", help="Run Jev retention and routing choices")
    classify_parser.add_argument("input", type=Path)
    classify_parser.add_argument("output", type=Path)
    apply_parser = sub.add_parser("apply", help="Write reviewed candidates through DataWeave")
    apply_parser.add_argument("plan", type=Path)
    sub.add_parser("projection", help="Show seven canonical projection hashes and sizes, not contents")
    sub.add_parser("jev-smoke", help="Test the official Jev API with public fixture text")
    persona_parser = sub.add_parser("persona-apply", help="Apply a configured per-notebook persona")
    persona_parser.add_argument("--notebook-key", default="ai-brain")
    sub.add_parser("publish", help="Create or refresh seven managed AI Brain sources")
    sub.add_parser("import-notes", help="Import curated AI Brain notes through pinned DataWeave")
    args = parser.parse_args()
    if args.command == "setup":
        result = {"runtime": str(install_runtime())}
    elif args.command == "status":
        result = _status()
    elif args.command == "check-updates":
        result = _check_updates()
    elif args.command == "promote":
        result = promote_runtime(args.revision)
    elif args.command == "pending":
        result = [json.loads(p.read_text(encoding="utf-8")) for p in pending(1000)]
    elif args.command == "done":
        mark_done(args.session_id)
        result = {"done": args.session_id}
    elif args.command == "classify":
        plan = classify(args.input, args.output)
        result = {"plan": str(args.output), "candidates": len(plan["candidates"]),
                  "statuses": {status: sum(1 for item in plan["candidates"] if item["status"] == status)
                               for status in sorted({item["status"] for item in plan["candidates"]})},
                  "needs_agent_attention": [item.get("candidate_id") for item in plan["candidates"]
                                            if item["status"] in {"REVIEW", "NEEDS_SEMANTIC_WORK"}]}
    elif args.command == "apply":
        result = apply(args.plan)
    elif args.command == "projection":
        result = {k: {"sha256": digest, "characters": len(content)} for k, (content, digest) in projections().items()}
    elif args.command == "jev-smoke":
        decision = TypeSafeJevProvider().pass_a({
            "candidate_id": "public-fixture", "kind": "decision",
            "title": "Fixture decision", "body": "The team chose option A for the fixture.",
            "evidence": [{"source": "transcript", "locator": "fixture:1", "excerpt": "We chose option A for the fixture."}],
            "scope": {"project": "fixture", "domain": "test"},
        })
        result = {"model": decision.model, "answers": {k: v.choice for k, v in decision.answers.items()}}
    elif args.command == "persona-apply":
        result = persona_apply(args.notebook_key)
    elif args.command == "publish":
        result = publish()
    elif args.command == "import-notes":
        result = import_notes()
    else:
        parser.error("unknown command")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
