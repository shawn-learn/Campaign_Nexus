#!/usr/bin/env python
"""Dev launcher: run the Campaign Nexus backend and frontend together.

    python start.py

Starts the FastAPI backend (uvicorn on http://127.0.0.1:8000) and the Vite frontend
(http://localhost:5200, which proxies /api to the backend). Press Ctrl+C to stop both;
child process trees are cleaned up on exit.
"""

from __future__ import annotations

import signal
import subprocess
import sys
import time
from pathlib import Path

# The Windows console defaults to cp1252; make our output UTF-8-safe regardless.
for _stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(_stream, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
IS_WINDOWS = sys.platform == "win32"

BACKEND_CMD = "uv run uvicorn app.main:app --host 127.0.0.1 --port 8000"
FRONTEND_CMD = "npm run dev"


def _spawn(cmd: str, cwd: Path) -> subprocess.Popen[bytes]:
    # New process group/session so we can terminate the whole tree (uvicorn/vite children).
    kwargs: dict[str, object] = {"cwd": str(cwd), "shell": True}
    if IS_WINDOWS:
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(cmd, **kwargs)  # type: ignore[call-overload]


def _terminate(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    if IS_WINDOWS:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True,
            check=False,
        )
    else:
        import os

        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass


def main() -> int:
    if not (BACKEND_DIR / "pyproject.toml").exists() or not (FRONTEND_DIR / "package.json").exists():
        print("error: run this from the repository root (backend/ and frontend/ not found).")
        return 1

    print("Starting Campaign Nexus...")
    print("  backend  -> http://127.0.0.1:8000  (API docs at /docs)")
    print("  frontend -> http://localhost:5200")
    print("Press Ctrl+C to stop.\n")

    backend = _spawn(BACKEND_CMD, BACKEND_DIR)
    frontend = _spawn(FRONTEND_CMD, FRONTEND_DIR)
    procs = {"backend": backend, "frontend": frontend}

    try:
        while True:
            for name, proc in procs.items():
                code = proc.poll()
                if code is not None:
                    print(f"\n{name} exited with code {code}; shutting down the other process.")
                    return code or 0
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping...")
        return 0
    finally:
        for proc in procs.values():
            _terminate(proc)


if __name__ == "__main__":
    raise SystemExit(main())
