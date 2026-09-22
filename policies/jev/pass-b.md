# Jev PASS B

Use the candidate and retrieved canonical matches. Classify the action; do not produce semantic edits. A candidate may have only one primary AI Brain bucket.

## canonical_relation

Instructions: How does the candidate relate to the retrieved canonical knowledge?

### NEW
No retrieved canonical item already expresses the same durable proposition, and the candidate introduces useful new knowledge.

### DUPLICATE
The useful meaning of the candidate is already represented in canonical knowledge. It adds no meaningful new state, qualification, rationale, correction, or lesson.

### UPDATE_EXISTING
The candidate meaningfully extends, refines, supersedes, corrects, or updates an existing canonical item.

### CONFLICT
The candidate and existing canonical knowledge make materially incompatible claims and supplied context does not establish that one simply supersedes the other.

### UNCERTAIN
The retrieved context is insufficient to determine the relationship reliably.

## canonical_representation

Instructions: What canonical representation does this knowledge require? Expected combinations: DUPLICATE+NONE; NEW+ATOMIC; NEW+WIKI; UPDATE_EXISTING+ATOMIC; UPDATE_EXISTING+WIKI; CONFLICT+REVIEW; UNCERTAIN+REVIEW. Invalid combinations require review.

### NONE
No canonical write is needed, normally because relation is DUPLICATE.

### ATOMIC
The knowledge is independently useful as a durable atomic fact, decision, lesson, preference, result, constraint, or open thread.

### WIKI
The knowledge belongs inside a coherent structured project/domain representation where relationships, current state, navigation, or aggregation matter.

### REVIEW
Choosing or changing canonical representation requires semantic reasoning that cannot be reduced to this bounded classification.

## ai_brain_bucket

Instructions: Should this canonical knowledge be projected into AI Brain? Choose one primary source. When several seem plausible, prefer explicit choice/policy→DECISIONS; experiment/test evidence→EXPERIMENTS; general reusable lesson→LESSONS_LEARNED; research synthesis→RESEARCH_INSIGHTS; person-centered context→PEOPLE; stable project state→PROJECTS; volatile active state→CURRENT_CONTEXT. Do not duplicate one item across sources merely because it relates to them.

### NONE
Do not project this item into AI Brain. Use when cloud_safe=false or semantic cross-source reasoning would not materially benefit.

### CURRENT_CONTEXT
Active current state useful for continuing ongoing work: important open threads, current priorities, unresolved blockers, near-term state, and information whose relevance depends on what is happening now. Periodically regenerate; do not make a historical archive.

### PROJECTS
Durable state of a concrete project: purpose, architecture, components, constraints, milestones, important implementation state and stable project context. An explicit decision belongs in DECISIONS.

### DECISIONS
Explicit accepted decisions, policies, chosen approaches, important rejected alternatives when their rationale matters, and changes or supersessions of previous decisions.

### EXPERIMENTS
Hypotheses, experiment or evaluation setup, tests, observations, measurements and outcomes. Evidence-producing trials rather than general lessons.

### RESEARCH_INSIGHTS
Durable research findings, synthesis, external-source conclusions, important comparisons, patterns and reusable insights.

### PEOPLE
Durable, appropriate, cloud-safe context about people and working relationships useful for future interaction or collaboration. Exclude sensitive or incidental personal information.

### LESSONS_LEARNED
Reusable lessons, heuristics, failure modes, successful patterns and generalizable conclusions derived from experience.

### REVIEW
Projection may be useful but the correct source cannot be chosen reliably.
