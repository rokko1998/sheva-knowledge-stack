"""Read the TypeSafe token without storing it in the repository or argv."""
from __future__ import annotations

import getpass
import os
import subprocess

KEYCHAIN_SERVICE = "sheva-knowledge-stack/typesafe"


def _security(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/usr/bin/security", *args],
        text=True,
        capture_output=True,
        timeout=10,
    )


def typesafe_key_available() -> bool:
    if os.environ.get("TYPESAFE_API_KEY"):
        return True
    result = _security("find-generic-password", "-a", getpass.getuser(), "-s", KEYCHAIN_SERVICE)
    return result.returncode == 0


def get_typesafe_key() -> str | None:
    from_env = os.environ.get("TYPESAFE_API_KEY")
    if from_env:
        return from_env
    result = _security("find-generic-password", "-a", getpass.getuser(), "-s", KEYCHAIN_SERVICE, "-w")
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None
