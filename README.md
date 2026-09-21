# sheva-knowledge-stack

Personal orchestration above independent upstream tools. This repository owns policy, lifecycle hooks, reviewed session extraction, Jev choices, DataWeave write orchestration, and an AI Brain projection. It does not fork ObsidianDataWeave or alter its source checkout.

## Layers

```text
Codex SessionEnd / PreCompact / SessionStart / explicit ending
            ↓ pending transcript locator
wrapup agent → candidate facts → official Jev API KEEP/DROP/UNCERTAIN
            ↓ reviewed plan, route
pinned ObsidianDataWeave worktree → vault_writer → Brain vault + FTS5
            ↓ curated local outbox
AI Brain publisher → NotebookLM
```

`deps.lock.json` fixes the DataWeave commit used by the runtime. The source checkout can fetch updates without changing the active worktree. `check-updates` fetches and reports an available commit; promoting one requires compatibility review and a deliberate lockfile/worktree change. NotebookLM CLI and MCP remain available for interactive work outside this pipeline.

## Local commands

Run from the repository root:

```bash
python3 -m pip install -r requirements.txt
python3 -m knowledge_stack setup
python3 -m knowledge_stack status
python3 -m knowledge_stack jev-smoke
python3 -m knowledge_stack pending
python3 -m knowledge_stack check-updates
python3 -m knowledge_stack classify .runtime/state/drafts/candidates.json .runtime/state/drafts/review.json
python3 -m knowledge_stack apply .runtime/state/drafts/review.json
python3 -m knowledge_stack persona-apply
python3 -m knowledge_stack publish
```

The decision provider boundary uses TypeSafe's official Jev API by default. Store its token in macOS Keychain as service `sheva-knowledge-stack/typesafe` and account `$USER`; `TYPESAFE_API_KEY` is an optional process-only override. In Terminal, run `security add-generic-password -U -a "$USER" -s "sheva-knowledge-stack/typesafe" -w` and type the token at the prompt. Do not paste it into chat, shell arguments or repository files. Verify with `python3 -m knowledge_stack jev-smoke`; the command prints only the model and decisions. Python needs the CA bundle from `requirements.txt` to validate TLS on this machine. Only candidates marked `jev_safe` are sent. Without a key or on API failure, classification becomes `UNCERTAIN`/`REVIEW`. The local MiniCPM adapter is isolated for later calibration and is not active. Hook handlers do not call Jev or Google. They keep private transcript snapshots and pending records under `.runtime/state/`, which is ignored by Git and restricted to the user account.

The NotebookLM persona is declared in `notebooks.json` and `policies/notebooklm/ai-brain.md`; it targets only the AI Brain UUID and preserves the notebook's response-length setting. Google commands are explicit: `persona-apply` and `publish`. Text source publishing checks live notebook identity, source list and readiness. Updated text is held locally instead of adding duplicate snapshots. The account currently has a working NotebookLM CLI auth profile named `default`. Codex has a global `notebooklm` MCP server bound to that profile with strict notebook/source IDs; restart the desktop app to load the new server into its tool catalog.

## Integration state

- Connected and verified: pinned DataWeave runtime, lifecycle reminders, guarded writer path, TypeSafe Jev API via Keychain, NotebookLM CLI auth, AI Brain notebook persona, and NotebookLM MCP handshake.
- To configure next: labeled-case Jev calibration, a stable Google Drive/URL source with content reconciliation, and optional local decision adapter. The outbox has no curated items yet, so `publish` has nothing to send.
- Current hooks capture and remind. They do not run a background LLM or publish anything when a session closes.

## Dependency updates

`python3 -m knowledge_stack check-updates` only fetches upstream. To promote a change: inspect the upstream diff, run upstream tests and `python3 -m unittest discover -s tests`, create a new versioned worktree at the tested commit, update `deps.lock.json`, and switch `.runtime/active/ObsidianDataWeave`. Keep the prior worktree for rollback. Never edit the upstream source checkout for local policy changes.
