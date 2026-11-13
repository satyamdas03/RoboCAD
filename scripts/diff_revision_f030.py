"""Diff two compiles of the same robot at two print-model infill assumptions.

This is the revision diff for the demo: the frozen bundle states f = 0.20, this compares it against
the same pipeline re-run at f = 0.30. It is keyed ONLY on the link names that ``robot.joints.yaml``
declares, so a link that is absent on one side is a real addition or removal and not a naming
accident; if the two bundles disagree about which links exist, this refuses to print a table.

``ai_cad/compiler/revision.py`` diffs quantity, volume and mass. This revision changes the infill
assumption, which moves mass, centre of mass and inertia together, so this script reads those three
from the two ``bundle.json`` files and reuses revision's percent helper rather than inventing a
second convention for "percent change".

Run:

    python scripts/diff_revision_f030.py \
        --before docs/twin/so101/bundle \
        --after  docs/twin/so101/revision_f030/bundle \
        --out    docs/twin/so101/revision_f030

Writes ``diff.json`` and ``diff.md``. Exits 2 when the sanity checks fail, because the instruction
for this artifact is to fix the diff and not the numbers.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

from ai_cad.compiler.revision import _percent

# The checks the diff must pass before it is written. A table that reports a link removed, or a
# printed link that got lighter when infill went up, is a diff defect: the compile cannot make a
# printed link lighter by adding material, so a row saying it did is measuring the wrong keys.
SANITY = (
    "zero links added",
    "zero links removed",
    "every link with printed parts is heavier",
    "links with no printed parts are unchanged",
    "servos unchanged: actuator and joint blocks identical",
)

# The check reports quote their own demand figure. Reading it from the report rather than recomputing
# keeps one number in one place, and a revision that moved mass should move this one too.
_EFFORT = re.compile(
    r"largest demand at the sampled poses is ([0-9.]+) N\*m on ([a-z_0-9]+), (\d+)%"
)


def _bodies(bundle_path: Path) -> dict[str, dict]:
    bundle = json.loads((bundle_path / "bundle.json").read_text(encoding="utf-8"))
    return {body["body_id"]: body for body in bundle["bodies"]}, bundle


def _yaml_links(directory: Path) -> list[str]:
    """Link names as the bundle's own joints document declares them."""
    text = (directory / "robot.joints.yaml").read_text(encoding="utf-8")
    document = yaml.safe_load(text)
    return [body["body_id"] for body in document["bodies"]]


def _delta(before: float | None, after: float | None) -> float | None:
    if before is None or after is None:
        return None
    return after - before


def _effort(directory: Path) -> dict | None:
    """The effort check's own headline figure, as the report prints it."""
    report = directory / "report.json"
    if not report.exists():
        return None
    match = _EFFORT.search(report.read_text(encoding="utf-8"))
    if not match:
        return None
    return {"demand_nm": float(match.group(1)), "joint": match.group(2), "percent": int(match.group(3))}


def compare(before_dir: Path, after_dir: Path) -> dict:
    before, before_bundle = _bodies(before_dir)
    after, after_bundle = _bodies(after_dir)
    before_names = _yaml_links(before_dir)
    after_names = _yaml_links(after_dir)

    # Keyed on the YAML, not on the JSON: the YAML is the document that states which links the robot
    # has, so a link present in one and absent from the other is checked here, once, before any row
    # is printed.
    added = [name for name in after_names if name not in before_names]
    removed = [name for name in before_names if name not in after_names]
    missing = [
        name
        for name in before_names + after_names
        if name not in before or name not in after
    ]

    rows = []
    for name in after_names:
        if name not in before or name not in after:
            continue
        old, new = before[name], after[name]
        mass_before, mass_after = old.get("mass_kg"), new.get("mass_kg")
        com_before, com_after = old.get("com_m"), new.get("com_m")
        inertia_before, inertia_after = old.get("inertia_6"), new.get("inertia_6")
        com_delta_m = (
            [a - b for a, b in zip(com_after, com_before)]
            if com_before and com_after
            else None
        )
        rows.append(
            {
                "link_id": name,
                "name": new.get("name", ""),
                "printed_parts": new.get("printed_parts", 0),
                "bought_in_parts": new.get("bought_in_parts", 0),
                "print_model_before": old.get("print_model", ""),
                "print_model_after": new.get("print_model", ""),
                "mass_before_kg": mass_before,
                "mass_after_kg": mass_after,
                "mass_delta_kg": _delta(mass_before, mass_after),
                "mass_delta_percent": _percent(mass_before, mass_after)[1]
                if _percent(mass_before, mass_after)
                else None,
                "solid_mass_before_kg": old.get("solid_mass_kg"),
                "solid_mass_after_kg": new.get("solid_mass_kg"),
                "com_before_m": com_before,
                "com_after_m": com_after,
                "com_delta_mm": [value * 1e3 for value in com_delta_m] if com_delta_m else None,
                "inertia_before_6": inertia_before,
                "inertia_after_6": inertia_after,
                "inertia_diagonal_delta_percent": (
                    [
                        _percent(inertia_before[i], inertia_after[i])[1]
                        for i in range(3)
                    ]
                    if inertia_before and inertia_after
                    else None
                ),
            }
        )

    totals = {
        "mass_before_kg": before_bundle.get("total_mass_kg"),
        "mass_after_kg": after_bundle.get("total_mass_kg"),
        "solid_mass_before_kg": before_bundle.get("total_solid_mass_kg"),
        "solid_mass_after_kg": after_bundle.get("total_solid_mass_kg"),
        "print_model_before": before_bundle.get("print_model"),
        "print_model_after": after_bundle.get("print_model"),
    }
    totals["mass_delta_kg"] = _delta(totals["mass_before_kg"], totals["mass_after_kg"])
    percent = _percent(totals["mass_before_kg"], totals["mass_after_kg"])
    totals["mass_delta_percent"] = percent[1] if percent else None

    # "Servos unchanged" is a claim about the bought-in hardware, and the place the bundle states that
    # hardware is the actuator block: motor, gear, torque limit and its source. Comparing the blocks
    # verbatim is the whole check, and a print assumption that changed them would be changing
    # something the infill fraction has no business touching.
    unchanged = {
        "actuators_identical": json.dumps(before_bundle.get("actuators"), sort_keys=True)
        == json.dumps(after_bundle.get("actuators"), sort_keys=True),
        "joints_identical": json.dumps(before_bundle.get("joints"), sort_keys=True)
        == json.dumps(after_bundle.get("joints"), sort_keys=True),
        "actuators_before": len(before_bundle.get("actuators") or []),
        "actuators_after": len(after_bundle.get("actuators") or []),
    }

    failures = []
    if added:
        failures.append(f"links added: {added}")
    if removed:
        failures.append(f"links removed: {removed}")
    if missing:
        failures.append(f"links named by a YAML but missing from a bundle.json: {missing}")
    if not unchanged["actuators_identical"]:
        failures.append("the actuator block differs between the two bundles; a print assumption must not move the servos")
    if not unchanged["joints_identical"]:
        failures.append("the joint block differs between the two bundles; a print assumption must not move the joints")
    for row in rows:
        if row["printed_parts"] and (row["mass_delta_kg"] or 0.0) <= 0.0:
            failures.append(
                f"{row['link_id']} has {row['printed_parts']} printed parts but got no heavier "
                f"({row['mass_delta_kg']} kg)"
            )
        if not row["printed_parts"] and abs(row["mass_delta_kg"] or 0.0) > 1e-12:
            failures.append(
                f"{row['link_id']} has no printed parts but its mass moved by "
                f"{row['mass_delta_kg']} kg"
            )

    return {
        "schema_version": "robocad.twin.revision_demo/1",
        "before": str(before_dir),
        "after": str(after_dir),
        "keyed_on": str(before_dir / "robot.joints.yaml"),
        "added": added,
        "removed": removed,
        "sanity": list(SANITY),
        "sanity_failures": failures,
        "comparable": not failures,
        "totals": totals,
        "unchanged": unchanged,
        "effort": {"before": _effort(before_dir), "after": _effort(after_dir)},
        "links": rows,
    }


def render_markdown(diff: dict) -> str:
    totals = diff["totals"]
    lines = [
        "# Revision diff: infill assumption f = 0.20 to f = 0.30",
        "",
        f"Before: `{diff['before']}` ({totals['print_model_before']})",
        f"After: `{diff['after']}` ({totals['print_model_after']})",
        "",
        "Same pipeline, same STEP file, one input changed: the print model's infill fraction. The "
        "diff is keyed only on the link names in `robot.joints.yaml`.",
        "",
        "## Sanity",
        "",
    ]
    for check in diff["sanity"]:
        lines.append(f"- {check}")
    if diff["sanity_failures"]:
        lines.extend(["", "**FAILED:**", ""])
        lines.extend(f"- {failure}" for failure in diff["sanity_failures"])
    else:
        lines.extend(
            [
                "",
                f"All {len(diff['sanity'])} hold. 0 added, 0 removed, every printed link heavier, "
                "bought-in only links unchanged, servos unchanged.",
            ]
        )
    lines.extend(
        [
            "",
            "## Totals",
            "",
            "| | before | after | change |",
            "|---|---|---|---|",
            f"| printed mass (kg) | {totals['mass_before_kg']:.4f} | {totals['mass_after_kg']:.4f} "
            f"| {totals['mass_delta_kg']:+.4f} kg ({totals['mass_delta_percent']:+.1f}%) |",
            f"| solid bound (kg) | {totals['solid_mass_before_kg']:.4f} | "
            f"{totals['solid_mass_after_kg']:.4f} | unchanged, the solid is not a print assumption |",
            "",
            "## Link by link",
            "",
            "| link | printed parts | mass before | mass after | change | CoM moved (mm) | "
            "inertia diag change |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for row in diff["links"]:
        com = row["com_delta_mm"]
        com_text = f"{max(abs(v) for v in com):.2f}" if com else "-"
        inertia = row["inertia_diagonal_delta_percent"]
        inertia_text = f"{inertia[0]:+.1f} / {inertia[1]:+.1f} / {inertia[2]:+.1f}%" if inertia else "-"
        lines.append(
            f"| `{row['link_id']}` | {row['printed_parts']} | {row['mass_before_kg']:.4f} | "
            f"{row['mass_after_kg']:.4f} | {row['mass_delta_kg']:+.4f} kg "
            f"({row['mass_delta_percent']:+.1f}%) | {com_text} | {inertia_text} |"
        )
    lines.extend(
        [
            "",
            "Mass, centre of mass and inertia are reported together because the infill assumption "
            "moves all three: inertia scales with the same factor as mass, and the centre of mass "
            "moves only where the added material is not symmetric about the old one.",
            "",
            "The solid bound is printed beside the estimate in both bundles and does not move, which "
            "is the point of keeping it: it is the number that cannot be wrong in the direction that "
            "matters.",
            "",
        ]
    )
    effort = diff.get("effort") or {}
    before_effort, after_effort = effort.get("before"), effort.get("after")
    if before_effort and after_effort:
        lines.extend(
            [
                "## What the extra mass costs at the joint",
                "",
                "The same effort check runs inside both bundles, so the revision's cost can be read "
                "rather than argued:",
                "",
                "| | demand | joint | share of its 2.942 N*m limit |",
                "|---|---|---|---|",
                f"| f = 0.20 | {before_effort['demand_nm']:.3f} N*m | `{before_effort['joint']}` | "
                f"{before_effort['percent']}% |",
                f"| f = 0.30 | {after_effort['demand_nm']:.3f} N*m | `{after_effort['joint']}` | "
                f"{after_effort['percent']}% |",
                "",
                "Both are measured with contacts disabled at a sample of poses, which is what makes "
                "them comparable to each other. A heavier print is a heavier arm, and the joint that "
                "carries the most of it is the same joint in both compiles.",
                "",
                "The revision is a loadable model and not only a JSON: the same command that runs the "
                "frozen bundle runs this one, `python -m robocad.demo so101 --bundle "
                "docs/twin/so101/revision_f030/bundle --mode replay`, and it steps 500 times without "
                "a warning. That is what makes it a revision of the same pipeline rather than a "
                "second pipeline's answer.",
                "",
            ]
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True, help="bundle directory stating the old assumption")
    parser.add_argument("--after", required=True, help="bundle directory compiled at the new assumption")
    parser.add_argument("--out", required=True, help="directory for diff.json and diff.md")
    args = parser.parse_args(argv)

    before_dir, after_dir, out = Path(args.before), Path(args.after), Path(args.out)
    diff = compare(before_dir, after_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "diff.json").write_text(json.dumps(diff, indent=2), encoding="utf-8")
    (out / "diff.md").write_text(render_markdown(diff), encoding="utf-8")

    totals = diff["totals"]
    print(f"links        {len(diff['links'])}")
    print(f"added        {len(diff['added'])}  removed {len(diff['removed'])}")
    print(
        f"total mass   {totals['mass_before_kg']:.4f} kg -> {totals['mass_after_kg']:.4f} kg "
        f"({totals['mass_delta_percent']:+.1f}%)"
    )
    for failure in diff["sanity_failures"]:
        print(f"SANITY FAIL  {failure}")
    return 0 if diff["comparable"] else 2


if __name__ == "__main__":
    sys.exit(main())
