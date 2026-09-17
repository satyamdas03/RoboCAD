"""Emit a progress report for the 7.7 -> 10.0 RoboCAD roadmap."""
from __future__ import annotations

import datetime
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

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


def _current_milestone() -> tuple[str, str, float, float]:
    # TODO: replace with real detection from docs/superpowers/plans/*.md state.
    # For now, hard-code Milestone A as active.
    return MILESTONES[0]


def main() -> None:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    code, name, start_pct, end_pct = _current_milestone()
    progress = start_pct  # placeholder; future version reads task checkboxes
    completion = int(progress * 100)
    print(f"[{now}] RoboCAD 7.7 -> 10.0 progress report")
    print(f"  Active milestone: {code} — {name} ({start_pct*100:.0f}% -> {end_pct*100:.0f}%)")
    print(f"  Overall completion: {completion}%")
    print(f"  Latest commit: {_latest_commit()}")
    uncommitted = _uncommitted_files()
    print(f"  Uncommitted changes: {len(uncommitted.splitlines()) if uncommitted else 0}")
    if uncommitted:
        print("  Files:")
        for line in uncommitted.splitlines()[:5]:
            print(f"    {line}")
    print("  Work completed so far: roadmap spec + Milestone A implementation plan committed.")
    print("  Next step: execute Milestone A tasks via subagent-driven development.")


if __name__ == "__main__":
    main()
