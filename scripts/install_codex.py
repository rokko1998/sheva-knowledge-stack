#!/usr/bin/env python3
"""Register the wrapup skill and lifecycle hooks without touching other entries."""
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


def managed_block() -> str:
    command = f"/usr/bin/python3 {HOOK}"
    return f'''{MARKER}
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
matcher = "^(startup|resume|compact)$"
[[hooks.SessionStart.hooks]]
type = "command"
command = "{command}"
timeout = 3
additionalContextLimit = 1600

[[hooks.UserPromptSubmit]]
[[hooks.UserPromptSubmit.hooks]]
type = "command"
command = "{command}"
timeout = 25
additionalContextLimit = 1600
'''


def main() -> None:
    if not CONFIG.is_file():
        raise SystemExit(f"Missing Codex config: {CONFIG}")
    original = CONFIG.read_text(encoding="utf-8")
    if MARKER in original:
        before, _, old_managed = original.partition(MARKER)
        if old_managed and "# " in old_managed:
            # This installer owns only the terminal managed block.
            raise SystemExit("Managed hook block is no longer terminal; reconcile manually")
        updated = before.rstrip() + "\n\n" + managed_block()
    else:
        updated = original.rstrip() + "\n\n" + managed_block()
    tomllib.loads(updated)
    if updated != original:
        backup = ROOT / ".runtime/backup" / f"config.toml.{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(CONFIG, backup)
        CONFIG.write_text(updated, encoding="utf-8")
        print(f"Installed hooks; config backup: {backup}")
    target = ROOT / "skills/wrapup"
    if SKILL.is_symlink() and SKILL.resolve() == target.resolve():
        print("Wrapup skill already linked")
        return
    if SKILL.exists() or SKILL.is_symlink():
        backup = ROOT / ".runtime/backup/wrapup-original"
        if backup.exists():
            raise SystemExit("Wrapup backup already exists; refusing to overwrite")
        shutil.move(SKILL, backup)
    SKILL.symlink_to(target)
    print(f"Linked wrapup skill: {SKILL} -> {target}")


if __name__ == "__main__":
    main()
