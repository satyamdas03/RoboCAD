"""Compile SO-101 from its STEP file and compare it with the published model.

Run:

    python scripts/demo_so101_twin.py --step path/to/so101.step --official path/to/so101_new_calib.urdf

Writes a bundle to ``docs/demo/so101/`` and a comparison to ``docs/demo/so101_vs_official.md``.
Nothing here is committed automatically: the bundle is derived from a third-party CAD file, and
whether it may be published is a decision for the person who owns that relationship, not for the
compiler.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ai_cad.compiler import compare, revision
from ai_cad.compiler.compile import compile_bundle, render_html

# Which of our bodies is which of theirs. This is a judgement from the two naming schemes, not a
# geometric result, and it is printed beside the numbers so a reader can map them differently.
BODY_MAP = {
    "base_so101": "base_link",
    "rotation_pitch_so101": "shoulder_link",
    "upper_arm_so101": "upper_arm_link",
    "under_arm_so101": "lower_arm_link",
    "wrist_roll_pitch_so100": "wrist_link",
    "wrist_roll_follower_so101": "gripper_link",
    "moving_jaw_so101": "moving_jaw_so101_v1_link",
}

JOINT_MAP = {
    "joint_1": "shoulder_pan",
    "joint_2": "shoulder_lift",
    "joint_3": "elbow_flex",
    "joint_4": "wrist_flex",
    "joint_5": "wrist_roll",
    "joint_6": "gripper",
}

# What the servos weigh, from the manufacturer rather than from this machine. The count is not set
# here: it comes from the bundle's own joints, one actuator per joint. The number is cited so a
# reader can check it instead of taking it.
SERVO_MASS_KG = 0.055
SERVO_MASS_TOLERANCE_KG = 0.001
SERVO_SOURCE = (
    "Feetech STS3215 product specification (STS3215-PRODUCT_SPECIFICATION.pdf, feetech.cn): "
    "weight 55 +/- 1 g, both the 7.4 V and the 12 V variant"
)


def limits_from_official(urdf_path: Path) -> tuple[dict[str, dict], str]:
    """Travel limits from the published model, with the provenance string that must travel with them.

    The CAD has no limits. Taking them from the published URDF is a decision with a named source, and
    the source is written into the YAML and the report so nobody has to guess where a number came
    from. It is not an inference from geometry.
    """
    _, joints = compare.read_urdf(urdf_path)
    out: dict[str, dict] = {}
    for our_joint, their_joint in JOINT_MAP.items():
        entry = joints.get(their_joint)
        limit = entry.get("limits") if entry else None
        if limit:
            out[our_joint] = dict(limit)
    source = (
        f"SO-ARM100 so101_new_calib.urdf at revision a758567c3978dfeefe282ede0500085a48fe8f78, "
        "joint <limit> elements. Not derived from the CAD: the STEP file carries no travel limits."
    )
    return out, source


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--step", required=True, help="SO-101 STEP assembly")
    parser.add_argument("--official", required=True, help="published so101_new_calib.urdf")
    parser.add_argument("--out", default="docs/demo/so101", help="bundle directory")
    parser.add_argument(
        "--markdown", default="docs/demo/so101_vs_official.md", help="comparison output"
    )
    parser.add_argument(
        "--no-official-limits",
        action="store_true",
        help="leave joint limits unknown rather than adopting the published ones",
    )
    parser.add_argument(
        "--previous",
        default=None,
        help="an earlier robot.joints.yaml to diff this run against; omitted means no diff",
    )
    args = parser.parse_args(argv)

    official = Path(args.official)
    limits = None
    source = None
    if not args.no_official_limits:
        limits, source = limits_from_official(official)

    report = compile_bundle(
        args.step,
        args.out,
        notice=_notice(Path(args.out)),
        limits=limits,
        limits_source=source,
    )

    bundle = json.loads((Path(args.out) / "bundle.json").read_text(encoding="utf-8"))
    comparison = compare.compare(
        bundle,
        official,
        BODY_MAP,
        JOINT_MAP,
        actuator_mass_kg=SERVO_MASS_KG,
        actuator_mass_source=SERVO_SOURCE,
    )
    markdown = compare.render_markdown(comparison)
    (Path(args.out) / "comparison.json").write_text(
        comparison.model_dump_json(indent=2), encoding="utf-8"
    )
    # The comparison goes into the bundle's own report as well as into the side document: a page a
    # recipient opens should carry the claim it is being asked to believe.
    report.comparison = json.loads(comparison.model_dump_json())
    if args.previous:
        before = revision.from_joints_yaml(args.previous)
        after = revision.from_bundle(bundle)
        diff = revision.diff_links(before, after, Path(args.previous).name, Path(args.out).name)
        report.revision = json.loads(diff.model_dump_json())
        (Path(args.out) / "revision.json").write_text(
            diff.model_dump_json(indent=2), encoding="utf-8"
        )
        (Path(args.out) / "revision.md").write_text(
            revision.render_markdown(diff), encoding="utf-8"
        )
        if not diff.comparable:
            # Printed, not swallowed: a revision file that says "not comparable" is a result, and a
            # reader who only sees the exit code should still see it.
            print(f"revision    not comparable: {diff.incomparable_reason}")
    (Path(args.out) / "report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    (Path(args.out) / "report.html").write_text(render_html(report), encoding="utf-8")
    Path(args.markdown).parent.mkdir(parents=True, exist_ok=True)
    Path(args.markdown).write_text(_header(report, source) + markdown, encoding="utf-8")

    print(f"bundle      {Path(args.out).resolve()}")
    print(f"comparison  {Path(args.markdown).resolve()}")
    print(f"worst check {report.worst_status}")
    for check in report.checks:
        print(f"  {check.id:22s} {check.status:8s} {check.explanation}")
    return 0 if report.worst_status != "fail" else 1


def _notice(out: Path) -> str | None:
    from ai_cad.compiler.compile import read_notice

    return read_notice(out)


def _header(report, limits_source: str | None) -> str:
    lines = [
        "# SO-101: compiled twin against the published model",
        "",
        f"Generated {report.generated_at} from `{report.source.get('file')}`.",
        "",
        f"- Bodies: {report.totals['bodies']}  Joints: {report.totals['joints']}  "
        f"Parts: {report.totals['parts']}  Instances: {report.totals['instances']}",
        f"- Collision hulls: {report.totals['hulls']}",
        "- Joint limits: "
        + (f"from {limits_source}" if limits_source else "UNKNOWN, the CAD carries none"),
        "",
        "## Checks",
        "",
        "| check | status | what it measured |",
        "|---|---|---|",
    ]
    for check in report.checks:
        lines.append(f"| `{check.id}` | {check.status} | {check.explanation} |")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.extend(f"- {note}" for note in report.notes)
    # Two blanks: the comparison's markdown is appended straight after this, and one blank line runs
    # the last note into the next heading.
    lines.extend(["", ""])
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
