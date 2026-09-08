"""Bootstrap optional open-source solvers for RoboCAD deep multi-physics.

This script is a convenience helper, not a required installer. It detects the
host platform and tries to install the following GPL/opensource solvers via the
platform's native package manager:

- CalculiX (ccx) — structural FEA
- ElmerFEM (ElmerSolver) — multiphysics / thermal
- OpenFOAM (blockMesh/simpleFoam) — CFD
- Gmsh — mesh generation helper

On Windows it falls back to printing download URLs because these solvers are
usually distributed as standalone binaries or via WSL/Docker.

All solvers remain optional. RoboCAD falls back to lightweight built-in
estimates when a solver is not installed.
"""
from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

SOLVER_PACKAGES: dict[str, dict[str, Any]] = {
    "gmsh": {
        "apt": "gmsh",
        "brew": "gmsh",
        "pacman": "gmsh",
        "command": "gmsh",
    },
    "calculix": {
        "apt": "calculix-ccx",
        "brew": None,
        "pacman": "calculix",
        "command": "ccx",
        "urls": {
            "linux": "https://www.calculix.de",
            "windows": "https://www.calculix.de",
        },
    },
    "elmerfem": {
        "apt": None,
        "snap": "elmerfem-csc",
        "brew": None,
        "pacman": "elmerfem",
        "command": "ElmerSolver",
        "urls": {"linux": "https://www.elmerfem.org/blog/binaries/", "windows": "https://www.elmerfem.org/blog/binaries/"},
    },
    "openfoam": {
        "apt": None,
        "brew": "openfoam",
        "pacman": "openfoam",
        "command": "blockMesh",
        "urls": {
            "linux": "https://openfoam.org/download/",
            "windows": "https://openfoam.org/download/",
        },
    },
}


def _run(cmd: list[str], check: bool = True, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=check, timeout=timeout)


def _detect_pm() -> str | None:
    """Return a supported package manager key or None."""
    if sys.platform == "win32":
        return None
    if shutil.which("apt-get"):
        return "apt"
    if shutil.which("brew"):
        return "brew"
    if shutil.which("pacman"):
        return "pacman"
    if shutil.which("snap"):
        return "snap"
    return None


def _install_with_pm(pm: str, packages: list[str], dry_run: bool = False) -> bool:
    if dry_run:
        print(f"[dry-run] Would run: {pm} install {' '.join(packages)}")
        return True
    try:
        if pm == "apt":
            _run(["sudo", "apt-get", "update"], check=False, timeout=120)
            _run(["sudo", "apt-get", "install", "-y", *packages])
        elif pm == "brew":
            _run(["brew", "install", *packages])
        elif pm == "pacman":
            _run(["sudo", "pacman", "-S", "--noconfirm", *packages])
        elif pm == "snap":
            _run(["sudo", "snap", "install"] + packages)
        else:
            print(f"Unsupported package manager: {pm}")
            return False
        return True
    except subprocess.CalledProcessError as exc:
        print(f"Install command failed: {exc}")
        print(exc.stderr)
        return False


def _solver_installed(command: str) -> bool:
    return shutil.which(command) is not None


def _install_solver(name: str, dry_run: bool = False) -> bool:
    spec = SOLVER_PACKAGES.get(name)
    if not spec:
        print(f"Unknown solver: {name}")
        return False
    if _solver_installed(spec["command"]):
        print(f"{name}: already installed ({shutil.which(spec['command'])})")
        return True

    pm = _detect_pm()
    pkg = spec.get(pm)
    if sys.platform == "win32" or pm is None or pkg is None:
        url = spec.get("urls", {}).get("linux" if sys.platform != "win32" else "windows", "https://robocad.readthedocs.io")
        if dry_run:
            print(f"{name}: manual install required on this platform. See {url}")
            return True
        print(f"{name}: please install manually. See {url}")
        return False

    print(f"{name}: installing via {pm} ({pkg})...")
    return _install_with_pm(pm, [pkg], dry_run=dry_run)


def install_all(dry_run: bool = False, solvers: list[str] | None = None) -> dict[str, bool]:
    solvers = solvers or list(SOLVER_PACKAGES.keys())
    results: dict[str, bool] = {}
    for name in solvers:
        results[name] = _install_solver(name, dry_run=dry_run)
    return results


def print_summary(results: dict[str, bool]) -> None:
    print("\nSolver bootstrap summary:")
    print("-" * 40)
    for name, ok in results.items():
        status = "OK" if ok else "MISSING/MANUAL"
        print(f"  {name}: {status}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap optional open-source solvers for RoboCAD.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands instead of running them.")
    parser.add_argument("--solvers", nargs="+", choices=list(SOLVER_PACKAGES.keys()), help="Solvers to install (default: all).")
    parser.add_argument("--check", action="store_true", help="Only check which solvers are already installed.")
    args = parser.parse_args(argv)

    if args.check:
        print("Checking installed solvers...")
        for name, spec in SOLVER_PACKAGES.items():
            cmd = spec["command"]
            print(f"  {name}: {'found' if shutil.which(cmd) else 'not found'} ({cmd})")
        return 0

    results = install_all(dry_run=args.dry_run, solvers=args.solvers)
    print_summary(results)
    return 0 if all(results.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
