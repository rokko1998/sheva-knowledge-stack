# sheva-knowledge-stack

Personal orchestration above independent upstream tools. This repository owns policy, lifecycle hooks, reviewed session extraction, Jev choices, DataWeave write orchestration, and an AI Brain projection. It does not fork ObsidianDataWeave or alter its source checkout.

The verified layer-by-layer state and remaining review points are in [ARCHITECTURE_STATUS.md](ARCHITECTURE_STATUS.md).

## Layers

```text
Codex SessionEnd / PreCompact / SessionStart / explicit ending
            ↓ pending transcript locator
wrapup agent → candidate facts → official Jev API KEEP/DROP/UNCERTAIN
            ↓ reviewed plan, route
pinned ObsidianDataWeave worktree → vault_writer → Brain vault + FTS5
            ↓ curated local outbox
one Google Drive Doc → refresh one AI Brain NotebookLM source
curated NotebookLM notes → DataWeave → Brain vault
```

`deps.lock.json` fixes the DataWeave commit used by the runtime. The source checkout can fetch updates without changing the active worktree. `check-updates` fetches and reports an available commit; `promote <commit>` runs compatibility checks before switching the lock and worktree. NotebookLM CLI and MCP remain available for interactive work outside this pipeline.

## Local commands

Run from the repository root:

```bash
python3 -m pip install -r requirements.txt
python3 -m knowledge_stack setup
python3 -m knowledge_stack status
python3 -m knowledge_stack jev-smoke
python3 -m knowledge_stack pending
python3 -m knowledge_stack check-updates
python3 -m knowledge_stack promote <fetched-commit>
python3 -m knowledge_stack classify .runtime/state/drafts/candidates.json .runtime/state/drafts/review.json
python3 -m knowledge_stack apply .runtime/state/drafts/review.json
python3 -m knowledge_stack persona-apply
python3 -m knowledge_stack publish
python3 -m knowledge_stack import-notes
```

The decision provider boundary uses TypeSafe's official Jev API by default. Store its token in macOS Keychain as service `sheva-knowledge-stack/typesafe` and account `$USER`; `TYPESAFE_API_KEY` is an optional process-only override. In Terminal, run `security add-generic-password -U -a "$USER" -s "sheva-knowledge-stack/typesafe" -w` and type the token at the prompt. Do not paste it into chat, shell arguments or repository files. Verify with `python3 -m knowledge_stack jev-smoke`; the command prints only the model and decisions. Python needs the CA bundle from `requirements.txt` to validate TLS on this machine. Only candidates marked `jev_safe` are sent. Without a key or on API failure, classification becomes `UNCERTAIN`/`REVIEW`. The local MiniCPM adapter is isolated for later calibration and is not active. Hook handlers do not call Jev or Google. They keep private transcript snapshots and pending records under `.runtime/state/`, which is ignored by Git and restricted to the user account.

NotebookLM personas are declared per notebook in `notebooks.json`, with prompt files under `policies/notebooklm/`. `persona-apply --notebook-key <key>` validates that notebook's live ID and title and changes only its persona; omitting the key targets AI Brain. A notebook without `persona` keeps its default chat behavior. `publish` checks the live AI Brain identity, Drive file ID, NotebookLM source ID and readiness. Its registry and outbox stay private under `.runtime/state/`. It updates the same Google-native document, then refreshes the same NotebookLM source. `import-notes` imports saved notebook notes through the pinned DataWeave workflow; an empty notebook note list is a clean no-op. The account uses NotebookLM CLI profile `default`. Codex also has a global `notebooklm` MCP server bound to that profile.

## Integration state

- Connected and verified: pinned DataWeave runtime, lifecycle reminders, guarded writer path, TypeSafe Jev API via Keychain, NotebookLM CLI auth, AI Brain notebook persona, Google Drive source sync, and NotebookLM MCP handshake.
- Further tuning: labeled-case Jev calibration, richer semantic merge and wiki routing, and the optional local decision adapter. These are intentionally review driven until calibrated. Routine AI Brain consultation is inactive until the user explicitly enables it.
- Current hooks capture and remind. They do not run a background LLM or publish anything when a session closes.

## Dependency updates

`python3 -m knowledge_stack check-updates` only fetches upstream. Inspect the upstream diff and run `python3 -m knowledge_stack promote <commit>` to test a candidate and switch the lock/runtime. The command commits the lock change; the previous worktree stays available for rollback. Never edit the upstream source checkout for local policy changes.
