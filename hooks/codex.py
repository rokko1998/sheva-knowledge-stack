#!/usr/bin/env python3
"""Codex lifecycle bridge: bounded end-intent Choice and durable recovery markers."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from knowledge_stack.decisions.typesafe import TypeSafeJevProvider  # noqa: E402
from knowledge_stack.privacy import has_obvious_secret  # noqa: E402
from knowledge_stack.state import capture, pending  # noqa: E402

# Only a cheap trigger: Jev decides whether the *session* ends.
END_CUES = re.compile(r"(?:^/wrapup\s*$|\b(?:пока|завтра|позже|продолжим|отложим|пауза|стоп|кончено|закончили|заканчиваем|всё|все|хватит|на\s+сегодня|до\s+встречи|goodbye|bye|later|done|stop|finish|see\s+you)\b)", re.I)


def output_context(name: str, message: str) -> None:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": name, "additionalContext": message}}, ensure_ascii=False))


def main() -> None:
    event = json.load(sys.stdin)
    name = event.get("hook_event_name")
    if name in {"SessionEnd", "PreCompact"}:
        capture(event)
        return
    if name == "SessionStart":
        items = pending(100)
        if items:
            paths = ", ".join(str(x) for x in items)
            output_context(name, "Перед обычным запросом обработай незавершённые wrapup-сессии через навык wrapup: " + paths + ". Помечай выполненными только после успешной локальной записи либо осознанного решения, что сохранять нечего.")
        return
    if name != "UserPromptSubmit":
        return
    prompt = str(event.get("prompt") or "").strip()
    if not prompt or len(prompt) > 240 or not END_CUES.search(prompt):
        return
    if prompt.casefold() == "/wrapup":
        choice = "SESSION_END"
    elif has_obvious_secret(prompt) or re.search(r"https?://|[\w.+-]+@[\w.-]+\.\w+|/(?:Users|home)/", prompt):
        return
    else:
        try:
            choice = TypeSafeJevProvider().end_intent(prompt).answers["end_intent"].choice
        except (RuntimeError, ValueError, OSError) as exc:
            print(f"knowledge-stack end-intent unavailable: {exc}", file=sys.stderr)
            return
    if choice == "SESSION_END":
        path = capture(event)
        if path:
            output_context(name, "Пользователь завершает текущую сессию. В ЭТОМ turn, до финального ответа, выполни навык wrapup для текущего transcript. Pending locator: " + str(path) + ".")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"knowledge-stack hook: {exc}", file=sys.stderr)
        raise SystemExit(1)
