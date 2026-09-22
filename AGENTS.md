# Agent contract

- This repository owns orchestration and policy. Keep `/Users/sheva/tools/ObsidianDataWeave` as a clean upstream checkout. Its pinned worktree under `.runtime/versions/` is the active code view; `deps.lock.json` controls its commit.
- Before any Obsidian operation, read the installed DataWeave `AGENTS.md`. All generated vault notes must pass through its `vault_writer.py`. Preserve the LLM Wiki link guard.
- Session transcripts and runtime registries stay in `.runtime/` and out of Git. Never commit credentials, API keys, transcripts or cloud source contents containing private data.
- The official TypeSafe Jev API is the primary bounded decision provider. Only `jev_safe` candidates may be sent. Local MiniCPM is a dormant adapter until it is deliberately calibrated and enabled. Use Jev's normal PASS A/B choices directly; send UNCERTAIN, inconsistent choices, and failures to REVIEW. Confidence values are telemetry, not thresholds. The current agent handles only extraction and semantic edits/conflicts.
- AI Brain UUID is fixed in `notebooks.json`. Do not use NotebookLM's shared active-notebook context. Revalidate notebook ID and title before writing. Never silently replace or delete a source.
- Lifecycle hooks must remain bounded. `UserPromptSubmit` may call the official Jev end-intent Choice after a cheap local prefilter; `PreCompact` and `SessionEnd` only capture recovery state. Google publishing is not part of `SessionEnd`.
- Run `python3 -m unittest discover -s tests -v` after changing pipeline, decision, or hook behavior.
