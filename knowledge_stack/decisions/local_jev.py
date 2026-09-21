from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from contextlib import contextmanager
from urllib.error import URLError
from urllib.request import Request, urlopen

from ..paths import JEV_ROOT, JEV_URL, lockfile


def _request(path: str, payload: dict | None = None, timeout: float = 5) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode() if payload else None
    req = Request(JEV_URL + path, data=body, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=timeout) as response:
        return json.load(response)


def ready() -> bool:
    try:
        return _request("/health", timeout=0.4).get("status") == "ready"
    except (OSError, URLError, ValueError):
        return False


@contextmanager
def runtime(auto_start: bool = True):
    child = None
    if not ready() and auto_start:
        uv = "/Users/sheva/.local/bin/uv"
        if not (JEV_ROOT / ".venv/bin/uvicorn").exists() and not os.path.isfile(uv):
            raise RuntimeError("Jev runtime is unavailable")
        env = os.environ.copy()
        env["HF_HUB_OFFLINE"] = "1"
        env["TRANSFORMERS_OFFLINE"] = "1"
        child = subprocess.Popen(
            [uv, "run", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "4319"],
            cwd=JEV_ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and child.poll() is None:
            if ready():
                break
            time.sleep(0.3)
    if not ready():
        if child is not None:
            _stop(child)
        raise RuntimeError("Jev did not become ready")
    try:
        yield
    finally:
        if child is not None:
            _stop(child)


def _stop(child: subprocess.Popen) -> None:
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        child.wait(timeout=4)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        child.wait(timeout=2)


def choice(context: str, options: list[str], timeout: float = 15) -> tuple[str, float]:
    result = _request("/choice", {"context": context, "options": options}, timeout=timeout)
    selected = result.get("choice")
    confidence = result.get("confidence")
    if selected not in options or not isinstance(confidence, (float, int)):
        raise ValueError("Invalid Jev choice response")
    if result.get("prompt_version") != lockfile()["local_jev_contract"]:
        raise ValueError("Jev prompt contract changed; review before continuing")
    return selected, float(confidence)
