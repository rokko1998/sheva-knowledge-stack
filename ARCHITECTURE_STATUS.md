# Knowledge architecture: observed state

Checked 2026-09-22. Obsidian Brain remains canonical. The two owned repositories are `sheva-agent-stack` (activation/updater) and this repository (knowledge pipeline); pinned ObsidianDataWeave and NotebookLM are external dependencies.

| Layer | Observed state |
| --- | --- |
| Git ownership/upstream | Both owned repositories have Git remotes. Pinned DataWeave worktree is active; its source checkout remains clean. |
| Lifecycle | Hooks installed; synthetic tests cover end/continue decisions, completed revision suppression, and pending recovery. A real Codex stop/start cycle still needs observation. |
| Jev | Official TypeSafe API responds. Live `SESSION_END` and `CONTINUE` examples matched the agreed examples. PASS A and PASS B ran on a safe fixture; uncertainty resulted in REVIEW without a write. |
| Canonical write/recall | Live Jev PASS A → FTS5 → PASS B → `apply` wrote a durable decision through DataWeave; FTS5 finds it. A meaningful canonical update and isolated atomic/wiki writer tests passed, including wikilink guard. |
| AI Brain projection | Seven sources were created and observed `ready` with matching notebook/source/Drive IDs. Legacy managed source was retired only afterward. Repeated publication returned seven `unchanged`; changing DECISIONS refreshed only that source. The indexed fulltext contained the new canonical sentence. |
| NotebookLM persona | The approved persona was applied to the exact AI Brain UUID. Other notebooks were not configured. |
| Reverse import | A contentful saved AI Brain note was imported through pinned DataWeave into a new atomic Obsidian note and found with FTS5; managed source fulltext was excluded. |
| Upgrades | DataWeave pin/promote remains separate from source fetch. Promotion contract now checks wiki APIs too. CLI updated to notebooklm-py 0.8.2; this did not change the regional redirect. |

One later Jev-backed canonical write has not yet reached AI Brain: the network route again redirected NotebookLM to `location=unsupported` during preflight. `python3 -m knowledge_stack status` currently shows only `DECISIONS` publication pending. A later `publish` resumes without replacing stable IDs. The two old outbox snapshots are ignored by the canonical renderer and remain in private runtime storage for recovery. Routine AI Brain consultation remains inactive until the user enables it.
