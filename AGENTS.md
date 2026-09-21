# Agent contract

- This repository owns orchestration and policy. Keep `/Users/sheva/tools/ObsidianDataWeave` as a clean upstream checkout. Its pinned worktree under `.runtime/versions/` is the active code view; `deps.lock.json` controls its commit.
- Before any Obsidian operation, read the installed DataWeave `AGENTS.md`. All generated vault notes must pass through its `vault_writer.py`. Preserve the LLM Wiki link guard.
- Session transcripts and runtime registries stay in `.runtime/` and out of Git. Never commit credentials, API keys, transcripts or cloud source contents containing private data.
- The official TypeSafe Jev API is the primary decision provider. Only `jev_safe` candidates may be sent. Local MiniCPM is a dormant adapter until it is deliberately calibrated and enabled. Jev choices are advisory until labeled-session evaluation is complete.
- AI Brain UUID is fixed in `notebooks.json`. Do not use NotebookLM's shared active-notebook context. Revalidate notebook ID and title before writing. Never silently replace or delete a source.
- Lifecycle hooks must remain fast and model-free. Google publishing is not part of `SessionEnd`.
- Run `python3 -m unittest discover -s tests -v` after changing pipeline, decision, or hook behavior.
