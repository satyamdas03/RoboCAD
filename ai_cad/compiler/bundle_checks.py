"""The seven bundle checks, run against a written bundle rather than against its inputs.

A check that reads the compiler's own objects proves the compiler agrees with itself. Every check
here re-reads the files on disk, because the files are what a simulator will see.

Two rules run through the file:

* **Nothing is matched by index.** MuJoCo and a URDF reader are free to order bodies and joints
  differently, and a comparison that assumes the same order passes on a broken file as happily as on
  a good one. Bodies are matched by name, joints by name.
* **A check that cannot be run says so.** SO-101 has no free base, so ``free_base_stand`` is reported
  ``skipped`` with the reason. Reporting it ``pass`` would be a claim about a test that never ran.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from ai_cad.compiler.properties import MassProperties, PropertyError, validate
from ai_cad.compiler.twin_bundle import (
    FK_SAMPLES,
    FK_SEED,
    FK_TOLERANCE_M,
    SETTLE_SECONDS,
    BodyModel,
    BundleError,
    BundleModel,
    CheckResult,
)

SELF_COLLISION_DEPTH_M = 1e-4


def _assets(directory: Path) -> dict[str, bytes]:
    """Mesh bytes under every name a reader might ask for: bare, and with the meshdir prefix."""
    out: dict[str, bytes] = {}
    for path in directory.glob("*.obj"):
        data = path.read_bytes()
        out[path.name] = data
        out[f"meshes/{path.name}"] = data
    return out


def _load(path: Path) -> tuple[object, list[str]]:
    import mujoco

    warnings: list[str] = []

    def collect(text) -> None:  # pragma: no cover - only fires on a bad model
        warnings.append(str(text))

    previous = mujoco.get_mju_user_warning()
    mujoco.set_mju_user_warning(collect)
    try:
        model = mujoco.MjModel.from_xml_path(str(path))
    finally:
        mujoco.set_mju_user_warning(previous)
    return model, warnings


# ------------------------------------------------------------------------------------------------
def check_inertia(model: BundleModel) -> CheckResult:
    """Every body's tensor is positive definite and obeys the triangle inequality.

    The triangle inequality is not decoration: a tensor that violates it describes a mass that
    cannot exist, MuJoCo accepts it without complaint, and the resulting simulation is nonsense in a
    way nothing downstream reports.
    """
    margin = math.inf
    failures: list[str] = []
    for body in model.bodies:
        ix, iy, iz, ixy, ixz, iyz = body.inertia_6
        matrix = ((ix, ixy, ixz), (ixy, iy, iyz), (ixz, iyz, iz))
        props = MassProperties(
            mass_kg=body.mass_kg,
            com_m=body.com_m,
            inertia_kg_m2=matrix,
            label=body.body_id,
        )
        try:
            validate(props)
        except PropertyError as exc:
            failures.append(str(exc))
            continue
        m0, m1, m2 = props.principal_moments()
        if m2 > 0.0:
            # How much room the tensor has before it breaks the triangle inequality, as a fraction of
            # the largest moment. 0 is the boundary; 1.0 is a cube, whose moments are equal.
            margin = min(margin, (m0 + m1 - m2) / m2)
    if failures:
        return CheckResult(
            id="inertia_valid",
            status="fail",
            measured={"failures": failures},
            threshold={"rule": "positive definite and triangle inequality"},
            explanation="; ".join(failures),
        )
    return CheckResult(
        id="inertia_valid",
        status="pass",
        measured={"bodies": len(model.bodies), "min_triangle_margin": float(margin)},
        threshold={"rule": "positive definite and triangle inequality", "min_margin": 0.0},
        explanation="Every body's tensor is positive definite and satisfies the triangle inequality.",
    )


# ------------------------------------------------------------------------------------------------
def check_meshes_load(path: Path, directory: Path, model: BundleModel) -> CheckResult:
    """MuJoCo loads the file and finds every mesh the model says it has."""
    import mujoco

    expected = sum(len(b.hull_files) for b in model.bodies)
    try:
        mujoco_model, warnings = _load(path)
    except Exception as exc:
        return CheckResult(
            id="meshes_load",
            status="fail",
            measured={"error": str(exc), "assets": len(list(directory.glob("*.obj")))},
            explanation=f"MuJoCo could not load {path.name}: {exc}",
        )
    meshes = int(mujoco_model.nmesh)
    geoms = int(mujoco_model.ngeom)
    status = "pass" if meshes == expected and not warnings else "fail"
    explanation = (
        f"{meshes} of {expected} meshes loaded as mesh geoms, "
        f"{len(warnings)} warning(s)."
        if status == "pass"
        else f"{meshes} meshes against {expected} expected; warnings: {warnings}"
    )
    return CheckResult(
        id="meshes_load",
        status=status,
        measured={"meshes": meshes, "geoms": geoms, "warnings": warnings},
        threshold={"expected_meshes": expected},
        explanation=explanation,
    )


# ------------------------------------------------------------------------------------------------
def _names(model) -> list[str]:
    """Body names in model order, with MuJoCo's implicit world body removed.

    ``nbody`` always counts index 0, the world. Counting it as a robot body would make every
    comparison of a model with N links report N+1 against N.
    """
    return [name for _, name in _indexed_names(model)]


def _indexed_names(model) -> list[tuple[int, str]]:
    import mujoco

    out: list[tuple[int, str]] = []
    for index in range(model.nbody):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, index)
        if index == 0 or name == "world":
            continue
        out.append((index, name))
    return out


def _pose_map(model, data, indexed) -> dict[str, np.ndarray]:
    import mujoco

    mujoco.mj_forward(model, data)
    return {
        name: np.array(data.xpos[index], dtype=float)
        for index, name in indexed
        if name
    }


def check_pose_equivalence(
    mjcf_path: Path,
    urdf_path: Path,
    samples: int = FK_SAMPLES,
    tolerance_m: float = FK_TOLERANCE_M,
    seed: int = FK_SEED,
) -> CheckResult:
    """The two files describe the same robot, at rest and over random configurations.

    MuJoCo reads both, so the comparison needs no second parser and no trust in my own forward
    kinematics. Configuration ``q`` is set **by joint name** in each model, because the two readers are
    free to order joints differently.
    """
    import mujoco

    try:
        mj_model, mj_warnings = _load(mjcf_path)
        urdf_model, urdf_warnings = _load(urdf_path)
    except Exception as exc:
        return CheckResult(
            id="pose_equivalence",
            status="fail",
            measured={"error": str(exc)},
            threshold={"tolerance_m": tolerance_m},
            explanation=f"a file did not load: {exc}",
        )

    mj_indexed = _indexed_names(mj_model)
    urdf_indexed = _indexed_names(urdf_model)
    mj_names = [n for _, n in mj_indexed]
    urdf_names = {n for _, n in urdf_indexed}
    shared = [n for n in mj_names if n in urdf_names]
    only_mj = [n for n in mj_names if n not in urdf_names]
    only_urdf = sorted(n for n in urdf_names if n not in set(mj_names))
    if only_mj or only_urdf:
        return CheckResult(
            id="pose_equivalence",
            status="fail",
            measured={"only_in_mjcf": only_mj, "only_in_urdf": only_urdf},
            threshold={"tolerance_m": tolerance_m},
            explanation="the two files do not carry the same bodies, so their poses are not comparable",
        )

    mj_joints = {
        mujoco.mj_id2name(mj_model, mujoco.mjtObj.mjOBJ_JOINT, i): i
        for i in range(mj_model.njnt)
    }
    urdf_joints = {
        mujoco.mj_id2name(urdf_model, mujoco.mjtObj.mjOBJ_JOINT, i): i
        for i in range(urdf_model.njnt)
    }
    movable = sorted(n for n in mj_joints if n and n in urdf_joints)
    if not movable:
        return CheckResult(
            id="pose_equivalence",
            status="fail",
            measured={"shared_joints": 0},
            threshold={"tolerance_m": tolerance_m},
            explanation="the two files share no movable joint, so no configuration can be compared",
        )

    rng = np.random.default_rng(seed)
    mj_data = mujoco.MjData(mj_model)
    urdf_data = mujoco.MjData(urdf_model)

    def max_error(values: np.ndarray) -> float:
        mujoco.mj_resetData(mj_model, mj_data)
        mujoco.mj_resetData(urdf_model, urdf_data)
        for name, value in zip(movable, values):
            mj_data.qpos[mj_model.jnt_qposadr[mj_joints[name]]] = value
            urdf_data.qpos[urdf_model.jnt_qposadr[urdf_joints[name]]] = value
        a = _pose_map(mj_model, mj_data, mj_indexed)
        b = _pose_map(urdf_model, urdf_data, urdf_indexed)
        return max(
            float(np.max(np.abs(a[name] - b[name]))) for name in shared
        )

    rest = max_error(np.zeros(len(movable)))
    worst = 0.0
    worst_q = None
    for _ in range(samples):
        q = rng.uniform(-0.6, 0.6, size=len(movable))
        error = max_error(q)
        if error > worst:
            worst, worst_q = error, q
    status = "pass" if worst <= tolerance_m and rest <= tolerance_m else "fail"
    return CheckResult(
        id="pose_equivalence",
        status=status,
        measured={
            "bodies_compared": len(shared),
            "joints_compared": len(movable),
            "samples": samples,
            "rest_error_m": rest,
            "worst_error_m": worst,
            "worst_q": None if worst_q is None else [float(v) for v in worst_q],
            "mjcf_warnings": mj_warnings,
            "urdf_warnings": urdf_warnings,
        },
        threshold={"tolerance_m": tolerance_m, "seed": seed},
        explanation=(
            f"URDF and MJCF agree to {worst:.3e} m over {samples} random configurations and "
            f"{rest:.3e} m at rest, against a {tolerance_m:.0e} m tolerance."
            if status == "pass"
            else (
                f"worst disagreement {worst:.3e} m over {samples} random configurations and "
                f"{rest:.3e} m at rest exceeds {tolerance_m:.0e} m; the largest gap is between "
                "the two readers' treatments of a joint, not of a mesh"
            )
        ),
    )


# ------------------------------------------------------------------------------------------------
def check_mujoco_load(path: Path) -> CheckResult:
    """Zero warnings, and a two-second passive settle that stays finite.

    The base is bolted to the world here, so the settle measures the model, not free-fall.
    """
    import mujoco

    try:
        model, warnings = _load(path)
    except Exception as exc:
        return CheckResult(
            id="mujoco_load",
            status="fail",
            measured={"error": str(exc)},
            explanation=f"MuJoCo could not load {path.name}: {exc}",
        )
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    steps = int(round(SETTLE_SECONDS / max(model.opt.timestep, 1e-6)))
    nonfinite = 0
    for _ in range(max(steps, 1)):
        mujoco.mj_step(model, data)
        if not np.all(np.isfinite(data.qacc)) or not np.all(np.isfinite(data.qpos)):
            nonfinite += 1
    finite = nonfinite == 0
    status = "pass" if finite and not warnings else "fail"
    return CheckResult(
        id="mujoco_load",
        status=status,
        measured={
            "warnings": warnings,
            "steps": max(steps, 1),
            "seconds": SETTLE_SECONDS,
            "nonfinite_samples": nonfinite,
            "final_qacc_norm": float(np.linalg.norm(data.qacc)),
        },
        threshold={"warnings": 0, "nonfinite_samples": 0},
        explanation=(
            f"Loaded with zero warnings; {max(steps, 1)} passive steps at "
            f"{model.opt.timestep:.4f} s stayed finite."
            if status == "pass"
            else f"{len(warnings)} warning(s), {nonfinite} step(s) left the finite range."
        ),
    )


# ------------------------------------------------------------------------------------------------
def check_self_collision(path: Path, fills: dict[str, float] | None = None) -> CheckResult:
    """No two bodies that are not bolted together overlap at the rest pose.

    Adjacent bodies are excluded because they *do* touch: a servo housing and the bracket it sits in
    are in contact by design, and reporting that as a collision would make the check useless.

    Known blind spot, measured rather than assumed: MuJoCo's convex-convex solver returns **no
    contact at all** for two meshes occupying exactly the same space. The check therefore catches
    partial overlap, which is what a bad hull or a wrong joint origin produces, and would miss an
    exact coincidence. ``contacts_total`` is reported so a run that found no contacts at all is
    visible rather than silently passing.

    ``fills`` maps a body to its collision volume over its solid volume. When a pair overlaps, the
    explanation names those ratios, because a body whose hulls cover 29 times its own solid is telling
    you the overlap is probably the approximation and not the CAD. The check still fails: the
    simulator will act on the hulls, not on the intent.
    """
    import mujoco

    model, _ = _load(path)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)

    body_of_geom = [int(model.geom_bodyid[i]) for i in range(model.ngeom)]
    body_name = dict(_indexed_names(model))
    parent = [int(model.body_parentid[i]) for i in range(model.nbody)]

    def related(a: int, b: int) -> bool:
        return a == b or parent[a] == b or parent[b] == a

    worst = 0.0
    pairs: set[tuple[str, str]] = set()
    for index in range(data.ncon):
        contact = data.contact[index]
        a = body_of_geom[int(contact.geom1)]
        b = body_of_geom[int(contact.geom2)]
        if related(a, b):
            continue
        depth = float(contact.dist)
        if depth < -SELF_COLLISION_DEPTH_M:
            worst = min(worst, depth)
            pairs.add((body_name.get(a, str(a)), body_name.get(b, str(b))))
    status = "pass" if not pairs else "fail"
    ratios = {
        name: round(fills[name], 3)
        for pair in pairs
        for name in pair
        if fills and name in fills
    }
    inflated = [name for name, ratio in ratios.items() if ratio >= 3.0]
    explanation = (
        f"{int(data.ncon)} contacts at rest, none between bodies that are not adjacent."
        if status == "pass"
        else f"{len(pairs)} non-adjacent pair(s) overlap, deepest {worst:.3e} m."
    )
    if status != "pass" and inflated:
        explanation += (
            f" The overlapping bodies' collision meshes fill {', '.join(f'{n} {ratios[n]:.1f}x' for n in inflated)}"
            " their own solid volume, so the overlap is most likely the convex approximation rather"
            " than an interference in the CAD -- but the simulator collides the hulls, not the intent."
        )
    return CheckResult(
        id="self_collision",
        status=status,
        measured={
            "non_adjacent_overlaps": sorted(pairs),
            "deepest_m": worst,
            "contacts_total": int(data.ncon),
            "body_fill": ratios,
        },
        threshold={"depth_m": SELF_COLLISION_DEPTH_M},
        explanation=explanation,
    )


# ------------------------------------------------------------------------------------------------
def brep_distances(
    assembly,
    instance_ids_by_body: dict[str, list[str]],
    pairs: list[tuple[str, str]] | list[list[str]],
    max_shape_pairs: int = 400,
) -> dict[str, dict[str, float | int | None]]:
    """Minimum distance between the true B-rep solids of each overlapping body pair.

    MuJoCo collides convex hulls; a hull of a concave part fills its concavity and two bodies can
    overlap in hull space while their CAD solids are apart. That is a statement about the proxy, not
    about the design, and it is worth printing beside the overlap rather than arguing about later.

    The number is the minimum over every placed solid in one body against every placed solid in the
    other, so a positive value means no real interference was found anywhere between the two bodies
    at the pose the CAD was stored in. Zero means the solids touch or intersect: the overlap is
    either real or the CAD itself is tangent there.

    Nothing here changes the self-collision status. The simulator acts on the hulls, so a check that
    flipped to ``pass`` on the strength of a B-rep gap would be answering a question MuJoCo will not
    ask.
    """
    out: dict[str, dict[str, float | int | None]] = {}
    by_id = {inst.instance_id: inst for inst in assembly.instances}
    # One cache for the whole call: a part commonly appears on more than one body, and the
    # millimetre-to-metre rescale is a geometry rebuild, so it is paid once per distinct shape.
    cache: dict[int, object] = {}
    for pair in pairs:
        a, b = str(pair[0]), str(pair[1])
        solids_a = _placed_solids(assembly, by_id, instance_ids_by_body.get(a, []), cache)
        solids_b = _placed_solids(assembly, by_id, instance_ids_by_body.get(b, []), cache)
        total = len(solids_a) * len(solids_b)
        if not total:
            out[f"{a}|{b}"] = {"distance_m": None, "shape_pairs": 0, "shape_pairs_total": total}
            continue
        best: float | None = None
        best_shapes: tuple[object, object] | None = None
        measured = 0
        for _, shape_a in solids_a:
            for _, shape_b in solids_b:
                if measured >= max_shape_pairs:
                    break
                value = _distance(shape_a, shape_b)
                measured += 1
                if value is None:
                    continue
                if best is None or value < best:
                    best = value
                    best_shapes = (shape_a, shape_b)
            if measured >= max_shape_pairs:
                break
        out[f"{a}|{b}"] = {
            "distance_m": best,
            "shape_pairs": measured,
            "shape_pairs_total": total,
            # A distance of zero is returned both for solids that touch and for solids that
            # overlap. Only a boolean common separates the two, and its volume is the amount of
            # material the two bodies actually share.
            "intersection_m3": (
                _shared_volume(*best_shapes) if best is not None and best <= 1e-6 and best_shapes else None
            ),
        }
    return out


def _shared_volume(shape_a, shape_b) -> float | None:
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    common = BRepAlgoAPI_Common(shape_a, shape_b)
    if not common.IsDone():
        return None
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(common.Shape(), props)
    return float(props.Mass())


# The STEP reader leaves geometry in millimetres and converts only the instance translations to
# metres (ai_cad.importers.step_import). Placing a millimetre shape with a metre transform is off by
# a factor of a thousand on every offset, which does not look like a unit error when it prints: it
# looks like every part sitting near its own origin and every solid touching every other. The shapes
# are therefore scaled to metres once, here, and both numbers then live in the same unit.
_MM_TO_M = 1e-3


def _metres(shape, cache: dict[int, object]):
    """The shape with its coordinates converted to metres, computed once per shape."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.gp import gp_Pnt, gp_Trsf

    key = id(shape)
    cached = cache.get(key)
    if cached is not None:
        return cached
    scale = gp_Trsf()
    scale.SetScale(gp_Pnt(0.0, 0.0, 0.0), _MM_TO_M)
    scaled = BRepBuilderAPI_Transform(shape, scale, True).Shape()
    cache[key] = scaled
    return scaled


def _placed_solids(assembly, by_id, instance_ids, cache: dict[int, object] | None = None) -> list[tuple[str, object]]:
    """Every solid of every instance, moved into the assembly frame the transforms describe."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.gp import gp_Trsf
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer

    cache = {} if cache is None else cache
    out: list[tuple[str, object]] = []
    for instance_id in instance_ids:
        instance = by_id.get(instance_id)
        if instance is None:
            continue
        part = assembly.parts.get(instance.part_id)
        shape = getattr(part, "shape", None) if part is not None else None
        if shape is None:
            continue
        m = instance.transform
        transform = gp_Trsf()
        transform.SetValues(m[0], m[1], m[2], m[3], m[4], m[5], m[6], m[7], m[8], m[9], m[10], m[11])
        moved = BRepBuilderAPI_Transform(_metres(shape, cache), transform, True).Shape()
        explorer = TopExp_Explorer(moved, TopAbs_SOLID)
        found = 0
        while explorer.More():
            out.append((instance_id, explorer.Current()))
            explorer.Next()
            found += 1
        if not found:
            # A shell or a compound with no solid is still geometry worth measuring.
            out.append((instance_id, moved))
    return out


def _distance(shape_a, shape_b) -> float | None:
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape

    measure = BRepExtrema_DistShapeShape(shape_a, shape_b)
    if not measure.IsDone():
        return None
    return float(measure.Value())


# ------------------------------------------------------------------------------------------------
def check_limits_and_effort(
    path: Path,
    skeleton_limits: dict[str, dict[str, float] | None],
    source: str | None = None,
) -> CheckResult:
    """Say which joints carry limits and which carry none, and read the effort field actually used.

    SO-101's CAD holds no travel limits, so this check cannot invent them. It reports ``warn`` with
    the joints named, which is the honest result: a model with unlimited joints loads and runs and is
    still not a model of this robot.

    ``source`` is the provenance string that travelled with the limits. When it is absent the check
    still reports warn, and says plainly that the file does not record where the numbers came from --
    a limit without a source is a specification nobody can check.

    Both halves have to hold for a pass. A travel limit without a stated effort is half a
    specification: the model says how far the joint may go and nothing about the torque it may be
    asked for, and a command range in a position servo is not an effort limit.
    """
    import mujoco

    model, _ = _load(path)
    missing: list[str] = []
    stated: dict[str, dict[str, float]] = {}
    for index in range(model.njnt):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, index)
        if not name:
            continue
        if model.jnt_limited[index]:
            stated[name] = {
                "range_rad": [float(v) for v in model.jnt_range[index]],
                "limited": True,
            }
        else:
            missing.append(name)
    efforts = {}
    for index in range(model.nu):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_ACTUATOR, index)
        if name:
            efforts[name] = {
                "ctrlrange": [float(v) for v in model.actuator_ctrlrange[index]],
                "gear": [float(v) for v in model.actuator_gear[index][:6]],
                # An effort limit is a force/torque range. ctrlrange is not one: for a position servo
                # it is the command in radians, and a model can carry a full command range and no
                # statement at all about the torque that command can deliver.
                "force_limited": bool(model.actuator_forcelimited[index]),
                "forcerange": [float(v) for v in model.actuator_forcerange[index]],
                "field_read": "actuator_ctrlrange and actuator_forcerange",
            }
    # Named for the effort half, so the effort half has to be able to fail the check.
    unstated = [name for name, effort in efforts.items() if not effort["force_limited"]]
    if missing:
        status = "warn"
        explanation = (
            f"{len(missing)} of {len(missing) + len(stated)} joints ship without a travel limit "
            f"({', '.join(missing)}). The CAD carries none, so none were written. Supply limits from "
            "a datasheet or a measurement before commanding motion."
        )
    elif not stated:
        status = "warn"
        explanation = (
            "the file declares no limits at all, so there is nothing here to check; an unlimited "
            "model loads and runs and is still not a model of this robot"
        )
    elif not efforts:
        # Previously this branch passed on the presence of a provenance string, which meant the check
        # named "limits_and_effort" passed with no effort stated anywhere in the model.
        status = "warn"
        explanation = (
            f"{len(stated)} joint(s) carry a travel limit, from "
            f"{(source or 'an unrecorded source').rstrip('.')}, but the file declares no actuators, "
            "so no torque or force limit is stated anywhere in it and the effort half of this check "
            "has nothing to verify. An actuator and its effort range have to be added before the "
            "model can be driven or the torque quoted."
        )
    elif unstated:
        status = "warn"
        explanation = (
            f"{len(stated)} joint(s) carry a travel limit, but "
            f"{len(unstated)} of {len(efforts)} actuator(s) state no force limit "
            f"({', '.join(sorted(unstated))}). A command range is not an effort limit: the model "
            "does not say what torque these actuators can deliver."
        )
    elif not source:
        status = "warn"
        explanation = (
            f"{len(stated)} joint(s) carry a travel limit, but the file does not record where those "
            "numbers came from; a limit without a source cannot be checked against the machine."
        )
    else:
        status = "pass"
        explanation = (
            f"{len(stated)} joint(s) carry a travel limit and {len(efforts)} actuator(s) state a "
            f"force limit, from {source.rstrip('.')}."
        )
    return CheckResult(
        id="limits_and_effort",
        status=status,
        measured={
            "no_limit": missing,
            "with_limit": stated,
            "actuators": efforts,
            "limits_source": source,
        },
        threshold={"rule": "every joint limited, effort stated with its source"},
        explanation=explanation,
    )


# ------------------------------------------------------------------------------------------------
def check_free_base_stand() -> CheckResult:
    """Not applicable: SO-101 is a bolted-down arm with no legs and no free base."""
    return CheckResult(
        id="free_base_stand",
        status="skipped",
        measured={},
        threshold={},
        explanation=(
            "the base body carries no free joint, so there is no balance to test; this check applies "
            "to legged robots only"
        ),
    )


__all__ = [
    "check_free_base_stand",
    "check_inertia",
    "check_limits_and_effort",
    "check_meshes_load",
    "check_mujoco_load",
    "check_pose_equivalence",
    "check_self_collision",
]
