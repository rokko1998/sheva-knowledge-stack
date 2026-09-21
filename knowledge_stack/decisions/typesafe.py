from __future__ import annotations

import json
import ssl
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import certifi

from ..paths import lockfile
from ..credentials import get_typesafe_key


ENDPOINT = "https://api.typesafe.ai/v1/systemone"


@dataclass(frozen=True)
class ChoiceResult:
    choice: str
    confidence: float
    probabilities: dict[str, float]


@dataclass(frozen=True)
class CandidateDecision:
    retention: ChoiceResult
    route: ChoiceResult
    model: str


class TypeSafeJevProvider:
    """Official TypeSafe Jev API adapter; no local-model behavior leaks here."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or get_typesafe_key()
        if not self.api_key:
            raise RuntimeError("TypeSafe token is not in macOS Keychain or TYPESAFE_API_KEY")

    def evaluate(self, title: str, body: str) -> CandidateDecision:
        payload = {
            "state": {
                "candidate": {"title": title[:240], "body": body[:1800]},
                "architecture": {
                    "canonical": "Obsidian Brain via ObsidianDataWeave vault_writer",
                    "projection": "AI Brain NotebookLM curated external copy",
                },
            },
            "model": lockfile()["jev_api_model"],
            "questions": {
                "retention": {
                    "type": "choice",
                    "instructions": "Should this candidate be kept as durable knowledge from the session?",
                    "criteria": {
                        "KEEP": "Specific reusable decision, correction, lesson, preference, verified result, or actionable open thread.",
                        "DROP": "Routine command output, transient status, duplicate fact, or material fully recoverable from source code without a separate lesson.",
                        "UNCERTAIN": "Insufficient provenance, likely conflict with existing memory, or unclear lasting value.",
                    },
                },
                "route": {
                    "type": "choice",
                    "instructions": "If retained, where should this candidate go in the knowledge system?",
                    "criteria": {
                        "LOCAL_ONLY": "Write a new canonical Obsidian atomic note; no external projection.",
                        "LOCAL_AND_AI_BRAIN": "Write the canonical Obsidian note and queue a concise, redacted AI Brain projection.",
                        "REVIEW": "Requires semantic merge into an existing note, wiki work, sensitive-content review, or unclear destination.",
                    },
                },
            },
        }
        request = Request(
            ENDPOINT,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=15, context=ssl.create_default_context(cafile=certifi.where())) as response:
                data = json.load(response)
        except HTTPError as exc:
            raise RuntimeError(f"TypeSafe API returned HTTP {exc.code}") from exc
        except (URLError, TimeoutError) as exc:
            raise RuntimeError("TypeSafe API is unavailable") from exc
        answers = data.get("answers") if isinstance(data, dict) else None
        if not isinstance(answers, dict):
            raise ValueError("TypeSafe API response has no answers map")
        retention = self._parse_choice(answers.get("retention"), payload["questions"]["retention"]["criteria"])
        route = self._parse_choice(answers.get("route"), payload["questions"]["route"]["criteria"])
        model = data.get("model")
        if not isinstance(model, str) or not model:
            raise ValueError("TypeSafe API response has no model")
        return CandidateDecision(retention=retention, route=route, model=model)

    @staticmethod
    def _parse_choice(answer: object, criteria: dict) -> ChoiceResult:
        if not isinstance(answer, dict) or answer.get("type") != "choice":
            raise ValueError("TypeSafe API answer is not a Choice")
        selected = answer.get("choice")
        confidence = answer.get("confidence")
        probabilities = answer.get("probabilities")
        if selected not in criteria or not isinstance(confidence, (float, int)) or not 0 <= confidence <= 1:
            raise ValueError("TypeSafe API Choice selected an invalid option or confidence")
        if not isinstance(probabilities, dict) or set(probabilities) != set(criteria):
            raise ValueError("TypeSafe API Choice probabilities do not match criteria")
        if any(not isinstance(v, (float, int)) or not 0 <= v <= 1 for v in probabilities.values()):
            raise ValueError("TypeSafe API Choice contains an invalid probability")
        return ChoiceResult(str(selected), float(confidence), {str(k): float(v) for k, v in probabilities.items()})
