"""``robocad twin``: the JSON contract another process uses to read and build a bundle.

This exists so a second application can drive RoboCAD without importing it. Hi-EV never links this
code; it runs a subprocess and reads JSON, which keeps the two repos independent and means a change
here cannot break it silently -- a changed field is a visible failure of a schema, not an import that
happens to still resolve.

Commands::

    robocad twin summary --bundle DIR [--json]
    robocad twin page    --bundle DIR --out PAGE_DIR [--seconds S] [--hz N] [--triangles N]
    robocad twin compile --step FILE --joints FILE --out DIR [--json-progress]

``summary`` describes a bundle as JSON. Its contract is ``robocad.twin.summary/1`` and its point is
the ``provenance`` block: every figure the bundle reports is labelled with what kind of claim it is,
and anything produced by a model rather than observed on the robot is flagged ``synthetic: true``. A
consumer that renders "mass: 0.9017 kg" without that label is quoting a density assumption.

``page`` builds the offline living page from a bundle. ``compile`` runs the compiler and, with
``--json-progress``, writes one JSON object per line so a GUI can show progress without scraping text.

Exit codes: 0 success, 2 bad input (missing file or unreadable bundle), 3 the command ran but the
result is a failure (the page could not be built, or the bundle's own checks failed). With
``--json-progress`` a failing run still ends with a JSON error line and a non-zero exit, because a
GUI that is waiting on a progress stream must not have to parse a stack trace to learn what happened.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

SUMMARY_SCHEMA = "robocad.twin.summary/1"

# The stages `twin compile` emits, in order. A consumer may rely on this list: no other stage name is
# produced, and "done" is only ever the last line of a successful run.
STAGES = ("import", "joints", "properties", "collision", "bundle", "checks", "done")

# Kinds a figure can be, and whether that kind is a measurement of the thing it names. The two that
# are not are `derived` (a model output over assumed inputs) and `synthetic` (generated data), and
# they are the ones a reader is allowed to be misled by if they go unlabelled.
SYNTHETIC_KINDS = frozenset({"derived", "synthetic"})


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
    return {"kind": kind, "synthetic": kind in SYNTHETIC_KINDS, "basis": basis}


def provenance(bundle_dir: Path, report: dict, manifest: dict, data: dict) -> dict:
    """What kind of claim each figure is, with the basis spelled out.

    Every key of ``totals`` gets an entry, including ones this function has no rule for: an unknown
    figure defaults to ``derived`` and says so, because the alternative -- leaving it out of the block
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
            out[f"totals.{key}"] = _entry("derived", mass_basis)
        elif key.startswith("printed_") or key.endswith("_volume_m3") or key == "volume_by_role_m3":
            out[f"totals.{key}"] = _entry(
                "derived", "CAD solid volume split by part name, at an assumed material density"
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
            out[f"totals.{key}"] = _entry("derived", "the assumption set this bundle was compiled with")
        elif key.endswith("_bytes") or key == "visual_budget_bytes":
            out[f"totals.{key}"] = _entry("counted", "file sizes on disk")
        else:
            out[f"totals.{key}"] = _entry(
                "derived",
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
    out["checks"] = _entry("computed", "each check ran against the written artifacts")
    return out


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
            "measured": c.get("measured", {}),
        }
        for c in report.get("checks") or []
    ]
    statuses = [c["status"] for c in checks]
    worst = "fail" if "fail" in statuses else ("warn" if "warn" in statuses else "pass")

    conventions = (manifest or {}).get("conventions") or {}
    prov = provenance(bundle_dir, report, manifest or {}, data)
    return {
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
        # Counted here rather than left for the consumer to derive, so a GUI can say "12 figures in
        # this panel are model outputs" without re-implementing the rule.
        "synthetic_count": sum(1 for v in prov.values() if v["synthetic"]),
        "warnings": report.get("warnings") or [],
        "notes": report.get("notes") or [],
    }


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
    print(f"  synthetic figures: {summary['synthetic_count']} of {len(summary['provenance'])}")
    for key, entry in summary["provenance"].items():
        if entry["synthetic"]:
            print(f"    {key:34s} {entry['kind']:10s} {entry['basis']}")


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
    return compile_bundle_cli(args.step, args.joints, args.out, args.json_progress)


if __name__ == "__main__":
    raise SystemExit(main())
