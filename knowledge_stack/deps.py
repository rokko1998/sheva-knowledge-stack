from __future__ import annotations

import os
import shutil
import subprocess
import sys
import json
import tempfile
from datetime import date
from pathlib import Path

from .paths import DATAWEAVE, LOCK, ROOT, RUNTIME, dataweave_python, lockfile


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


def promote_runtime(revision: str) -> dict:
    """Test a fetched upstream commit, then switch the pinned worktree and lock."""
    dependency = lockfile()["obsidian_dataweave"]
    source = Path(dependency["source"])
    current = dependency["commit"]
    candidate = _git("rev-parse", "--verify", f"{revision}^{{commit}}", cwd=source)
    if candidate == current:
        return {"status": "already_active", "commit": current}
    if subprocess.run(["git", "merge-base", "--is-ancestor", candidate, "origin/main"], cwd=source).returncode:
        raise RuntimeError("Candidate commit is not on fetched origin/main")
    if _git("status", "--porcelain", cwd=source) or _git("status", "--porcelain", cwd=ROOT):
        raise RuntimeError("Both source and knowledge-stack worktrees must be clean before promotion")
    active = verify_runtime()
    candidate_dir = RUNTIME / "versions" / candidate
    if not candidate_dir.exists():
        subprocess.run(["git", "worktree", "add", "--detach", str(candidate_dir), candidate], cwd=source, check=True)
    if _git("rev-parse", "HEAD", cwd=candidate_dir) != candidate or _git("status", "--porcelain", cwd=candidate_dir):
        raise RuntimeError("Candidate worktree is dirty or points to another commit")
    for relative in ("AGENTS.md", "scripts/generate_notes.py", "scripts/vault_writer.py", "scripts/memory_index.py", "scripts/process_notebook.py", "scripts/wiki_compile.py", "scripts/wiki_models.py"):
        if not (candidate_dir / relative).is_file():
            raise RuntimeError(f"Candidate lacks required DataWeave contract: {relative}")
    config_link = candidate_dir / "config.toml"
    config_target = source / "config.toml"
    if config_link.exists() or config_link.is_symlink():
        if not (config_link.is_symlink() and config_link.resolve() == config_target.resolve()):
            raise RuntimeError("Candidate config.toml is not the approved machine config")
    else:
        config_link.symlink_to(config_target)

    subprocess.run([str(dataweave_python()), "-m", "pytest", "-q"], cwd=candidate_dir, check=True)
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"], cwd=ROOT, check=True)
    for script in ("generate_notes.py", "vault_writer.py", "memory_index.py", "process_notebook.py"):
        subprocess.run([str(dataweave_python()), f"scripts/{script}", "--help"], cwd=candidate_dir, check=True, capture_output=True)
    subprocess.run([str(dataweave_python()), "-c",
                    "from scripts.wiki_models import parse_changeset; "
                    "from scripts.wiki_compile import (snapshot_wiki_space, validate_changeset, materialize_to_staging, "
                    "_append_log_to_staging, regenerate_index_to_staging, write_to_vault)"],
                   cwd=candidate_dir, check=True, capture_output=True)
    with tempfile.TemporaryDirectory(prefix="dataweave-contract-", dir=RUNTIME) as tmp:
        test_root = Path(tmp)
        sample = test_root / "atom-plan.json"
        sample.write_text(json.dumps({"notes": [{
            "title": "DataWeave compatibility probe", "tags": ["codex-wrapup"],
            "date": date.today().isoformat(), "source_doc": "compatibility-probe",
            "note_type": "atomic", "body": "A harmless generated note in temporary staging.",
        }]}), encoding="utf-8")
        staged = test_root / "notes"
        subprocess.run(
            [str(dataweave_python()), "scripts/generate_notes.py", str(sample),
             "--staging-dir", str(staged)], cwd=candidate_dir, check=True,
            capture_output=True, text=True,
        )
        if len(list(staged.glob("*.md"))) != 1:
            raise RuntimeError("Candidate DataWeave did not generate the expected staged note")

    registry_source = active / "processed.json"
    registry_target = candidate_dir / "processed.json"
    if registry_target.exists() and registry_source.exists() and registry_target.read_bytes() != registry_source.read_bytes():
        raise RuntimeError("Candidate has a different processed.json; reconcile before promotion")
    if registry_source.exists() and not registry_target.exists():
        shutil.copy2(registry_source, registry_target)
    previous_lock = LOCK.read_bytes()
    next_lock = lockfile()
    next_lock["obsidian_dataweave"]["commit"] = candidate
    next_bytes = (json.dumps(next_lock, ensure_ascii=False, indent=2) + "\n").encode()
    next_link = DATAWEAVE.with_name(".ObsidianDataWeave.next")
    try:
        if next_link.exists() or next_link.is_symlink():
            next_link.unlink()
        next_link.symlink_to(candidate_dir)
        os.replace(next_link, DATAWEAVE)
        lock_tmp = LOCK.with_suffix(".json.next")
        lock_tmp.write_bytes(next_bytes)
        os.replace(lock_tmp, LOCK)
        verify_runtime()
        subprocess.run(["git", "add", "deps.lock.json"], cwd=ROOT, check=True)
        subprocess.run(["git", "commit", "-m", f"chore: promote ObsidianDataWeave to {candidate[:12]}"], cwd=ROOT, check=True)
    except Exception:
        rollback_link = DATAWEAVE.with_name(".ObsidianDataWeave.rollback")
        rollback_link.symlink_to(active)
        os.replace(rollback_link, DATAWEAVE)
        LOCK.write_bytes(previous_lock)
        subprocess.run(["git", "reset", "--", "deps.lock.json"], cwd=ROOT, capture_output=True)
        raise
    return {"status": "promoted", "previous": current, "active": candidate}
