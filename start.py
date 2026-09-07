#!/usr/bin/env python3
"""One-command entry point to start RoboCAD.

Usage:
    python start.py
    python start.py --no-browser --backend-port 9000
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure the repo root is on sys.path so ``robocad`` is importable even when the
# script is invoked via a symlink or from a different directory.
REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from robocad.launcher import main

if __name__ == "__main__":
    sys.exit(main())
