"""``robocad joints``: the M2 review surface.

The plan puts joint review in the CLI rather than a UI on purpose. The human accepts a proposal by
editing the YAML it wrote, and the same command that produced the proposal can then say what moved.
Nothing here decides a joint is correct: ``propose`` always writes ``review_required: true``; the
only way a joint becomes trusted is a person editing the file.

Commands::

    robocad joints propose <assembly.step> [--out FILE] [--quiet]
    robocad joints diff <proposal.yaml> <spec.yaml>

``propose`` reads CAD and writes a proposal. ``diff`` reads two YAML files and prints what changed;
it is the command a reviewer runs after editing, and after a new CAD revision arrives.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

DEFAULT_OUT = "robot.joints.proposed.yaml"

# CAD label names and YAML values are attacker-controlled: a STEP file can carry ESC sequences and
# a shared proposal can carry control characters. Printing them raw lets either one rewrite the
# reviewer's terminal (CWE-150). The file keeps the exact bytes; only the terminal view is escaped.
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def _safe(value: object, limit: int = 200) -> str:
    text = _CONTROL.sub("?", str(value))
    return text if len(text) <= limit else text[: limit - 1] + "…"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="robocad joints",
        description="Propose joints from CAD geometry, and diff proposals against a reviewed spec.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    propose = sub.add_parser("propose", help="infer joints from a STEP assembly")
    propose.add_argument("assembly", type=Path, help="STEP file to import")
    propose.add_argument(
        "--out", type=Path, default=None,
        help=f"proposal path (default: alongside the input, named {DEFAULT_OUT})",
    )
    propose.add_argument("--quiet", action="store_true", help="write the file, print only the path")
    propose.add_argument(
        "--notice", type=Path, default=None,
        help="file whose text is prepended as comments; use it for the licence notice and a "
             "statement of changes when the CAD belongs to someone else",
    )

    diff = sub.add_parser("diff", help="compare a proposal with a reviewed spec")
    diff.add_argument("before", type=Path)
    diff.add_argument("after", type=Path)

    args = parser.parse_args(argv)
    if args.command == "propose":
        return _propose(args.assembly, args.out, args.quiet, args.notice)
    return _diff(args.before, args.after)


def _propose(assembly_path: Path, out: Path | None, quiet: bool, notice_path: Path | None) -> int:
    from ai_cad.importers.features import FeatureExtractionError, extract_cylinders, summarize
    from ai_cad.importers.joints import (
        JointInferenceError,
        group_links,
        infer_joints,
        write_proposal,
    )
    from ai_cad.importers.step_import import StepImportError, import_step

    notice = None
    if notice_path is not None:
        try:
            notice = notice_path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"cannot read notice file: {exc}", file=sys.stderr)
            return 2

    try:
        assembly = import_step(assembly_path)
    except StepImportError as exc:
        print(f"cannot import {assembly_path}: {exc}", file=sys.stderr)
        return 2

    try:
        cylinders = extract_cylinders(assembly)
        links = group_links(assembly)
        proposal = infer_joints(assembly, links=links, cylinders=cylinders)
    except (FeatureExtractionError, JointInferenceError) as exc:
        # A guard that fired is a real answer: the command refuses rather than writing a proposal
        # that looks complete and is silently missing faces or bodies.
        print(f"refusing to write a partial proposal: {exc}", file=sys.stderr)
        return 3
    out = out or assembly_path.parent / DEFAULT_OUT
    write_proposal(proposal, out, notice=notice)

    if quiet:
        print(out)
        return 0

    roles = Counter(g.role for g in links)
    print(f"imported {assembly.part_count} parts / {assembly.instance_count} instances "
          f"from {assembly_path.name}")
    print(f"cylinders {summarize(cylinders)}")
    print(f"bodies {len(links)} " + " ".join(f"{role}={n}" for role, n in sorted(roles.items())))
    print(f"proposed joints {len(proposal.joints)}")
    for joint in proposal.joints:
        px = ", ".join(f"{v * 1e3:.1f}" for v in joint.axis_point)
        ax = ", ".join(f"{v:.3f}" for v in joint.axis_dir)
        print(f"  {_safe(joint.joint_id)} {_safe(joint.parent_link)} -> {_safe(joint.child_link)} "
              f"r={joint.evidence.radius_m * 1e3:.2f}mm conf={joint.confidence:.2f} "
              f"origin=({px})mm axis=({ax})")
    print(f"unresolved pairs {len(proposal.unresolved_pairs)} "
          f"(bodies that meet but share no bore/shaft interface)")
    for warning in proposal.warnings:
        print(f"warning: {_safe(warning, 500)}")
    print(f"wrote {out}")
    print("Every joint above is a PROPOSAL. Check the axes, add limits, and edit this file before "
          "anything compiles from it.")
    return 0


def _diff(before_path: Path, after_path: Path) -> int:
    from ai_cad.importers.joints import diff_proposals, read_proposal

    try:
        before = read_proposal(before_path)
        after = read_proposal(after_path)
    except FileNotFoundError as exc:
        print(f"no such file: {exc.filename}", file=sys.stderr)
        return 2
    except Exception as exc:  # malformed YAML is a user-facing error, not a crash
        print(f"cannot read proposal: {exc}", file=sys.stderr)
        return 2

    changes = diff_proposals(before, after)
    if not (changes["added"] or changes["removed"] or changes["changed"]):
        print(f"no joint changes ({changes['same']} joint(s) identical)")
        return 0

    for joint_id in changes["removed"]:
        joint = before.by_id()[joint_id]
        print(f"- {_safe(joint_id)} {_safe(joint.parent_link)} -> {_safe(joint.child_link)} "
              "(removed)")
    for joint_id in changes["added"]:
        joint = after.by_id()[joint_id]
        print(f"+ {_safe(joint_id)} {_safe(joint.parent_link)} -> {_safe(joint.child_link)} "
              "(added)")
    for entry in changes["changed"]:
        old, new = before.by_id()[entry["joint_id"]], after.by_id()[entry["joint_id"]]
        fields = ", ".join(entry["fields"])
        print(f"~ {_safe(entry['joint_id'])} {_safe(old.parent_link)} -> "
              f"{_safe(old.child_link)}: {fields}")
        if "axis_position" in entry["fields"]:
            moved = max(abs(a - b) for a, b in zip(old.axis_point, new.axis_point))
            print(f"    axis moved {moved * 1e3:.2f} mm")
        if "axis_direction" in entry["fields"]:
            print(f"    axis {tuple(round(v, 3) for v in old.axis_dir)} -> "
                  f"{tuple(round(v, 3) for v in new.axis_dir)}")
        if "topology" in entry["fields"]:
            print(f"    parent/child {_safe(old.parent_link)}->{_safe(old.child_link)} became "
                  f"{_safe(new.parent_link)}->{_safe(new.child_link)}")
    print(f"{changes['same']} joint(s) unchanged")
    return 0


__all__ = ["main"]
