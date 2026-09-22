from __future__ import annotations

import json
import ssl
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import certifi

from ..credentials import get_typesafe_key
from ..paths import lockfile
from ..policy import choice_questions, shared_policy


ENDPOINT = "https://api.typesafe.ai/v1/systemone"


@dataclass(frozen=True)
class ChoiceResult:
    choice: str
    confidence: float
    probabilities: dict[str, float]


@dataclass(frozen=True)
class JevResult:
    answers: dict[str, ChoiceResult]
    model: str


class TypeSafeJevProvider:
    """Official SystemOne Choice API; policy prose is loaded from Git files."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or get_typesafe_key()
        if not self.api_key:
            raise RuntimeError("TypeSafe token is not in macOS Keychain or TYPESAFE_API_KEY")

    def _ask(self, policy_name: str, state: dict) -> JevResult:
        questions = choice_questions(policy_name)
        payload = {
            "state": {"policy": shared_policy(), **state},
            "model": lockfile()["jev_api_model"],
            "questions": questions,
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
        raw_answers = data.get("answers") if isinstance(data, dict) else None
        if not isinstance(raw_answers, dict):
            raise ValueError("TypeSafe API response has no answers map")
        answers = {name: self._parse_choice(raw_answers.get(name), definition["criteria"])
                   for name, definition in questions.items()}
        model = data.get("model")
        if not isinstance(model, str) or not model:
            raise ValueError("TypeSafe API response has no model")
        return JevResult(answers=answers, model=model)

    def pass_a(self, candidate: dict) -> JevResult:
        return self._ask("pass-a", {"candidate": candidate})

    def pass_b(self, candidate: dict, canonical_matches: list[dict], wiki_candidates: list[dict]) -> JevResult:
        return self._ask("pass-b", {
            "candidate": candidate,
            "canonical_matches": canonical_matches,
            "wiki_candidates": wiki_candidates,
            "cloud_safe": candidate.get("cloud_safe") is True,
        })

    def end_intent(self, message: str) -> JevResult:
        return self._ask("end-intent", {"latest_user_message": message})

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
