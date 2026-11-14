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
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from ai_cad.compiler import bundle_checks
from ai_cad.compiler.actuators import ActuatorSpec
from ai_cad.compiler.collision import MAX_FILL_RATIO
from ai_cad.compiler.conventions import Conventions, write_manifest
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
    write_visual_meshes,
)
from ai_cad.compiler.visual import VISUAL_BUDGET_BYTES, visual_meshes
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
    actuator: ActuatorSpec | None = None,
    visual: bool = False,
    conventions: Conventions | None = None,
    progress: Callable[[str, int, str], None] | None = None,
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

    ``conventions`` is the measured zero-pose offset and base translation that make this bundle
    comparable with another model of the same robot. It is written twice, from one object: a comment
    block in ``model.mjcf`` (what a simulator opens) and the ``conventions`` block of
    ``manifest.json`` (what a consumer reads). Omitted, the bundle states that no convention was
    measured rather than shipping a zero vector that reads like a finding.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    chain = chain or SO101_CHAIN
    # ``progress`` is a status sink, not a hook that changes what runs: the stages it names are the
    # stages this function already executes in order, and the percentages are emitted after each one
    # finishes. A caller that reports progress therefore cannot report a stage as done that was not.
    def emit(stage: str, pct: int, msg: str) -> None:
        if progress is not None:
            progress(stage, pct, msg)

    if notice is None:
        notice = read_notice(out)
    if (limits is None) != (limits_source is None):
        raise ValueError("limits and limits_source must be supplied together, or neither")

    assembly = import_step(str(step_path))
    emit("import", 10, f"{assembly.part_count} parts, {assembly.instance_count} instances")
    part_of = {instance.instance_id: instance.part_id for instance in assembly.instances}
    if (actuator_mass_kg is None) != (actuator_mass_source is None):
        raise ValueError(
            "actuator_mass_kg and actuator_mass_source must be supplied together: a datasheet mass "
            "without the document it came from is indistinguishable from a guess"
        )
    densities = dict(density_by_part or {})
    actuator_skipped: list[str] = []
    if actuator_mass_kg is not None:
        bought_in, actuator_skipped = actuator_densities(
            assembly, actuator_mass_kg, actuator_mass_source
        )
        for part_id, density in bought_in.items():
            densities.setdefault(part_id, density)
        for message in actuator_skipped:
            print(f"warning: {message}")
    skeleton = derive_skeleton(assembly, chain)
    if limits:
        skeleton = apply_limits(skeleton, limits, limits_source)
    write_skeleton(skeleton, out / "robot.joints.yaml", notice=notice)
    emit("joints", 25, f"{len(skeleton.joints)} joints, {len(skeleton.bodies)} bodies")

    visuals: dict[str, object] = {}
    visual_warnings: list[str] = []
    if visual:
        # Visual meshes are written per placed instance, not per part, so the budget has to be
        # spent against the number of files that will exist rather than the number of parts.
        part_of = {i.instance_id: i.part_id for i in assembly.instances}
        counts = Counter(part_of[iid] for b in skeleton.bodies for iid in b.instance_ids)
        visuals, visual_warnings = visual_meshes(
            assembly, sorted(assembly.parts), counts=dict(counts)
        )
        for message in visual_warnings:
            print(f"warning: {message}")

    model, properties, meshes = build_bundle(
        skeleton,
        assembly,
        name=name,
        density_by_part=densities or None,
        print_model=print_model,
        actuator=actuator,
        visual=visuals or None,
    )
    emit(
        "properties",
        45,
        f"{len(model.bodies)} bodies, {model.total_mass_kg:.3f} kg modelled",
    )
    mesh_dir = write_meshes(model, assembly, meshes, out / "meshes")
    if visuals:
        # Same directory as the hulls: MuJoCo joins every mesh file to one meshdir, and a second
        # directory would need a ".." path that only resolves from the right working directory.
        write_visual_meshes(model, assembly, visuals, mesh_dir)
    visual_bytes = (
        sum(p.stat().st_size for p in mesh_dir.glob("*_vis.obj")) if visuals else 0
    )
    emit(
        "collision",
        70,
        f"{sum(len(b.hull_files) for b in model.bodies)} hulls, "
        f"{sum(len(b.visual_files) for b in model.bodies)} visual meshes",
    )
    mjcf_path = write_mjcf(model, out / "model.mjcf", conventions=conventions)
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

    # What the bundle is and how to read it, in one file a consumer can open without this repo. The
    # conventions block is the point of it: a comparison that reads the offsets out of its own source
    # instead of out of here keeps working after this bundle is recompiled with a different
    # convention, and is wrong without saying so.
    write_manifest(out, model.name, conventions or Conventions())
    emit("bundle", 85, "bundle.json, model.mjcf, model.urdf and manifest.json written")

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
        bundle_checks.check_limits_and_effort(
            mjcf_path,
            limits,
            limits_source,
            rated_torque_nm=(actuator.rated_torque_nm if actuator is not None else None),
        ),
        bundle_checks.check_free_base_stand(),
    ]

    worst = "fail" if any(c.status == "fail" for c in checks) else (
        "warn" if any(c.status == "warn" for c in checks) else "pass"
    )
    emit("checks", 97, f"{len(checks)} checks, worst {worst}")

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
            # The effort limit, with the kind of figure it is and the document behind it. Separated
            # from the mass because they are different claims from different lines of a datasheet.
            "actuators": len(model.actuators),
            "actuator_torque_nm": (actuator.torque_nm if actuator is not None else None),
            "actuator_torque_kind": (actuator.torque_kind if actuator is not None else None),
            "actuator_rated_torque_nm": (
                actuator.rated_torque_nm if actuator is not None else None
            ),
            "actuator_torque_source": (actuator.source if actuator is not None else None),
            "actuator_kp": (actuator.kp if actuator is not None else None),
            "actuator_kv": (actuator.kv if actuator is not None else None),
            # Pictures, kept apart from the collision model they cannot influence.
            "visual_meshes": sum(len(b.visual_files) for b in model.bodies),
            "visual_triangles": sum(b.visual_triangles for b in model.bodies),
            "visual_bytes": visual_bytes,
            "visual_budget_bytes": VISUAL_BUDGET_BYTES,
        },
        checks=checks,
        bodies=body_rows,
        warnings=sorted(
            set(model.warnings)
            | set(skeleton.warnings)
            | set(actuator_skipped)
            | set(visual_warnings)
        ),
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
            _actuator_note(actuator_mass_kg, actuator_mass_source, actuator_skipped),
            _drive_note(actuator, len(skeleton.joints)),
            _collision_verdict(self_collision, meshes),
            _visual_note(
                bool(visuals),
                sum(len(b.visual_files) for b in model.bodies),
                sum(b.visual_triangles for b in model.bodies),
                visual_bytes,
                max(0, len(assembly.parts) - len(visuals)) if visuals else 0,
                max((getattr(m, "cell_m", 0.0) for m in visuals.values()), default=0.0) * 0.5 * 1e3,
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
    emit("done", 100, f"bundle written to {out}")
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
    #
    # The second sentence used to say that a torque read from inverse dynamics on this model *would*
    # include those push-apart forces, and so was not reported. That was true and it was the reason
    # the first version of the effort check reported 1,110 N*m against a 2.94 N*m limit. The check
    # now disables contacts for the measurement, so the sentence has to say what is actually done
    # rather than warn about what used to happen.
    #
    # The claim is stated once. A separate "the status stays fail either way: MuJoCo collides the
    # hulls" sentence used to follow this one, saying the same thing in different words; read aloud
    # it was the same fact twice, which is what a listener notices and a reader skims past.
    torque = (
        " MuJoCo collides the convex hulls, and this overlap is an overlap of those hulls, so a "
        "rollout on this model will see the solver push them apart; the status stays fail whatever "
        "the B-rep says. The effort check therefore measures with contact forces disabled, which is "
        "why its torque is the load the gearing must hold rather than this overlap's contact forces; "
        "a torque read from inverse dynamics with contacts enabled would be neither."
    )
    return " " + " ".join(parts) + torque


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


def _actuator_note(
    mass_kg: float | None, source: str | None, skipped: list[str]
) -> str:
    """What the report may say about actuator masses, given what was actually applied.

    A note that claims a datasheet mass was applied while some actuator kept an assumed density is
    worse than no note: it turns a disclosed guess into an undisclosed one. The three cases are
    therefore separate sentences, and the partial case names the count rather than the figure.
    """
    if mass_kg is None:
        return (
            "The bundle's own mass model carries no actuator mass. A servo's mass comes from a "
            "datasheet or a scale, and this model has neither, so the all-parts mass treats every "
            "actuator as its own solid volume of PLA. That number is labelled as an assumption "
            "wherever it appears; it is not a weigh-in. A comparison that adds a catalogue actuator "
            "mass does so beside this model, states the figure and its source, and does not change "
            "these masses."
        )
    if skipped:
        return (
            f"A datasheet actuator mass of {mass_kg:.4f} kg ({source}) was supplied, but it could "
            f"NOT be applied to {len(skipped)} actuator part(s); they are named in this report's "
            "warnings. Those parts keep an assumed density and therefore mass as a solid block of "
            "that assumed material, so the all-parts mass overstates them. This report does not "
            "claim a datasheet mass for those parts."
        )
    return (
        f"Each actuator carries a datasheet mass of {mass_kg:.4f} kg: {source}. It is applied as "
        "the density that reproduces that mass through the part's own CAD envelope, so the mass is "
        "the datasheet's and the centre of mass and inertia remain the envelope's. It is not a "
        "weigh-in, and it is one figure applied to every actuator rather than one per unit."
    )


def _visual_note(
    wanted: bool, meshes: int, triangles: int, size_bytes: int, missing: int, worst_mm: float = 0.0
) -> str:
    """What the bundle says about its pictures, and what a viewer draws when there are none."""
    if not wanted:
        return (
            "This bundle carries no visual meshes. A viewer that opens it draws the collision hulls, "
            "which are convex covers and larger than the parts; nothing here is a picture of the CAD. "
            "That is a rendering limitation, not a physics one: the hulls are the physics."
        )
    text = (
        f"{meshes} visual mesh(es), {triangles:,} triangles, {size_bytes / 1e6:.2f} MB, written with "
        "contype and conaffinity zero so the simulator never collides them. They are the B-rep "
        "tessellated coarsely rather than the collision hulls, so what a viewer draws is the part's "
        "own surface. One file is written per placed instance, in the body frame, so a part used "
        "several times is written several times."
    )
    if missing:
        text += (
            f" {missing} part(s) could not be meshed and are drawn by their hull instead; the "
            "warnings name them."
        )
    if worst_mm > 0.0:
        text += (
            f" Where a part was coarsened, its vertices moved by up to {worst_mm:.2f} mm on the "
            "coarsest one -- a visible bevel at demo zoom, stated rather than hidden; the per-part "
            "warnings give each part's own figure and say which grid it was reduced on."
        )
    if size_bytes > VISUAL_BUDGET_BYTES:
        text += (
            f" That exceeds the {VISUAL_BUDGET_BYTES / 1024 / 1024:.0f} MB budget set for visual geometry."
        )
    else:
        text += (
            f" That is inside the {VISUAL_BUDGET_BYTES / 1024 / 1024:.0f} MB budget set for visual geometry; "
            "the per-part warnings give the grid cell any part was clustered on to get there."
        )
    return text


def _collision_verdict(check: CheckResult, meshes: dict) -> str:
    """What a red or green self_collision means, in terms of how the hulls were built.

    A status alone invites the reader to either ignore the failure or distrust the robot. This
    paragraph carries the two numbers that say which it is: how many parts the hulls inflate beyond
    the expected band, and how many did not tessellate closed -- and then what the B-rep measurement
    of the same bodies concluded.
    """
    oversized = sorted(pid for pid, m in meshes.items() if getattr(m, "fill_ratio", 0.0) > MAX_FILL_RATIO)
    open_parts = sorted(pid for pid, m in meshes.items() if not getattr(m, "closed", True))
    hulls = sum(getattr(m, "hull_count", 0) for m in meshes.values())
    lead = (
        f"The collision model is {hulls} convex hulls over {len(meshes)} parts. "
        f"{len(oversized)} part(s) are covered by hulls that inflate them beyond {MAX_FILL_RATIO:g}x "
        f"their own solid volume and {len(open_parts)} did not tessellate to a closed surface, so on "
        "those parts the hulls are an envelope rather than a shape."
    )
    if check.status == "pass":
        return (
            lead + " At the rest pose no pair of bodies that are not bolted together produces a "
            "contact, so that inflation costs nothing here."
        )
    overlaps = check.measured.get("non_adjacent_overlaps") or []
    return (
        lead + f" self_collision is {check.status.upper()} on {len(overlaps)} non-adjacent pair(s). "
        "That is a statement about the hulls, which are what MuJoCo collides; the same check measures "
        "the B-rep of the same bodies, and where the solids only touch, the overlap is the convex "
        "approximation rather than an interference in the CAD. The status stays fail either way: the "
        "simulator acts on the hulls."
    )


def _drive_note(actuator: ActuatorSpec | None, joints: int) -> str:
    """What the bundle may claim about its actuators, in the same three-way shape as the mass note."""
    if actuator is None:
        return (
            "This bundle declares no actuators. Its joints are limits and inertias with nothing to "
            "command them, so nothing in the file states what torque any joint may be given and the "
            "model cannot be driven without adding one. That is why limits_and_effort does not pass."
        )
    if not actuator.is_stated():
        return (
            f"{joints} position actuator(s) were written with kp and kv, and no force limit: no "
            "torque figure was supplied, and none was invented to fill the field. A model with an "
            "unstated effort limit loads and moves; it just cannot say how hard it may push."
        )
    return (
        f"Each of the {joints} joints carries a position actuator with a force limit of "
        f"{actuator.describe()}. The limit is the figure the datasheet states for this servo; the "
        "torque each joint is actually asked for is measured by inverse dynamics and reported under "
        "limits_and_effort. " + " ".join(actuator.assumptions())
    )


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
