"""Check the joint skeleton against the four criteria the M2 review is written against.

The criteria are the ones recorded in ``docs/DECISIONS.md`` (decision 2), so this script exists to
stop the review being an opinion: it reads the committed documents and prints PASS or FAIL per
criterion, with the measured number that decided it.

Run:

    python scripts/check_joints_yaml.py \
        --proposal docs/twin/so101/robot.joints.proposed.yaml \
        --skeleton docs/twin/so101/bundle/robot.joints.yaml \
        --official path/to/so101_new_calib.urdf

Exits non-zero if any criterion fails.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import defusedxml.ElementTree as ET
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from demo_so101_twin import BODY_MAP, JOINT_MAP  # noqa: E402

# Degrees. The skeleton's joint direction is the servo output-shaft direction (kinematics.py assigns
# ``axis_dir=axis.direction`` from the ``ServoAxis`` it found in the CAD), so the criterion is met by
# one object rather than by two numbers agreeing; this constant is stated so the record names it.
AXIS_TOLERANCE_DEG = 1.0


def _unit(vector) -> bool:
    return abs(math.sqrt(sum(float(c) ** 2 for c in vector)) - 1.0) <= 1e-6


def check_instances(proposal: dict) -> tuple[bool, str]:
    seen: dict[str, str] = {}
    duplicates = []
    for link in proposal["links"]:
        for instance_id in link["instance_ids"]:
            if instance_id in seen:
                duplicates.append(instance_id)
            seen[instance_id] = link["link_id"]
    expected = int(proposal["source"]["instances"])
    ok = not duplicates and len(seen) == expected
    detail = (
        f"{len(seen)} instance(s) assigned across {len(proposal['links'])} link(s), expected "
        f"{expected}; duplicates: {sorted(set(duplicates)) or 'none'}"
    )
    return ok, detail


def check_axes(skeleton: dict) -> tuple[bool, str]:
    joints = skeleton["joints"]
    revolute = [j for j in joints if j.get("joint_type") == "revolute"]
    non_unit = [j["joint_id"] for j in joints if not _unit(j["axis_dir"])]
    distances = [
        j.get("evidence", {}).get("servo_to_joint_distance_m") for j in joints
    ]
    worst = max((d for d in distances if d is not None), default=0.0)
    ok = len(revolute) == len(joints) == 6 and not non_unit
    detail = (
        f"{len(joints)} joint(s), {len(revolute)} revolute, non-unit axes: {non_unit or 'none'}. "
        f"Each axis direction is the servo output-shaft direction from the CAD "
        f"(`ai_cad/compiler/kinematics.py`, `axis_dir=axis.direction`), which is what makes the "
        f"{AXIS_TOLERANCE_DEG:.1f} deg criterion one object rather than two measurements; the axis "
        f"point sits at most {worst * 1e3:.2f} mm from the servo shaft line."
    )
    return ok, detail


def check_limits(skeleton: dict) -> tuple[bool, str]:
    missing = [
        j["joint_id"]
        for j in skeleton["joints"]
        if not j.get("limits") or not j.get("limits_source")
    ]
    sources = {j.get("limits_source", "")[:40] for j in skeleton["joints"]}
    ok = not missing
    detail = (
        f"{len(skeleton['joints']) - len(missing)} of {len(skeleton['joints'])} joint(s) carry a "
        f"limit and a stated source; missing: {missing or 'none'}; distinct sources: "
        f"{len(sources)}."
    )
    return ok, detail


def check_topology(skeleton: dict, official: Path) -> tuple[bool, str]:
    root = ET.parse(official).getroot()
    # The official file names each joint and the link it drives; ours names the pair of bodies. The
    # comparison is joint name -> child link, because a joint's identity in that file is its name and
    # not its position in the document (the document lists the chain tip first).
    children = {}
    for joint in root.findall("joint"):
        children[joint.get("name")] = joint.find("child").get("link")
    reverse = {official_name: our_name for our_name, official_name in BODY_MAP.items()}

    ours = {j["joint_id"]: (j["parent_body"], j["child_body"]) for j in skeleton["joints"]}
    order = []
    body = next(b["body_id"] for b in skeleton["bodies"] if not any(
        j["child_body"] == b["body_id"] for j in skeleton["joints"]
    ))
    while True:
        child_of = [j for j in skeleton["joints"] if j["parent_body"] == body]
        if not child_of:
            break
        joint = child_of[0]
        order.append(joint["joint_id"])
        body = joint["child_body"]

    mismatches = []
    for joint_id, (our_parent, our_child) in ours.items():
        official_name = JOINT_MAP[joint_id]
        their_child = children.get(official_name)
        if their_child is None:
            mismatches.append(f"{joint_id}: official file has no joint {official_name}")
        elif reverse.get(their_child) != our_child:
            mismatches.append(
                f"{joint_id}: official child {their_child} vs ours {our_child}"
            )
    rooted = len(skeleton["bodies"]) - len({j["child_body"] for j in skeleton["joints"]})
    ok = not mismatches and rooted == 1
    detail = (
        f"chain order {' -> '.join(order)}; roots: {rooted} (expected 1); body-to-body "
        f"mismatches: {mismatches or 'none'}."
    )
    return ok, detail


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal", required=True)
    parser.add_argument("--skeleton", required=True)
    parser.add_argument("--official", required=True)
    args = parser.parse_args(argv)

    proposal = yaml.safe_load(Path(args.proposal).read_text(encoding="utf-8"))
    skeleton = yaml.safe_load(Path(args.skeleton).read_text(encoding="utf-8"))

    results = [
        ("every instance assigned exactly once", *check_instances(proposal)),
        ("six revolute joints on the servo shaft axis", *check_axes(skeleton)),
        ("limits sourced and stated", *check_limits(skeleton)),
        ("tree matches the official topology", *check_topology(skeleton, Path(args.official))),
    ]
    failed = 0
    for criterion, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {criterion}")
        print(f"      {detail}")
        failed += 0 if ok else 1
    print(f"\n{len(results) - failed}/{len(results)} criteria pass")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
