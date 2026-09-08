"""Environment health report for RoboCAD.

Prints the status of interpreters, solvers, API keys, and optional dependencies.
Can be run as ``python -m robocad.health`` or imported as ``health_report()``.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

REQUIRED_ENV = ["ANTHROPIC_API_KEY"]
OPTIONAL_ENV = [
    "NVIDIA_API_KEY",
    "LIVEKIT_URL",
    "LIVEKIT_API_KEY",
    "LIVEKIT_API_SECRET",
    "ONSHAPE_ACCESS_KEY",
    "ONSHAPE_SECRET_KEY",
]

SOLVERS: list[dict[str, Any]] = [
    {"name": "gmsh", "command": "gmsh", "version_flag": "-info", "optional": True,
     "install_hint": "https://gmsh.info/#Download or `pip install gmsh` (SDK wrapper; binary still required for meshing)"},
    {"name": "calculix", "command": "ccx", "version_flag": "-v", "optional": True,
     "install_hint": "Ubuntu/Debian: `sudo apt install calculix-ccx` | Windows: download https://www.calculix.de"},
    {"name": "elmerfem", "command": "ElmerSolver", "version_flag": "-v", "optional": True,
     "install_hint": "Ubuntu: `sudo snap install elmerfem` or build from https://www.elmerfem.org"},
    {"name": "openfoam", "command": "blockMesh", "version_flag": "-help", "optional": True,
     "install_hint": "Ubuntu: https://openfoam.org/download | Windows/WSL or Docker recommended"},
    {"name": "mujoco", "command": None, "python_module": "mujoco", "optional": True,
     "install_hint": "`pip install mujoco`"},
    {"name": "livekit", "command": None, "python_module": "livekit", "optional": True,
     "install_hint": "`pip install livekit livekit-agents` (requires LiveKit cloud or self-hosted server)"},
]


def _find_command(name: str) -> str | None:
    path = shutil.which(name)
    if path:
        return path
    if sys.platform == "win32":
        for ext in (".exe", ".cmd", ".bat"):
            path = shutil.which(f"{name}{ext}")
            if path:
                return path
    return None


def _run_version(command: str, flag: str) -> str:
    try:
        result = subprocess.run(
            [command, flag],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        text = (result.stdout.strip() or result.stderr.strip())
        lines = text.splitlines()
        return lines[0] if lines else "unknown"
    except Exception as exc:
        return f"error: {exc}"


def check_python_version(min_version: tuple[int, int] = (3, 10)) -> dict[str, Any]:
    current = sys.version_info[:2]
    ok = current >= min_version
    return {
        "group": "environment",
        "name": "python",
        "ok": ok,
        "version": f"{current[0]}.{current[1]}",
        "message": "OK" if ok else f"Python >= {min_version[0]}.{min_version[1]} required",
    }


def check_virtualenv() -> dict[str, Any]:
    in_venv = hasattr(sys, "real_prefix") or (
        hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
    )
    return {
        "group": "environment",
        "name": "virtualenv",
        "ok": True,
        "version": "yes" if in_venv else "no",
        "message": "virtualenv active" if in_venv else "system interpreter (virtualenv recommended)",
    }


def check_api_keys() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in REQUIRED_ENV:
        value = os.environ.get(key)
        rows.append(
            {
                "group": "api_keys",
                "name": key,
                "ok": bool(value),
                "version": "set" if value else "missing",
                "message": "OK" if value else f"Required env var {key} missing",
            }
        )
    for key in OPTIONAL_ENV:
        value = os.environ.get(key)
        rows.append(
            {
                "group": "api_keys",
                "name": key,
                "ok": True,
                "version": "set" if value else "missing",
                "message": "OK" if value else "optional key missing",
            }
        )
    return rows


def check_solvers() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for solver in SOLVERS:
        command = solver.get("command")
        py_module = solver.get("python_module")
        optional = solver.get("optional", True)
        version = None
        installed = False
        path: str | None = None

        if command:
            path = _find_command(command)
            installed = path is not None
            if path:
                version = _run_version(path, solver.get("version_flag", "--version"))
        elif py_module:
            try:
                __import__(py_module)
                installed = True
                version = "importable"
            except Exception as exc:
                version = f"not importable ({type(exc).__name__})"

        rows.append(
            {
                "group": "solvers",
                "name": solver["name"],
                "ok": installed or optional,
                "installed": installed,
                "version": version,
                "path": path,
                "install_hint": solver.get("install_hint"),
                "message": "OK" if installed else (f"optional solver {solver['name']} not found" if optional else f"{solver['name']} not found"),
            }
        )
    return rows


def check_python_deps() -> list[dict[str, Any]]:
    """Check that core Python dependencies are importable."""
    core = [
        "fastapi",
        "uvicorn",
        "pydantic",
        "build123d",
        "trimesh",
        "numpy",
        "anthropic",
    ]
    rows: list[dict[str, Any]] = []
    for module in core:
        try:
            mod = __import__(module)
            version = getattr(mod, "__version__", "importable")
            rows.append(
                {
                    "group": "python_deps",
                    "name": module,
                    "ok": True,
                    "version": version,
                    "message": "OK",
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "group": "python_deps",
                    "name": module,
                    "ok": False,
                    "version": "missing",
                    "message": f"Failed to import {module}: {exc}",
                }
            )
    return rows


def health_report() -> dict[str, Any]:
    """Return a structured health report dict."""
    rows: list[dict[str, Any]] = []
    rows.append(check_python_version())
    rows.append(check_virtualenv())
    rows.extend(check_api_keys())
    rows.extend(check_python_deps())
    rows.extend(check_solvers())
    required_ok = all(row["ok"] for row in rows if row.get("group") == "api_keys" and not row["name"].startswith("optional_"))
    return {"ready": required_ok, "checks": rows}


def print_health() -> None:
    """Print a human-readable health report."""
    report = health_report()
    print("RoboCAD Health Report")
    print("=" * 50)
    current_group = ""
    for row in report["checks"]:
        if row["group"] != current_group:
            current_group = row["group"]
            print(f"\n{current_group.upper()}")
        status = "[OK]" if row["ok"] else "[FAIL]"
        version = f" ({row.get('version')})" if row.get("version") else ""
        print(f"  {status} {row['name']}{version}: {row['message']}")
        if not row["ok"] and row.get("install_hint"):
            print(f"        install hint: {row['install_hint']}")
    print("\n" + ("READY" if report["ready"] else "NOT READY"))


def main() -> int:
    print_health()
    return 0 if health_report()["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
