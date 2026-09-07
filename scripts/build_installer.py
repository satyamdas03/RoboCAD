"""Build a desktop installer bundle for RoboCAD using PyInstaller.

This is a skeleton build script. PyInstaller is intentionally not a hard
requirement; if it is missing the script prints install instructions and exits.

Usage:
    python scripts/build_installer.py [--onedir|--onefile]
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = REPO_ROOT / "dist"
SPEC_PATH = REPO_ROOT / "robocad.spec"


def _find_pyinstaller() -> str | None:
    return shutil.which("pyinstaller")


def _write_spec(onefile: bool) -> None:
    """Generate a PyInstaller spec tuned for RoboCAD."""
    mode = "onefile" if onefile else "onedir"
    hidden_imports = [
        "fastapi",
        "uvicorn",
        "pydantic",
        "build123d",
        "trimesh",
        "numpy",
        "anthropic",
        "web.backend.main",
    ]
    hidden_block = ", ".join(f"'{h}'" for h in hidden_imports)
    content = f'''# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['{REPO_ROOT.as_posix()}/start.py'],
    pathex=['{REPO_ROOT.as_posix()}'],
    binaries=[],
    datas=[('web/frontend/dist', 'web/frontend/dist')],
    hiddenimports=[{hidden_block}],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='RoboCAD',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
'''
    if not onefile:
        # For onedir we need a COLLECT block instead of EXE-only.
        content = f'''# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['{REPO_ROOT.as_posix()}/start.py'],
    pathex=['{REPO_ROOT.as_posix()}'],
    binaries=[],
    datas=[('web/frontend/dist', 'web/frontend/dist')],
    hiddenimports=[{hidden_block}],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='RoboCAD',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='RoboCAD',
)
'''
    SPEC_PATH.write_text(content, encoding="utf-8")
    print(f"Wrote PyInstaller spec to {SPEC_PATH}")


def _build_frontend() -> None:
    """Ensure the production frontend build exists."""
    frontend_dir = REPO_ROOT / "web" / "frontend"
    npm = shutil.which("npm")
    if not npm:
        raise RuntimeError("npm not found; cannot build frontend")
    print("Building frontend production bundle...")
    subprocess.run([npm, "run", "build"], cwd=str(frontend_dir), check=True)


def _run_pyinstaller(onefile: bool) -> None:
    pyinstaller = _find_pyinstaller()
    if not pyinstaller:
        print("PyInstaller not found. Install it with:")
        print("  pip install pyinstaller")
        sys.exit(1)
    _write_spec(onefile)
    print(f"Building PyInstaller bundle ({'onefile' if onefile else 'onedir'})...")
    subprocess.run([pyinstaller, str(SPEC_PATH), "--clean", "-y"], cwd=str(REPO_ROOT), check=True)
    print(f"Installer bundle written to {DIST_DIR}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a RoboCAD desktop installer bundle.")
    parser.add_argument("--onefile", action="store_true", help="Build a single executable file.")
    parser.add_argument("--skip-frontend", action="store_true", help="Skip frontend production build.")
    args = parser.parse_args(argv)

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    if not args.skip_frontend:
        _build_frontend()
    _run_pyinstaller(onefile=args.onefile)
    return 0


if __name__ == "__main__":
    sys.exit(main())
