"""``robocad twin``: the JSON contract another process uses to read and build a bundle.

This exists so a second application can drive RoboCAD without importing it. Hi-EV never links this
code; it runs a subprocess and reads JSON, which keeps the two repos independent and means a change
here cannot break it silently -- a changed field is a visible failure of a schema, not an import that
happens to still resolve.

Commands::

    robocad twin summary --bundle DIR [--json]
    robocad twin page    --bundle DIR --out PAGE_DIR [--seconds S] [--hz N] [--triangles N]
    robocad twin compile --step FILE --joints FILE --out DIR [--json-progress]
    robocad twin unpack  --zip FILE --out DIR [--verify-sha SHA]

``summary`` describes a bundle as JSON. Its contract is ``robocad.twin.summary/1`` and its point is
the ``provenance`` block: every figure the bundle reports is labelled with what kind of claim it is,
and anything produced by a model rather than observed on the robot is labelled ``modelled``. A
consumer that renders "mass: 0.9017 kg" without that label is quoting a density assumption. Only
data generated in simulation is labelled ``synthetic``, and only ``calibration`` is.

``page`` builds the offline living page from a bundle. ``compile`` runs the compiler and, with
``--json-progress``, writes one JSON object per line so a GUI can show progress without scraping text.

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
import re
import shutil
import sys
import zipfile
from pathlib import Path

SUMMARY_SCHEMA = "robocad.twin.summary/1"
UNPACK_SCHEMA = "robocad.twin.unpack/1"

# The stages `twin compile` emits, in order. A consumer may rely on this list: no other stage name is
# produced, and "done" is only ever the last line of a successful run.
STAGES = ("import", "joints", "properties", "collision", "bundle", "checks", "done")

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
    if not path.exists():
        return None
    try:
        import yaml

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
    if totals.get("actuator_mass_kg") is not None:
        assumptions["servo_g"] = _node(round(totals["actuator_mass_kg"] * 1000.0, 1), "stated")
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
    spacings = comparison.get("link_spacings") or []
    deltas = [abs(float(s["delta_m"])) for s in spacings if s.get("delta_m") is not None]
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
            "pose_gate_mm": _node(torque.get("pose_gate_worst_mm"), "modelled"),
            "pose_gate_samples_mm": torque.get("pose_gate_samples_mm"),
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
                if (link.get("mass_delta_kg") or 0.0) != 0.0
            ),
            "added": list(diff.get("added") or []),
            "removed": list(diff.get("removed") or []),
        }

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
                for key, name in (("damping", "viscous_damping"), ("coulomb", "coulomb_friction")):
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
        if scenarios:
            base = scenarios[0]
            calibration["position_only"] = {
                "snr": base.get("snr"),
                "status": "sufficient" if base.get("crosses_snr_3") else "insufficient",
                "scenario": base.get("scenario"),
            }
        # Every number in this block came out of simulated logs with planted parameters. That is the
        # one place in the summary where `synthetic` is the true kind, and it says so here.
        calibration["synthetic"] = True
        section["calibration"] = calibration

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
    return document


def _print_summary(summary: dict) -> None:
    totals = summary["totals"]
    print(f"{summary['name']}: {summary['bundle']['path']}")
    print(f"  bodies {totals.get('bodies')}  joints {totals.get('joints')}  "
          f"parts {totals.get('parts')}  instances {totals.get('instances')}")
    print(f"  mass {totals.get('total_mass_kg')} kg modelled, "
          f"{totals.get('total_solid_mass_kg')} kg solid bound "
          f"[{(summary['provenance'].get('totals.total_mass_kg') or {}).get('kind')}]")
    for check in summary["checks"]:
        print(f"  {check['id']:22s} {check['status']:8s} {check['explanation']}")
    print(f"  worst check {summary['worst_status']}")
    conventions = summary["conventions"]
    print("  conventions: " + (
        f"measured, {conventions['source']}" if conventions["measured"]
        else "none measured; the bundle says so rather than shipping zeros"
    ))
    counts = summary.get("check_counts") or {}
    if counts:
        print(f"  checks {counts.get('pass', 0)} pass  {counts.get('fail', 0)} fail  "
              f"{counts.get('skipped', 0)} skipped")
    if "masses" in summary:
        masses = summary["masses"]
        parts = [
            f"{name} {masses[key]['value']:.4g} [{masses[key]['kind']}]"
            for key, name in (("solid_kg", "solid"), ("print_kg", "print"),
                              ("published_kg", "published"))
            if key in masses
        ]
        print("  masses: " + ", ".join(parts))
    if "torque" in summary and summary["torque"].get("static_poses"):
        rest = summary["torque"]["static_poses"][0]
        print(f"  torque at {rest['pose']}: {rest['compiled_nm']['value']} compiled vs "
              f"{rest['published_nm']['value']} published N m, "
              f"limit {summary['torque']['limit_stall_nm']['value']}")
    if "revision" in summary:
        revision = summary["revision"]
        print(f"  revision infill {revision['infill_before']['value']} -> "
              f"{revision['infill_after']['value']}: mass {revision['mass_before_kg']['value']:.4g}"
              f" -> {revision['mass_after_kg']['value']:.4g} kg, "
              f"{revision['links_changed']} links changed")
    print(f"  synthetic figures: {summary['synthetic_count']} of {len(summary['provenance'])}")
    for key, entry in summary["provenance"].items():
        if entry["kind"] in SYNTHETIC_KINDS:
            print(f"    {key:34s} {entry['kind']:10s} {entry['basis']}")
    for key, entry in summary["provenance"].items():
        if entry["kind"] == "modelled":
            print(f"  modelled  {key:34s} {entry['basis'][:88]}")


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
    out.mkdir(parents=True, exist_ok=True)
    repo = Path(__file__).resolve().parents[1]
    assets = Path(assets) if assets else repo / "docs" / "demo" / "page"

    sys.path.insert(0, str(repo / "teardown_export"))
    try:
        import bake  # noqa: PLC0415 - imported here so the rest of the CLI has no numpy/mujoco dep
        import bake_report  # noqa: PLC0415

        bake.main([
            str(model), str(out),
            "--seconds", str(seconds), "--hz", str(hz), "--triangles", str(triangles),
        ])
        bake_report.main([
            str(report_json), str(out / "report.js"),
            "--bundle", str(bundle_dir / "bundle.json"),
        ])
    finally:
        sys.path.remove(str(repo / "teardown_export"))

    rebuilt = {"trajectory.js", "meshes.js", "report.js"}
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
        infos = [info for info in archive.infolist() if not info.is_dir()]
        names = [info.filename for info in infos]

        # Resource checks before any write: a declared expansion past the cap, or an entry count no
        # demo plausibly has, is refused rather than attempted. Declared sizes can lie low, so the
        # resolved-path containment check below remains the guarantee about *where* bytes land.
        if len(infos) > MAX_MEMBERS:
            raise ArchiveError(f"{zip_path} has {len(infos)} entries: past the {MAX_MEMBERS} cap")
        expanded = sum(info.file_size for info in infos)
        if expanded > MAX_EXPANDED_BYTES:
            raise ArchiveError(
                f"{zip_path} expands to {expanded} bytes: past the {MAX_EXPANDED_BYTES} cap"
            )

        problems = [(info.filename, _member_problem(info.filename)) for info in infos]
        unsafe = [(name, why) for name, why in problems if why]
        for info in infos:
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
        for info in infos:
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


def compile_bundle_cli(step: Path, joints: Path | None, out: Path, json_progress: bool,
                       emit=None) -> int:
    """Run the compiler, emitting one JSON line per stage when asked.

    The progress stream is line-delimited JSON so a GUI can read it without buffering the whole run:
    ``{"stage": "...", "pct": 0-100, "msg": "..."}``, with the stage set fixed by ``STAGES``.
    """

    def default_emit(stage: str, pct: int, msg: str) -> None:
        print(json.dumps({"stage": stage, "pct": int(pct), "msg": msg}), flush=True)

    sink = emit or (default_emit if json_progress else (lambda stage, pct, msg: print(
        f"{stage:11s} {pct:3d}%  {msg}", flush=True)))

    def progress(stage: str, pct: int, msg: str) -> None:
        if stage not in STAGES:  # a stage the consumer cannot know about is a bug, not a feature
            raise ValueError(f"unknown stage {stage!r}")
        sink(stage, pct, msg)

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
            print(f"error: {error}", file=sys.stderr)
            if args.json:
                print(json.dumps({"schema_version": SUMMARY_SCHEMA, "error": str(error)}))
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
            print(f"error: {error}", file=sys.stderr)
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
            print(f"error: {error}", file=sys.stderr)
            if args.json:
                print(json.dumps({"schema_version": UNPACK_SCHEMA, "error": str(error)}))
            return 2
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"unpacked {payload['zip']['path']}")
            print(f"  sha256 {payload['zip']['sha256']} ({'verified' if payload['verified'] else 'NOT CHECKED'})")
            print(f"  {len(payload['files'])} files into {payload['out']}")
            print(f"  bundle (set ROBOCAD_BUNDLE_DIR to this): {payload['bundle']}")
        return 0
    return compile_bundle_cli(args.step, args.joints, args.out, args.json_progress)


if __name__ == "__main__":
    raise SystemExit(main())
