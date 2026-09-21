# Knowledge architecture: operating state

Verified 2026-09-22. Obsidian Brain is canonical; AI Brain is a curated projection.

| Layer | Owner | State |
| --- | --- | --- |
| Agent activation, weekly source update discovery | `sheva-agent-stack` | Installed; activates this repository's skill and hooks |
| Session lifecycle | This repository | `SessionEnd` and `PreCompact` capture pending sessions; `SessionStart` reminds about pending wrapup or publication; explicit endings invoke wrapup guidance |
| Retention and routing | This repository + official TypeSafe Jev API | Live API verified; agent reviews every candidate; local model dormant |
| Canonical write and recall | Pinned ObsidianDataWeave + Brain vault | Two real reviewed notes written through `vault_writer.py` and found in FTS5 |
| AI Brain publication | This repository + rclone + NotebookLM CLI | Google-native Drive document and one NotebookLM source created; a second update kept both IDs; fulltext contains both entries; repeat publish returned `unchanged` |
| AI Brain persona | This repository + NotebookLM CLI | AI Brain persona applied; `notebooks.json` supports separate prompts for future notebooks |
| Reverse import | Pinned ObsidianDataWeave | Explicit `import-notes` command connected; live empty-note branch verified. Contentful import waits for an actual curated NotebookLM note |
| DataWeave upgrades | This repository | Locked commit, clean upstream source, update detection, tested `promote <commit>` command; no newer commit was available for a live promotion |

The generic skill updater still fast-forwards clean external skill checkouts. This repository pins only ObsidianDataWeave, whose runtime is independent of its source checkout. Local code and policy are held in the two personal repositories; third-party source checkouts live separately.

## Intentional review points

- Jev scores are advisory until labeled real-session calibration. `UNCERTAIN`, duplicate candidates, wiki routing, and merges require agent review. The pipeline does not silently overwrite existing knowledge.
- The reverse path imports saved NotebookLM **notes**, not indexed source fulltext. AI Brain currently has no saved notes, so a contentful reverse import has not been exercised.
- AI Brain is not consulted automatically during ordinary questions until the user enables that behavior.
- Google publication is retried from the outbox after network failures; session start reminds the agent of unpublished content. Closing a session never launches a long-running cloud operation.

## Commands

Run from this repository: `python3 -m knowledge_stack status`, `pending`, `classify INPUT OUTPUT`, `apply PLAN`, `publish`, `import-notes`, `check-updates`, and `promote COMMIT`. The wrapup skill documents semantic review. The agent repository's `scripts/activate-knowledge-stack` restores the installed links and pinned runtime.
