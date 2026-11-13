"""Compile a CAD assembly into a checked simulation bundle, and write the report.

The pipeline is fixed and each stage is a file you can open:

    STEP -> skeleton (bodies, servo axes) -> mass properties + collision hulls
         -> model.mjcf and model.urdf, describing the same kinematics
         -> seven checks, run against the written files -> report.json, report.html

A stage that cannot produce an honest number stops the compile. There is no path here where a guess
is promoted to a measurement: an unknown joint limit stays unknown, an assumed density is named as
assumed in every body it touches, and a check that does not apply is reported ``skipped``.
"""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from ai_cad.compiler import bundle_checks
from ai_cad.compiler.kinematics import apply_limits, derive_skeleton, write_skeleton
from ai_cad.compiler.materials import MATERIALS, Density, datasheet_density
from ai_cad.compiler.print_model import PrintModel
from ai_cad.importers.joints import classify_part
from ai_cad.compiler.twin_bundle import (
    BundleError,
    BundleModel,
    CheckResult,
    build_bundle,
    write_meshes,
    write_mjcf,
    write_urdf,
)
from ai_cad.importers.step_import import import_step

# The CAD's own assembly names. This is the designer's topology, not a geometric result; see the
# module docstring of ai_cad.compiler.kinematics for why no geometry rule recovers it.
SO101_CHAIN = [
    "base_so101",
    "rotation_pitch_so101",
    "upper_arm_so101",
    "under_arm_so101",
    "wrist_roll_pitch_so100",
    "wrist_roll_follower_so101",
    "moving_jaw_so101",
]


class Report(BaseModel):
    schema_version: str = "robocad.twin.report/1"
    name: str
    generated_at: str
    source: dict
    totals: dict
    checks: list[CheckResult]
    bodies: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    # Filled in by a caller that has a published model to compare against; absent otherwise. It is
    # stored as a plain dict so a report stays readable without this module's models.
    comparison: dict | None = None
    revision: dict | None = None

    @property
    def worst_status(self) -> str:
        for level in ("fail", "warn", "skipped"):
            if any(c.status == level for c in self.checks):
                return level
        return "pass"


def _volume_by_role(assembly, instance_ids: list[str], part_of: dict[str, str]) -> dict[str, float]:
    """Solid volume of a body split by what its parts are: link, actuator, fastener, unclassified.

    The split exists because a servo is not a solid block of PLA and a screw is not printed. One
    density applied to the whole assembly produces one number that means nothing in particular; the
    split lets the report show a printed-only mass, which is the number the published model appears to
    publish, beside the all-parts mass.
    """
    out: dict[str, float] = {}
    instances = {inst.instance_id: inst for inst in assembly.instances}
    for instance_id in instance_ids:
        instance = instances.get(instance_id)
        part = assembly.parts.get(part_of.get(instance_id, "")) if instance else None
        if part is None:
            continue
        role = classify_part(part.name)
        out[role] = out.get(role, 0.0) + part.signature.volume_m3
    return out


def actuator_densities(
    assembly, mass_kg: float, source: str
) -> tuple[dict[str, Density], list[str]]:
    """A datasheet density for every part the name classifier calls an actuator.

    A servo's CAD solid is its envelope, not its contents, so nothing in ``materials.MATERIALS`` is
    right for it: modelled as PLA it weighs whatever its envelope displaces, which on this robot is
    several times a real servo. What is actually known is what the part weighs, so the density that
    reproduces that mass through the kernel is the honest number to use, and it is flagged
    ``bought_in`` so the print model leaves it alone.

    Returns the densities and one sentence per part that could not be given one. A part whose CAD
    envelope cannot hold its datasheet mass is a modelling mismatch: it stays on the assumed density,
    which the report already discloses, rather than being handed an invented number.
    """
    if not source or not source.strip():
        raise ValueError("an actuator mass needs a citation; pass the document it came from")
    if mass_kg <= 0.0:
        raise ValueError("an actuator mass must be positive")
    out: dict[str, Density] = {}
    skipped: list[str] = []
    for part in assembly.parts.values():
        if classify_part(part.name) != "actuator":
            continue
        volume = part.signature.volume_m3
        if volume is None or volume <= 0.0:
            skipped.append(f"actuator {part.name!r} has no positive CAD volume; left on a density")
            continue
        try:
            out[part.part_id] = datasheet_density(mass_kg, volume, source)
        except ValueError as exc:
            skipped.append(f"actuator {part.name!r} kept an assumed density: {exc}")
    return out, skipped


def read_notice(directory: str | Path) -> str | None:
    """The licence notice that travels with a derived bundle, if one is beside it.

    ``NOTICE.md`` is preferred and ``NOTICE.txt`` is the fallback. Two notices that both describe
    the same derived work are two documents that drift apart, and the one a recipient forwards is
    the one they happened to open; so a directory that carries ``NOTICE.md`` is read from it and the
    text that lands in ``robot.joints.yaml`` is the same text the reader sees.
    """
    for name in ("NOTICE.md", "NOTICE.txt"):
        path = Path(directory) / name
        if path.exists():
            return path.read_text(encoding="utf-8")
    return None


def compile_bundle(
    step_path: str | Path,
    out_dir: str | Path,
    chain: list[str] | None = None,
    name: str = "so101",
    notice: str | None = None,
    limits: dict[str, dict] | None = None,
    limits_source: str | None = None,
    density_by_part: dict[str, Density] | None = None,
    print_model: PrintModel | None = None,
    actuator_mass_kg: float | None = None,
    actuator_mass_source: str | None = None,
) -> Report:
    """Run every stage and write the bundle. Raises rather than emitting a partial report.

    ``notice`` is carried into the header of ``robot.joints.yaml``. A derived file that leaves its
    licence notice behind in a sibling is one a recipient can forward without it.

    ``limits`` and ``limits_source`` are how travel limits enter, and they must arrive together: the
    CAD has none, so a number here without a named source is a fabricated specification.

    ``print_model`` turns the solid-volume mass into a shell-and-infill estimate and records both
    figures, so a reader can see how much of the number is the kernel and how much is the infill
    choice. ``actuator_mass_kg`` with ``actuator_mass_source`` is the datasheet mass of one actuator,
    applied to every part the name classifier calls an actuator: those parts are bought, not printed,
    and their CAD solids are envelopes rather than material. An explicit ``density_by_part`` entry
    wins over both.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    chain = chain or SO101_CHAIN
    if notice is None:
        notice = read_notice(out)
    if (limits is None) != (limits_source is None):
        raise ValueError("limits and limits_source must be supplied together, or neither")

    assembly = import_step(str(step_path))
    part_of = {instance.instance_id: instance.part_id for instance in assembly.instances}
    if (actuator_mass_kg is None) != (actuator_mass_source is None):
        raise ValueError(
            "actuator_mass_kg and actuator_mass_source must be supplied together: a datasheet mass "
            "without the document it came from is indistinguishable from a guess"
        )
    densities = dict(density_by_part or {})
    if actuator_mass_kg is not None:
        bought_in, skipped = actuator_densities(assembly, actuator_mass_kg, actuator_mass_source)
        for part_id, density in bought_in.items():
            densities.setdefault(part_id, density)
        for message in skipped:
            print(f"warning: {message}")
    skeleton = derive_skeleton(assembly, chain)
    if limits:
        skeleton = apply_limits(skeleton, limits, limits_source)
    write_skeleton(skeleton, out / "robot.joints.yaml", notice=notice)

    model, properties, meshes = build_bundle(
        skeleton,
        assembly,
        name=name,
        density_by_part=densities or None,
        print_model=print_model,
    )
    mesh_dir = write_meshes(model, assembly, meshes, out / "meshes")
    mjcf_path = write_mjcf(model, out / "model.mjcf")
    urdf_path = write_urdf(model, out / "model.urdf")
    assumed = [b.body_id for b in model.bodies if b.rests_on_an_assumed_density]
    body_rows = [
        {
            "body_id": b.body_id,
            "name": b.name,
            "parent": b.parent,
            "joint_id": b.joint_id,
            "mass_kg": b.mass_kg,
            "com_m": list(b.com_m),
            "inertia_6": list(b.inertia_6),
            "origin_m": list(b.origin_m),
            "axis_dir": list(b.axis_dir),
            "hulls": b.hull_count,
            "parts": b.part_count,
            "instances": b.instance_count,
            "assumed_density": b.rests_on_an_assumed_density,
            # The solid bound and the modelled estimate, side by side. A report that carried only
            # one of them could not say how much of its own figure was the kernel and how much was
            # the infill choice.
            "solid_mass_kg": b.solid_mass_kg,
            "printed_mass_kg": b.printed_mass_kg,
            "printed_parts": b.printed_parts,
            "bought_in_parts": b.bought_in_parts,
            # Solid volume of every part on the body, at the density-neutral level. It is what
            # lets a reader ask "what fill fraction would reproduce their published mass",
            # which is a question with an answer, rather than a guess at one.
            "solid_volume_m3": round(sum(p.volume_m3 for p in properties[b.body_id].parts), 15),
            "role_volume_m3": {
                role: round(value, 15)
                for role, value in _volume_by_role(
                    assembly,
                    next(a.instance_ids for a in skeleton.bodies if a.body_id == b.body_id),
                    part_of,
                ).items()
            },
        }
        for b in model.bodies
    ]
    # The bundle file carries the same per-body volume rows the report does. Without them a consumer
    # of bundle.json -- the comparison and the revision diff both are -- reads no volume at all and
    # prints a dash where a number exists.
    extra = {row["body_id"]: row for row in body_rows}
    bundle_bodies = []
    for body in model.bodies:
        entry = json.loads(body.model_dump_json())
        row = extra.get(body.body_id, {})
        entry["solid_volume_m3"] = row.get("solid_volume_m3")
        entry["role_volume_m3"] = row.get("role_volume_m3")
        bundle_bodies.append(entry)
    (out / "bundle.json").write_text(
        json.dumps(
            {
                **json.loads(model.model_dump_json(exclude={"bodies"})),
                "bodies": bundle_bodies,
                "joints": [
                    {
                        "joint_id": j.joint_id,
                        "parent_body": j.parent_body,
                        "child_body": j.child_body,
                        "axis_dir": list(j.axis_dir),
                        "axis_point": list(j.axis_point),
                        "limits": j.limits,
                        "servo": j.servo,
                        "review_required": j.review_required,
                    }
                    for j in skeleton.joints
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    limits = {j.joint_id: j.limits for j in skeleton.joints}
    # Collision volume over solid volume per body. When the self-collision check finds an overlap,
    # this is what lets it say whether the offending hulls are a loose approximation or a faithful
    # one; an overlap between two 29x hulls means something different from one between two 1.0x hulls.
    body_fill: dict[str, float] = {}
    for body in model.bodies:
        solid = sum(p.volume_m3 for p in properties[body.body_id].parts)
        hulled = sum(
            sum(h.volume_m3 for h in meshes[p.part_id].hulls)
            for p in properties[body.body_id].parts
            if p.part_id in meshes
        )
        if solid > 0.0:
            body_fill[body.body_id] = hulled / solid
    self_collision = bundle_checks.check_self_collision(mjcf_path, body_fill)
    if self_collision.status != "pass":
        # The hulls are what MuJoCo collides, but the CAD is what was designed. Measuring the true
        # solids separates a proxy artefact from an interference, and both numbers go into the
        # report so the red check can be read instead of merely obeyed.
        overlaps = self_collision.measured.get("non_adjacent_overlaps") or []
        instance_ids = {a.body_id: list(a.instance_ids) for a in skeleton.bodies}
        measured = bundle_checks.brep_distances(assembly, instance_ids, overlaps)
        self_collision.measured["brep_distance_m"] = measured
        self_collision.explanation += _brep_note(measured)

    checks = [
        bundle_checks.check_meshes_load(mjcf_path, mesh_dir, model),
        bundle_checks.check_inertia(model),
        bundle_checks.check_pose_equivalence(mjcf_path, urdf_path),
        bundle_checks.check_mujoco_load(mjcf_path),
        self_collision,
        bundle_checks.check_limits_and_effort(mjcf_path, limits, limits_source),
        bundle_checks.check_free_base_stand(),
    ]

    # One PLA density over every part of the assembly produces a total that means nothing in
    # particular, because a servo is not a solid block of plastic and a screw is not printed. The
    # printed-only mass is the number the published model appears to publish, and it is computed at
    # 100% fill, so it is an upper bound on a printed part rather than an estimate of one.
    by_role: dict[str, float] = {}
    for row in body_rows:
        for role, value in row["role_volume_m3"].items():
            by_role[role] = by_role.get(role, 0.0) + value
    printed_volume = by_role.get("link", 0.0)
    unknown_volume = by_role.get("unclassified", 0.0)
    report = Report(
        name=name,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        source=dict(skeleton.source),
        totals={
            "bodies": len(model.bodies),
            "joints": len(skeleton.joints),
            "parts": assembly.part_count,
            "instances": assembly.instance_count,
            "hulls": sum(len(b.hull_files) for b in model.bodies),
            "total_mass_kg": round(model.total_mass_kg, 9),
            "total_solid_mass_kg": round(model.total_solid_mass_kg or model.total_mass_kg, 9),
            "print_model": model.print_model,
            "assumed_density_bodies": assumed,
            "printed_mass_upper_bound_kg": round(printed_volume * MATERIALS["pla"], 9),
            "printed_volume_m3": round(printed_volume, 15),
            "unclassified_volume_m3": round(unknown_volume, 15),
            "volume_by_role_m3": {role: round(v, 15) for role, v in sorted(by_role.items())},
            # Not measured here and not guessed here: an actuator's mass needs a datasheet or a
            # scale. When a caller supplies one, the value and its citation travel together.
            "actuator_mass_kg": actuator_mass_kg,
            "actuator_mass_source": actuator_mass_source,
        },
        checks=checks,
        bodies=body_rows,
        warnings=sorted(set(model.warnings) | set(skeleton.warnings)),
        notes=[
            "Axes and origins come from the servos' output shafts and drive-horn placements in the CAD.",
            "Topology order comes from the CAD assembly names, not from geometry.",
            (
                f"Joint limits come from {limits_source}"
                if limits_source
                else "Joint limits are UNKNOWN: the CAD carries no travel limits."
            ),
            "Every mass rests on an assumed density unless a part was weighed; the per-body flag "
            "says which, and the report never presents an assumed mass as a measurement.",
            "The printed/actuator/fastener split comes from the CAD part names. On this file 13 parts "
            "carry generic names (SOLID, Component1..7) and cannot be placed by name, so they are "
            "counted as unclassified and their volume is reported separately rather than folded into "
            "either side of the split.",
            (
                f"Each actuator carries a datasheet mass of {actuator_mass_kg:.4f} kg: "
                f"{actuator_mass_source}. It is applied as the density that reproduces that mass "
                "through the part's own CAD envelope, so the mass is the datasheet's and the centre "
                "of mass and inertia remain the envelope's. It is not a weigh-in, and it is one "
                "figure applied to every actuator rather than one per unit."
                if actuator_mass_kg is not None
                else "The bundle's own mass model carries no actuator mass. A servo's mass comes "
                "from a datasheet or a scale, and this model has neither, so the all-parts mass "
                "treats every actuator as its own solid volume of PLA. That number is labelled as an "
                "assumption wherever it appears; it is not a weigh-in. A comparison that adds a "
                "catalogue actuator mass does so beside this model, states the figure and its "
                "source, and does not change these masses."
            ),
            (
                f"Masses in this report are a shell-and-infill estimate at {model.print_model}; the "
                "solid bound is reported beside it and is never replaced. The centre of mass is held "
                "at the solid's centre and the inertia tensor is scaled by the same factor as the "
                "mass, which is an approximation stated here rather than hidden in the arithmetic."
                if print_model is not None
                else "Masses in this report are solid volumes at a stated density: an upper bound on "
                "what the parts weigh, not an estimate of it."
            ),
        ],
    )
    (out / "report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    (out / "report.html").write_text(render_html(report), encoding="utf-8")
    return report


# ------------------------------------------------------------------------------------------------
def _brep_note(measured: dict[str, dict]) -> str:
    """What the B-rep distance says about a hull overlap, in the words the report can stand behind."""
    parts: list[str] = []
    for key, row in sorted(measured.items()):
        a, _, b = key.partition("|")
        distance = row.get("distance_m")
        pairs = row.get("shape_pairs")
        total = row.get("shape_pairs_total")
        capped = "" if pairs is None or total is None or pairs >= total else (
            f" over {pairs} of {total} shape pairs"
        )
        if distance is None:
            parts.append(f"The CAD solids of {a} and {b} could not be measured.")
        elif distance > 1e-6:
            parts.append(
                f"The CAD solids of {a} and {b} are {distance * 1e3:.3f} mm apart{capped}, so that "
                "overlap is the convex hull filling a concavity rather than an interference in the "
                "design."
            )
        else:
            shared = row.get("intersection_m3")
            if shared is None:
                parts.append(
                    f"The CAD solids of {a} and {b} touch or intersect{capped}, so the overlap is "
                    "not explained by the hull."
                )
            elif shared * 1e9 >= 0.01:
                parts.append(
                    f"The CAD solids of {a} and {b} intersect and share {shared * 1e9:.2f} mm3 of "
                    "material, so part of that overlap is real and part of it may be the hull; this "
                    "measurement does not split the two."
                )
            else:
                parts.append(
                    f"The CAD solids of {a} and {b} are in contact without shared volume "
                    f"({shared * 1e9:.4f} mm3), so the overlap is the hull filling the contact, not "
                    "two parts occupying the same space."
                )
    if not parts:
        return ""
    # The torque caveat follows from the hull overlap, not from the B-rep. MuJoCo collides the
    # hulls, this check only runs when two non-adjacent hulls overlap, and the solver pushes them
    # apart whether or not the CAD solids do. Tying the caveat to the shared volume instead would
    # have switched it off for a hull overlap whose B-rep turned out to be a tangency, which is
    # exactly the case the caveat needs to cover.
    torque = (
        " MuJoCo collides the convex hulls, and this overlap is an overlap of those hulls, so any "
        "torque read from inverse dynamics on this model includes the contact forces the simulator "
        "applies to push them apart. A posed inverse-dynamics torque is therefore not the actuator "
        "load and is not reported as one."
    )
    return (
        " "
        + " ".join(parts)
        + " The status stays fail either way: MuJoCo collides the hulls, so the simulator will act "
        "on the overlap whatever the B-rep says."
        + torque
    )


# ------------------------------------------------------------------------------------------------
def _row(check: CheckResult) -> str:
    return (
        f"<tr class='{check.status}'><td>{html.escape(check.id)}</td>"
        f"<td>{html.escape(check.status)}</td>"
        f"<td>{html.escape(check.explanation)}</td></tr>"
    )


def _mass_cell(value) -> str:
    """A mass that may be absent. A dash, never a zero: a missing model is not a weightless body."""
    if value is None:
        return "—"
    try:
        return f"{float(value):.6f}"
    except (TypeError, ValueError):
        return "—"


def render_csv(report: Report) -> str:
    lines = ["check,status,explanation"]
    for check in report.checks:
        lines.append(f"{check.id},{check.status},\"{check.explanation}\"")
    return "\n".join(lines) + "\n"


def render_html(report: Report) -> str:
    """A page you can open without a toolchain. Every number here came out of report.json."""
    rows = "\n".join(_row(c) for c in report.checks)
    bodies = "\n".join(
        f"<tr><td>{html.escape(b['body_id'])}</td><td>{b['mass_kg']:.6f}</td>"
        f"<td>{_mass_cell(b.get('solid_mass_kg'))}</td>"
        f"<td>{_mass_cell(b.get('printed_mass_kg'))}</td>"
        f"<td>{b.get('bought_in_parts', 0)}</td>"
        f"<td>{b.get('solid_volume_m3', 0.0) * 1e6:.3f}</td>"
        f"<td>{b['hulls']}</td><td>{b['parts']}</td><td>{b['instances']}</td>"
        f"<td>{'yes' if b['assumed_density'] else 'no'}</td></tr>"
        for b in report.bodies
    )
    warnings = "".join(f"<li>{html.escape(w)}</li>" for w in report.warnings) or "<li>none</li>"
    notes = "".join(f"<li>{html.escape(n)}</li>" for n in report.notes)
    totals = "".join(
        f"<tr><th>{html.escape(k)}</th><td>{html.escape(str(v))}</td></tr>"
        for k, v in report.totals.items()
    )
    comparison = ""
    if report.comparison:
        from ai_cad.compiler import compare as _compare

        comparison = _compare.render_html(_compare.Comparison(**report.comparison))
    if report.revision:
        from ai_cad.compiler import revision as _revision

        comparison += _revision.render_html(_revision.Revision(**report.revision))
    return f"""<!doctype html>
<meta charset="utf-8">
<title>{html.escape(report.name)} twin bundle report</title>
<style>
 body{{font:15px/1.55 system-ui,sans-serif;max-width:60rem;margin:2rem auto;padding:0 1rem;color:#111}}
 table{{border-collapse:collapse;width:100%;margin:1rem 0}}
 th,td{{text-align:left;padding:.35rem .5rem;border-bottom:1px solid #ddd;vertical-align:top}}
 tr.pass td:nth-child(2){{color:#0a6b2d;font-weight:600}}
 tr.warn td:nth-child(2){{color:#8a5a00;font-weight:600}}
 tr.fail td:nth-child(2){{color:#a11212;font-weight:600}}
 tr.skipped td:nth-child(2){{color:#555;font-weight:600}}
 code{{background:#f3f3f3;padding:.1rem .25rem;border-radius:3px}}
 h2{{margin-top:2rem;font-size:1.1rem}}
 .banner{{border-left:4px solid #8a5a00;background:#fdf6e3;padding:.75rem 1rem}}
</style>
<h1>{html.escape(report.name)} twin bundle</h1>
<p>Generated {html.escape(report.generated_at)} from
<code>{html.escape(str(report.source.get('file')))}</code>.</p>
<div class="banner">{len([c for c in report.checks if c.status != 'pass'])} of
{len(report.checks)} checks did not pass. Read the checks before using this model for motion.</div>
<h2>Totals</h2><table>{totals}</table>
<h2>Checks</h2>
<table><tr><th>check</th><th>status</th><th>what it measured</th></tr>{rows}</table>
<h2>Bodies</h2>
<table><tr><th>body</th><th>mass (kg)</th><th>solid bound (kg)</th><th>print estimate (kg)</th>
<th>bought-in parts</th><th>solid volume (cm3)</th><th>hulls</th><th>parts</th>
<th>instances</th><th>assumed density</th></tr>{bodies}</table>
{comparison}
<h2>Warnings</h2><ul>{warnings}</ul>
<h2>Notes</h2><ul>{notes}</ul>
"""


__all__ = ["Report", "SO101_CHAIN", "compile_bundle", "render_csv", "render_html"]
