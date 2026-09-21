# sheva-knowledge-stack

Personal orchestration above independent upstream tools. This repository owns policy, lifecycle hooks, reviewed session extraction, Jev choices, DataWeave write orchestration, and a future AI Brain projection. It does not fork ObsidianDataWeave or alter its source checkout.

## Layers

```text
Codex SessionEnd / PreCompact / SessionStart / explicit ending
            ↓ pending transcript locator
wrapup agent → candidate facts → official Jev API KEEP/DROP/UNCERTAIN
            ↓ reviewed plan, route
pinned ObsidianDataWeave worktree → vault_writer → Brain vault + FTS5
            ↓ curated local outbox
AI Brain publisher → NotebookLM (deferred until Google access works)
```

`deps.lock.json` fixes the DataWeave commit used by the runtime. The source checkout can fetch updates without changing the active worktree. `check-updates` fetches and reports an available commit; promoting one requires compatibility review and a deliberate lockfile/worktree change. NotebookLM MCP/CLI remains available for interactive work outside this pipeline.

## Local commands

Run from the repository root:

```bash
python3 -m knowledge_stack setup
python3 -m knowledge_stack status
python3 -m knowledge_stack pending
python3 -m knowledge_stack check-updates
python3 -m knowledge_stack classify .runtime/state/drafts/candidates.json .runtime/state/drafts/review.json
python3 -m knowledge_stack apply .runtime/state/drafts/review.json
```

The decision provider boundary uses TypeSafe's official Jev API (`TYPESAFE_API_KEY`) by default. Only candidates marked `jev_safe` are sent to it. Without a key or on API failure, classification becomes `UNCERTAIN`/`REVIEW`. The local MiniCPM adapter is isolated for later calibration and is not active. Hook handlers do not call Jev or Google. They keep private transcript snapshots and pending records under `.runtime/state/`, which is ignored by Git and restricted to the user account.

The NotebookLM persona is declared in `notebooks.json` and `policies/notebooklm/ai-brain.md`; it targets only the AI Brain UUID. Google commands are explicit: `persona-apply` and `publish`. Text source publishing checks live notebook identity, source list and readiness. Updated text is held locally instead of adding duplicate snapshots.

## Integration state

- Ready locally: pinned DataWeave runtime, skill, lifecycle reminders, private pending records, reviewed-plan schema, guarded writer path, official Jev HTTP adapter and fail-safe review path.
- To configure next: TypeSafe API key and labeled-case calibration; Google network and NotebookLM persona; a stable Google Drive/URL source with content reconciliation; optional local decision adapter. The existing NotebookLM CLI/skill remains separate for ad hoc notebook work.
- Current hooks capture and remind. They do not run a background LLM or publish anything when a session closes.

## Dependency updates

`python3 -m knowledge_stack check-updates` only fetches upstream. To promote a change: inspect the upstream diff, run upstream tests and `python3 -m unittest discover -s tests`, create a new versioned worktree at the tested commit, update `deps.lock.json`, and switch `.runtime/active/ObsidianDataWeave`. Keep the prior worktree for rollback. Never edit the upstream source checkout for local policy changes.
