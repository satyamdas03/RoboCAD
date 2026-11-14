"""``robocad twin``: the JSON contract another process uses to read and build a bundle.

This exists so a second application can drive RoboCAD without importing it. Hi-EV never links this
code; it runs a subprocess and reads JSON, which keeps the two repos independent and means a change
here cannot break it silently -- a changed field is a visible failure of a schema, not an import that
happens to still resolve.

Commands::

    robocad twin summary --bundle DIR [--json]
    robocad twin page    --bundle DIR --out PAGE_DIR [--seconds S] [--hz N] [--triangles N]
    robocad twin compile --step FILE --joints FILE --out DIR [--json-progress]
                         [--infill F] [--wall-mm W] [--servo-mass-kg KG --servo-source TEXT]
    robocad twin revise  --step FILE --before DIR --out DIR [--infill F] [--wall-mm W]
                         [--joints FILE] [--servo-mass-kg KG --servo-source TEXT]
                         [--json-progress] [--json]
    robocad twin unpack  --zip FILE --out DIR [--verify-sha SHA]

``summary`` describes a bundle as JSON. Its contract is ``robocad.twin.summary/1`` and its point is
the ``provenance`` block: every figure the bundle reports is labelled with what kind of claim it is,
and anything produced by a model rather than observed on the robot is labelled ``modelled``. A
consumer that renders "mass: 0.9017 kg" without that label is quoting a density assumption. Only
data generated in simulation is labelled ``synthetic``, and only ``calibration`` is.

``page`` builds the offline living page from a bundle. ``compile`` runs the compiler and, with
``--json-progress``, writes one JSON object per line so a GUI can show progress without scraping text.

``revise`` is the sentence "change the infill to 30 percent" as a command: it recompiles the same STEP
file at a print model the caller named, diffs the new bundle against ``--before`` link by link, and
prints the modelled mass before and after. It refuses a diff whose solid bound moved, because wall
thickness and infill cannot change the solid, so a diff that reports otherwise is comparing two
different compiles. ``--infill`` and ``--wall-mm`` are bounded here (0.1-1.0 and 0.8-3.0 mm) rather
than at the print model, because a value outside them is a number rather than a printable part.

``unpack`` is the one source of truth for a shipped demo. It extracts the zip and, given
``--verify-sha``, refuses before writing anything when the archive does not hash to that digest. A
consumer then points at the extracted directory and nowhere else: a second copy of the page or the
report that a human serves by hand is a copy that can disagree with the package, and the v1.1 review
found exactly that, one injected `<div>` apart.

Exit codes: 0 success, 2 bad input (missing file or unreadable bundle), 3 the command ran but the
result is a failure (the page could not be built, or the bundle's own checks failed). With
``--json-progress`` a failing run still ends with a JSON error line and a non-zero exit, because a
GUI that is waiting on a progress stream must not have to parse a stack trace to learn what happened.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import sys
import zipfile
from pathlib import Path

SUMMARY_SCHEMA = "robocad.twin.summary/1"
UNPACK_SCHEMA = "robocad.twin.unpack/1"
REVISE_SCHEMA = "robocad.twin.revise/1"
# The sidecar a package may carry: one `sha256  path` line per file it ships. Optional, because a
# consumer's zip is theirs; when present it is checked, and a mismatch refuses the unpack.
FILE_DIGESTS = "FILES.sha256"

# The stages `twin compile` emits, in order. A consumer may rely on this list: no other stage name is
# produced, and "done" is only ever the last line of a successful run.
STAGES = ("import", "joints", "properties", "collision", "bundle", "checks", "done")

# `tooling:*` stages describe decisions made BEFORE the compiler runs, so they are emitted with a
# percentage below the compiler's first stage rather than squeezed into its ordered list. A consumer
# that only knows STAGES still sees them as lines it can ignore; one that reads them learns which
# print assumptions the run used.
TOOLING_STAGE = "tooling:print_model"

# The ranges a print assumption may take. The print model itself allows any infill from 0 to 1 and
# any positive wall; these are the bounds this CLI will accept from a spoken or typed instruction,
# because a 0 percent infill or a 0.1 mm wall is not a part anyone can print and the mass it implies
# is a number, not a result.
PRINT_INFILL_RANGE = (0.1, 1.0)
PRINT_WALL_MM_RANGE = (0.8, 3.0)

# Every stage name a caller may see. STAGES stays the compiler's own ordered list; this is the
# superset the emitter will pass through, so a tooling line is a known line rather than a crash.
KNOWN_STAGES = STAGES + (TOOLING_STAGE,)

# What kind of claim a figure is. `counted`, `measured`, `stated` and `adopted` are observations of
# something that exists; `assumed` is an input a person chose; `modelled` is a model output over those
# inputs; `synthetic` is data generated in simulation with no hardware behind it. `unknown` is not a
# claim at all -- it is the absence of one, and it is the only label allowed to stand beside no value.
#
# The distinction that matters to a listener: a mass from a CAD volume at an assumed density is
# `modelled`, not `synthetic` and not a measurement, so a voice that says "weighed" or "synthetic"
# about it is wrong in opposite directions.
KINDS = frozenset({"counted", "measured", "stated", "adopted", "assumed", "modelled", "synthetic"})
SYNTHETIC_KINDS = frozenset({"synthetic"})


def _read_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _read_yaml(path: Path):
    """The file parsed as YAML, or None. A missing parser is a missing optional input, not a crash.

    ``robot.joints.yaml`` carries travel limits alongside the bundle; a machine running the JSON CLI
    without PyYAML installed still has a full summary, and the limits it cannot read are simply not
    claimed. Raising here would turn an optional dependency into a command that does not run.
    """
    if not path.exists():
        return None
    try:
        import yaml
    except ImportError:  # no parser installed: the caller sees no file and says so
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _entry(kind: str, basis: str) -> dict:
    """A provenance entry: what kind of claim a figure is, and what the claim rests on."""
    return {"kind": kind, "basis": basis}


def _node(value, kind: str) -> dict:
    """A figure and its kind, in one place, so a consumer cannot read the number without the label.

    Flat sections whose numbers are bare and whose labels live in a parallel map are how a figure gets
    quoted without its provenance: one `dict.get` on the wrong map and the label is gone. Here the
    label travels with the value.
    """
    return {"value": value, "kind": kind}


def _value_of(node):
    """The bare value of a node, for a caller that wants the number and already has the kind."""
    return node.get("value") if isinstance(node, dict) and "value" in node else node


_CONTROL = re.compile("[\x00-\x1f\x7f-\x9f]")


def _safe(text) -> str:
    """Text read from a bundle, made safe for a terminal: control characters removed.

    A bundle is untrusted input -- it arrives inside an extracted archive -- so a part name
    carrying an escape sequence could clear the reader's screen, and one carrying a carriage
    return would rewrite the line that just reported a check. Printing is a sink like any other;
    the control characters are stripped here rather than trusted at whatever wrote them.
    """
    return _CONTROL.sub("", str(text))


def _text(value) -> str:
    """A value from the bundle, shown as it was written but with its control characters gone."""
    return _safe("None" if value is None else value)


def _number(value):
    """A float, or None when what the bundle carries is not a number.

    A summary reads JSON from an extracted archive, which is untrusted input. Arithmetic on a string
    there raises a traceback out of a documented JSON contract, so every computed figure goes through
    here first: a field that is not a number is omitted, never guessed at.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def provenance(bundle_dir: Path, report: dict, manifest: dict, data: dict) -> dict:
    """What kind of claim each figure is, with the basis spelled out.

    Every key of ``totals`` gets an entry, including ones this function has no rule for: an unknown
    figure defaults to ``modelled`` and says so, because the alternative -- leaving it out of the block
    -- would let an unlabelled model output sit in a summary a consumer reads as measurement.

    The rules are deliberately coarse. The honest distinctions on this bundle are few: counts are
    counted, masses are a model over CAD solids at assumed densities, the servo's mass and torque are
    a manufacturer's statement, travel limits were adopted from a published model, and the zero-pose
    convention was measured on the robot. Anything finer would be a claim about the method that the
    method does not support.
    """
    out: dict[str, dict] = {}
    actuator_source = report.get("totals", {}).get("actuator_mass_source")
    torque_source = report.get("totals", {}).get("actuator_torque_source")
    print_model = data.get("print_model") if isinstance(data, dict) else None

    mass_basis = (
        f"CAD solid volume at an assumed density, then a shell-and-infill model ({print_model})"
        if print_model
        else "CAD solid volume at an assumed density: an upper bound on the printed parts"
    )
    for key in report.get("totals", {}):
        if key in ("bodies", "joints", "parts", "instances", "hulls", "actuators",
                   "visual_meshes", "visual_triangles"):
            out[f"totals.{key}"] = _entry("counted", "counted from the compiled model, not modelled")
        elif key == "actuator_mass_kg":
            out[f"totals.{key}"] = (
                _entry("stated", f"manufacturer datasheet: {actuator_source}")
                if actuator_source
                else _entry("unknown", "no datasheet mass was supplied for this bundle")
            )
        elif key in ("actuator_torque_nm", "actuator_rated_torque_nm"):
            out[f"totals.{key}"] = (
                _entry("stated", f"manufacturer datasheet: {torque_source}")
                if torque_source
                else _entry("unknown", "no datasheet torque was supplied for this bundle")
            )
        elif key in ("total_mass_kg", "total_solid_mass_kg"):
            out[f"totals.{key}"] = _entry("modelled", mass_basis)
        elif key.startswith("printed_") or key.endswith("_volume_m3") or key == "volume_by_role_m3":
            out[f"totals.{key}"] = _entry(
                "modelled", "CAD solid volume split by part name, at an assumed material density"
            )
        elif key.endswith("_source"):
            # The citation itself. Not a measurement, and not a model output either: it is the
            # document the neighbouring number was read from, quoted so a reader can go and check.
            out[f"totals.{key}"] = _entry("stated", "the source this bundle quotes for the figure beside it")
        elif key == "actuator_torque_kind":
            out[f"totals.{key}"] = _entry(
                "stated", "which figure the datasheet torque is: stall or rated, per the source beside it"
            )
        elif key in ("actuator_kp", "actuator_kv"):
            out[f"totals.{key}"] = _entry("assumed", "a controller gain chosen for this bundle, not measured")
        elif key in ("assumed_density_bodies", "print_model"):
            out[f"totals.{key}"] = _entry("modelled", "the assumption set this bundle was compiled with")
        elif key.endswith("_bytes") or key == "visual_budget_bytes":
            out[f"totals.{key}"] = _entry("counted", "file sizes on disk")
        else:
            out[f"totals.{key}"] = _entry(
                "modelled",
                "no provenance rule for this figure: treat it as a model output, not a measurement",
            )

    conventions = (manifest or {}).get("conventions") or {}
    measured = conventions.get("measured") is True
    out["conventions.zero_pose_offsets_deg"] = (
        _entry("measured", str(conventions.get("source") or "measured on the robot"))
        if measured
        else _entry("unknown", "no convention was measured for this bundle")
    )
    out["conventions.base_translation_mm"] = out["conventions.zero_pose_offsets_deg"]
    out["conventions.residual_mm"] = _entry(
        "measured" if measured else "unknown",
        "the residual of the offsets against 100 poses, in mm"
        if measured
        else "no convention was measured for this bundle",
    )

    joints = _read_yaml(bundle_dir / "robot.joints.yaml") or {}
    sources = {str(j.get("limits_source") or "") for j in joints.get("joints") or []}
    sources.discard("")
    if sources:
        # One statement, quoted from the bundle, whichever joint it came from: the file carries the
        # same provenance on every joint that has limits, and a per-joint copy would repeat it 6 times
        # in a payload a GUI renders.
        out["joints.limits"] = _entry("adopted", sorted(sources)[0])
    else:
        out["joints.limits"] = _entry(
            "unknown", "the CAD carries no travel limits and none were adopted for this bundle"
        )
    out["checks"] = _entry("measured", "each check ran against the written artifacts")
    return out


_PRINT_MODEL = re.compile(r"([\d.]+)\s*mm wall over\s*([\d.]+)\s*%\s*infill")
_INTERVALS = re.compile(
    r"intervals viscous \(([-\d.]+),\s*([-\d.]+)\), coulomb \(([-\d.]+),\s*([-\d.]+)\)"
)


def _print_assumptions(text) -> tuple[float | None, float | None]:
    """Wall thickness in mm and infill as a fraction, read from the bundle's own print model string."""
    match = _PRINT_MODEL.search(str(text or ""))
    if not match:
        return None, None
    return float(match.group(1)), round(float(match.group(2)) / 100.0, 4)


def _intervals(note: str) -> dict[str, list[float]]:
    """The current-channel confidence intervals, which the run writes into its own note.

    ``ai_cad/twin/identification.py`` writes structured ``intervals`` now, and the shipped
    ``identification.json`` predates that field, so its intervals are recovered from the note it
    generated in a fixed format rather than re-estimated. Nothing is recomputed here: a missing
    interval stays missing and the caller says so.
    """
    match = _INTERVALS.search(str(note or ""))
    if not match:
        return {}
    return {
        "damping": [float(match.group(1)), float(match.group(2))],
        "coulomb": [float(match.group(3)), float(match.group(4))],
    }


def _sections(bundle_dir: Path, report: dict) -> dict:
    """The demo's own numbers, each copied from the bundle's files and labelled with what it is.

    Every section is additive and optional: the file that carries it is read if it exists, and the
    section is absent rather than zero-filled when it does not. A bundle compiled from CAD alone has
    no revision to show, and a summary that invented one would be the defect this whole sprint is
    fixing. The shipped package carries all six files.
    """
    section: dict = {}
    totals = report.get("totals") or {}
    comparison = _read_json(bundle_dir / "comparison.json") or {}

    # counts: a count is a count. There is no kind that could make 5 checks pass mean anything else.
    statuses = [c.get("status") for c in report.get("checks") or []]
    section["check_counts"] = {
        status: statuses.count(status) for status in ("pass", "fail", "skipped")
    }

    masses: dict = {}
    if "total_solid_mass_kg" in totals:
        masses["solid_kg"] = _node(totals["total_solid_mass_kg"], "modelled")
    if "total_mass_kg" in totals:
        masses["print_kg"] = _node(totals["total_mass_kg"], "modelled")
    if comparison.get("theirs_total_kg") is not None:
        masses["published_kg"] = _node(comparison["theirs_total_kg"], "stated")
    if comparison.get("delta_percent") is not None:
        # The gap the page prints beside the published figure, computed once here rather than in
        # the page's own arithmetic: a second computation is a second answer waiting to disagree.
        masses["delta_percent"] = _node(comparison["delta_percent"], "modelled")
    solid, printed = _number(totals.get("total_solid_mass_kg")), _number(totals.get("total_mass_kg"))
    if solid and printed:
        masses["infill_saving_percent"] = _node(round(100.0 * (1.0 - printed / solid), 1), "modelled")
    wall_mm, infill = _print_assumptions(totals.get("print_model"))
    assumptions: dict = {}
    if wall_mm is not None:
        assumptions["wall_mm"] = _node(wall_mm, "assumed")
        assumptions["infill"] = _node(infill, "assumed")
    try:
        from ai_cad.compiler.materials import DEFAULT_DENSITY_KG_M3  # noqa: PLC0415

        assumptions["density_kg_m3"] = _node(
            DEFAULT_DENSITY_KG_M3, "assumed"
        )
    except Exception:  # noqa: BLE001 - a missing constant must not remove the other assumptions
        pass
    servo_kg = _number(totals.get("actuator_mass_kg"))
    if servo_kg is not None:
        assumptions["servo_g"] = _node(round(servo_kg * 1000.0, 1), "stated")
    # Assumptions belong to a mass; with no mass in the bundle they would be a section describing
    # nothing, which reads as a mass that is merely missing its number.
    if assumptions and any(k in masses for k in ("solid_kg", "print_kg", "published_kg")):
        masses["assumptions"] = assumptions
    bodies = {
        b.get("ours"): _node(b.get("theirs_kg"), "stated")
        for b in comparison.get("bodies") or []
        if b.get("theirs_kg") is not None
    }
    if bodies:
        # The published model's per-link masses, which is where a figure like the base link's
        # 0.147 kg comes from. Without this the summary has the total and the voice needs the link.
        masses["published_bodies_kg"] = bodies
    if masses:
        section["masses"] = masses

    residuals: dict = {}
    alignment = comparison.get("alignment") or {}
    if alignment.get("rms_axis_deg") is not None:
        residuals["axis_rms_deg"] = _node(alignment["rms_axis_deg"], "measured")
        residuals["axis_worst_deg"] = _node(alignment.get("worst_axis_deg"), "measured")
    conventions = _read_json(bundle_dir / "manifest.json") or {}
    residual_mm = (conventions.get("conventions") or {}).get("residual_mm") or {}
    if residual_mm:
        residuals["origin_median_mm"] = _node(residual_mm.get("median"), "measured")
        residuals["origin_p90_mm"] = _node(residual_mm.get("p90"), "measured")
        residuals["origin_max_mm"] = _node(residual_mm.get("max"), "measured")
    if alignment.get("worst_point_m") is not None:
        # The same joint origins, measured before the zero-pose offsets are applied. The page states
        # both figures side by side ("they look 110 mm apart; with the conventions, 2.50 mm median"),
        # and the pair only means something if both come from the files rather than from the prose.
        residuals["origin_worst_no_conventions_mm"] = _node(
            round(float(alignment["worst_point_m"]) * 1000.0, 2), "measured"
        )
    spacings = comparison.get("link_spacings") or []
    deltas = [abs(n) for n in (_number(s.get("delta_m")) for s in spacings
                               if isinstance(s, dict)) if n is not None]
    if deltas:
        # The worst of the bundle's own spacing deltas, which is the "1.69 mm" the script quotes.
        residuals["link_length_mm"] = _node(round(max(deltas) * 1000.0, 2), "measured")
    if residuals:
        section["residuals"] = residuals

    torque = _read_json(bundle_dir / "torque.json")
    if torque:
        poses = [
            {
                "pose": row.get("pose"),
                # One number per pose, the peak over joints, which is what the page draws and the
                # voice says. Per-joint arrays are keyed by name if the payload ever carries them.
                "compiled_nm": _node(row.get("compiled_nm"), "modelled"),
                "published_nm": _node(row.get("published_nm"), "modelled"),
            }
            for row in torque.get("static_by_pose") or []
        ]
        section["torque"] = {
            "static_poses": poses,
            "limit_stall_nm": _node(totals.get("actuator_torque_nm"), "stated"),
            "rated_nm": _node(totals.get("actuator_rated_torque_nm"), "stated"),
            "dynamic_comparable": torque.get("dynamic_comparable"),
            "dynamic_reason": torque.get("dynamic_reason"),
            # The saturation flag travels with the summary too: the page's warning line reads it from
            # here, so a stale torque.js cannot say a different thing about the same rollover.
            "saturated": torque.get("saturated"),
            "pose_gate_mm": _node(torque.get("pose_gate_worst_mm"), "modelled"),
            "pose_gate_samples_mm": torque.get("pose_gate_samples_mm"),
            # Per-joint residuals behind the axis paragraph: the page prints one row per joint, so the
            # numbers it prints have to be the numbers this summary carries, or the two disagree.
            "axis_residual_deg": torque.get("axis_residual_deg_after_datum_fit"),
            "anchor_perp_mm": torque.get("anchor_perp_mm_after_datum_fit"),
            "basis": "same joint-space trajectory, contacts disabled; static rows are qfrc_bias at rest",
        }

    diff = _read_json(bundle_dir / "diff.json")
    if diff:
        before = (diff.get("totals") or {}).get("print_model_before")
        after = (diff.get("totals") or {}).get("print_model_after")
        infill_before, infill_after = _print_assumptions(before)[1], _print_assumptions(after)[1]
        section["revision"] = {
            "infill_before": _node(infill_before, "assumed"),
            "infill_after": _node(infill_after, "assumed"),
            "mass_before_kg": _node((diff.get("totals") or {}).get("mass_before_kg"), "modelled"),
            "mass_after_kg": _node((diff.get("totals") or {}).get("mass_after_kg"), "modelled"),
            "links_changed": sum(
                1 for link in diff.get("links") or []
                if isinstance(link, dict) and _number(link.get("mass_delta_kg")) not in (None, 0.0)
            ),
            "added": list(diff.get("added") or []),
            "removed": list(diff.get("removed") or []),
        }
        # The effort check's demand, which is the same quantity the torque section reports as
        # qfrc_bias at rest. Both are on the page, so both are here: a reader comparing 0.652 with
        # 0.767 is comparing a load case with a pose, and the summary is where that is written down.
        effort = diff.get("effort") or {}
        for key, field in (("before", "effort_before_nm"), ("after", "effort_after_nm")):
            demand = (effort.get(key) or {}).get("demand_nm")
            if demand is not None:
                section["revision"][field] = _node(demand, "modelled")
                section["revision"][field.replace("_nm", "_percent")] = (
                    effort.get(key) or {}
                ).get("percent")

    identification = _read_json(bundle_dir / "identification.json")
    scenarios = _read_json(bundle_dir / "identifiability_scenarios.json")
    if identification or scenarios:
        calibration: dict = {}
        if identification:
            params = []
            for rung in identification.get("rungs") or []:
                if rung.get("rung") != 5:
                    continue
                joint = str(rung.get("name") or "").split(",")[-1].strip()
                intervals = rung.get("intervals") or _intervals(rung.get("note"))
                # Coulomb first: it is the parameter this current channel actually resolves. The
                # viscous estimate beside it is attenuated (0.0436 recovered against 0.08 true) and
                # reading it first makes the block look like it failed at its strongest number.
                for key, name in (("coulomb", "coulomb_friction"), ("damping", "viscous_damping")):
                    if key not in (rung.get("recovered") or {}):
                        continue
                    lo_hi = intervals.get(key) or [None, None]
                    params.append({
                        "joint": joint,
                        "name": name,
                        "true": (rung.get("truth") or {}).get(key),
                        "recovered": (rung.get("recovered") or {}).get(key),
                        "lo": lo_hi[0],
                        "hi": lo_hi[1],
                    })
            calibration["current_channel"] = {"params": params}
            calibration["stopped_at_rung"] = identification.get("stopped_at")
            # How far the method got, counted here rather than on the page: "5 of 6 rungs" is a
            # statement about this file, and a page that counts its own rows can count them wrong.
            rungs = [r for r in identification.get("rungs") or [] if isinstance(r, dict)]
            reached = {r.get("rung") for r in rungs if r.get("reached")}
            calibration["rungs_total"] = len({r.get("rung") for r in rungs})
            calibration["rungs_recovered"] = len(reached)
            # The rung rows themselves, notes included. The page prints the blocked rung's reason,
            # and that reason is full of figures (1.53 mrad, 998 N m per rad, 4096 counts); if the
            # page reads them from identification.js instead, the two can disagree about the same
            # sentence, which is the defect this summary exists to prevent.
            calibration["rungs"] = [
                {"rung": r.get("rung"), "name": r.get("name"), "reached": bool(r.get("reached")),
                 "note": r.get("note")}
                for r in rungs
            ]
        if scenarios:
            base = scenarios[0]
            calibration["position_only"] = {
                "snr": base.get("snr"),
                "status": "sufficient" if base.get("crosses_snr_3") else "insufficient",
                "scenario": base.get("scenario"),
            }
            calibration["scenarios"] = [
                {"scenario": row.get("scenario"), "snr": row.get("snr"),
                 "crosses": bool(row.get("crosses_snr_3"))}
                for row in scenarios if isinstance(row, dict)
            ]
        # Every number in this block came out of simulated logs with planted parameters. That is the
        # one place in the summary where `synthetic` is the true kind, and it says so here.
        calibration["synthetic"] = True
        section["calibration"] = calibration

    # The twin preview the page draws: synthetic logs with planted parameters, and the count of
    # parameters the method could and could not recover. It lives beside the bundle rather than in
    # it because it is a method-validation artefact, and it is summarised here for the same reason
    # the torque numbers are -- the page and the voice quote one set of figures, not two.
    # It goes INSIDE `calibration`, not beside it: this is simulated data with planted parameters,
    # and `synthetic` is a kind this summary reserves for exactly that block. Beside it, a reader
    # checking which figures are synthetic would have found two blocks and no rule for the second.
    preview = _read_json(bundle_dir / "synthetic_preview.json")
    if preview:
        estimates = preview.get("estimates") or []
        calibration = section.setdefault("calibration", {})
        calibration["synthetic"] = True
        calibration["twin_preview"] = {
            "identified": sum(1 for e in estimates if isinstance(e, dict) and e.get("identifiable")),
            "total": len(estimates),
            "hz": preview.get("hz"),
            "runs": preview.get("runs"),
            "rmse_uncalibrated_mrad": _node(
                preview.get("trajectory_rmse_mrad_uncalibrated"), "synthetic"
            ),
            "rmse_calibrated_mrad": _node(
                preview.get("trajectory_rmse_mrad_calibrated"), "synthetic"
            ),
            "data": (f"{preview.get('runs')} synthetic runs at {preview.get('hz')} Hz, "
                     "position logs only"),
            "source": "synthetic_preview.json",
            "synthetic": True,
        }

    return section


def build_summary(bundle_dir: Path) -> dict:
    """The summary document. Raises FileNotFoundError when the directory has no bundle in it."""
    bundle_dir = Path(bundle_dir)
    if not bundle_dir.is_dir():
        raise FileNotFoundError(f"no bundle directory at {bundle_dir}")
    report = _read_json(bundle_dir / "report.json")
    manifest = _read_json(bundle_dir / "manifest.json")
    data = _read_json(bundle_dir / "bundle.json")
    if report is None and data is None:
        raise FileNotFoundError(
            f"{bundle_dir} has neither report.json nor bundle.json: it is not a compiled bundle"
        )
    report = report or {}
    data = data or {}
    totals = report.get("totals") or {}
    checks = [
        {
            "id": c.get("id"),
            "status": c.get("status"),
            "explanation": c.get("explanation", ""),
            # The same sentence under the name a consumer speaks it by. `explanation` stays because
            # the page and the report use it; `reason` exists so a voice does not have to learn that.
            "reason": c.get("explanation", ""),
            "measured": c.get("measured", {}),
        }
        for c in report.get("checks") or []
    ]
    statuses = [c["status"] for c in checks]
    worst = "fail" if "fail" in statuses else ("warn" if "warn" in statuses else "pass")

    conventions = (manifest or {}).get("conventions") or {}
    prov = provenance(bundle_dir, report, manifest or {}, data)
    document = {
        "schema_version": SUMMARY_SCHEMA,
        "name": report.get("name") or data.get("name") or bundle_dir.name,
        "bundle": {
            "path": bundle_dir.resolve().as_posix(),
            "generated_at": report.get("generated_at"),
            "source": report.get("source"),
            # Both files that publish the convention, so a consumer reads the same numbers the
            # model does rather than trusting this summary to have copied them correctly.
            "manifest": (bundle_dir / "manifest.json").exists(),
            "model_mjcf": (bundle_dir / "model.mjcf").exists(),
            "model_urdf": (bundle_dir / "model.urdf").exists(),
        },
        "totals": totals,
        "checks": checks,
        "worst_status": worst,
        "conventions": {
            "measured": conventions.get("measured") is True,
            "source": conventions.get("source"),
            "zero_pose_offsets_deg": conventions.get("zero_pose_offsets_deg") or {},
            "base_translation_mm": conventions.get("base_translation_mm"),
            "residual_mm": conventions.get("residual_mm") or {},
        },
        "provenance": prov,
        # Counted here rather than left for the consumer to derive, so a GUI can say "3 figures in
        # this panel were generated in simulation" without re-implementing the rule. Only `synthetic`
        # counts: a modelled mass is a model output over real inputs, not generated data.
        "synthetic_count": sum(1 for v in prov.values() if v["kind"] in SYNTHETIC_KINDS),
        "warnings": report.get("warnings") or [],
        "notes": report.get("notes") or [],
    }
    # The demo's numbers travel beside the report-derived ones. A section is present only when the
    # file that carries it is, so a bare compiled bundle gets no invented revision.
    document.update(_sections(bundle_dir, report))
    # `synthetic_count` covers the provenance block only, and on this bundle that is honest zero.
    # Read alone it would say "nothing here is synthetic" while the calibration section beside it is
    # built entirely from simulated logs, so the calibration count is reported next to it. The
    # calibration block's figures are bare numbers (a parameter table, not provenance nodes), which
    # is why this is a second count rather than one walk over the document.
    calibration = document.get("calibration") or {}
    document["synthetic_figures"] = {
        "provenance": document["synthetic_count"],
        "calibration": _numeric_leaves(calibration) if calibration.get("synthetic") else 0,
        "calibration_is_synthetic": bool(calibration.get("synthetic")),
    }
    return document


def _numeric_leaves(node) -> int:
    """How many numbers a block carries, counting through dicts and lists and not booleans."""
    if isinstance(node, bool):
        return 0
    if isinstance(node, (int, float)):
        return 1
    if isinstance(node, dict):
        return sum(_numeric_leaves(value) for value in node.values())
    if isinstance(node, list):
        return sum(_numeric_leaves(value) for value in node)
    return 0


def _print_summary(summary: dict) -> None:
    totals = summary["totals"]
    print(f"{_safe(summary['name'])}: {_safe(summary['bundle']['path'])}")
    print(f"  bodies {_text(totals.get('bodies'))}  joints {_text(totals.get('joints'))}  "
          f"parts {_text(totals.get('parts'))}  instances {_text(totals.get('instances'))}")
    # The totals block is copied straight out of report.json, so every value here is untrusted text
    # until it is printed: a mass field carrying a carriage return would start a new terminal line.
    print(f"  mass {_text(totals.get('total_mass_kg'))} kg modelled, "
          f"{_text(totals.get('total_solid_mass_kg'))} kg solid bound "
          f"[{_text((summary['provenance'].get('totals.total_mass_kg') or {}).get('kind'))}]")
    for check in summary["checks"]:
        print(f"  {_safe(check['id'])[:22]:22s} {_safe(check['status'])[:8]:8s} "
              f"{_safe(check['explanation'])}")
    print(f"  worst check {_text(summary['worst_status'])}")
    conventions = summary["conventions"]
    print("  conventions: " + (
        f"measured, {_safe(conventions['source'])}" if conventions["measured"]
        else "none measured; the bundle says so rather than shipping zeros"
    ))
    counts = summary.get("check_counts") or {}
    if counts:
        print(f"  checks {_text(counts.get('pass', 0))} pass  "
              f"{_text(counts.get('fail', 0))} fail  "
              f"{_text(counts.get('skipped', 0))} skipped")
    if "masses" in summary:
        masses = summary["masses"]
        parts = []
        for key, name in (("solid_kg", "solid"), ("print_kg", "print"),
                          ("published_kg", "published")):
            if key not in masses:
                continue
            number = _number(_value_of(masses[key]))
            shown = f"{number:.4g}" if number is not None else _safe(_value_of(masses[key]))
            parts.append(f"{name} {shown} [{_text(masses[key]['kind'])}]")
        print("  masses: " + ", ".join(parts))
    if "torque" in summary and summary["torque"].get("static_poses"):
        rest = summary["torque"]["static_poses"][0]
        print(f"  torque at {_text(rest['pose'])}: {_text(rest['compiled_nm']['value'])} compiled vs "
              f"{_text(rest['published_nm']['value'])} published N m, "
              f"limit {_text(summary['torque']['limit_stall_nm']['value'])}")
    if "revision" in summary:
        revision = summary["revision"]
        before = _number(_value_of(revision.get("mass_before_kg")))
        after = _number(_value_of(revision.get("mass_after_kg")))
        print(f"  revision infill {_safe(_value_of(revision['infill_before']))} -> "
              f"{_safe(_value_of(revision['infill_after']))}: mass "
              f"{f'{before:.4g}' if before is not None else 'unreadable'} -> "
              f"{f'{after:.4g}' if after is not None else 'unreadable'} kg, "
              f"{revision['links_changed']} links changed")
    figures = summary.get("synthetic_figures") or {}
    if figures:
        print(f"  synthetic figures: {figures.get('provenance', 0)} of "
              f"{len(summary['provenance'])} provenance entries, "
              f"{figures.get('calibration', 0)} in the calibration block")
    else:
        print(f"  synthetic figures: {summary['synthetic_count']} of "
              f"{len(summary['provenance'])} provenance entries")
    for key, entry in summary["provenance"].items():
        if entry["kind"] in SYNTHETIC_KINDS:
            print(f"    {_safe(key)[:34]:34s} {_safe(entry['kind'])[:10]:10s} {_safe(entry['basis'])}")
    for key, entry in summary["provenance"].items():
        if entry["kind"] == "modelled":
            print(f"  modelled  {_safe(key)[:34]:34s} {_safe(entry['basis'])[:88]}")


def build_page(bundle_dir: Path, out: Path, seconds: float, hz: int, triangles: int,
               assets: Path | None = None) -> dict:
    """Build the offline page from a bundle, and say which payloads came from where.

    Three payloads are rebuilt from this bundle: the trajectory and the meshes, baked from
    ``model.mjcf``, and the report, baked from ``report.json``. The rest of the page is code and data
    that a bundle does not contain -- the torque comparison needs the published model as well as the
    compiled one, and the identifiability and revision payloads come from documents beside the bundle
    -- so those are copied when they exist and named as copied. A page that silently carried last
    week's torque number beside this week's bundle would be the worst of both.
    """
    bundle_dir = Path(bundle_dir)
    out = Path(out)
    model = bundle_dir / "model.mjcf"
    report_json = bundle_dir / "report.json"
    if not model.exists():
        raise FileNotFoundError(f"no model.mjcf in {bundle_dir}: nothing to bake a trajectory from")
    if not report_json.exists():
        raise FileNotFoundError(f"no report.json in {bundle_dir}: the page has no checks to show")
    # The page's 3D payload is baked from the compiled model's own meshes. A distribution package
    # carries `meshes.js` (the decimated copy) and not the 692 source meshes, so rebuilding a page
    # from it is impossible by design -- say that, rather than letting MuJoCo report a missing file
    # from a directory the package never had.
    meshdir = bundle_dir / "meshes"
    if not meshdir.is_dir() or not any(meshdir.iterdir()):
        raise FileNotFoundError(
            f"{bundle_dir} carries no meshes/: this package ships meshes.js, the decimated payload, "
            "not the source meshes the 3D view is baked from. Build the page from the tagged bundle "
            "the package was cut from."
        )
    out.mkdir(parents=True, exist_ok=True)
    repo = Path(__file__).resolve().parents[1]
    assets = Path(assets) if assets else repo / "docs" / "demo" / "page"

    # The trajectory is baked by MuJoCo. MuJoCo is the `sim` extra and is deliberately not a base
    # dependency, so a clean install without it must say so in one sentence rather than arrive as a
    # ModuleNotFoundError from a helper module the caller has never heard of.
    import importlib.util  # noqa: PLC0415

    if importlib.util.find_spec("mujoco") is None:
        raise FileNotFoundError(
            "building the page needs MuJoCo: teardown_export/bake.py bakes the trajectory and meshes "
            "from model.mjcf. Install it with `pip install -e \".[sim]\"`, or use the packaged "
            "so101_demo.zip, which is already baked"
        )

    sys.path.insert(0, str(repo / "teardown_export"))
    try:
        import bake  # noqa: PLC0415 - imported here so the rest of the CLI has no numpy/mujoco dep
        import bake_manifest  # noqa: PLC0415
        import bake_report  # noqa: PLC0415

        bake.main([
            str(model), str(out),
            "--seconds", str(seconds), "--hz", str(hz), "--triangles", str(triangles),
        ])
        bake_report.main([
            str(report_json), str(out / "report.js"),
            "--bundle", str(bundle_dir / "bundle.json"),
        ])
        manifest_path = bundle_dir / "manifest.json"
        if manifest_path.exists():
            bake_manifest.bake(manifest_path, out / "manifest.js", None)
    finally:
        sys.path.remove(str(repo / "teardown_export"))

    # The summary the voice speaks from, shipped as a script so the page can quote the same figure
    # the voice does. One generator means one document: a page that recomputes its own numbers is a
    # second source, and the two drift the moment either side is edited.
    (out / "summary.js").write_text(
        "window.SO101_SUMMARY = " + json.dumps(build_summary(bundle_dir)) + ";\n", encoding="utf-8"
    )

    rebuilt = {"trajectory.js", "meshes.js", "report.js", "summary.js", "manifest.js"}
    copied, missing = [], []
    for name in ("index.html", "three.min.js", "twin.js", "torque.js", "identification.js",
                 "diff.js"):
        source = assets / name
        if source.exists():
            shutil.copy2(source, out / name)
            if name not in rebuilt:
                copied.append(name)
        elif name != "index.html":
            missing.append(name)
    if not (out / "index.html").exists():
        raise FileNotFoundError(f"no index.html in {assets}: there is no page to fill")

    # Everything the page links locally has to exist locally: it is opened from file://, where a
    # missing script is a blank panel and a broken path looks like a bug in the model.
    html = (out / "index.html").read_text(encoding="utf-8")
    referenced = [
        part.split('"')[0].split("'")[0]
        for part in html.split('src=')[1:]
    ]
    referenced = [r for r in referenced if r and not r.startswith(("http:", "https:", "data:"))]
    absent = sorted({r for r in referenced if not (out / r).exists()})
    return {
        "schema_version": "robocad.twin.page/1",
        "out": out.resolve().as_posix(),
        "rebuilt_from_this_bundle": sorted(rebuilt),
        "triangle_budget": triangles,
        "copied_from_page_assets": sorted(copied),
        "absent_optional": sorted(missing),
        "referenced_but_absent": absent,
        "complete": not absent,
    }


def sha256_file(path: Path) -> str:
    """The digest of a file, in the form ``verify.json`` and the tag check both use."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ArchiveError(ValueError):
    """An archive that cannot be extracted as given: a bad digest, a bad path, a dirty target."""


# A zip can lie about how much it expands to. The demo is 4 MB and expands to 7 MB; anything past
# this is not the demo, and an archive of 20 000 entries is not a page and a report.
MAX_EXPANDED_BYTES = 512 * 1024 * 1024
MAX_MEMBERS = 20_000


def _member_problem(name: str) -> str | None:
    """Why this archive member would be written outside the target, or None if it is safe.

    Two independent checks, because either alone has a hole. The name check refuses absolute,
    drive-qualified and parent-directory components -- including `.. ` and `..` spelled with trailing
    dots or spaces, which Windows strips before resolving, and which is how a literal `".. "` part
    becomes traversal after the last check has finished agreeing it is not `".."`. The containment
    check on the resolved path then catches anything the name rules did not anticipate. Extraction
    also passes `filter="data"` on interpreters that have it, which is the third layer.
    """
    normalised = name.replace("\\", "/")
    if normalised.startswith("/"):
        return "absolute path"
    if len(normalised) > 1 and normalised[1] == ":":
        return "drive-qualified path"
    for part in normalised.split("/"):
        if part in ("", "."):
            continue
        # Windows ignores trailing dots and spaces in a component, so `".. "` resolves to `..`.
        stripped = part.rstrip(" .")
        if stripped in ("", "..") or ":" in part:
            return "parent-directory escape"
    return None


def _check_file_digests(root: Path) -> dict:
    """Verify a package against the per-file digests it shipped, if it shipped any.

    A zip digest says the archive is the one a caller checked. It does not say the archive holds the
    files the build meant to put in it: twice now a file has existed in the tree and differed in the
    package, and both times the only detector was a person diffing two copies. A sidecar of per-file
    digests, written by the packager after every file is final, turns that into a check.
    """
    sidecar = root / FILE_DIGESTS
    if not sidecar.is_file():
        return {"sidecar": None, "checked": 0, "verified": None}

    listed: dict[str, str] = {}
    for line in sidecar.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        digest, _, rel = line.partition("  ")
        if len(digest) != 64 or not rel.strip():
            raise ArchiveError(
                f"{FILE_DIGESTS} carries a line this reader cannot parse: {_safe(line)[:80]!r}"
            )
        listed[rel.strip()] = digest.lower()

    base = root.resolve()
    problems: list[str] = []
    for rel, digest in sorted(listed.items()):
        target = (root / rel).resolve()
        if not target.is_relative_to(base):
            problems.append(f"{rel} resolves outside the package")
        elif not target.is_file():
            problems.append(f"{rel} is recorded but missing")
        elif sha256_file(target) != digest:
            problems.append(f"{rel} does not match the digest recorded for it")
    present = {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    } - {FILE_DIGESTS}
    for rel in sorted(present - set(listed)):
        problems.append(f"{rel} is in the package but no digest records it")
    if problems:
        raise ArchiveError(
            f"{root} does not match {FILE_DIGESTS}: " + "; ".join(problems[:5])
            + (f" (and {len(problems) - 5} more)" if len(problems) > 5 else "")
            + ". The archive is what was checked; its contents are not what the build recorded."
        )
    return {"sidecar": FILE_DIGESTS, "checked": len(listed), "verified": True}


def unpack_zip(zip_path: Path, out: Path, verify_sha: str | None = None) -> dict:
    """Extract a shipped demo zip, refusing on a digest mismatch or an unsafe member.

    Order matters: the digest is checked, then every member name, and only then is anything written.
    A refusal therefore leaves the target untouched rather than half-populated, which is the state a
    consumer would otherwise read as a partial success.
    """
    zip_path = Path(zip_path)
    out = Path(out)
    if not zip_path.is_file():
        raise FileNotFoundError(f"no zip at {zip_path}")

    actual = sha256_file(zip_path)
    expected = (verify_sha or "").strip().lower()
    if expected and expected != actual:
        raise ArchiveError(
            f"{zip_path} hashes to {actual}, not the {expected} this caller verified: refusing to "
            "extract it. A demo that reads an archive other than the one that was checked is the "
            "defect unpack exists to prevent."
        )

    with zipfile.ZipFile(zip_path) as archive:
        # The cap counts every entry, directory entries included: a zip of 10 000 files and 10 000
        # directory entries is 20 000 records to carry through extraction, and counting only the
        # files would let the number of records climb past the limit the constant names.
        every = archive.infolist()
        if len(every) > MAX_MEMBERS:
            raise ArchiveError(f"{zip_path} has {len(every)} entries: past the {MAX_MEMBERS} cap")
        infos = [info for info in every if not info.is_dir()]
        names = [info.filename for info in infos]

        # Resource checks before any write: a declared expansion past the cap is refused rather than
        # attempted. Declared sizes can lie low, so the resolved-path containment check below remains
        # the guarantee about *where* bytes land.
        expanded = sum(info.file_size for info in infos)
        if expanded > MAX_EXPANDED_BYTES:
            raise ArchiveError(
                f"{zip_path} expands to {expanded} bytes: past the {MAX_EXPANDED_BYTES} cap"
            )

        # Every entry is validated, directories included: a directory member is written by extractall
        # just like a file member, so `"../elsewhere/"` escapes exactly as `"../elsewhere/x"` would.
        problems = [(info.filename, _member_problem(info.filename)) for info in every]
        unsafe = [(name, why) for name, why in problems if why]
        for info in every:
            if info.external_attr >> 16 & 0o170000 == 0o120000:
                unsafe.append((info.filename, "symlink"))
        if unsafe:
            raise ArchiveError(
                "refusing to extract: unsafe member(s) "
                + ", ".join(f"{name!r} ({why})" for name, why in unsafe[:5])
            )

        # The name rules are a fast path; containment on the resolved path is the actual promise. A
        # member whose resolved target leaves `out` is refused even if every name rule passed.
        root = out.resolve()
        for info in every:
            target = (out / info.filename).resolve()
            if not target.is_relative_to(root):
                raise ArchiveError(f"refusing to extract {info.filename!r}: it resolves outside {out}")

        # A populated target is refused rather than merged. Extraction over yesterday's files leaves
        # a directory holding both packages, and the next reader cannot tell which report.json it got.
        if out.exists() and any(out.iterdir()):
            raise ArchiveError(f"{out} already has files in it: unpack into a new directory")
        out.mkdir(parents=True, exist_ok=True)
        try:
            # Python 3.12+: the stdlib's own data filter rejects the same traps this code names.
            archive.extractall(out, filter="data")
        except TypeError:  # older interpreter, no filter argument
            archive.extractall(out)

    # The zip may carry one top-level folder (`so101_demo/`) or its files at the root. Both are
    # normal; the caller wants the directory with the bundle in it, not a path to guess at.
    bundle = out
    if not (bundle / "report.json").exists():
        candidates = [p for p in out.iterdir() if p.is_dir() and (p / "report.json").exists()]
        if len(candidates) == 1:
            bundle = candidates[0]
        elif len(candidates) > 1:
            raise ArchiveError(
                f"{out} carries {len(candidates)} bundle directories: refusing to guess which one "
                "this package means"
            )

    file_digests = _check_file_digests(bundle)

    return {
        "schema_version": UNPACK_SCHEMA,
        "zip": {
            "path": zip_path.resolve().as_posix(),
            "sha256": actual,
            "bytes": zip_path.stat().st_size,
            "entries": len(names),
        },
        "verified": bool(expected),
        "expected_sha256": expected or None,
        "out": out.resolve().as_posix(),
        # What a consumer sets ROBOCAD_BUNDLE_DIR to: the directory whose report.json and page are
        # the shipped ones, never a sibling copy.
        "bundle": bundle.resolve().as_posix(),
        "file_digests": file_digests,
        "files": sorted(names),
    }


def _limits_from_joints(path: Path) -> tuple[dict[str, dict], str]:
    """Travel limits and their provenance, read from a reviewed ``robot.joints.yaml``.

    The reviewer-edited file is the artifact a person accepted, so it is the right source for a
    compile that follows a review. The provenance string is the file's own, quoted rather than
    reconstructed: a compile that restated it in its own words would be asserting a source it did not
    check.
    """
    data = _read_yaml(path)
    if not data:
        raise ValueError(f"{path} is not a readable joints file")
    limits: dict[str, dict] = {}
    sources: list[str] = []
    for joint in data.get("joints") or []:
        joint_id = joint.get("joint_id")
        if joint_id and joint.get("limits"):
            limits[str(joint_id)] = dict(joint["limits"])
            if joint.get("limits_source"):
                sources.append(str(joint["limits_source"]))
    if not limits:
        raise ValueError(f"{path} carries no joint limits: pass a reviewed file or omit --joints")
    unique = sorted(set(sources))
    if len(unique) != 1:
        raise ValueError(
            f"{path} does not state one source for its limits ({len(unique)} found): a bundle cannot "
            "say where its limits came from if the file it was given does not"
        )
    return limits, unique[0]


def print_model_from_cli(infill: float | None, wall_mm: float | None):
    """The print model a run should use, refusing assumptions no printer makes.

    ``None`` means "the bundle's own default", not "zero": a caller that says nothing about infill
    must get the 1.2 mm wall and 0.20 infill the report already states, or two bundles of the same
    robot would disagree about mass for a reason nobody chose.
    """
    from ai_cad.compiler.print_model import (
        DEFAULT_INFILL_FRACTION,
        DEFAULT_WALL_THICKNESS_M,
        PrintModel,
    )

    if infill is None and wall_mm is None:
        return None
    lo, hi = PRINT_INFILL_RANGE
    fraction = DEFAULT_INFILL_FRACTION if infill is None else float(infill)
    if not lo <= fraction <= hi:
        raise ValueError(
            f"infill {fraction:g} is outside {lo:g}-{hi:g}: below {lo:g} is not a printable part "
            "and above 1.0 is solid, so the mass would be a number with no process behind it"
        )
    wlo, whi = PRINT_WALL_MM_RANGE
    wall = DEFAULT_WALL_THICKNESS_M * 1000.0 if wall_mm is None else float(wall_mm)
    if not wlo <= wall <= whi:
        raise ValueError(
            f"wall {wall:g} mm is outside {wlo:g}-{whi:g} mm: a wall thinner than {wlo:g} mm does "
            "not survive a print, and one thicker than the part has no infilled interior to model"
        )
    return PrintModel(wall_thickness_m=wall / 1000.0, infill_fraction=fraction)


def compile_bundle_cli(step: Path, joints: Path | None, out: Path, json_progress: bool,
                       print_model=None, servo_mass_kg: float | None = None,
                       servo_source: str | None = None, emit=None) -> int:
    """Run the compiler, emitting one JSON line per stage when asked.

    The progress stream is line-delimited JSON so a GUI can read it without buffering the whole run:
    ``{"stage": "...", "pct": 0-100, "msg": "..."}``, with the stage set fixed by ``STAGES``.

    ``servo_mass_kg`` with ``servo_source`` is the datasheet mass of one actuator, so a servo's CAD
    envelope is counted as bought-in hardware instead of as printed plastic. It is passed together
    because a mass without the document it came from is indistinguishable from a guess; the compiler
    enforces the pairing, and a caller that supplies one and not the other is refused there.
    """

    def default_emit(stage: str, pct: int, msg: str) -> None:
        print(json.dumps({"stage": stage, "pct": int(pct), "msg": msg}), flush=True)

    sink = emit or (default_emit if json_progress else (lambda stage, pct, msg: print(
        f"{stage:11s} {pct:3d}%  {msg}", flush=True)))

    def progress(stage: str, pct: int, msg: str) -> None:
        if stage not in KNOWN_STAGES:  # a stage the consumer cannot know about is a bug, not a feature
            raise ValueError(f"unknown stage {stage!r}")
        sink(stage, pct, msg)

    if print_model is not None:
        # Said before the compiler starts, not after: the print model decides every body's mass, and
        # a caller reading the stream has to know which assumptions the numbers that follow rest on.
        sink(TOOLING_STAGE, 0, f"print model: {print_model.wall_thickness_m * 1000:.2f} mm wall, "
                               f"{print_model.infill_fraction:.2f} infill")

    try:
        from ai_cad.compiler.compile import compile_bundle

        limits, source = (None, None)
        if joints is not None:
            limits, source = _limits_from_joints(Path(joints))
        report = compile_bundle(
            str(step),
            str(out),
            limits=limits,
            limits_source=source,
            print_model=print_model,
            actuator_mass_kg=servo_mass_kg,
            actuator_mass_source=servo_source,
            progress=progress,
        )
    except Exception as error:  # noqa: BLE001 - a CLI contract: report, do not traceback at a GUI
        # Through the same sink as the stages, so a caller that supplied one sees the failure there
        # rather than having to also capture stderr. A GUI waiting on a progress stream must not have
        # to parse a traceback to learn what went wrong, and must not wait forever on a dead pipe.
        sink("error", 0, f"{type(error).__name__}: {error}")
        return 2
    worst = "fail" if any(c.status == "fail" for c in report.checks) else (
        "warn" if any(c.status == "warn" for c in report.checks) else "pass"
    )
    return 3 if worst == "fail" else 0


def _bundle_document(directory: Path) -> dict:
    """The compiled ``bundle.json`` in a directory, or a caller-facing error naming what is missing."""
    path = Path(directory) / "bundle.json"
    if not path.exists():
        raise FileNotFoundError(
            f"{_safe(directory)} has no bundle.json: a revision compares two compiles of the same robot"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _bought_in_parts(document: dict) -> int:
    """How many parts in a compile are bought in rather than printed."""
    return sum(
        int(body.get("bought_in_parts") or 0)
        for body in document.get("bodies") or []
        if isinstance(body, dict)
    )


def _servo_provenance_error(before_document: dict, servo_mass_kg: float | None,
                            servo_source: str | None) -> str | None:
    """Why a revision cannot start without a stated actuator mass, or ``None`` if it can.

    The frozen bundle models bought-in parts — servos sitting in a CAD envelope that carries no mass
    of its own. A compile that is not told their mass counts those envelopes as printed plastic, so
    the two compiles disagree about how much of the robot is printed. That disagreement is not a
    revision, and the solid-bound guard downstream can only report it after 26 minutes of compilation.
    Refusing here costs milliseconds and names the flag.
    """
    bought_in = _bought_in_parts(before_document)
    if bought_in == 0:
        return None
    if servo_mass_kg is None:
        return (
            f"the frozen bundle models {bought_in} bought-in part(s) with no printed mass,"
            " and this compile was not told their mass: pass --servo-mass-kg with --servo-source, or"
            " the servo envelopes are counted as printed plastic and the solid bound moves for a"
            " reason that is not the print model"
        )
    if not (servo_source or "").strip():
        return (
            "a servo mass without its source is a number with nothing behind it: pass --servo-source"
            " naming the datasheet the mass came from, so the revision carries its assumption"
        )
    return None


def revise_cli(step: Path, before: Path, out: Path, infill: float | None, wall_mm: float | None,
               joints: Path | None, json_progress: bool, json_out: bool,
               servo_mass_kg: float | None = None, servo_source: str | None = None,
               emit=None) -> int:
    """Recompile ``before``'s robot against a new print model and diff the two compiles.

    This is the sentence "change the infill to 30 percent" made into a command: the STEP file is
    recompiled with a print model the caller named, written into ``out/bundle``, and diffed link by
    link against the frozen bundle with ``ai_cad/compiler/revision.py``. Both sides are compiles of
    the same robot, so the diff is a statement about one changed assumption and nothing else.
    """
    try:
        print_model = print_model_from_cli(infill, wall_mm)
    except ValueError as error:
        # A range refusal is bad input, not a failed revision: nothing was compiled and no number was
        # produced, so the caller gets exit 2 and the reason rather than a mass built on a bad guess.
        print(f"error: {error}", file=sys.stderr)
        if json_out:
            print(json.dumps({"schema_version": REVISE_SCHEMA, "error": str(error)}))
        return 2

    # Read the frozen bundle before compiling anything: everything that can be refused in
    # milliseconds should be, and the servo provenance check needs the bundle's own body records.
    try:
        before_document = _bundle_document(before)
    except FileNotFoundError as error:
        print(f"error: {_safe(error)}", file=sys.stderr)
        if json_out:
            print(json.dumps({"schema_version": REVISE_SCHEMA, "error": str(error)}))
        return 2
    provenance_error = _servo_provenance_error(before_document, servo_mass_kg, servo_source)
    if provenance_error is not None:
        print(f"error: {provenance_error}", file=sys.stderr)
        if json_out:
            print(json.dumps({"schema_version": REVISE_SCHEMA, "error": provenance_error}))
        return 2

    # Imported before the compiler runs, not after: `revision.py` imports PyYAML at module scope, so
    # a missing dependency has to fail in a second rather than at the end of a 26-minute compile.
    from ai_cad.compiler.revision import diff_links, from_bundle, render_markdown  # noqa: PLC0415

    bundle_out = Path(out) / "bundle"
    code = compile_bundle_cli(Path(step), joints, bundle_out, json_progress, print_model,
                              servo_mass_kg, servo_source, emit)
    if code == 2:
        return 2  # the compiler reported through the same sink; there is nothing to diff

    try:
        after_document = _bundle_document(bundle_out)
    except FileNotFoundError as error:
        print(f"error: {_safe(error)}", file=sys.stderr)
        if json_out:
            print(json.dumps({"schema_version": REVISE_SCHEMA, "error": str(error)}))
        return 2

    revision = diff_links(
        from_bundle(before_document),
        from_bundle(after_document),
        before_label=Path(before).as_posix(),
        after_label=bundle_out.as_posix(),
    )
    Path(out).mkdir(parents=True, exist_ok=True)
    (Path(out) / "diff.json").write_text(revision.model_dump_json(indent=2), encoding="utf-8")
    markdown = render_markdown(revision)
    (Path(out) / "diff.md").write_text(markdown, encoding="utf-8")

    # The spoken figures: both totals are printed from the two bundles, and the solid bound is named
    # beside them because it does not move with a print assumption and that is the point of it.
    mass_before = before_document.get("total_mass_kg")
    mass_after = after_document.get("total_mass_kg")
    solid_before = before_document.get("total_solid_mass_kg")
    solid_after = after_document.get("total_solid_mass_kg")
    change = None
    if mass_before and mass_after is not None and mass_before > 0:
        change = 100.0 * (mass_after - mass_before) / mass_before

    # A print assumption cannot move the solid bound: the solid is the volume the CAD holds at a
    # stated density, and neither wall thickness nor infill enters it. When the two bundles disagree
    # about it, something OTHER than the print model differs between the compiles -- the servo mass,
    # the density map, the decimation -- and the mass change below is that difference plus the
    # revision rather than the revision. That is the defect revision_f030's sanity list exists to
    # prevent, so the diff is refused instead of printed as if it were one changed assumption.
    solid_moved = (
        solid_before is not None
        and solid_after is not None
        and abs(solid_after - solid_before) > max(1e-9, 1e-6 * max(abs(solid_before), abs(solid_after)))
    )
    reason = revision.incomparable_reason
    if solid_moved:
        reason = (
            f"the solid bound moved {solid_before:.4f} kg -> {solid_after:.4f} kg, and wall "
            "thickness and infill cannot change it: the two compiles differ by something other than "
            "the print model. Recompile with the same inputs the frozen bundle was built with "
            "(`--servo-mass-kg` and `--servo-source`, and the same `--joints`), or the printed mass "
            "below is that difference plus the revision, not the revision."
        )
    comparable = revision.comparable and not solid_moved

    payload = {
        "schema_version": REVISE_SCHEMA,
        "before": Path(before).as_posix(),
        "after": bundle_out.as_posix(),
        "print_model": (
            None if print_model is None
            else {
                "wall_thickness_m": print_model.wall_thickness_m,
                "infill_fraction": print_model.infill_fraction,
            }
        ),
        "totals": {
            "printed_mass_before_kg": mass_before,
            "printed_mass_after_kg": mass_after,
            "printed_mass_change_percent": change,
            "solid_mass_before_kg": solid_before,
            "solid_mass_after_kg": solid_after,
        },
        "links": {"added": [], "removed": [], "changed": len(revision.changed)},
        "solid_bound_moved": solid_moved,
        "comparable": comparable,
        "incomparable_reason": reason,
        "written": [str(Path(out) / "diff.json"), str(Path(out) / "diff.md")],
    }
    for link in revision.links:
        if link.status == "added":
            payload["links"]["added"].append(link.link_id)
        elif link.status == "removed":
            payload["links"]["removed"].append(link.link_id)

    if solid_moved:
        # The table is still written -- a refused diff is evidence -- but it says why it is refused,
        # so a reader of the file alone is never handed a mass change with no caveat.
        markdown += (
            f"\n**Not comparable.** {reason}\n"
        )
        (Path(out) / "diff.md").write_text(markdown, encoding="utf-8")

    if json_out:
        print(json.dumps(payload, indent=2))
    else:
        model = ("the bundle's own print model" if print_model is None
                 else f"{print_model.wall_thickness_m * 1000:.2f} mm wall, "
                      f"{print_model.infill_fraction:.2f} infill")
        print(f"recompiled at {model}")
        if not comparable:
            print(f"NOT COMPARABLE: {reason}")
        else:
            print(f"links        {len(revision.links)}  ({len(payload['links']['added'])} added, "
                  f"{len(payload['links']['removed'])} removed, {len(revision.changed)} changed)")
            if change is None:
                print("printed mass  not stated: one of the two bundles carries no total mass")
            else:
                print(f"printed mass {mass_before:.4f} kg -> {mass_after:.4f} kg ({change:+.1f}%)")
            if solid_before is not None and solid_after is not None:
                print(f"solid bound  {solid_before:.4f} kg -> {solid_after:.4f} kg "
                      "(the solid is not a print assumption)")
            print(f"diff written {Path(out) / 'diff.md'}")
    return 0 if comparable else 3


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="robocad twin", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    summary = sub.add_parser("summary", help="describe a bundle as JSON")
    summary.add_argument("--bundle", type=Path, required=True)
    summary.add_argument("--json", action="store_true", help="machine-readable output")

    page = sub.add_parser("page", help="build the offline page from a bundle")
    page.add_argument("--bundle", type=Path, required=True)
    page.add_argument("--out", type=Path, required=True)
    page.add_argument("--assets", type=Path, default=None,
                      help="page sources (default: docs/demo/page in this repo)")
    page.add_argument("--seconds", type=float, default=6.0)
    page.add_argument("--hz", type=int, default=100)
    # The demo page ships at a 500-triangle per-mesh budget (3.1 MB of payload); bake's own default
    # is 2500, which is 10.9 MB for the same robot. The default here matches the demo because the
    # page exists to be opened in front of someone, and the budget is reported in the payload either
    # way so a caller who wants the fidelity can ask for it and see what it cost.
    page.add_argument("--triangles", type=int, default=500)
    page.add_argument("--json", action="store_true", help="machine-readable output")

    compile_cmd = sub.add_parser("compile", help="compile a STEP assembly into a bundle")
    compile_cmd.add_argument("--step", type=Path, required=True)
    compile_cmd.add_argument(
        "--joints", type=Path, default=None,
        help="reviewed robot.joints.yaml whose limits this compile adopts",
    )
    compile_cmd.add_argument("--out", type=Path, required=True)
    compile_cmd.add_argument("--json-progress", action="store_true",
                             help="emit one JSON object per line instead of text")
    compile_cmd.add_argument(
        "--infill", type=float, default=None,
        help=f"print-model infill fraction, {PRINT_INFILL_RANGE[0]:g}-{PRINT_INFILL_RANGE[1]:g}; "
             "outside that range the command refuses",
    )
    compile_cmd.add_argument(
        "--wall-mm", type=float, default=None,
        help=f"print-model wall thickness in mm, {PRINT_WALL_MM_RANGE[0]:g}-{PRINT_WALL_MM_RANGE[1]:g}; "
             "outside that range the command refuses",
    )
    compile_cmd.add_argument(
        "--servo-mass-kg", type=float, default=None,
        help="datasheet mass of one actuator, so its CAD envelope is not counted as printed plastic",
    )
    compile_cmd.add_argument(
        "--servo-source", default=None,
        help="the document the servo mass comes from; required with --servo-mass-kg",
    )

    revise_cmd = sub.add_parser(
        "revise", help="recompile a bundle's robot at a new print model and diff the two compiles"
    )
    revise_cmd.add_argument("--step", type=Path, required=True)
    revise_cmd.add_argument("--before", type=Path, required=True,
                            help="the compiled bundle the revision is measured against")
    revise_cmd.add_argument("--out", type=Path, required=True,
                            help="directory for the new compile, diff.json and diff.md")
    revise_cmd.add_argument("--joints", type=Path, default=None,
                            help="reviewed robot.joints.yaml whose limits this compile adopts")
    revise_cmd.add_argument("--infill", type=float, default=None,
                            help=f"print-model infill fraction, {PRINT_INFILL_RANGE[0]:g}-"
                                 f"{PRINT_INFILL_RANGE[1]:g}")
    revise_cmd.add_argument("--wall-mm", type=float, default=None,
                            help=f"print-model wall thickness in mm, {PRINT_WALL_MM_RANGE[0]:g}-"
                                 f"{PRINT_WALL_MM_RANGE[1]:g}")
    revise_cmd.add_argument("--json-progress", action="store_true",
                            help="emit one JSON object per line instead of text")
    revise_cmd.add_argument("--json", action="store_true", help="machine-readable output")
    revise_cmd.add_argument("--servo-mass-kg", type=float, default=None,
                            help="the mass the frozen bundle was compiled with, so the only stated "
                                 "difference between the two compiles is the print model")
    revise_cmd.add_argument("--servo-source", default=None,
                            help="the document the servo mass comes from; required with --servo-mass-kg")

    unpack_cmd = sub.add_parser("unpack", help="extract a shipped demo zip, refusing a bad digest")
    unpack_cmd.add_argument("--zip", type=Path, required=True)
    unpack_cmd.add_argument("--out", type=Path, required=True)
    unpack_cmd.add_argument(
        "--verify-sha", default=None,
        help="sha256 the archive must have; the digest recorded in verify.json",
    )
    unpack_cmd.add_argument("--json", action="store_true", help="machine-readable output")

    args = parser.parse_args(argv)
    if args.command == "summary":
        try:
            document = build_summary(args.bundle)
        except FileNotFoundError as error:
            print(f"error: {_safe(error)}", file=sys.stderr)
            if args.json:
                print(json.dumps({"schema_version": SUMMARY_SCHEMA, "error": str(error)}))
            return 2
        except Exception as error:  # noqa: BLE001 - a documented JSON contract, not a traceback
            # A bundle is untrusted input: it arrives inside an extracted archive. Whatever shape it
            # turns out to have, the caller gets the same error line and exit code as for a missing
            # bundle, because a stack trace on stdout is not a contract.
            message = f"{type(error).__name__}: {_safe(error)}"
            print(f"error: {_safe(args.bundle)} is not a readable bundle: {message}",
                  file=sys.stderr)
            if args.json:
                print(json.dumps({"schema_version": SUMMARY_SCHEMA, "error": message}))
            return 2
        if args.json:
            print(json.dumps(document, indent=2))
        else:
            _print_summary(document)
        return 0
    if args.command == "page":
        try:
            payload = build_page(
                args.bundle, args.out, args.seconds, args.hz, args.triangles, args.assets
            )
        except FileNotFoundError as error:
            print(f"error: {_safe(error)}", file=sys.stderr)
            if args.json:
                print(json.dumps({"schema_version": "robocad.twin.page/1", "error": str(error)}))
            return 2
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"page at {payload['out']}")
            print(f"  rebuilt from this bundle: {', '.join(payload['rebuilt_from_this_bundle'])}")
            print(f"  copied from page assets:  {', '.join(payload['copied_from_page_assets']) or 'none'}")
            if payload["referenced_but_absent"]:
                print(f"  MISSING, the page links these: {', '.join(payload['referenced_but_absent'])}")
        return 0 if payload["complete"] else 3
    if args.command == "unpack":
        try:
            payload = unpack_zip(args.zip, args.out, args.verify_sha)
        except (FileNotFoundError, ArchiveError) as error:
            print(f"error: {_safe(error)}", file=sys.stderr)
            if args.json:
                print(json.dumps({"schema_version": UNPACK_SCHEMA, "error": str(error)}))
            return 2
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"unpacked {payload['zip']['path']}")
            print(f"  sha256 {payload['zip']['sha256']} ({'verified' if payload['verified'] else 'NOT CHECKED'})")
            print(f"  {len(payload['files'])} files into {payload['out']}")
            digests = payload.get("file_digests") or {}
            if digests.get("verified"):
                print(f"  {digests['checked']} files match the {FILE_DIGESTS} the package ships")
            else:
                print(f"  no {FILE_DIGESTS} in this package: the zip digest is the only check")
            print(f"  bundle (set ROBOCAD_BUNDLE_DIR to this): {payload['bundle']}")
        return 0
    if args.command == "revise":
        return revise_cli(args.step, args.before, args.out, args.infill, args.wall_mm,
                          args.joints, args.json_progress, args.json,
                          args.servo_mass_kg, args.servo_source)
    try:
        print_model = print_model_from_cli(args.infill, args.wall_mm)
    except ValueError as error:
        # Refused before the compiler starts: a compile that produced masses from an impossible print
        # assumption would be a number with no process behind it, and the caller has to see why.
        print(f"error: {error}", file=sys.stderr)
        if args.json_progress:
            print(json.dumps({"stage": "error", "pct": 0, "msg": str(error)}), flush=True)
        return 2
    return compile_bundle_cli(args.step, args.joints, args.out, args.json_progress, print_model,
                              args.servo_mass_kg, args.servo_source)


if __name__ == "__main__":
    raise SystemExit(main())
