"""Emit a progress report for the 7.7 -> 10.0 RoboCAD roadmap."""
from __future__ import annotations

import datetime
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLANS_DIR = REPO / "docs" / "superpowers" / "plans"

MILESTONES = [
    ("A", "Adaptive gait robustness", 0.0, 0.30),      # 7.7 -> 8.0
    ("B", "Structural dynamics / FEA", 0.30, 0.50),    # 8.0 -> 8.3
    ("C", "Workspace / collision / manipulability", 0.50, 0.65),  # 8.3 -> 8.5
    ("D", "Real end-effector families", 0.65, 0.75),    # 8.5 -> 8.7
    ("E", "Topology grammar", 0.75, 0.85),             # 8.7 -> 9.0
    ("F", "Real MuJoCo brain training", 0.85, 0.90),   # 9.0 -> 9.3
    ("G", "Automatic simulation certification", 0.90, 0.95),  # 9.3 -> 9.6
    ("H", "Sim-to-real bridge", 0.95, 0.98),             # 9.6 -> 9.8
    ("I", "Fully automated voice-to-certified-design", 0.98, 1.00),  # 9.8 -> 10.0
]


def _run(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, cwd=REPO, text=True, stderr=subprocess.STDOUT).strip()
    except subprocess.CalledProcessError as exc:
        return f"error: {exc.output.strip()}"


def _latest_commit() -> str:
    return _run(["git", "log", "-1", "--oneline"])


def _uncommitted_files() -> str:
    return _run(["git", "status", "--short"])


def _current_milestone() -> tuple[str, str, float, float, float]:
    """Detect active milestone from plan checkbox state.

    Returns (code, name, start_pct, end_pct, fraction_done).
    A milestone with no plan file is treated as not yet started (0% done) once
    all earlier milestones are fully checked off.
    """
    for code, name, start_pct, end_pct in MILESTONES:
        paths = list(PLANS_DIR.glob(f"*milestone-{code.lower()}-*.md"))
        if not paths:
            # No plan yet for this milestone: it is the next active one at 0%.
            return code, name, start_pct, end_pct, 0.0
        text = paths[0].read_text(encoding="utf-8")
        total = text.count("- [ ]") + text.count("- [x]")
        done = text.count("- [x]")
        fraction = done / total if total else 0.0
        if fraction < 1.0:
            return code, name, start_pct, end_pct, fraction
    # All milestones complete.
    code, name, start_pct, end_pct = MILESTONES[-1]
    return code, name, start_pct, end_pct, 1.0


def main() -> None:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    code, name, start_pct, end_pct, fraction = _current_milestone()
    milestone_span = end_pct - start_pct
    progress = start_pct + milestone_span * fraction
    completion = int(progress * 100)
    print(f"[{now}] RoboCAD 7.7 -> 10.0 progress report")
    print(f"  Active milestone: {code} — {name} ({start_pct*100:.0f}% -> {end_pct*100:.0f}%)")
    print(f"  Milestone tasks done: {int(fraction * 100)}%")
    print(f"  Overall completion: {completion}%")
    print(f"  Latest commit: {_latest_commit()}")
    uncommitted = _uncommitted_files()
    print(f"  Uncommitted changes: {len(uncommitted.splitlines()) if uncommitted else 0}")
    if uncommitted:
        print("  Files:")
        for line in uncommitted.splitlines()[:5]:
            print(f"    {line}")


if __name__ == "__main__":
    main()
