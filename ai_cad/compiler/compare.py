"""Compare a compiled twin against a published model of the same robot.

The comparison is the point of the demo. A table that only shows our numbers proves nothing; a table
that shows theirs beside ours, with the difference in grams and percent, is a claim a reader can
reject.

Three rules:

* **Nothing is scaled to match.** If our total mass is 1.4 kg and theirs is 0.63 kg, both numbers are
  printed and the difference is printed. Quietly normalising ours to theirs would make the table look
  better and make it worthless.
* **The body correspondence is stated, not assumed.** Our bodies are named after the CAD's assembly
  tree and theirs are named after their own convention. The mapping below is a judgement about which
  is which; it is printed with the table so a reader who maps them differently can redo the numbers.
* **Directions are compared in one frame.** The two files pick their own world datum, so a rigid
  transform is fitted and ours is carried into their frame before any angle is computed. The
  transform and its residuals are printed; without them an angle measures whichever datum each side
  happened to choose.
* **The rotation is fitted from directions, not from anchors.** An anchor point is a poor thing to
  fit a rotation to: a revolute joint's anchor is free to sit anywhere along its own axis, so two
  files describing the same robot can disagree about an anchor without disagreeing about the robot.
  Fitting the rotation to anchor positions mixes that freedom, and any difference in the pose the
  two files were saved in, into the rotation itself. Fitting it to the axis directions leaves only
  the directions, and the anchor residual is then reported as a separate number rather than being
  hidden inside the rotation.
"""
from __future__ import annotations

import re
from pathlib import Path

import defusedxml.ElementTree as ET
from pydantic import BaseModel, Field

from ai_cad.compiler.materials import MATERIALS


class BodyComparison(BaseModel):
    ours: str
    theirs: str | None
    ours_kg: float
    theirs_kg: float | None
    delta_kg: float | None
    delta_percent: float | None
    ours_parts: int = 0
    ours_instances: int = 0
    assumed_density: bool = False
    ours_solid_volume_m3: float | None = None
    # Printed parts at 100% solid PLA: an upper bound on what this body weighs if it is only
    # printed plastic, which is the like-for-like counterpart to a published printed-part mass.
    ours_printed_upper_kg: float | None = None
    # Their mass over the mass our geometry would have at 100% solid PLA. This is a derived number,
    # not an assumption: it asks what fill fraction their published mass would correspond to if
    # their link is our link printed in PLA. Above 1.0 means the two are not the same part.
    implied_fill: float | None = None
    # Solid volume the name classifier could not place. When it is non-zero, the printed-only
    # figure for this body is a lower bound: a printed part with a generic name is not counted.
    ours_unclassified_volume_m3: float | None = None
    # How many of our joints hang off this body. Used to remove actuators from their mass before
    # reading a printed fill fraction, since the servo that drives a link is usually carried by it.
    servos_on_body: int = 0
    # Their mass less those servos, over the printed-only upper bound. Only defined when the
    # subtraction leaves a positive mass and the body has printed parts we could identify.
    printed_fill: float | None = None


class JointComparison(BaseModel):
    ours: str
    theirs: str | None
    ours_axis: list[float]
    # World-frame axis read from MuJoCo's own xaxis for their file. The URDF stores the axis in the
    # joint's local frame; comparing that number against a CAD-world axis reports a right angle
    # wherever the two conventions differ, which says nothing about the robot.
    theirs_axis: list[float] | None
    theirs_axis_local: list[float] | None = None
    # Our axis carried into their world frame by the single rigid transform fitted below. The angle
    # that matters is the one after this carry: before it, the two files' world datums are free to
    # differ by any rotation and translation at all, and an angle between them measures that.
    ours_axis_in_theirs: list[float] | None = None
    axis_angle_deg: float | None = None
    # Distance from our joint anchor, carried into their frame, to where their joint sits. A frame
    # can align in rotation and still be the wrong frame, so both the direction and the position are
    # reported.
    anchor_delta_m: float | None = None
    # The same distance split along their joint's own axis. Only the perpendicular part says the two
    # files put the joint somewhere else: a revolute anchor is free to sit anywhere along its axis,
    # so an along-axis difference is a convention and a perpendicular one is a position.
    anchor_along_axis_m: float | None = None
    anchor_perpendicular_m: float | None = None
    ours_limits: dict | None = None
    theirs_limits: dict | None = None


class FrameAlignment(BaseModel):
    """The one rigid transform that carries our world frame onto theirs, and what is left after it."""

    method: str = (
        "rotation fitted to the joint axis directions (with a search over axis senses), "
        "translation from the anchor centroid"
    )
    rotation_deg: list[float] = Field(default_factory=list)  # rotation vector, axis * angle
    translation_m: list[float] = Field(default_factory=list)
    joints_used: int = 0
    # Which way each of our axes had to point to agree with theirs. A revolute axis has no natural
    # sense -- both files are free to pick one -- so a run of -1 here is a convention difference, not
    # a joint that turns backwards, and printing it stops a reader assuming the axes were simply
    # compared as written.
    axis_signs: list[int] = Field(default_factory=list)
    # How many sense combinations fitted the axis directions within the tie tolerance. More than one
    # means the directions alone did not choose the datum and the anchors broke the tie; the report
    # says so rather than presenting the winner as the only answer the data supported.
    rotations_tied: int = 1
    rms_axis_deg: float | None = None
    worst_axis_deg: float | None = None
    # What is left of the anchors after the transform. This is not an axis error and is not a
    # rotation error: it is how far apart the two files place the joints, given that the directions
    # agree. A bend in the pose each file was stored in shows up here and nowhere else.
    rms_point_m: float | None = None
    worst_point_m: float | None = None


class LinkSpacing(BaseModel):
    """Distance between two consecutive joint origins, a quantity no choice of frame can change.

    Every other joint number in this comparison depends on the transform that was fitted; this one
    does not. A rotation and a translation move both endpoints of a segment by the same amount, so
    the length survives any datum, any pose difference that is not a change of length, and any
    disagreement about where along an axis an anchor sits -- the last only if the axes themselves are
    parallel, which is why it is reported as the distance between the two origins rather than as a
    claim about the links.
    """

    from_joint: str
    to_joint: str
    ours_m: float
    theirs_m: float
    delta_m: float
    delta_percent: float | None


class Comparison(BaseModel):
    schema_version: str = "robocad.twin.comparison/1"
    ours: str
    theirs: str
    ours_total_kg: float
    theirs_total_kg: float
    delta_kg: float
    delta_percent: float | None
    bodies: list[BodyComparison] = Field(default_factory=list)
    joints: list[JointComparison] = Field(default_factory=list)
    link_spacings: list[LinkSpacing] = Field(default_factory=list)
    alignment: FrameAlignment | None = None
    notes: list[str] = Field(default_factory=list)


def _float_list(text: str | None) -> list[float]:
    if not text:
        return []
    return [float(v) for v in re.split(r"[\s,]+", text.strip()) if v]


def read_urdf(path: str | Path) -> tuple[dict[str, float], dict[str, dict]]:
    """``({link: mass}, {joint: {parent, child, axis, limits}})`` from a URDF.

    Parsed with defusedxml rather than the stdlib parser: a URDF here is a file that arrived from
    somewhere else, and the stdlib ElementTree expands external entities by default.
    """
    root = ET.parse(str(path)).getroot()
    masses: dict[str, float] = {}
    for link in root.findall("link"):
        name = link.get("name")
        if not name:
            continue
        mass = link.find("inertial/mass")
        masses[name] = float(mass.get("value", 0.0)) if mass is not None else 0.0
    joints: dict[str, dict] = {}
    for joint in root.findall("joint"):
        name = joint.get("name")
        if not name:
            continue
        parent = joint.find("parent")
        child = joint.find("child")
        axis = joint.find("axis")
        limit = joint.find("limit")
        joints[name] = {
            "type": joint.get("type"),
            "parent": parent.get("link") if parent is not None else None,
            "child": child.get("link") if child is not None else None,
            "axis": _float_list(axis.get("xyz")) if axis is not None else [],
            "limits": (
                {
                    "lower": float(limit.get("lower", 0.0)),
                    "upper": float(limit.get("upper", 0.0)),
                    "effort": float(limit.get("effort", 0.0)),
                    "velocity": float(limit.get("velocity", 0.0)),
                }
                if limit is not None
                else None
            ),
        }
    return masses, joints


def _angle_deg(a: list[float], b: list[float]) -> float | None:
    """Angle between two axis lines, ignoring which way each points."""
    if len(a) < 3 or len(b) < 3:
        return None
    import math

    na = math.sqrt(sum(v * v for v in a[:3]))
    nb = math.sqrt(sum(v * v for v in b[:3]))
    if na == 0.0 or nb == 0.0:
        return None
    dot = abs(sum(a[i] * b[i] for i in range(3)) / (na * nb))
    return math.degrees(math.acos(max(-1.0, min(1.0, dot))))


def _load_without_meshes(path: Path):
    """Load a model whose mesh assets may be missing.

    Their file references STL assets that are often not shipped beside it. The axes and anchors live
    in the kinematic tree, which needs no mesh to load, so dropping the geometry lets MuJoCo answer
    the question actually being asked instead of failing on a file the comparison never looks at.
    """
    import mujoco

    try:
        return mujoco.MjModel.from_xml_path(str(path))
    except Exception:
        root = ET.parse(str(path)).getroot()
        for link in root.findall("link"):
            for tag in ("visual", "collision"):
                for element in link.findall(tag):
                    link.remove(element)
        return mujoco.MjSpec.from_string(ET.tostring(root, encoding="unicode")).compile()


def world_joint_frames(model_path: str | Path) -> dict[str, tuple[list[float], list[float]]]:
    """``{joint: (axis, anchor)}`` in the world frame at the rest pose, read from MuJoCo.

    A URDF states each joint axis in that joint's local frame, and so does an MJCF body-local joint.
    Either number compared against a CAD-world direction is a comparison of two conventions, not of
    two robots: it reports a right angle wherever the frames differ by one. MuJoCo carries the axis
    and anchor in world coordinates for the configuration it has loaded, so both sides of the
    comparison can be read in the same frame from the same reader.
    """
    import mujoco

    model = _load_without_meshes(Path(model_path))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    out: dict[str, tuple[list[float], list[float]]] = {}
    for index in range(model.njnt):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, index)
        if name:
            out[name] = (
                [float(v) for v in data.xaxis[index]],
                [float(v) for v in data.xanchor[index]],
            )
    return out


def world_joint_axes(model_path: str | Path) -> dict[str, list[float]]:
    """Just the axes, when the anchors are not needed."""
    return {name: axis for name, (axis, _) in world_joint_frames(model_path).items()}


def _rotation_vector(rotation) -> list[float]:
    """A rotation matrix as an axis times an angle in degrees."""
    import numpy as np

    angle = float(np.arccos(max(-1.0, min(1.0, (float(np.trace(rotation)) - 1.0) / 2.0))))
    if angle == 0.0:
        return [0.0, 0.0, 0.0]
    # The skew part of a rotation is 2 sin(angle) times the unit axis, so the rotation vector
    # (axis times angle in degrees) is that skew scaled. A half turn leaves the skew at zero and its
    # direction has to come from the symmetric part instead.
    skew = rotation - rotation.T
    norm = float(np.linalg.norm(skew))
    if norm > 1e-12:
        # The skew matrix is 2 sin(angle) times the unit-axis cross-product matrix, whose flattened
        # norm is 2 sin(angle) * sqrt(2). Normalising it gives the axis over sqrt(2).
        unit = skew.flatten() / norm * np.sqrt(2.0)
        k = [float(unit[7]), float(unit[2]), float(unit[3])]
    else:
        symmetric = (rotation + np.eye(3)) / 2.0
        column = symmetric[:, int(np.argmax(np.diag(symmetric)))]
        k = [float(v) for v in column / float(np.linalg.norm(column))]
    return [float(v * np.degrees(angle)) for v in k]


# Six joints give 64 sense combinations, ten give 1024. Past that the search is a coordinate descent
# instead of an enumeration, because 2**20 SVDs is not a thing to do inside a report.
_SIGN_SEARCH_LIMIT = 10


def _wahba(a, b):
    """The rotation that best carries direction set ``a`` onto ``b``, with det +1 enforced."""
    import numpy as np

    u, _, vt = np.linalg.svd(a.T @ b)
    d = float(np.sign(np.linalg.det(vt.T @ u.T)))
    return vt.T @ np.diag([1.0, 1.0, d]) @ u.T


def _axis_angles_deg(rotation, ours, theirs):
    import numpy as np

    carried = ours @ rotation.T
    carried = carried / np.linalg.norm(carried, axis=1, keepdims=True)
    return np.degrees(np.arccos(np.clip(np.sum(carried * theirs, axis=1), -1.0, 1.0)))


# Two sense combinations whose axis residuals differ by less than this are treated as one answer.
# A robot arm whose joints share a handful of directions does not pin a rotation any tighter than
# this, and pretending one of two equally good rotations is the answer would be a choice dressed as
# a measurement.
_TIE_DEG = 0.25


def _perp_rms(rotation, our_anchors, their_anchors, their_axes):
    """RMS distance from our carried anchors to their joint axis lines."""
    import numpy as np

    translation = their_anchors.mean(axis=0) - rotation @ our_anchors.mean(axis=0)
    delta = (rotation @ our_anchors.T).T + translation - their_anchors
    along = np.sum(delta * their_axes, axis=1)
    return float(np.sqrt(np.mean(np.sum((delta - along[:, None] * their_axes) ** 2, axis=1))))


def _fit_rotation_from_axes(ours, theirs, our_anchors=None, their_anchors=None, their_axes=None):
    """``(rotation, senses, rms_deg, per_joint_deg, tied)`` from one set of directions onto the other.

    A revolute axis has no natural sense: each file picks one, and the two are free to disagree. A
    least-squares fit over the directions as written would spend the disagreement on the rotation, so
    every sense combination is tried and the one with the smallest residual wins.

    Directions alone often leave more than one rotation equally good -- on an arm whose joints repeat
    a few directions, a quarter turn and a half turn can both fit every axis within a degree. When
    that happens the anchors choose between the tied rotations, and ``tied`` says how many were
    equally good so the report can admit the directions did not decide it.
    """
    import itertools

    import numpy as np

    ours = ours / np.linalg.norm(ours, axis=1, keepdims=True)
    theirs = theirs / np.linalg.norm(theirs, axis=1, keepdims=True)

    def scored(senses):
        rotation = _wahba(ours * senses[:, None], theirs)
        angles = _axis_angles_deg(rotation, ours * senses[:, None], theirs)
        return float(np.sqrt(np.mean(np.square(angles)))), rotation, angles

    count = len(ours)
    candidates: list[tuple[float, object, object, object]] = []
    if count <= _SIGN_SEARCH_LIMIT:
        for bits in itertools.product((1.0, -1.0), repeat=count):
            senses = np.array(bits)
            rms, rotation, angles = scored(senses)
            candidates.append((rms, rotation, senses, angles))
    else:
        senses = np.ones(count)
        rms, rotation, angles = scored(senses)
        for _ in range(4):
            changed = False
            for index in range(count):
                trial = senses.copy()
                trial[index] *= -1.0
                trial_rms, trial_rotation, trial_angles = scored(trial)
                if trial_rms < rms - 1e-12:
                    rms, rotation, angles, senses, changed = (
                        trial_rms, trial_rotation, trial_angles, trial, True
                    )
            if not changed:
                break
        candidates.append((rms, rotation, senses, angles))

    best_rms = min(c[0] for c in candidates)
    tied = [c for c in candidates if c[0] <= best_rms + _TIE_DEG]
    if (
        len(tied) > 1
        and our_anchors is not None
        and their_anchors is not None
        and their_axes is not None
    ):
        tied.sort(key=lambda c: _perp_rms(c[1], our_anchors, their_anchors, their_axes))
    rms, rotation, senses, angles = tied[0]
    return rotation, [int(v) for v in senses], rms, [float(v) for v in angles], len(tied)


def fit_frame_alignment(
    ours: list[tuple[str, list[float], list[float]]],
    theirs: dict[str, tuple[list[float], list[float]]],
) -> tuple[FrameAlignment | None, dict[str, tuple[list[float], list[float]]]]:
    """Fit the one rigid transform that carries our world frame onto theirs.

    ``ours`` is ``[(joint, axis, anchor)]``. Returns the alignment and our joints carried into their
    frame. Two files are free to choose different world datums: a CAD assembly has its own origin and
    axes, and a published URDF picks its own. Comparing directions across those datums measures the
    choice, not the robot, so the datum is fitted once and the leftover error is what gets reported.

    The rotation comes from the axis directions and the translation from the anchors. Fitting the
    rotation to the anchors instead was an earlier version of this function, and on the SO-101 it
    reported 9 to 12 degrees of disagreement on axes that agree within 2: a revolute anchor is free
    to slide along its own axis, and a difference in the pose the two files were stored in moves every
    anchor, so an anchor cloud constrains the rotation through two things that are not its axes. The
    anchor residual is therefore reported as its own number rather than spent on the rotation.

    Fewer than three shared joints leave the rotation underdetermined, and the fit says so.
    """
    import numpy as np

    shared = [(joint, axis, anchor) for joint, axis, anchor in ours if joint in theirs]
    if len(shared) < 3:
        return None, {}

    p_axis = np.array([axis for _, axis, _ in shared], dtype=float)
    q_axis = np.array([theirs[joint][0] for joint, _, _ in shared], dtype=float)
    p_anchor = np.array([anchor for _, _, anchor in shared], dtype=float)
    q_anchor = np.array([theirs[joint][1] for joint, _, _ in shared], dtype=float)

    rotation, senses, rms_axis, axis_errors, tied = _fit_rotation_from_axes(
        p_axis, q_axis, p_anchor, q_anchor, q_axis
    )
    # With the rotation fixed the least-squares translation is the shift between the two anchor
    # centroids. It is the best any translation can do; what is left over is the pose difference and
    # is reported as such rather than being folded back into the rotation.
    translation = q_anchor.mean(axis=0) - rotation @ p_anchor.mean(axis=0)

    def carry(axis: list[float], anchor: list[float]) -> tuple[list[float], list[float]]:
        return (
            [float(v) for v in rotation @ np.asarray(axis, dtype=float)],
            [float(v) for v in rotation @ np.asarray(anchor, dtype=float) + translation],
        )

    point_errors = [
        float(np.linalg.norm(rotation @ p_anchor[i] + translation - q_anchor[i]))
        for i in range(len(shared))
    ]
    alignment = FrameAlignment(
        rotation_deg=_rotation_vector(rotation),
        translation_m=[float(v) for v in translation],
        joints_used=len(shared),
        axis_signs=senses,
        rotations_tied=tied,
        rms_axis_deg=rms_axis,
        worst_axis_deg=max(axis_errors) if axis_errors else None,
        rms_point_m=float(np.sqrt(np.mean(np.square(point_errors)))),
        worst_point_m=max(point_errors),
    )
    carried = {joint: carry(axis, anchor) for joint, axis, anchor in shared}
    return alignment, carried


def compare(
    bundle: dict,
    urdf_path: str | Path,
    body_map: dict[str, str],
    joint_map: dict[str, str],
    ours_label: str = "RoboCAD",
    theirs_label: str = "SO-ARM100 so101_new_calib.urdf",
    actuator_mass_kg: float | None = None,
    actuator_mass_source: str | None = None,
) -> Comparison:
    """Pair our bodies and joints with theirs and print both sides.

    ``body_map`` and ``joint_map`` are ours-to-theirs. A body with no counterpart is compared against
    nothing and still printed, so a missing link is visible instead of absent.

    ``actuator_mass_kg`` is one actuator's mass from a datasheet or a scale, with ``actuator_mass_source``
    naming where it came from; the two arrive together or not at all. It is what lets the report say
    whether their published masses can include servos, and read a printed fill fraction from their
    numbers without silently dividing a servo by a plastic density.
    """
    masses, joints = read_urdf(urdf_path)
    ours_bodies = {b["body_id"]: b for b in bundle["bodies"]}
    ours_total = float(bundle["total_mass_kg"])
    theirs_total = float(sum(masses.values()))
    if (actuator_mass_kg is None) != (actuator_mass_source is None):
        raise ValueError("actuator_mass_kg and actuator_mass_source must be supplied together")
    # One actuator per joint, carried by the joint's parent body. That is our topology, stated in
    # the bundle, not a guess: a joint's servo is mounted in the link upstream of it.
    servos: dict[str, int] = {}
    for joint in bundle.get("joints", []) or []:
        parent = joint.get("parent_body")
        if parent:
            servos[parent] = servos.get(parent, 0) + 1

    bodies: list[BodyComparison] = []
    for our_id, their_id in body_map.items():
        body = ours_bodies.get(our_id)
        if body is None:
            continue
        ours_kg = float(body["mass_kg"])
        theirs_kg = masses.get(their_id) if their_id else None
        delta = None if theirs_kg is None else ours_kg - theirs_kg
        percent = (
            None
            if not theirs_kg or delta is None
            else 100.0 * delta / theirs_kg
        )
        volume = body.get("solid_volume_m3")
        volume = None if volume is None else float(volume)
        role_volume = body.get("role_volume_m3") or {}
        # Only parts the names call links. Folding the unclassified volume in here would make the
        # "printed only" column count the servos -- which on this file are named SOLID and ZK_122 and
        # land in unclassified -- as printed plastic, and the column would then overstate exactly the
        # quantity it exists to isolate.
        printed_volume = role_volume.get("link", 0.0)
        printed_kg = (printed_volume * MATERIALS["pla"]) if role_volume else None
        unclassified = role_volume.get("unclassified", 0.0) if role_volume else None
        solid_pla = None if not volume else volume * MATERIALS["pla"]
        fill = (
            None
            if solid_pla is None or theirs_kg is None
            else theirs_kg / solid_pla
        )
        # Their link mass less the servos that link carries, over our printed-only upper bound.
        # Undefined when the subtraction leaves nothing, or when no printed part on this body could
        # be identified: a fill fraction with a zero or a guessed denominator is not a fraction.
        on_body = servos.get(our_id, 0)
        printed_fill = None
        if actuator_mass_kg is not None and theirs_kg is not None and printed_kg:
            remainder = theirs_kg - on_body * actuator_mass_kg
            if remainder > 0.0:
                printed_fill = remainder / printed_kg
        bodies.append(
            BodyComparison(
                ours=our_id,
                theirs=their_id,
                ours_kg=ours_kg,
                theirs_kg=theirs_kg,
                delta_kg=delta,
                delta_percent=percent,
                # The bundle file names these part_count/instance_count; the report's body rows name
                # them parts/instances. Reading only one spelling printed a zero for every body.
                ours_parts=int(body.get("parts", body.get("part_count", 0)) or 0),
                ours_instances=int(body.get("instances", body.get("instance_count", 0)) or 0),
                # bundle.json writes the model field name ``rests_on_an_assumed_density``; the
                # report's body rows write ``assumed_density``. Reading only the short spelling made
                # this flag False for every body of a bundle whose masses all rest on 1240 kg/m3,
                # which turned a disclosure off without any error -- the worst shape a missing
                # disclosure can take.
                assumed_density=bool(
                    body.get(
                        "assumed_density",
                        body.get("rests_on_an_assumed_density", False),
                    )
                ),
                ours_solid_volume_m3=volume,
                ours_printed_upper_kg=printed_kg,
                implied_fill=fill,
                ours_unclassified_volume_m3=unclassified,
                servos_on_body=on_body,
                printed_fill=printed_fill,
            )
        )

    comparison_joints: list[JointComparison] = []
    try:
        their_world = world_joint_frames(urdf_path)
        world_error = None
    except Exception as exc:  # a reader that cannot load their file says so instead of guessing
        their_world = {}
        world_error = str(exc)

    # One rigid transform carries our world datum onto theirs. It is fitted over the joints both
    # files place, and only over joints whose anchor the bundle actually carries: an anchor invented
    # from a missing value would drag the fit towards the invention.
    ours_for_fit: list[tuple[str, list[float], list[float]]] = []
    for our_joint_id, their_joint_id in joint_map.items():
        if not their_joint_id or their_joint_id not in their_world:
            continue
        our = next((j for j in bundle.get("joints", []) or [] if j["joint_id"] == our_joint_id), None)
        if our is None or our.get("axis_point") is None:
            continue
        ours_for_fit.append(
            (their_joint_id, list(our["axis_dir"]), [float(v) for v in our["axis_point"]])
        )
    alignment, carried = (
        fit_frame_alignment(ours_for_fit, their_world) if their_world else (None, {})
    )

    for our_joint_id, their_joint_id in joint_map.items():
        our = next((j for j in bundle.get("joints", []) or [] if j["joint_id"] == our_joint_id), None)
        if our is None:
            continue
        # Theirs is looked up by joint name. A URDF joint name is unique and is what the mapping
        # states; keying on the child link would silently compare against the wrong joint whenever
        # one link is the child of more than one joint.
        theirs = joints.get(their_joint_id)
        frame = their_world.get(their_joint_id) if their_joint_id else None
        theirs_axis = frame[0] if frame else None
        their_anchor = frame[1] if frame else None
        ours_in_theirs = carried.get(their_joint_id, (None, None))[0]
        # The angle is read from the carried axis when the fit exists: before the carry, the two
        # datums are free to differ by any rotation at all, and an angle taken across them measures
        # the datum, not the joint. A robot whose joints disagree by a degree still reports the
        # residual of the fit when the fit is good.
        basis = ours_in_theirs if ours_in_theirs is not None else list(our["axis_dir"])
        # The anchor distance split along their joint's own axis. Only the perpendicular part is a
        # statement about position: a revolute anchor is free to sit anywhere on its axis line, so an
        # along-axis difference is a convention both files are entitled to pick.
        along = perpendicular = total = None
        if carried.get(their_joint_id) and their_anchor is not None and theirs_axis is not None:
            delta = [
                float(a) - float(b) for a, b in zip(carried[their_joint_id][1], their_anchor)
            ]
            total = float(sum(v * v for v in delta) ** 0.5)
            along = float(sum(d * a for d, a in zip(delta, theirs_axis)))
            perpendicular = float(sum((d - along * a) ** 2 for d, a in zip(delta, theirs_axis)) ** 0.5)
        comparison_joints.append(
            JointComparison(
                ours=our_joint_id,
                theirs=their_joint_id,
                ours_axis=list(our["axis_dir"]),
                theirs_axis=list(theirs_axis) if theirs_axis else None,
                theirs_axis_local=list(theirs["axis"]) if theirs else None,
                ours_axis_in_theirs=list(ours_in_theirs) if ours_in_theirs else None,
                axis_angle_deg=_angle_deg(basis, theirs_axis) if theirs_axis else None,
                anchor_delta_m=total,
                anchor_along_axis_m=along,
                anchor_perpendicular_m=perpendicular,
                ours_limits=our.get("limits"),
                theirs_limits=theirs["limits"] if theirs else None,
            )
        )

    # Consecutive joint spacings, which no choice of frame can alter. This is the part of the joint
    # geometry the comparison can state without a transform at all, so it is stated first and its
    # agreement is not a consequence of the fit.
    spacings: list[LinkSpacing] = []
    placed: list[tuple[str, list[float], list[float]]] = []
    for our_joint_id, their_joint_id in joint_map.items():
        our = next((j for j in bundle.get("joints", []) or [] if j["joint_id"] == our_joint_id), None)
        frame = their_world.get(their_joint_id) if their_joint_id else None
        if our is None or our.get("axis_point") is None or frame is None:
            continue
        placed.append((our_joint_id, [float(v) for v in our["axis_point"]], frame[1]))
    for (name_a, ours_a, theirs_a), (name_b, ours_b, theirs_b) in zip(placed, placed[1:]):
        ours_d = float(sum((x - y) ** 2 for x, y in zip(ours_b, ours_a)) ** 0.5)
        theirs_d = float(sum((x - y) ** 2 for x, y in zip(theirs_b, theirs_a)) ** 0.5)
        spacings.append(
            LinkSpacing(
                from_joint=name_a,
                to_joint=name_b,
                ours_m=ours_d,
                theirs_m=theirs_d,
                delta_m=ours_d - theirs_d,
                delta_percent=None if theirs_d == 0.0 else 100.0 * (ours_d - theirs_d) / theirs_d,
            )
        )

    notes = [
        "Ours is measured from the CAD B-rep at a stated density. Theirs is the value published in "
        "the official model. Neither is adjusted to match the other.",
        "The body correspondence is a judgement from the two naming schemes and is printed beside the "
        "numbers so it can be disputed.",
    ]
    if any(b.assumed_density for b in bodies):
        notes.append(
            "Some of our bodies rest on an ASSUMED material density; their mass is therefore an "
            "estimate, not a measurement, and the report says which."
        )
    if theirs_total > 0.0:
        if actuator_mass_kg is not None:
            all_servos = sum(servos.values()) * actuator_mass_kg
            remainder = theirs_total - all_servos
            notes.append(
                f"The official model accounts for {theirs_total:.4f} kg. Our joints imply "
                f"{sum(servos.values())} actuators, and at {actuator_mass_source} they weigh "
                f"{all_servos * 1e3:.0f} g, which is {100.0 * all_servos / theirs_total:.0f}% of "
                f"their total. That leaves {remainder * 1e3:.0f} g for every printed link and "
                f"fastener. Our printed parts alone are "
                f"{sum(b.ours_printed_upper_kg or 0.0 for b in bodies) * 1e3:.0f} g at 100% solid, "
                "so the arithmetic is consistent with their masses being whole-body masses that "
                "include the servos, at a fill fraction well under solid. That is a reading of the "
                "numbers, not a statement of their method."
            )
        else:
            notes.append(
                f"The official model accounts for {theirs_total:.4f} kg. No actuator mass was "
                "supplied for this comparison, so the table cannot say whether that total includes "
                "the servos. Without that, the fill column divides a body's whole mass by solid "
                "plastic and is an upper bound on printed fill, not a fill fraction."
            )
    if any(b.ours_unclassified_volume_m3 for b in bodies):
        notes.append(
            "The printed-only column counts parts whose CAD names classify them as links. Parts with "
            "generic names (SOLID, Component1..7) are left out of it rather than guessed into it, so "
            "it is a lower bound on printed plastic, not a total; a body marked with an asterisk "
            "carries such parts, and a printed-only figure of 0 for that body means only that no "
            "part on it could be identified as printed."
        )
    if any(b.implied_fill is not None for b in bodies):
        notes.append(
            "The fill column is derived, not assumed: the official mass divided by the mass our "
            "geometry would have as 100% solid PLA (1240 kg/m3). Read against a body's whole "
            "published mass it can exceed a real fill fraction, because a servo is not plastic."
        )
    if any(b.printed_fill is not None for b in bodies):
        notes.append(
            "The printed-fill column removes one actuator per joint from their body mass and divides "
            "what is left by our printed-only upper bound. It assumes their link masses include the "
            "servo that link carries, which is the common convention and is stated here rather than "
            "silently applied."
        )
    if spacings:
        largest = max(spacings, key=lambda s: abs(s.delta_m))
        notes.append(
            "The joint-to-joint spacings are printed before the frame alignment because no change of "
            "frame can alter them: a rotation and a translation move both ends of a segment by the "
            "same amount, so their agreement is not a consequence of the fit. The largest difference "
            f"is {abs(largest.delta_m) * 1e3:.1f} mm between {largest.from_joint} and "
            f"{largest.to_joint}. A difference in the pose the two files were stored in would show "
            "up here too, so agreement means the links are the same length and both files are in "
            "much the same configuration."
        )
    if joint_map and world_error:
        notes.append(
            f"Their joint axes could not be read in the world frame ({world_error}), so the axis "
            "angles are absent rather than compared across two different frame conventions."
        )
    if alignment is not None:
        notes.append(
            "Our world datum and theirs are different choices of origin and axes, so one rigid "
            f"transform is fitted over the {alignment.joints_used} joints both files place and ours "
            "is carried into their frame before any angle is computed. The rotation is fitted to the "
            "axis directions and the translation to the anchor centroid. It is a change of frame, "
            "not a correction of the robot: the axis angles and anchor distances below are the "
            "residual after it."
        )
        notes.append(
            "The rotation is fitted to the axis directions rather than to the anchor positions. An "
            "anchor is a poor constraint on a rotation: a revolute joint's origin is free to sit "
            "anywhere along its own axis, and a difference in the pose the two files were stored in "
            "moves every anchor at once. Fitting the rotation to anchors spends both of those on the "
            "rotation and reports the robot as worse than it is."
        )
        if alignment.rotations_tied > 1:
            notes.append(
                f"{alignment.rotations_tied} sense combinations fitted the axis directions within "
                f"{_TIE_DEG} degrees of each other, so the directions alone did not decide the "
                "datum. The anchors chose between them, and the rotation printed above is the one "
                "they chose. A reader who disagrees with that tie-break should know the axis "
                "agreement would look the same under the others."
            )
        if any(sign < 0 for sign in alignment.axis_signs):
            flipped = sum(1 for sign in alignment.axis_signs if sign < 0)
            notes.append(
                f"{flipped} of {len(alignment.axis_signs)} of our axes had to be reversed to agree "
                "with theirs. A revolute axis has no natural sense, so a reversed axis is a "
                "convention both files are free to choose differently; the per-joint signs are in "
                "the frame alignment table so the choice is visible rather than assumed."
            )
        notes.append(
            "The anchor distance is split along their joint's own axis and perpendicular to it. Only "
            "the perpendicular part is a statement about where the joint is: an along-axis "
            "difference is the freedom every revolute joint has to put its origin anywhere on its "
            "axis line. A perpendicular difference is real, and it can come from the pose each file "
            "was stored in as well as from the geometry, so this comparison reports it without "
            "attributing it."
        )
    elif joint_map and not world_error:
        notes.append(
            "No rigid frame alignment could be fitted: fewer than three joints are shared with a "
            "known anchor on both sides. The axis angles below are therefore read across two "
            "independent world datums, and where the datums differ they measure the datum rather "
            "than the joint."
        )
    return Comparison(
        ours=ours_label,
        theirs=theirs_label,
        ours_total_kg=ours_total,
        theirs_total_kg=theirs_total,
        delta_kg=ours_total - theirs_total,
        delta_percent=(
            None if theirs_total <= 0.0 else 100.0 * (ours_total - theirs_total) / theirs_total
        ),
        bodies=bodies,
        joints=comparison_joints,
        link_spacings=spacings,
        alignment=alignment,
        notes=notes,
    )


def _printed_kg_text(body: BodyComparison) -> str:
    if body.ours_printed_upper_kg is None:
        return "—"
    text = f"{body.ours_printed_upper_kg:.4f}"
    return text + "*" if body.ours_unclassified_volume_m3 else text


def _printed_fill_text(body: BodyComparison) -> str:
    return "—" if body.printed_fill is None else f"{body.printed_fill:.2f}"


def render_markdown(comparison: Comparison) -> str:
    rows = [
        "| body (ours) | body (theirs) | ours kg | printed only (ub) kg | theirs kg | delta g "
        "| delta % | fill vs whole mass | printed fill |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for b in comparison.bodies:
        theirs = "—" if b.theirs_kg is None else f"{b.theirs_kg:.4f}"
        delta = "—" if b.delta_kg is None else f"{(b.delta_kg) * 1e3:+.1f}"
        pct = "—" if b.delta_percent is None else f"{b.delta_percent:+.1f}%"
        fill = "—" if b.implied_fill is None else f"{b.implied_fill:.2f}"
        rows.append(
            f"| `{b.ours}` | {b.theirs or '—'} | {b.ours_kg:.4f} | {_printed_kg_text(b)} | "
            f"{theirs} | {delta} | {pct} | {fill} | {_printed_fill_text(b)} |"
        )
    printed_total = [b.ours_printed_upper_kg for b in comparison.bodies]
    printed_total = (
        f"{sum(printed_total):.4f}" if all(v is not None for v in printed_total) and printed_total
        else "—"
    )
    rows.append(
        f"| **total** | | **{comparison.ours_total_kg:.4f}** | **{printed_total}** "
        f"| **{comparison.theirs_total_kg:.4f}** "
        f"| **{comparison.delta_kg * 1e3:+.1f}** "
        f"| **{'—' if comparison.delta_percent is None else f'{comparison.delta_percent:+.1f}%'}** | | |"
    )
    joints = [
        "| joint (ours) | joint (theirs) | ours axis (CAD world) | ours in their frame "
        "| theirs axis (world, rest) | angle after carry | anchor delta (mm) | along axis (mm) "
        "| perpendicular (mm) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for j in comparison.joints:
        ours = " ".join(f"{v:+.3f}" for v in j.ours_axis)
        carried_axis = (
            " ".join(f"{v:+.3f}" for v in j.ours_axis_in_theirs) if j.ours_axis_in_theirs else "—"
        )
        theirs = " ".join(f"{v:+.3f}" for v in j.theirs_axis) if j.theirs_axis else "—"
        angle = "—" if j.axis_angle_deg is None else f"{j.axis_angle_deg:.2f}°"
        anchor = "—" if j.anchor_delta_m is None else f"{j.anchor_delta_m * 1e3:.2f}"
        along = "—" if j.anchor_along_axis_m is None else f"{j.anchor_along_axis_m * 1e3:+.2f}"
        perp = "—" if j.anchor_perpendicular_m is None else f"{j.anchor_perpendicular_m * 1e3:.2f}"
        joints.append(
            f"| `{j.ours}` | {j.theirs or '—'} | {ours} | {carried_axis} | {theirs} | {angle} "
            f"| {anchor} | {along} | {perp} |"
        )
    spacing_rows = []
    if comparison.link_spacings:
        spacing_rows = [
            "| joint | to joint | ours (mm) | theirs (mm) | delta (mm) | delta % |",
            "|---|---|---|---|---|---|",
        ]
        for s in comparison.link_spacings:
            pct = "—" if s.delta_percent is None else f"{s.delta_percent:+.2f}%"
            spacing_rows.append(
                f"| `{s.from_joint}` | `{s.to_joint}` | {s.ours_m * 1e3:.2f} "
                f"| {s.theirs_m * 1e3:.2f} | {s.delta_m * 1e3:+.2f} | {pct} |"
            )
    notes = "\n".join(f"- {n}" for n in comparison.notes)
    return (
        f"## Mass: {comparison.ours} against {comparison.theirs}\n\n"
        + "\n".join(rows)
        + (
            "\n\n## Joint-to-joint spacing (no frame needed)\n\n" + "\n".join(spacing_rows)
            if spacing_rows
            else ""
        )
        + "\n\n## Frame alignment\n\n"
        + _alignment_markdown(comparison.alignment)
        + "\n\n## Joint axes\n\n"
        + "\n".join(joints)
        + "\n\n## Notes\n\n"
        + notes
        + "\n"
    )


def _alignment_markdown(alignment: FrameAlignment | None) -> str:
    if alignment is None:
        return (
            "Not fitted: fewer than three joints are placed in both files, so our axes and theirs "
            "are read in two independent world frames."
        )
    return (
        "| | value |\n|---|---|\n"
        f"| method | {alignment.method} |\n"
        f"| joints used | {alignment.joints_used} |\n"
        f"| rotation (axis x angle, deg) | {' '.join(f'{v:+.3f}' for v in alignment.rotation_deg)} |\n"
        f"| translation (m) | {' '.join(f'{v:+.4f}' for v in alignment.translation_m)} |\n"
        f"| axis senses used | {' '.join(f'{v:+d}' for v in alignment.axis_signs) or '—'} |\n"
        f"| rotations that fitted equally | {alignment.rotations_tied} |\n"
        f"| axis residual, RMS (deg) | "
        f"{'—' if alignment.rms_axis_deg is None else f'{alignment.rms_axis_deg:.2f}'} |\n"
        f"| axis residual, worst (deg) | "
        f"{'—' if alignment.worst_axis_deg is None else f'{alignment.worst_axis_deg:.2f}'} |\n"
        f"| anchor residual, RMS (mm) | "
        f"{'—' if alignment.rms_point_m is None else f'{alignment.rms_point_m * 1e3:.3f}'} |\n"
        f"| anchor residual, worst (mm) | "
        f"{'—' if alignment.worst_point_m is None else f'{alignment.worst_point_m * 1e3:.3f}'} |"
    )


def render_html(comparison: Comparison) -> str:
    """The same table as the markdown, so the bundle's own report carries the comparison.

    A reader who opens ``report.html`` should not have to trust a side document that may have been
    edited separately; the numbers on the page are the numbers the run produced.
    """
    import html as _html

    rows = []
    for b in comparison.bodies:
        theirs = "—" if b.theirs_kg is None else f"{b.theirs_kg:.4f}"
        delta = "—" if b.delta_kg is None else f"{b.delta_kg * 1e3:+.1f}"
        pct = "—" if b.delta_percent is None else f"{b.delta_percent:+.1f}%"
        fill = "—" if b.implied_fill is None else f"{b.implied_fill:.2f}"
        flag = " (assumed density)" if b.assumed_density else ""
        rows.append(
            f"<tr><td><code>{_html.escape(b.ours)}</code>{flag}</td>"
            f"<td>{_html.escape(b.theirs or '—')}</td><td>{b.ours_kg:.4f}</td>"
            f"<td>{_printed_kg_text(b)}</td>"
            f"<td>{theirs}</td><td>{delta}</td><td>{pct}</td><td>{fill}</td>"
            f"<td>{_printed_fill_text(b)}</td></tr>"
        )
    rows.append(
        f"<tr><th>total</th><th></th><th>{comparison.ours_total_kg:.4f}</th><th></th>"
        f"<th>{comparison.theirs_total_kg:.4f}</th><th>{comparison.delta_kg * 1e3:+.1f}</th>"
        f"<th>{'—' if comparison.delta_percent is None else f'{comparison.delta_percent:+.1f}%'}</th>"
        f"<th></th><th></th></tr>"
    )
    joints = "".join(
        f"<tr><td><code>{_html.escape(j.ours)}</code></td><td>{_html.escape(j.theirs or '—')}</td>"
        f"<td>{' '.join(f'{v:+.3f}' for v in j.ours_axis)}</td>"
        f"<td>{' '.join(f'{v:+.3f}' for v in j.ours_axis_in_theirs) if j.ours_axis_in_theirs else '—'}</td>"
        f"<td>{' '.join(f'{v:+.3f}' for v in j.theirs_axis) if j.theirs_axis else '—'}</td>"
        f"<td>{'—' if j.axis_angle_deg is None else f'{j.axis_angle_deg:.2f}&deg;'}</td>"
        f"<td>{'—' if j.anchor_delta_m is None else f'{j.anchor_delta_m * 1e3:.2f}'}</td>"
        f"<td>{'—' if j.anchor_along_axis_m is None else f'{j.anchor_along_axis_m * 1e3:+.2f}'}</td>"
        f"<td>{'—' if j.anchor_perpendicular_m is None else f'{j.anchor_perpendicular_m * 1e3:.2f}'}</td>"
        "</tr>"
        for j in comparison.joints
    )
    spacing_html = ""
    if comparison.link_spacings:
        spacing_html = (
            "<h3>Joint-to-joint spacing (no frame needed)</h3>"
            "<table><tr><th>joint</th><th>to joint</th><th>ours (mm)</th><th>theirs (mm)</th>"
            "<th>delta (mm)</th><th>delta %</th></tr>"
            + "".join(
                f"<tr><td><code>{_html.escape(s.from_joint)}</code></td>"
                f"<td><code>{_html.escape(s.to_joint)}</code></td>"
                f"<td>{s.ours_m * 1e3:.2f}</td><td>{s.theirs_m * 1e3:.2f}</td>"
                f"<td>{s.delta_m * 1e3:+.2f}</td>"
                f"<td>{'—' if s.delta_percent is None else f'{s.delta_percent:+.2f}%'}</td></tr>"
                for s in comparison.link_spacings
            )
            + "</table>"
        )
    notes = "".join(f"<li>{_html.escape(n)}</li>" for n in comparison.notes)
    return (
        f"<h2>Against {_html.escape(comparison.theirs)}</h2>"
        "<table><tr><th>body (ours)</th><th>body (theirs)</th><th>ours kg</th>"
        "<th>printed only (ub) kg</th><th>theirs kg</th>"
        "<th>delta g</th><th>delta %</th><th>fill vs whole mass</th>"
        "<th>printed fill</th></tr>"
        + "".join(rows)
        + "</table>"
        + spacing_html
        + f"<h3>Frame alignment</h3>{_alignment_html(comparison.alignment)}"
        + ("<table><tr><th>joint (ours)</th><th>joint (theirs)</th>"
           "<th>ours axis (CAD world)</th><th>ours in their frame</th>"
           "<th>theirs axis (world, rest)</th><th>angle after carry</th>"
           "<th>anchor delta (mm)</th><th>along axis (mm)</th><th>perpendicular (mm)</th></tr>"
           + joints + "</table>")
        + f"<ul>{notes}</ul>"
    )


def _alignment_html(alignment: FrameAlignment | None) -> str:
    import html as _html

    if alignment is None:
        return (
            "<p>Not fitted: fewer than three joints are placed in both files, so our axes and "
            "theirs are read in two independent world frames.</p>"
        )
    def num(value: float | None, scale: float = 1.0, digits: int = 3, suffix: str = "") -> str:
        return "—" if value is None else f"{value * scale:.{digits}f}{suffix}"

    return (
        "<table><tr><th>field</th><th>value</th></tr>"
        f"<tr><td>method</td><td>{_html.escape(alignment.method)}</td></tr>"
        f"<tr><td>joints used</td><td>{alignment.joints_used}</td></tr>"
        f"<tr><td>rotations that fitted equally</td><td>{alignment.rotations_tied}</td></tr>"
        f"<tr><td>rotation (axis x angle, deg)</td><td>"
        f"{' '.join(f'{v:+.3f}' for v in alignment.rotation_deg)}</td></tr>"
        f"<tr><td>translation (m)</td><td>"
        f"{' '.join(f'{v:+.4f}' for v in alignment.translation_m)}</td></tr>"
        f"<tr><td>anchor residual, RMS (mm)</td><td>{num(alignment.rms_point_m, 1e3)}</td></tr>"
        f"<tr><td>anchor residual, worst (mm)</td><td>{num(alignment.worst_point_m, 1e3)}</td></tr>"
        f"<tr><td>axis residual, worst (deg)</td><td>{num(alignment.worst_axis_deg)}</td></tr>"
        "</table>"
    )


__all__ = [
    "BodyComparison",
    "Comparison",
    "FrameAlignment",
    "JointComparison",
    "LinkSpacing",
    "compare",
    "fit_frame_alignment",
    "read_urdf",
    "render_html",
    "render_markdown",
    "world_joint_axes",
    "world_joint_frames",
]
