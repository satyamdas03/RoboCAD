"""The zero-pose convention that lets two models of the same robot be compared at all.

The compiled SO-101 and the published ``so101_new_calib.urdf`` describe the same robot but do not
share a zero pose or a base frame. Read raw, their joint origins disagree by a median of 168 mm, and
that number is a property of the comparison, not of the robot. Five constant per-joint offsets and
one base translation bring them into the same physical pose, and only then does a torque or a tip
position from one model mean the same as the same number from the other.

This module is the single place those numbers are written down. The bundle carries them in
``manifest.json`` and repeats them as a comment block in ``model.mjcf``, both rendered from here, so a
recipient who has the bundle has the convention without needing this repository. A consumer that
reads a constant out of its own source instead of out of the bundle will keep working after the
bundle is recompiled with a different convention, and will be wrong without saying so.

Two things this module does not do, both stated because a reader will assume otherwise:

* **It does not make a jaw-tip comparison valid.** The offsets align joint *origins*. The jaw's own
  frame sits 5.74 mm from the published jaw link origin at rest and no constant gripper offset
  reduces it (the best scan leaves 40.21 mm across poses), so a tip residual carries that frame into
  every sample and grows with reach. A constant offset cannot fix a translation of a frame. See
  ``docs/twin/so101/CONVENTIONS.md``.
* **Applying the offsets puts some compiled joints outside the compiled joint ranges.** That is a
  consequence of the convention itself: the two models state different zero poses, so a pose that is
  legal in one vector is not legal in the other. MuJoCo then applies joint-limit constraint forces,
  and inverse dynamics reports them as required torque -- 71 N m on a 0.9 kg arm whose own
  ``qfrc_bias`` is 0.34 N m, measured the hard way. A dynamics measurement that applies these
  offsets must disable contact AND limit constraints; see :func:`apply_to_compiled`.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

MANIFEST_SCHEMA = "robocad.twin.manifest/1"
CONVENTIONS_SCHEMA = "robocad.twin.conventions/1"

# Keys the residual block must carry. A single number would hide whether the tail is the same size
# as the middle, and it is the tail that decides whether a comparison of a 0.15 N*m signal survives.
RESIDUAL_KEYS = ("median", "p90", "max")


def _number(value: Any, where: str) -> float:
    """A finite float, or a refusal.

    ``bool`` is rejected on purpose. It is an ``int`` in Python and ``True`` would otherwise arrive as
    1.0, turning a flag someone typed into a measured degree.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{where}: expected a number, got {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{where}: {number!r} is not finite; a convention has to be a real number")
    return number


@dataclass(frozen=True)
class Conventions:
    """How one model's joint vector maps onto another's, plus the evidence it rests on.

    ``zero_pose_offsets_deg`` is keyed by the compiled joint name and applied to the compiled model,
    which is the direction every consumer here needs: replay a published trajectory on the compiled
    model. ``gripper_offset_deg`` is carried separately because the jaw's frame is a known-unknown
    rather than a sixth fitted offset -- its value is zero and that zero is not a measurement.
    """

    zero_pose_offsets_deg: Mapping[str, float] = field(default_factory=dict)
    gripper_offset_deg: float = 0.0
    base_translation_mm: tuple[float, float, float] = (0.0, 0.0, 0.0)
    base_rotation_deg: float = 0.0
    residual_mm: Mapping[str, float] = field(default_factory=dict)
    # False means no measurement was supplied, and the bundle says so rather than shipping a zero
    # vector that reads like a measured finding. A convention that was not measured is not identity,
    # it is unknown.
    measured: bool = False
    source: str = ""
    applied_to: str = "compiled"

    # -- construction -----------------------------------------------------------------------------
    def __post_init__(self) -> None:
        for joint, value in self.zero_pose_offsets_deg.items():
            _number(value, f"zero_pose_offsets_deg[{joint!r}]")
        _number(self.gripper_offset_deg, "gripper_offset_deg")
        if len(self.base_translation_mm) != 3:
            raise ValueError(
                f"base_translation_mm needs three components, got {len(self.base_translation_mm)}"
            )
        for index, value in enumerate(self.base_translation_mm):
            _number(value, f"base_translation_mm[{index}]")
        _number(self.base_rotation_deg, "base_rotation_deg")
        for key, value in self.residual_mm.items():
            _number(value, f"residual_mm[{key!r}]")
        if self.measured:
            missing = [key for key in RESIDUAL_KEYS if key not in self.residual_mm]
            if missing:
                raise ValueError(
                    "a measured convention must carry its residual "
                    f"(missing {missing}); an offset without an uncertainty is indistinguishable "
                    "from a guess that happens to be precise"
                )
            if not self.source:
                raise ValueError("a measured convention must name its source")
            if not self.zero_pose_offsets_deg:
                raise ValueError("a measured convention with no offsets is not a convention")

    # -- queries ----------------------------------------------------------------------------------
    def joint_offset_deg(self, joint_id: str) -> float:
        """The offset for one compiled joint, in degrees.

        A joint the convention does not name gets zero, which is the right answer for the jaw and
        the wrong answer for a joint nobody looked at. ``0.0 in`` the mapping is how a caller tells
        the two apart, so this returns zero rather than raising and callers that care check
        membership first.
        """
        return float(self.zero_pose_offsets_deg.get(joint_id, 0.0))

    def offset_vector_rad(self, joint_ids: Sequence[str]) -> np.ndarray:
        """The offsets in radians, in the caller's joint order.

        Ordering is the caller's, not this module's. A vector that arrives in the bundle's body
        order and is added to a vector in another order is the same class of defect as comparing at
        the same joint vector: it produces a number and the number is meaningless.
        """
        degrees = np.array([self.joint_offset_deg(j) for j in joint_ids], dtype=float)
        return np.radians(degrees)

    # -- mapping a state --------------------------------------------------------------------------
    def apply_to_compiled(self, qpos, qvel=None, qacc=None):
        """Map a published joint state onto the compiled model: ``q_compiled = q_official + offset``.

        The offsets are constant, so velocity and acceleration pass through unchanged -- and they
        are accepted and returned anyway, so the call site reads as "the whole state was mapped"
        rather than leaving a caller to infer that qvel was safe to keep.

        **Read this before using the result for dynamics.** With the offsets applied, some compiled
        joints land outside the compiled ``jnt_range``. MuJoCo resolves that with joint-limit
        constraint forces, and ``mj_inverse`` reports those as required torque. Contacts being
        disabled is not enough: disable ``mjDSBL_LIMIT`` as well, or the number is the solver pushing
        against a range rather than the load a gearbox holds. For the same reason, any trajectory
        compared this way has to be compared on a property that is invariant to the residual -- joint
        origins, not the jaw tip.
        """
        qpos = np.asarray(qpos, dtype=float)
        if qpos.ndim != 1:
            raise ValueError(f"qpos must be one-dimensional, got shape {qpos.shape}")
        if self.measured:
            # The chain the convention was fitted on is the named joints plus the jaw, in that order.
            # A vector of another length is a different robot or a different order, and adding a
            # prefix of the offsets to it would silently mis-align every joint after the first --
            # producing a number, which is the failure mode that hides.
            expected = len(self.zero_pose_offsets_deg) + 1
            if len(qpos) != expected:
                raise ValueError(
                    f"qpos has {len(qpos)} joints but this convention covers "
                    f"{len(self.zero_pose_offsets_deg)} plus the jaw ({expected}); the vector and "
                    "the convention are not for the same chain"
                )
            offsets = np.radians(
                np.array([*self.zero_pose_offsets_deg.values(), self.gripper_offset_deg], dtype=float)
            )
            mapped = qpos + offsets
        else:
            # No measurement: the mapping is the identity, and it is the identity because nothing is
            # known, not because the two models were shown to share a zero pose.
            mapped = qpos.copy()
        out = [mapped]
        for extra, name in ((qvel, "qvel"), (qacc, "qacc")):
            if extra is None:
                out.append(None)
                continue
            extra = np.asarray(extra, dtype=float)
            if extra.shape != qpos.shape:
                raise ValueError(f"{name} has shape {extra.shape}, qpos has {qpos.shape}")
            out.append(extra.copy())
        return tuple(out)

    # -- serialisation ----------------------------------------------------------------------------
    def to_manifest(self) -> dict:
        return {
            "schema_version": CONVENTIONS_SCHEMA,
            "applied_to": self.applied_to,
            "measured": self.measured,
            "zero_pose_offsets_deg": {k: float(v) for k, v in self.zero_pose_offsets_deg.items()},
            "gripper_offset_deg": float(self.gripper_offset_deg),
            "base_translation_mm": [float(v) for v in self.base_translation_mm],
            "base_rotation_deg": float(self.base_rotation_deg),
            "residual_mm": {k: float(v) for k, v in self.residual_mm.items()},
            "source": self.source,
            "note": (
                "Offsets apply to the compiled model, in degrees, in joint order. The base "
                "translation is world-frame millimetres at identity rotation. A consumer must read "
                "these from here rather than from its own constants: a stale copy keeps working "
                "after the bundle is recompiled and is wrong without saying so."
            ),
        }

    @classmethod
    def from_manifest(cls, data: Mapping[str, Any]) -> "Conventions":
        """Rebuild the convention from a bundle's ``manifest.json`` conventions block.

        Everything is validated here rather than trusted, because the file arrives from a bundle
        someone may have edited, generated on another machine, or hand-written. A convention that
        silently defaults to zero on a malformed field is worse than one that raises.
        """
        if not isinstance(data, Mapping):
            raise ValueError(f"conventions must be an object, got {type(data).__name__}")
        schema = data.get("schema_version")
        if schema != CONVENTIONS_SCHEMA:
            raise ValueError(
                f"conventions schema_version is {schema!r}, this reader speaks {CONVENTIONS_SCHEMA!r}"
            )
        offsets = data.get("zero_pose_offsets_deg")
        if not isinstance(offsets, Mapping):
            raise ValueError("zero_pose_offsets_deg must be an object of joint name to degrees")
        offsets = {str(k): _number(v, f"zero_pose_offsets_deg[{k!r}]") for k, v in offsets.items()}
        translation = data.get("base_translation_mm")
        if not isinstance(translation, (list, tuple)) or len(translation) != 3:
            raise ValueError("base_translation_mm must be three numbers")
        translation = tuple(
            _number(v, f"base_translation_mm[{i}]") for i, v in enumerate(translation)
        )
        residual = data.get("residual_mm")
        if not isinstance(residual, Mapping):
            raise ValueError("residual_mm must be an object")
        residual = {str(k): _number(v, f"residual_mm[{k!r}]") for k, v in residual.items()}
        measured = data.get("measured")
        if not isinstance(measured, bool):
            raise ValueError(f"measured must be true or false, got {measured!r}")
        source = data.get("source", "")
        if not isinstance(source, str):
            raise ValueError("source must be a string")
        return cls(
            zero_pose_offsets_deg=offsets,
            gripper_offset_deg=_number(data.get("gripper_offset_deg", 0.0), "gripper_offset_deg"),
            base_translation_mm=translation,
            base_rotation_deg=_number(data.get("base_rotation_deg", 0.0), "base_rotation_deg"),
            residual_mm=residual,
            measured=measured,
            source=source,
            applied_to=str(data.get("applied_to", "compiled")),
        )

    # -- rendering --------------------------------------------------------------------------------
    def mjcf_comment(self, indent: str = "  ") -> str:
        """The same convention as an XML comment, for the top of ``model.mjcf``.

        In the model file rather than only in a manifest because the model file is what a simulator
        opens and what a reader opens first. A convention that lives in a sibling is one a recipient
        can forward the model without.
        """
        if not self.measured:
            return (
                f"{indent}<!-- conventions: none measured. This bundle states no zero-pose offset or "
                "base translation; comparing its joint origins with another model's without one is "
                "meaningless. See manifest.json. -->"
            )
        offsets = ", ".join(
            f"{joint} {value:+.2f} deg" for joint, value in self.zero_pose_offsets_deg.items()
        )
        tx, ty, tz = (float(v) for v in self.base_translation_mm)
        residual = " / ".join(
            f"{key} {float(self.residual_mm[key]):.2f} mm" for key in RESIDUAL_KEYS
        )
        return (
            f"{indent}<!-- conventions: comparing joint origins without these offsets gives "
            f"misleading errors of several cm. Zero-pose offsets, applied to THIS (compiled) model, "
            f"in joint order, degrees: {offsets}; jaw {self.gripper_offset_deg:+.2f} deg (fixed, its "
            f"frame is excluded). Base translation of this model in world coordinates: "
            f"({tx:.2f}, {ty:.2f}, {tz:.2f}) mm at identity rotation "
            f"(base rotation {self.base_rotation_deg:.3f} deg, fitted and rejected: identity is the "
            f"better model of the frame). Residual at the five joint origins over 100 sampled poses: "
            f"{residual}. These offsets align joint ORIGINS, not the jaw tip; a tip residual carries "
            f"the jaw frame and is not a convention error. Applying them can put joints outside this "
            f"model's jnt_range, so a dynamics run must disable contact AND limit constraints. "
            f"Measured values live in manifest.json; read them there, not from a local constant. -->"
        )


# The measured SO-101 convention. Fitted by P0-a, independently reproduced by the second session from
# a zero seed, so the fit is a global basin rather than a lucky start. Values are authoritative from
# ``docs/demo/twin/p0a_confirmation.json``; where ``DECISIONS.md`` prints +90.28 and 6.63 the JSON
# wins, and the difference is a second-decimal transcription slip.
SO101 = Conventions(
    zero_pose_offsets_deg={
        "joint_1": -88.17,
        "joint_2": 90.29,
        "joint_3": -90.31,
        "joint_4": -0.15,
        "joint_5": 0.00,
    },
    gripper_offset_deg=0.0,
    base_translation_mm=(38.74, 6.64, -2.86),
    base_rotation_deg=0.0,
    residual_mm={"median": 2.50, "p90": 5.95, "max": 11.25},
    measured=True,
    source=(
        "P0-a registration of the compiled chain against so101_new_calib.urdf at "
        "TheRobotStudio/SO-ARM100 a758567: 100 poses from numpy.random.default_rng(0), uniform "
        "-1.7 to 1.7 rad, Euclidean distance at each of five joint origins. Reproduced from the "
        "published vector and from zero. See docs/demo/twin/p0a_confirmation.json and "
        "docs/twin/so101/CONVENTIONS.md."
    ),
)

NONE = Conventions(measured=False, source="no measurement supplied for this bundle")


# ------------------------------------------------------------------------------------------------
# the bundle side
# ------------------------------------------------------------------------------------------------
def manifest_path(bundle_dir: str | Path) -> Path:
    return Path(bundle_dir) / "manifest.json"


def write_manifest(
    bundle_dir: str | Path,
    name: str,
    conventions: Conventions,
    files: Mapping[str, str] | None = None,
) -> Path:
    """Write the bundle's ``manifest.json``, with the conventions inside it."""
    path = manifest_path(bundle_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": MANIFEST_SCHEMA,
        "name": name,
        "files": dict(
            files
            or {
                "joints": "robot.joints.yaml",
                "model_mjcf": "model.mjcf",
                "model_urdf": "model.urdf",
                "bundle": "bundle.json",
                "report": "report.json",
                "meshes": "meshes/",
            }
        ),
        "conventions": conventions.to_manifest(),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def from_bundle(bundle_dir: str | Path) -> Conventions:
    """Read the convention out of a bundle directory.

    This is the reader every consumer should use. It raises when the file or the block is absent,
    because "no conventions" and "identity conventions" are different claims and only one of them is
    true here.
    """
    path = manifest_path(bundle_dir)
    if not path.exists():
        raise FileNotFoundError(
            f"no manifest.json in {bundle_dir}; a bundle that does not state its zero-pose convention "
            "cannot be compared with another model without re-deriving the offsets by hand"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    if "conventions" not in data:
        raise KeyError(f"{path} carries no 'conventions' block")
    return Conventions.from_manifest(data["conventions"])
