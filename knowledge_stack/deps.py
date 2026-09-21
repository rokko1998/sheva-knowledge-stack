from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .paths import DATAWEAVE, RUNTIME, dataweave_python, lockfile


def _git(*args: str, cwd: Path) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def install_runtime() -> Path:
    """Create an immutable-by-convention worktree at the approved upstream commit."""
    dependency = lockfile()["obsidian_dataweave"]
    source = Path(dependency["source"])
    commit = dependency["commit"]
    if not source.is_dir() or not dataweave_python().is_file():
        raise RuntimeError("ObsidianDataWeave source or virtualenv is missing")
    if _git("cat-file", "-t", commit, cwd=source) != "commit":
        raise RuntimeError("Pinned DataWeave commit is unavailable locally")
    version_dir = RUNTIME / "versions" / commit
    if not version_dir.exists():
        version_dir.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "worktree", "add", "--detach", str(version_dir), commit], cwd=source, check=True)
    if _git("rev-parse", "HEAD", cwd=version_dir) != commit:
        raise RuntimeError("DataWeave runtime commit differs from deps.lock")
    config_target = source / "config.toml"
    config_link = version_dir / "config.toml"
    if not config_target.exists():
        raise RuntimeError("DataWeave machine config is missing")
    if not (config_link.is_symlink() and config_link.resolve() == config_target.resolve()):
        if config_link.exists() or config_link.is_symlink():
            raise RuntimeError(f"Unexpected runtime file: {config_link}")
        config_link.symlink_to(config_target)
    # DataWeave replaces processed.json atomically. A symlink would be replaced
    # on the first write and silently split the registry from its source.
    registry = version_dir / "processed.json"
    if registry.is_symlink() and registry.resolve() == (source / "processed.json").resolve():
        registry.unlink()
    if not registry.exists() and (source / "processed.json").exists():
        shutil.copy2(source / "processed.json", registry)
    DATAWEAVE.parent.mkdir(parents=True, exist_ok=True)
    if DATAWEAVE.is_symlink() and DATAWEAVE.resolve() == version_dir.resolve():
        return version_dir
    if DATAWEAVE.exists() or DATAWEAVE.is_symlink():
        raise RuntimeError("Active runtime exists and differs; use promote after verification")
    tmp_link = DATAWEAVE.with_name(".ObsidianDataWeave.next")
    if tmp_link.exists() or tmp_link.is_symlink():
        tmp_link.unlink()
    tmp_link.symlink_to(version_dir)
    os.replace(tmp_link, DATAWEAVE)
    return version_dir


def verify_runtime() -> Path:
    if not DATAWEAVE.is_symlink():
        raise RuntimeError("Pinned DataWeave runtime not installed; run `setup`")
    actual = DATAWEAVE.resolve()
    expected = lockfile()["obsidian_dataweave"]["commit"]
    if _git("rev-parse", "HEAD", cwd=actual) != expected:
        raise RuntimeError("Pinned DataWeave runtime changed unexpectedly")
    if not (actual / "config.toml").exists():
        raise RuntimeError("Pinned DataWeave runtime has no config")
    return actual
