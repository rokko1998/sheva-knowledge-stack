# sheva-knowledge-stack

This repository owns the knowledge policy and pipeline. [`sheva-agent-stack`](https://github.com/rokko1998/sheva-agent-stack) activates shared Codex skills/hooks and discovers external updates. ObsidianDataWeave stays a clean upstream dependency at the commit in `deps.lock.json`; changing that commit requires `promote` and compatibility tests.

## Flow

```text
Codex session / pending transcript
  → current agent extracts evidence-backed candidates
  → official Jev PASS A: support + retention
  → FTS5 recall of canonical Obsidian notes and wiki
  → official Jev PASS B: relation + representation + AI Brain bucket
  → deterministic action or current-agent semantic merge/ChangeSet
  → pinned ObsidianDataWeave writer → Obsidian Brain (canonical)
  → seven current-state projections → Google Docs → NotebookLM AI Brain
```

Jev prose is versioned in `policies/jev/`; choice labels and combinations are validated in code. No extra model review or confidence threshold is required for normal Jev choices. Failures, uncertainty, inconsistent choices, conflicts, and semantic updates stay in `REVIEW` or `NEEDS_SEMANTIC_WORK` until the current agent resolves them. The local Jev adapter is dormant.

`UserPromptSubmit` runs a cheap local end cue check, then official Jev `SESSION_END / CONTINUE / UNCERTAIN`. A clear end injects same-turn wrapup. `PreCompact` captures a recovery checkpoint, `SessionEnd` captures only unprocessed revisions, and `SessionStart` handles pending sessions before ordinary work. Google work never runs inside `SessionEnd`.

AI Brain has seven stable logical sources: `CURRENT_CONTEXT`, `PROJECTS`, `DECISIONS`, `EXPERIMENTS`, `RESEARCH_INSIGHTS`, `PEOPLE`, and `LESSONS_LEARNED`. The catalog stores routing metadata, while every publication reads current canonical note text from Obsidian. Only changed buckets refresh. Migration from the legacy single source is restart-safe: all seven sources must be ready before the old managed source is retired. Unrelated sources are never touched.

## Commands

```bash
python3 -m pip install -r requirements.txt
python3 -m knowledge_stack setup
python3 scripts/install_codex.py
python3 -m knowledge_stack status
python3 -m knowledge_stack jev-smoke
python3 -m knowledge_stack classify .runtime/state/drafts/candidates.json .runtime/state/drafts/plan.json
python3 -m knowledge_stack apply .runtime/state/drafts/plan.json
python3 -m knowledge_stack projection
python3 -m knowledge_stack persona-apply
python3 -m knowledge_stack publish
python3 -m knowledge_stack import-notes
python3 -m knowledge_stack check-updates
python3 -m knowledge_stack promote <fetched-commit>
```

See `skills/wrapup/SKILL.md` for candidate and semantic mutation formats. Store the TypeSafe token in macOS Keychain, service `sheva-knowledge-stack/typesafe`, account `$USER`; never commit it. All transcripts, registries, catalogs, publication text, and credentials stay outside Git under `.runtime/` or their installed service stores. NotebookLM calls always pass the full notebook UUID. Per-notebook persona text lives under `policies/notebooklm/`.

The current verified state and outstanding live gates are in [ARCHITECTURE_STATUS.md](ARCHITECTURE_STATUS.md). Acceptance criteria are in [ACCEPTANCE.md](ACCEPTANCE.md).
