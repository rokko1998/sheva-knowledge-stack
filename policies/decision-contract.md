# Knowledge decision contract v1

Canonical knowledge lives in the Obsidian Brain vault. ObsidianDataWeave is the only writer for generated vault notes. The FTS5 index is local recall. AI Brain is a curated NotebookLM projection of selected canonical knowledge, not a second source of truth. The managed projection is a Google-native Drive document: update its content, then refresh its existing NotebookLM source. Curated NotebookLM notes may return through DataWeave, without ingesting the source fulltext again.

Official Jev makes small choices through the TypeSafe API, not summaries or factual claims. The local MiniCPM adapter is reserved for a later stage. Codex extracts candidate facts, decisions, corrections, lessons and open threads first. Only externally safe candidates are sent to Jev. For each candidate:

- `KEEP`: a durable, specific and reusable item with enough context to be understood later.
- `DROP`: transient tool output, status chatter, duplicate material, or a fact already represented by canonical code and no additional lesson.
- `UNCERTAIN`: missing provenance, possible duplicate, conflicting evidence, or uncertain future value.

For a kept item:

- `LOCAL_ONLY`: write to Obsidian; do not publish to AI Brain.
- `LOCAL_AND_AI_BRAIN`: write to Obsidian and queue a redacted, curated projection for NotebookLM. Requires `cloud_safe: true` from the reviewing agent.
- `REVIEW`: semantic merge, existing-note update, wiki compilation, sensitive content, or unclear destination. Do not write automatically.

Provisional confidence below 0.68 for retention or 0.60 for routing is `UNCERTAIN`/`REVIEW`; calibrate these values with labeled real sessions before trusting automation. The reviewing agent may override Jev, recording a short reason. Neither Jev nor a lifecycle hook may silently delete or overwrite existing knowledge.
