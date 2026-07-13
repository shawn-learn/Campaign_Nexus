#!/usr/bin/env python
"""Dev launcher: run the Campaign Nexus backend and frontend together.

    python start.py

Starts the FastAPI backend (uvicorn on http://127.0.0.1:8000) and the Vite frontend
(http://localhost:5200, which proxies /api to the backend). Press Ctrl+C to stop both;
child process trees are cleaned up on exit.
"""

from __future__ import annotations

import shutil
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

UV_BIN = Path.home() / ".local" / "bin" / ("uv.exe" if IS_WINDOWS else "uv")
BACKEND_VENV_PYTHON = BACKEND_DIR / ".venv" / ("Scripts" if IS_WINDOWS else "bin") / (
    "python.exe" if IS_WINDOWS else "python"
)
BACKEND_REQUIRED_MODULES = (
    "fastapi",
    "uvicorn",
    "sqlalchemy",
    "alembic",
    "pydantic",
    "pydantic_settings",
    "jsonschema",
    "multipart",
)
BACKEND_CMD = (
    f'"{UV_BIN}" run uvicorn app.main:app --host 127.0.0.1 --port 8000'
    if UV_BIN.exists()
    else f'"{BACKEND_VENV_PYTHON}" -m uvicorn app.main:app --host 127.0.0.1 --port 8000'
)
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


def _module_available(python: Path, module: str) -> bool:
    code = (
        "import importlib.util, sys; "
        f"sys.exit(0 if importlib.util.find_spec({module!r}) else 1)"
    )
    return subprocess.run([str(python), "-c", code], check=False).returncode == 0


def _ensure_backend_requirements() -> None:
    if not BACKEND_VENV_PYTHON.exists():
        print("Creating backend virtual environment...")
        subprocess.run([sys.executable, "-m", "venv", str(BACKEND_DIR / ".venv")], check=True)

    if not _module_available(BACKEND_VENV_PYTHON, "pip"):
        print("Bootstrapping pip in the backend virtual environment...")
        subprocess.run([str(BACKEND_VENV_PYTHON), "-m", "ensurepip", "--upgrade"], check=True)

    missing = [module for module in BACKEND_REQUIRED_MODULES if not _module_available(BACKEND_VENV_PYTHON, module)]
    if missing:
        print(f"Installing missing backend dependencies: {', '.join(missing)}")
        subprocess.run([str(BACKEND_VENV_PYTHON), "-m", "pip", "install", "-e", "."], cwd=BACKEND_DIR, check=True)


def _ensure_frontend_requirements() -> None:
    if (FRONTEND_DIR / "node_modules").exists():
        return

    if shutil.which("npm") is None:
        print("error: npm is required to start the frontend development server.")
        raise SystemExit(1)

    print("Installing frontend dependencies...")
    subprocess.run(["npm", "install"], cwd=FRONTEND_DIR, check=True)


def main() -> int:
    if not (BACKEND_DIR / "pyproject.toml").exists() or not (FRONTEND_DIR / "package.json").exists():
        print("error: run this from the repository root (backend/ and frontend/ not found).")
        return 1

    _ensure_backend_requirements()
    _ensure_frontend_requirements()

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
