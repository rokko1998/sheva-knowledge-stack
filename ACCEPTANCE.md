# Acceptance gates for knowledge pipeline v2

| Gate | Evidence required | Current result |
| --- | --- | --- |
| A. Session end intent | Actual `UserPromptSubmit` end and continue examples; same-turn injection | Live Jev choices verified; hook unit tests and actual Codex lifecycle still to observe |
| B. No duplicate wrapup | Explicit wrapup followed by `SessionEnd`, then a later user turn | Synthetic revision test passes |
| C. Evidence retention | Candidate with transcript locator; unsupported/noisy candidate dropped or reviewed | Live PASS A returned SUPPORTED+KEEP on a real design decision; uncertainty and outage fail-safe tested. Labeled-session calibration remains future work. |
| D. Retrieval and relation | FTS5/wiki context before PASS B; no pre-retrieval duplicate guess | Live PASS A → FTS5/wiki → PASS B returned NEW+ATOMIC+DECISIONS; unit test checks order. |
| E. Canonical writes | NEW atomic, UPDATE_EXISTING semantic merge, wiki ChangeSet with link guard | Live `apply` wrote an atomic decision found by FTS5; canonical update through DataWeave passed. Isolated real writer tests cover atomic update and wiki link guard. |
| F. Seven AI Brain buckets | Current canonical rendering; only changed buckets refreshed | Seven ready sources observed. The latest Jev-backed DECISIONS note appears in indexed fulltext; only DECISIONS refreshed, and a repeat publication returned seven `unchanged`. No bucket remains pending. |
| G. Migration | Seven ready sources before retiring owned legacy source; restart safe | Live migration completed; seven ID/ready checks and legacy absence verified. Failure/retry test passes. |
| H. Persona | Exact approved AI Brain persona on the one notebook | Live configure succeeded for AI Brain UUID. |
| I. Reverse path | Saved NotebookLM note imported through DataWeave, not source fulltext | One contentful saved note became a canonical atomic note and was found by FTS5. |
| J. Dependency updates | Source fetch separate from active pin; promotion tests writer/retrieval/wiki contracts | Code and existing pin verified; no new upstream commit promoted |

No gate is reported as complete from an accepted API call alone: live NotebookLM sources require `ready` state and identity checks; local writes require the DataWeave writer result and canonical file verification.
