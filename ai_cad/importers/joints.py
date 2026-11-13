"""Joint inference from imported CAD, and the review file it writes.

The design constraint comes from measurement, not from taste. On the pinned SO-101 assembly the six
named arm links share **zero** coaxial bore/shaft interfaces with each other, at any tolerance down
to 0.5 mm: those links meet through servos, planar faces and M3 screw holes, not through a bore and
a matching boss. A geometry-only rule therefore recovers one joint on that robot (the gripper jaw on
its servo), and a rule loosened until it finds the others also matches screws to screws.

So this module does not pretend to find the whole kinematic tree. It finds what the geometry
supports, says so per joint with the evidence attached, and leaves the rest in ``unresolved_pairs``
for a human to fill in. The output is a proposal, never a claim: ``review_required`` is true on
every joint and nothing downstream may treat a proposed joint as verified.

Tolerances are stated in metres and are deliberately tight enough that a false joint is rarer than a
missing one: a wrong axis in a physics model is worse than an axis a user has to draw.
"""
from __future__ import annotations

import math
import re
import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from ai_cad.importers.features import CylinderFace, extract_cylinders
from ai_cad.importers.models import ImportedAssembly

SCHEMA = "robocad.joints/1"

# A joint interface is a bore and a shaft of the same nominal size on a shared axis. These are the
# numbers that separate a real interface from two holes that happen to line up.
MIN_JOINT_RADIUS_M = 2.0e-3
RADIAL_MATCH_M = 0.5e-3
AXIS_OFFSET_M = 0.5e-3
PARALLEL_DOT = 0.995  # ~5.7 degrees; a bearing axis is much tighter than this in practice
# Two bodies further apart than this cannot be joined directly, so their missing interface is not
# an unresolved joint: listing every pair in a 26-body robot produces 275 lines of noise that bury
# the pairs a reviewer needs to look at. It is also the cheap test that runs before the expensive
# cylinder comparison, so a pathological assembly costs bbox maths, not an n^2 cylinder scan.
MAX_PAIR_GAP_M = 5.0e-3

# Guards on the review artefact and on the pairing loop. A CAD file is untrusted input: the number
# of bodies and the number of faces per body are both attacker-controlled, and the loop is
# quadratic in the first and linear in the second.
MAX_PAIRING_BODIES = 400
MAX_CYLINDERS_PER_LINK = 400
MAX_UNRESOLVED_PAIRS = 250
DEFAULT_INFER_BUDGET_S = 60.0
BUDGET_CHECK_EVERY = 512


class JointInferenceError(RuntimeError):
    """Raised when inference exceeds a budget instead of returning a partial proposal."""

FASTENER_PATTERN = re.compile(
    r"\b(screw|nut|bolt|washer|rivet|circlip|pin|spring|bearing|din|iso\s?\d|m\d\s?x)\b",
    re.IGNORECASE,
)
ACTUATOR_PATTERN = re.compile(r"\b(servo|motor|actuator|stepper|encoder)\b", re.IGNORECASE)


class LinkGroup(BaseModel):
    """A set of placed instances the proposal treats as one rigid body."""

    link_id: str
    name: str
    instance_ids: list[str] = Field(default_factory=list)
    part_ids: list[str] = Field(default_factory=list)
    volume_m3: float = 0.0
    bbox_min_m: tuple[float, float, float] = (0.0, 0.0, 0.0)
    bbox_max_m: tuple[float, float, float] = (0.0, 0.0, 0.0)
    role: str = "link"  # "link" | "actuator" | "fastener" | "unclassified"


class JointEvidence(BaseModel):
    kind: str = "coaxial_bore_shaft"
    radius_m: float
    radial_gap_m: float
    axis_offset_m: float
    face_pairs: int


class ProposedJoint(BaseModel):
    joint_id: str
    parent_link: str
    child_link: str
    joint_type: str = "revolute"
    axis_point: tuple[float, float, float]
    axis_dir: tuple[float, float, float]
    limits: dict[str, float] | None = None
    evidence: JointEvidence
    confidence: float = 0.0
    review_required: bool = True


class JointProposal(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # Named ``schema`` in the file, because that is the key a reader expects; stored under
    # ``schema_version`` in Python because pydantic's BaseModel already owns ``schema``.
    schema_version: str = Field(default=SCHEMA, alias="schema", serialization_alias="schema")
    source: dict = Field(default_factory=dict)
    links: list[LinkGroup] = Field(default_factory=list)
    joints: list[ProposedJoint] = Field(default_factory=list)
    unresolved_pairs: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary: dict = Field(default_factory=dict)
    status: str = "proposed"

    def by_id(self) -> dict[str, ProposedJoint]:
        return {j.joint_id: j for j in self.joints}


# ------------------------------------------------------------------------------------------------
# link grouping
# ------------------------------------------------------------------------------------------------
def group_links(assembly: ImportedAssembly) -> list[LinkGroup]:
    """Group instances into rigid bodies using the assembly's own first-level structure.

    Designers already split a robot arm into links in the CAD tree: SO-101 has ``Base_SO101``,
    ``Rotation_Pitch_SO101``, ``Upper_arm_SO101`` and so on, one level below the root. That is better
    evidence than any clustering we could invent, so it is used directly. Loose instances that are
    fasteners or carry no meaningful name are not links: they are attached to the nearest link by
    bounding-box distance and recorded in it, because a joint axis never runs through a screw head.
    """
    groups: dict[str, LinkGroup] = {}
    seen_ids: dict[str, int] = {}
    instances = {inst.instance_id: inst for inst in assembly.instances}
    for inst in assembly.instances:
        key = inst.assembly_path[1] if len(inst.assembly_path) > 1 else "<root>"
        group = groups.get(key)
        if group is None:
            name = _clean_name(key)
            # The CAD keys groups by label name, which carries a version suffix ("Base_SO101
            # v12:1"). The readable identity for review is the part name; the suffix is noise a
            # reviewer would have to skip past on every line. Seven identical servos share one
            # name, so repeats are numbered in the order they appear.
            link_id = _slug(name)
            seen_ids[link_id] = seen_ids.get(link_id, 0) + 1
            if seen_ids[link_id] > 1:
                link_id = f"{link_id}_{seen_ids[link_id]}"
            group = LinkGroup(link_id=link_id, name=name)
            groups[key] = group
        group.instance_ids.append(inst.instance_id)
        if inst.part_id not in group.part_ids:
            group.part_ids.append(inst.part_id)
        part = assembly.parts.get(inst.part_id)
        if part is not None:
            group.volume_m3 += part.signature.volume_m3

    for group in groups.values():
        group.role = _classify(group.name)
        group.bbox_min_m, group.bbox_max_m = _group_bbox(instances, assembly.parts, group)

    primary = [g for g in groups.values() if g.role in ("link", "unclassified")]
    loose = [g for g in groups.values() if g.role == "fastener"]
    for group in loose:
        host = _nearest_group(group, primary)
        if host is None:
            continue
        host.instance_ids.extend(group.instance_ids)
        for pid in group.part_ids:
            if pid not in host.part_ids:
                host.part_ids.append(pid)
        host.volume_m3 += group.volume_m3
    attached = {id(g) for g in loose}
    return [g for g in groups.values() if id(g) not in attached]


def _classify(name: str) -> str:
    if ACTUATOR_PATTERN.search(name):
        return "actuator"
    if FASTENER_PATTERN.search(name):
        return "fastener"
    if re.fullmatch(r"(component|part|solid)\s*\d*", name.strip(), re.IGNORECASE):
        return "unclassified"
    if name.strip().isdigit():
        return "unclassified"
    return "link"


def _group_bbox(instances: dict[str, object], parts, group: LinkGroup):
    lo = [math.inf] * 3
    hi = [-math.inf] * 3
    for iid in group.instance_ids:
        inst = instances.get(iid)
        part = parts.get(inst.part_id) if inst is not None else None
        if part is None:
            continue
        m = inst.transform
        t = (m[3], m[7], m[11])
        for axis in range(3):
            v = part.signature.bbox_min_m[axis]
            lo[axis] = min(lo[axis], v + t[axis])
            v = part.signature.bbox_max_m[axis]
            hi[axis] = max(hi[axis], v + t[axis])
    if any(math.isinf(v) for v in lo):
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
    return tuple(lo), tuple(hi)


def _nearest_group(group: LinkGroup, candidates: list[LinkGroup]) -> LinkGroup | None:
    best = None
    for cand in candidates:
        gap = _bbox_gap(group, cand)
        if best is None or gap < best[0]:
            best = (gap, cand)
    return best[1] if best else None


def _bbox_gap(a: LinkGroup, b: LinkGroup) -> float:
    total = 0.0
    for axis in range(3):
        gap = max(0.0, a.bbox_min_m[axis] - b.bbox_max_m[axis],
                  b.bbox_min_m[axis] - a.bbox_max_m[axis])
        total += gap * gap
    return math.sqrt(total)


# ------------------------------------------------------------------------------------------------
# joint inference
# ------------------------------------------------------------------------------------------------
def infer_joints(
    assembly: ImportedAssembly,
    links: list[LinkGroup] | None = None,
    cylinders: list[CylinderFace] | None = None,
    budget_s: float | None = DEFAULT_INFER_BUDGET_S,
) -> JointProposal:
    links = links if links is not None else group_links(assembly)
    cylinders = cylinders if cylinders is not None else extract_cylinders(assembly)
    deadline = None if budget_s is None else time.monotonic() + budget_s
    if deadline is not None and time.monotonic() > deadline:
        raise JointInferenceError(
            f"joint inference exceeded its {budget_s:.0f} s budget before pairing began"
        )
    link_of = {iid: g.link_id for g in links for iid in g.instance_ids}
    by_link: dict[str, list[CylinderFace]] = {}
    for face in cylinders:
        lid = link_of.get(face.instance_id)
        if lid:
            by_link.setdefault(lid, []).append(face)

    joints: list[ProposedJoint] = []
    unresolved: list[dict] = []
    jointed: set[frozenset[str]] = set()
    extra_warnings: list[str] = []

    candidates = [g for g in links if g.role in ("link", "actuator", "unclassified")]
    if len(candidates) > MAX_PAIRING_BODIES:
        # Pairing is quadratic. Keep the bodies that could plausibly matter (largest first) and say
        # so, rather than spend an unbounded amount of time proving the rest cannot be jointed.
        ordered = sorted(candidates, key=lambda g: -g.volume_m3)
        candidates = ordered[:MAX_PAIRING_BODIES]
        extra_warnings.append(
            f"{len(links)} candidate bodies exceeds the {MAX_PAIRING_BODIES}-body pairing cap; "
            "only the largest bodies were compared. Review this proposal as partial."
        )

    faces_for = {
        g.link_id: sorted(by_link.get(g.link_id, []), key=lambda f: -f.area_m2)[
            :MAX_CYLINDERS_PER_LINK
        ]
        for g in candidates
    }

    checks = 0
    for i, left in enumerate(candidates):
        for right in candidates[i + 1:]:
            checks += 1
            if deadline is not None and checks % BUDGET_CHECK_EVERY == 0:
                if time.monotonic() > deadline:
                    raise JointInferenceError(
                        f"joint inference exceeded its {budget_s:.0f} s budget after {checks} "
                        "body pairs"
                    )
            # Cheap test first: two bodies that do not touch cannot share a bearing interface.
            if _bbox_gap(left, right) > MAX_PAIR_GAP_M:
                continue
            pair = _best_interface(faces_for[left.link_id], faces_for[right.link_id])
            if pair is None:
                continue
            jointed.add(frozenset((left.link_id, right.link_id)))
            joints.append(_to_joint(len(joints) + 1, left, right, pair))

    joints, dropped = _spanning_tree(joints)
    omitted = 0
    for i, left in enumerate(candidates):
        for right in candidates[i + 1:]:
            if frozenset((left.link_id, right.link_id)) in jointed:
                continue
            if left.role == "unclassified" or right.role == "unclassified":
                continue
            if _bbox_gap(left, right) > MAX_PAIR_GAP_M:
                continue
            if len(unresolved) >= MAX_UNRESOLVED_PAIRS:
                omitted += 1
                continue
            unresolved.append(
                {
                    "parent_link": left.link_id,
                    "child_link": right.link_id,
                    "reason": "no coaxial bore/shaft interface between these bodies at "
                    f"radius >= {MIN_JOINT_RADIUS_M * 1e3:.1f} mm",
                    "next_step": "supply the joint axis by hand, or add contact analysis",
                }
            )
    if omitted:
        extra_warnings.append(
            f"{omitted} further unresolved pair(s) were not listed; the cap is "
            f"{MAX_UNRESOLVED_PAIRS}. Review this proposal as partial."
        )

    warnings = _structure_warnings(links, joints)
    warnings.extend(extra_warnings)
    for joint in dropped:
        warnings.append(
            f"joint {joint.joint_id} ({joint.parent_link} -> {joint.child_link}) closes a loop "
            "with stronger joints and was dropped; check whether the assembly is over-constrained"
        )
    return JointProposal(
        source={
            # The basename, not the absolute path: a proposal is written to be committed and read
            # by someone else, and a machine-local temp path leaks where it came from without
            # identifying which revision. The hash is what identifies the input.
            "file": Path(assembly.source_path).name,
            "sha256": _sha256(assembly.source_path),
            "bytes": assembly.source_bytes,
            "parts": assembly.part_count,
            "instances": assembly.instance_count,
            "units": assembly.units,
        },
        links=links,
        joints=joints,
        unresolved_pairs=unresolved,
        warnings=warnings,
        summary={
            "links": len(links),
            "joints": len(joints),
            "unresolved_pairs": len(unresolved),
            "cylinders_extracted": len(cylinders),
            "tolerances": {
                "min_radius_m": MIN_JOINT_RADIUS_M,
                "radial_match_m": RADIAL_MATCH_M,
                "axis_offset_m": AXIS_OFFSET_M,
                "parallel_dot": PARALLEL_DOT,
                "max_pair_gap_m": MAX_PAIR_GAP_M,
            },
            "note": "geometry-confirmed joints only; a missing joint is expected on "
                    "servo-mediated assemblies and is for review, not a failure",
        },
    )


def _best_interface(left: list[CylinderFace], right: list[CylinderFace]):
    best = None
    face_pairs = 0
    for a in left:
        if a.radius_m < MIN_JOINT_RADIUS_M:
            continue
        for b in right:
            if b.radius_m < MIN_JOINT_RADIUS_M:
                continue
            if a.is_bore == b.is_bore:
                continue
            gap = abs(a.radius_m - b.radius_m)
            if gap > RADIAL_MATCH_M:
                continue
            if abs(_dot(a.axis_dir, b.axis_dir)) < PARALLEL_DOT:
                continue
            offset = _line_distance(a.axis_point, a.axis_dir, b.axis_point)
            if offset > AXIS_OFFSET_M:
                continue
            face_pairs += 1
            score = (gap, offset)
            if best is None or score < best[0]:
                best = (score, a, b)
    if best is None:
        return None
    _, first, second = best
    # ``left`` and ``right`` arrive as whole links, but either one may be the bore: record which
    # side holds it so the joint's parent/child is decided by the interface, not by argument order.
    bore_on_left = first.is_bore
    bore, shaft = (first, second) if bore_on_left else (second, first)
    return {
        "bore": bore,
        "shaft": shaft,
        "radius": (bore.radius_m + shaft.radius_m) * 0.5,
        "gap": abs(bore.radius_m - shaft.radius_m),
        "offset": _line_distance(bore.axis_point, bore.axis_dir, shaft.axis_point),
        "face_pairs": face_pairs,
        "bore_on_left": bore_on_left,
    }


def _to_joint(index: int, left: LinkGroup, right: LinkGroup, pair: dict) -> ProposedJoint:
    """Turn an interface into a proposed joint.

    Convention: the body carrying the **shaft** is the parent and the body carrying the **bore** is
    the child. On a servo-driven arm that is the servo body holding the output spline and the link
    that rotates around it, which is the tree a reviewer expects. It is a convention, not a
    measurement, so the joint stays marked as needing review.
    """
    bore = pair["bore"]
    parent, child = (right, left) if pair["bore_on_left"] else (left, right)
    point = _project_to_midpoint(bore.axis_point, bore.axis_dir, parent, child)
    confidence = _confidence(pair)
    return ProposedJoint(
        joint_id=f"joint_{index:02d}",
        parent_link=parent.link_id,
        child_link=child.link_id,
        axis_point=point,
        axis_dir=bore.axis_dir,
        evidence=JointEvidence(
            radius_m=pair["radius"],
            radial_gap_m=pair["gap"],
            axis_offset_m=pair["offset"],
            face_pairs=pair["face_pairs"],
        ),
        confidence=confidence,
    )


def _project_to_midpoint(point, direction, parent: LinkGroup, child: LinkGroup):
    """A point on the joint axis, chosen near the interface so the YAML is readable.

    OCC reports a cylinder's axis origin wherever the surface was parameterised, which on real parts
    can be tens of metres from the body. The line is what is physical, so the reported point is the
    projection of the interface midpoint onto that line.
    """
    mid = tuple(
        (parent.bbox_min_m[a] + parent.bbox_max_m[a] + child.bbox_min_m[a] + child.bbox_max_m[a]) / 4.0
        for a in range(3)
    )
    along = _dot(_sub(mid, point), direction)
    return tuple(point[a] + along * direction[a] for a in range(3))


def _confidence(pair: dict) -> float:
    """Rises with the number of matching faces, falls with radial gap and axis offset."""
    base = min(0.6, 0.1 * pair["face_pairs"])
    gap_term = max(0.0, 0.25 - 200.0 * pair["gap"])
    offset_term = max(0.0, 0.15 - 150.0 * pair["offset"])
    return round(min(0.95, base + gap_term + offset_term), 3)


def _spanning_tree(joints: list[ProposedJoint]) -> tuple[list[ProposedJoint], list[ProposedJoint]]:
    """Keep the strongest joints that form a tree, and hand back the rest as dropped cycles.

    A set of joints that closes a loop cannot all be right: either one is a false positive from two
    holes that happen to line up, or the assembly really is over-constrained. Either way the extra
    joint is not silently discarded, it is reported.
    """
    ordered = sorted(joints, key=lambda j: (-j.confidence, j.joint_id))
    parent: dict[str, str] = {}
    for joint in ordered:
        parent.setdefault(joint.parent_link, joint.parent_link)
        parent.setdefault(joint.child_link, joint.child_link)

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    kept: list[ProposedJoint] = []
    dropped: list[ProposedJoint] = []
    for joint in ordered:
        a, b = find(joint.parent_link), find(joint.child_link)
        if a == b:
            dropped.append(joint)
            continue
        parent[a] = b
        kept.append(joint)
    kept.sort(key=lambda j: j.joint_id)
    dropped.sort(key=lambda j: j.joint_id)
    return kept, dropped


def _structure_warnings(links: list[LinkGroup], joints: list[ProposedJoint]) -> list[str]:
    warnings: list[str] = []
    roots = set()
    connected = {j.parent_link for j in joints} | {j.child_link for j in joints}
    for group in links:
        if group.link_id not in connected:
            continue
        if group.link_id not in {j.child_link for j in joints}:
            roots.add(group.link_id)
    if len(roots) > 1:
        warnings.append(
            f"{len(roots)} separate kinematic trees in the proposal; expected one root"
        )
    isolated = [g.name for g in links if g.link_id not in connected]
    if isolated:
        warnings.append(
            f"{len(isolated)} body group(s) have no inferred joint: "
            + ", ".join(isolated[:6])
        )
    return warnings


# ------------------------------------------------------------------------------------------------
# YAML output
# ------------------------------------------------------------------------------------------------
def write_proposal(proposal: JointProposal, path: str | Path, notice: str | None = None) -> Path:
    """Write the proposal as YAML.

    ``notice`` is prepended as comments. It exists for third-party robots: a proposal derived from
    someone else's CAD file is a derived work, so the file that carries it must carry the licence
    notice and a statement of what was changed too, not just the proposal.
    """
    import yaml

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# RoboCAD joint proposal\n"
        "# Generated from CAD geometry. Every joint here is a PROPOSAL: limits are unknown and\n"
        "# the joint tree has not been verified against the real machine. Review before use.\n"
        "# Geometry-confirmed joints only; pairs with no coaxial bore/shaft interface are listed\n"
        "# under unresolved_pairs with the reason they are missing.\n"
    )
    attribution = ""
    if notice:
        attribution = "".join(
            f"# {line}\n" if line else "#\n" for line in notice.strip().splitlines()
        )
        attribution += "#\n"
    body = yaml.safe_dump(
        proposal.model_dump(mode="json", by_alias=True), sort_keys=False, allow_unicode=True
    )
    out.write_text(header + attribution + body, encoding="utf-8")
    return out


def read_proposal(path: str | Path) -> JointProposal:
    import yaml

    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return JointProposal.model_validate(data)


def diff_proposals(before: JointProposal, after: JointProposal) -> dict:
    """What changed between two proposals, in terms a reviewer can act on."""
    old, new = before.by_id(), after.by_id()
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = []
    for joint_id in sorted(set(old) & set(new)):
        a, b = old[joint_id], new[joint_id]
        fields = []
        if a.parent_link != b.parent_link or a.child_link != b.child_link:
            fields.append("topology")
        if _angle_deg(a.axis_dir, b.axis_dir) > 0.5:
            fields.append("axis_direction")
        if _norm(_sub(a.axis_point, b.axis_point)) > 1e-5:
            fields.append("axis_position")
        if abs(a.evidence.radius_m - b.evidence.radius_m) > 1e-6:
            fields.append("radius")
        if a.joint_type != b.joint_type:
            fields.append("type")
        if fields:
            changed.append({"joint_id": joint_id, "fields": fields})
    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "same": len(set(old) & set(new)) - len(changed),
    }


# -- helpers -------------------------------------------------------------------------------------
def _sha256(path: str) -> str:
    """Content hash of the source CAD, so a proposal names the exact revision it came from."""
    import hashlib

    if not path:
        return ""
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:  # a proposal is still useful when the file has been moved since import
        return ""


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _norm(v) -> float:
    return math.sqrt(_dot(v, v))


def _line_distance(p1, d, p2) -> float:
    v = _sub(p2, p1)
    along = _dot(v, d)
    perp = (v[0] - along * d[0], v[1] - along * d[1], v[2] - along * d[2])
    return _norm(perp)


def _angle_deg(a, b) -> float:
    cos = max(-1.0, min(1.0, abs(_dot(a, b))))
    return math.degrees(math.acos(cos))


def _slug(name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return cleaned or "body"

def _clean_name(name: str) -> str:
    return re.sub(r"\s+v\d+(:\d+)?$", "", name).strip()


__all__ = [
    "JointEvidence",
    "JointInferenceError",
    "JointProposal",
    "LinkGroup",
    "MAX_PAIR_GAP_M",
    "ProposedJoint",
    "SCHEMA",
    "diff_proposals",
    "group_links",
    "infer_joints",
    "read_proposal",
    "write_proposal",
]
