"""One-command launcher for RoboCAD.

Checks the environment, installs missing dependencies, and starts the FastAPI
backend plus the Vite React frontend. Cross-platform: Windows, macOS, Linux.
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = REPO_ROOT / "requirements.txt"
FRONTEND_DIR = REPO_ROOT / "web" / "frontend"
BACKEND_MODULE = "web.backend.main:app"

REQUIRED_ENV = ["ANTHROPIC_API_KEY"]
OPTIONAL_ENV = [
    "NVIDIA_API_KEY",
    "LIVEKIT_URL",
    "LIVEKIT_API_KEY",
    "LIVEKIT_API_SECRET",
    "ONSHAPE_ACCESS_KEY",
    "ONSHAPE_SECRET_KEY",
]


def _log(message: str) -> None:
    print(f"[robocad] {message}", flush=True)


def check_python_version(min_version: tuple[int, int] = (3, 10)) -> dict[str, Any]:
    """Return status of the Python interpreter."""
    current = sys.version_info[:2]
    ok = current >= min_version
    return {
        "name": "python",
        "required": True,
        "ok": ok,
        "installed": True,
        "version": f"{current[0]}.{current[1]}",
        "message": "OK" if ok else f"Python >= {min_version[0]}.{min_version[1]} required",
    }


def find_command(name: str) -> str | None:
    """Locate an executable on PATH, with Windows fallbacks."""
    path = shutil.which(name)
    if path:
        return path
    if platform.system() == "Windows":
        for ext in (".exe", ".cmd", ".bat"):
            path = shutil.which(f"{name}{ext}")
            if path:
                return path
    return None


def check_command(name: str, required: bool = False, version_flag: str = "--version") -> dict[str, Any]:
    """Check availability of a system command and try to capture its version."""
    path = find_command(name)
    version = None
    if path:
        try:
            result = subprocess.run(
                [path, version_flag],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            version = (result.stdout.strip() or result.stderr.strip()).splitlines()[0]
        except Exception:
            version = "unknown"
    return {
        "name": name,
        "required": required,
        "ok": path is not None,
        "installed": path is not None,
        "path": path,
        "version": version,
        "message": "OK" if path else (f"{name} not found; required" if required else f"{name} not found; optional"),
    }


def check_virtualenv() -> dict[str, Any]:
    """Report whether we are running inside a virtual environment."""
    in_venv = (
        hasattr(sys, "real_prefix")
        or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix)
    )
    return {
        "name": "virtualenv",
        "required": False,
        "ok": True,  # not a blocker
        "installed": in_venv,
        "message": "active virtualenv" if in_venv else "no virtualenv (global interpreter)",
    }


def check_env_keys() -> list[dict[str, Any]]:
    """Return status rows for required and optional API keys."""
    rows: list[dict[str, Any]] = []
    for key in REQUIRED_ENV:
        value = os.environ.get(key)
        rows.append(
            {
                "name": key,
                "required": True,
                "ok": bool(value),
                "installed": bool(value),
                "message": "OK" if value else f"Missing required env var {key} in .env",
            }
        )
    for key in OPTIONAL_ENV:
        value = os.environ.get(key)
        rows.append(
            {
                "name": key,
                "required": False,
                "ok": True,
                "installed": bool(value),
                "message": "OK" if value else f"Missing optional env var {key}",
            }
        )
    return rows


def environment_report() -> list[dict[str, Any]]:
    """Collect all launcher environment checks."""
    rows: list[dict[str, Any]] = []
    rows.append(check_python_version())
    rows.append(check_virtualenv())
    rows.append(check_command("pip", required=True, version_flag="--version"))
    rows.append(check_command("node", required=False, version_flag="--version"))
    rows.append(check_command("npm", required=False, version_flag="--version"))
    rows.extend(check_env_keys())
    return rows


def report_is_ready(rows: list[dict[str, Any]]) -> bool:
    """Return True iff every required row is ok."""
    return all(row["ok"] for row in rows if row.get("required"))


def install_python_deps(requirements: Path = REQUIREMENTS, offline: bool = False) -> dict[str, Any]:
    """Install Python requirements with pip."""
    pip = find_command("pip") or find_command("pip3")
    if not pip:
        return {"name": "pip-install", "ok": False, "message": "pip not found"}
    cmd = [pip, "install", "-r", str(requirements)]
    if offline:
        cmd.append("--offline")
    try:
        _log("Installing Python dependencies...")
        subprocess.run(cmd, cwd=str(REPO_ROOT), check=True)
        return {"name": "pip-install", "ok": True, "message": "Python dependencies installed"}
    except subprocess.CalledProcessError as exc:
        return {"name": "pip-install", "ok": False, "message": f"pip install failed: {exc}"}


def install_frontend_deps(frontend_dir: Path = FRONTEND_DIR, offline: bool = False) -> dict[str, Any]:
    """Install frontend npm dependencies."""
    npm = find_command("npm")
    if not npm:
        return {"name": "npm-install", "ok": False, "message": "npm not found"}
    cmd = [npm, "install"]
    if offline:
        cmd.append("--offline")
    try:
        _log("Installing frontend dependencies...")
        subprocess.run(cmd, cwd=str(frontend_dir), check=True)
        return {"name": "npm-install", "ok": True, "message": "Frontend dependencies installed"}
    except subprocess.CalledProcessError as exc:
        return {"name": "npm-install", "ok": False, "message": f"npm install failed: {exc}"}


def start_backend(host: str = "0.0.0.0", port: int = 8000, reload: bool = True) -> subprocess.Popen[Any]:
    """Start the FastAPI backend as a subprocess."""
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        BACKEND_MODULE,
        "--host",
        host,
        "--port",
        str(port),
    ]
    if reload:
        cmd.append("--reload")
    _log(f"Starting backend on http://{host}:{port}")
    return subprocess.Popen(
        cmd,
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def start_frontend(port: int = 5173) -> subprocess.Popen[Any]:
    """Start the Vite dev server as a subprocess."""
    npm = find_command("npm")
    if not npm:
        raise RuntimeError("npm not found; cannot start frontend")
    env = os.environ.copy()
    env["PORT"] = str(port)
    cmd = [npm, "run", "dev"]
    _log(f"Starting frontend dev server on http://localhost:{port}")
    return subprocess.Popen(
        cmd,
        cwd=str(FRONTEND_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def wait_for_service(url: str, timeout: float = 30.0) -> bool:
    """Poll a URL until it responds or timeout is reached."""
    import urllib.request
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return True
        except Exception:
            time.sleep(0.5)
    return False


def stream_process(proc: subprocess.Popen[Any], prefix: str) -> None:
    """Print process stdout lines with a prefix until it closes."""
    if proc.stdout is None:
        return
    for line in proc.stdout:
        print(f"[{prefix}] {line.rstrip()}", flush=True)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the RoboCAD launcher."""
    parser = argparse.ArgumentParser(prog="robocad", description="Launch the RoboCAD backend and frontend.")
    parser.add_argument("--skip-deps", action="store_true", help="Skip dependency installation checks.")
    parser.add_argument("--offline", action="store_true", help="Try offline dependency installs (may fail).")
    parser.add_argument("--backend-port", type=int, default=8000, help="Port for the FastAPI backend.")
    parser.add_argument("--frontend-port", type=int, default=5173, help="Port for the Vite frontend dev server.")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind the backend.")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the browser automatically.")
    parser.add_argument("--no-reload", action="store_true", help="Disable backend auto-reload.")
    args = parser.parse_args(argv)

    _log("Checking environment...")
    env_rows = environment_report()
    for row in env_rows:
        status = "OK" if row["ok"] else ("MISSING" if row.get("required") else "OPTIONAL")
        _log(f"  {row['name']}: {row['message']} ({status})")

    if not report_is_ready(env_rows):
        _log("Environment not ready. Please fix the required items above.")
        return 1

    if not args.skip_deps:
        pip_result = install_python_deps(offline=args.offline)
        if not pip_result["ok"]:
            _log(f"Warning: {pip_result['message']}")
        node_present = any(
            row["ok"] for row in env_rows if row["name"] == "node"
        )
        if node_present:
            npm_result = install_frontend_deps(offline=args.offline)
            if not npm_result["ok"]:
                _log(f"Warning: {npm_result['message']}")
        else:
            _log("Node not found; skipping frontend dependency install.")

    backend = start_backend(host=args.host, port=args.backend_port, reload=not args.no_reload)
    frontend: subprocess.Popen[Any] | None = None

    try:
        backend_ready = wait_for_service(f"http://127.0.0.1:{args.backend_port}/health", timeout=30.0)
        if not backend_ready:
            _log("Backend did not become ready in time.")
            return 1

        node_present = find_command("node") is not None
        if node_present:
            frontend = start_frontend(port=args.frontend_port)
            frontend_ready = wait_for_service(f"http://localhost:{args.frontend_port}", timeout=45.0)
            if not frontend_ready:
                _log("Frontend did not become ready in time; continuing without it.")
        else:
            _log("Node not found; running backend only.")

        url = f"http://localhost:{args.frontend_port}"
        _log(f"RoboCAD is running: {url}")
        if not args.no_browser:
            try:
                webbrowser.open(url)
            except Exception as exc:
                _log(f"Could not open browser: {exc}")

        # Stream logs from both processes until the user kills the launcher.
        if frontend:
            import threading
            backend_thread = threading.Thread(target=stream_process, args=(backend, "backend"), daemon=True)
            frontend_thread = threading.Thread(target=stream_process, args=(frontend, "frontend"), daemon=True)
            backend_thread.start()
            frontend_thread.start()
            frontend.wait()
        else:
            stream_process(backend, "backend")

    except KeyboardInterrupt:
        _log("Shutting down...")
    finally:
        if frontend and frontend.poll() is None:
            frontend.terminate()
        if backend.poll() is None:
            backend.terminate()
        try:
            backend.wait(timeout=5)
        except subprocess.TimeoutExpired:
            backend.kill()
        if frontend:
            try:
                frontend.wait(timeout=5)
            except subprocess.TimeoutExpired:
                frontend.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
