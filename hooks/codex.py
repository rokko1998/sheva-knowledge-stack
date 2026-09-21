#!/usr/bin/env python3
"""Fast Codex lifecycle bridge. No model startup or network writes here."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from knowledge_stack.state import capture, pending  # noqa: E402
from knowledge_stack.notebook import projection  # noqa: E402
from knowledge_stack.paths import STATE  # noqa: E402


END_PATTERNS = (
    r"^(?:ну\s+)?(?:всё|все)\s+(?:на сегодня|пока)[.!\s]*$",
    r"^(?:спасибо[,!\s]+)?(?:закончили|закрываем|на сегодня всё|на сегодня все)[.!\s]*$",
    r"^(?:спасибо[,!\s]+)?(?:потом продолжим|продолжим завтра)[.!\s]*$",
    r"^/wrapup\s*$",
)


def output_context(name: str, message: str) -> None:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": name, "additionalContext": message}}, ensure_ascii=False))


def main() -> None:
    event = json.load(sys.stdin)
    name = event.get("hook_event_name")
    if name in {"SessionEnd", "PreCompact"}:
        capture(event)
        return
    if name == "SessionStart":
        notices = []
        items = pending()
        if items:
            paths = ", ".join(str(x) for x in items)
            notices.append("Есть незавершённые итоги прошлых сессий: " + paths + ". После выполнения запроса пользователя обработай их через установленный навык wrapup и sheva-knowledge-stack; не публикуй сырую стенограмму. Отметь завершёнными только после успешной локальной записи.")
        outbox = STATE / "outbox"
        if outbox.exists() and any(outbox.glob("*.json")):
            registry_path = STATE / "publication.json"
            registry = json.loads(registry_path.read_text(encoding="utf-8")) if registry_path.exists() else {}
            try:
                _, digest = projection()
                if digest != registry.get("content_hash"):
                    notices.append("Есть проверенные записи, ожидающие публикации в AI Brain. После основного запроса повтори `python3 -m knowledge_stack publish`, если сеть Google доступна.")
            except (ValueError, KeyError, json.JSONDecodeError):
                notices.append("Очередь AI Brain требует проверки перед публикацией: `python3 -m knowledge_stack status`.")
        if notices:
            output_context(name, " ".join(notices))
        return
    if name == "UserPromptSubmit":
        prompt = str(event.get("prompt") or "").strip().casefold()
        if len(prompt) <= 180 and any(re.fullmatch(pattern, prompt) for pattern in END_PATTERNS):
            output_context(name, "Пользователь явно завершает разговор. До окончания этого turn выполни навык wrapup и сохрани долговременно полезные итоги через sheva-knowledge-stack. Если нет полезных фактов, отметь это кратко.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"knowledge-stack hook: {exc}", file=sys.stderr)
        raise SystemExit(1)
