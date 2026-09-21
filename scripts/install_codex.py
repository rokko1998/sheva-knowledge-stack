#!/usr/bin/env python3
"""Register the knowledge-stack skill and fast lifecycle hooks in Codex."""
from __future__ import annotations

import shutil
import tomllib
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = Path.home() / ".codex/config.toml"
SKILL = Path.home() / ".agents/skills/wrapup"
MARKER = "# sheva-knowledge-stack lifecycle hooks"
HOOK = ROOT / "hooks/codex.py"


def main() -> None:
    if not CONFIG.is_file():
        raise SystemExit(f"Missing Codex config: {CONFIG}")
    original = CONFIG.read_text(encoding="utf-8")
    if MARKER not in original:
        backup = ROOT / ".runtime/backup" / f"config.toml.{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(CONFIG, backup)
        command = f"/usr/bin/python3 {HOOK}"
        addition = f'''

{MARKER}
[[hooks.SessionEnd]]
[[hooks.SessionEnd.hooks]]
type = "command"
command = "{command}"
timeout = 3

[[hooks.PreCompact]]
[[hooks.PreCompact.hooks]]
type = "command"
command = "{command}"
timeout = 3

[[hooks.SessionStart]]
matcher = "^(startup|resume)$"
[[hooks.SessionStart.hooks]]
type = "command"
command = "{command}"
timeout = 3
additionalContextLimit = 1000

[[hooks.UserPromptSubmit]]
[[hooks.UserPromptSubmit.hooks]]
type = "command"
command = "{command}"
timeout = 3
additionalContextLimit = 1000
'''
        updated = original + addition
        tomllib.loads(updated)
        CONFIG.write_text(updated, encoding="utf-8")
        print(f"Added hooks; config backup: {backup}")
    else:
        print("Hooks already present")
    target = ROOT / "skills/wrapup"
    if SKILL.is_symlink() and SKILL.resolve() == target.resolve():
        print("Wrapup skill already linked")
        return
    if SKILL.exists() or SKILL.is_symlink():
        backup = ROOT / ".runtime/backup/wrapup-original"
        if backup.exists():
            raise SystemExit("Wrapup backup already exists; refusing to overwrite")
        shutil.move(SKILL, backup)
        print(f"Saved original wrapup skill: {backup}")
    SKILL.symlink_to(target)
    print(f"Linked wrapup skill: {SKILL} -> {target}")


if __name__ == "__main__":
    main()
