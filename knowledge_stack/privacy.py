from __future__ import annotations

import re

# A narrow backstop for obvious credentials. Semantic privacy review stays with
# the agent before either external provider receives any candidate text.
SENSITIVE = re.compile(
    r"(?i)(?:api[_-]?key|secret|password|token)\s*[:=]\s*\S+|sk-[A-Za-z0-9_-]{16,}|-----BEGIN [A-Z ]+PRIVATE KEY-----"
)


def has_obvious_secret(text: str) -> bool:
    return bool(SENSITIVE.search(text))
