"""Load versioned Choice semantics without duplicating their prose in code."""
from __future__ import annotations

from .paths import ROOT

CHOICES = {
    "pass-a": {"evidence_support": ("SUPPORTED", "UNSUPPORTED", "UNCERTAIN"), "retention": ("KEEP", "DROP", "UNCERTAIN")},
    "pass-b": {
        "canonical_relation": ("NEW", "DUPLICATE", "UPDATE_EXISTING", "CONFLICT", "UNCERTAIN"),
        "canonical_representation": ("NONE", "ATOMIC", "WIKI", "REVIEW"),
        "ai_brain_bucket": ("NONE", "CURRENT_CONTEXT", "PROJECTS", "DECISIONS", "EXPERIMENTS", "RESEARCH_INSIGHTS", "PEOPLE", "LESSONS_LEARNED", "REVIEW"),
    },
    "end-intent": {"end_intent": ("SESSION_END", "CONTINUE", "UNCERTAIN")},
}


def choice_questions(policy_name: str) -> dict:
    expected = CHOICES[policy_name]
    path = ROOT / "policies" / "jev" / f"{policy_name}.md"
    lines = path.read_text(encoding="utf-8").splitlines()
    preamble: list[str] = []
    questions: dict[str, dict] = {}
    current_question: str | None = None
    current_option: str | None = None
    option_lines: list[str] = []

    def finish_option() -> None:
        nonlocal option_lines
        if current_question and current_option:
            questions[current_question]["criteria"][current_option] = " ".join(option_lines).strip()
            option_lines = []

    for line in lines:
        if line.startswith("## "):
            finish_option()
            current_question = line[3:].strip()
            current_option = None
            questions[current_question] = {"type": "choice", "instructions": "", "criteria": {}}
        elif line.startswith("### "):
            finish_option()
            current_option = line[4:].strip()
        elif current_question is None:
            if line.strip() and not line.startswith("# "):
                preamble.append(line.strip())
        elif current_option is None:
            if line.startswith("Instructions:"):
                questions[current_question]["instructions"] = line.removeprefix("Instructions:").strip()
            elif line.strip():
                questions[current_question]["instructions"] += " " + line.strip()
        elif line.strip():
            option_lines.append(line.strip())
    finish_option()
    if set(questions) != set(expected):
        raise ValueError(f"Policy {path} has unexpected questions")
    for name, labels in expected.items():
        question = questions[name]
        if tuple(question["criteria"]) != labels or not question["instructions"] or any(not value for value in question["criteria"].values()):
            raise ValueError(f"Policy {path} has incomplete Choice {name}")
        question["instructions"] = " ".join(preamble) + " " + question["instructions"]
    return questions


def shared_policy() -> str:
    return (ROOT / "policies" / "knowledge-system.md").read_text(encoding="utf-8").strip()
