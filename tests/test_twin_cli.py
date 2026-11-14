"""The JSON contract another process reads: `robocad twin summary|page|compile`.

Hi-EV drives RoboCAD through these commands and never imports it, so the contract has to hold at the
process boundary: parseable lines, a documented stage set, and a non-zero exit with a JSON error line
rather than a traceback when something fails. The summary's real content is its provenance block --
every figure the bundle reports is labelled with what kind of claim it is -- so the tests here are
mostly about what that block must never do: leave a model output unflagged, or claim a measurement
the bundle does not carry.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from robocad import twin_cli

REPO = Path(__file__).resolve().parents[1]
BUNDLE = REPO / "docs" / "twin" / "so101" / "bundle"
SYNTHETIC_KINDS = twin_cli.SYNTHETIC_KINDS


@pytest.mark.skipif(not (BUNDLE / "report.json").exists(), reason="no published bundle checked out")
def test_the_summary_carries_its_schema_and_the_fields_a_consumer_switches_on():
    document = twin_cli.build_summary(BUNDLE)
    assert document["schema_version"] == "robocad.twin.summary/1"
    for key in ("name", "bundle", "totals", "checks", "worst_status", "conventions", "provenance",
                "synthetic_count", "notes", "warnings"):
        assert key in document, key
    assert document["bundle"]["path"].endswith("bundle")
    # A Windows path in a published payload is one a consumer on another machine cannot use.
    assert "\\" not in document["bundle"]["path"]
    assert document["name"] == "so101"


@pytest.mark.skipif(not (BUNDLE / "report.json").exists(), reason="no published bundle checked out")
def test_every_totals_figure_carries_a_provenance_entry():
    """No figure is allowed to arrive unlabelled, including one no rule anticipated."""
    document = twin_cli.build_summary(BUNDLE)
    labelled = {k.split(".", 1)[1] for k in document["provenance"] if k.startswith("totals.")}
    assert set(document["totals"]) <= labelled
    for key, entry in document["provenance"].items():
        assert entry["kind"] in twin_cli.KINDS, key
        assert entry["basis"].strip(), key


@pytest.mark.skipif(not (BUNDLE / "report.json").exists(), reason="no published bundle checked out")
def test_the_provenance_kind_is_the_only_label_and_synthetic_is_one_value_of_it():
    """There is no boolean beside the kind, so a hand-written flag cannot disagree with it."""
    document = twin_cli.build_summary(BUNDLE)
    for key, entry in document["provenance"].items():
        assert "synthetic" not in entry, key
        assert entry["kind"] in twin_cli.KINDS, (key, entry)


@pytest.mark.skipif(not (BUNDLE / "report.json").exists(), reason="no published bundle checked out")
def test_the_masses_are_modelled_not_synthetic_because_no_scale_touched_them():
    """A mass is a model output over real CAD, not generated data: the two words mean different things."""
    document = twin_cli.build_summary(BUNDLE)
    for key in ("totals.total_mass_kg", "totals.total_solid_mass_kg"):
        assert document["provenance"][key]["kind"] == "modelled"
    assert document["synthetic_count"] == sum(
        1 for v in document["provenance"].values() if v["kind"] in SYNTHETIC_KINDS
    )


@pytest.mark.skipif(not (BUNDLE / "report.json").exists(), reason="no published bundle checked out")
def test_the_conventions_are_reported_as_measured_and_match_the_manifest():
    document = twin_cli.build_summary(BUNDLE)
    manifest = json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))
    assert document["conventions"]["measured"] is True
    assert document["conventions"]["zero_pose_offsets_deg"] == {
        k: v for k, v in manifest["conventions"]["zero_pose_offsets_deg"].items()
    }
    assert document["provenance"]["conventions.zero_pose_offsets_deg"]["kind"] == "measured"


def test_an_unmeasured_bundle_says_so_rather_than_reporting_zero_offsets(tmp_path):
    """The default `Conventions()` is what a bundle compiled without a measurement carries."""
    (tmp_path / "report.json").write_text(
        json.dumps({"name": "fixture", "totals": {}, "checks": [], "notes": [], "warnings": []}),
        encoding="utf-8",
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps({"conventions": {"measured": False, "source": "no measurement supplied"}}),
        encoding="utf-8",
    )
    document = twin_cli.build_summary(tmp_path)
    assert document["conventions"]["measured"] is False
    assert document["provenance"]["conventions.zero_pose_offsets_deg"]["kind"] == "unknown"


def test_a_directory_that_is_not_a_bundle_raises_rather_than_summarising_nothing(tmp_path):
    with pytest.raises(FileNotFoundError, match="neither report.json nor bundle.json"):
        twin_cli.build_summary(tmp_path)
    with pytest.raises(FileNotFoundError, match="no bundle directory"):
        twin_cli.build_summary(tmp_path / "absent")


def test_a_failed_summary_exits_non_zero_and_still_prints_json(tmp_path, capsys):
    code = twin_cli.main(["summary", "--bundle", str(tmp_path), "--json"])
    assert code == 2
    printed = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert printed["schema_version"] == "robocad.twin.summary/1"
    assert "error" in printed


# ------------------------------------------------------------------------------------------------
# the progress stream `twin compile --json-progress` produces
# ------------------------------------------------------------------------------------------------
def _fake_compile(stages, boom: Exception | None = None):
    """A stand-in for compile_bundle that drives the progress sink through the named stages."""

    def compile_bundle(step, out, limits=None, limits_source=None, progress=None, **kwargs):
        for stage, pct, msg in stages:
            progress(stage, pct, msg)
        if boom is not None:
            raise boom

        class _Check:
            def __init__(self, status):
                self.status = status

        class _Report:
            checks = [_Check("pass")]

        return _Report()

    return compile_bundle


def test_the_progress_lines_are_one_json_object_each_and_cover_every_stage(monkeypatch, tmp_path):
    seen = []

    def emit(stage, pct, msg):
        seen.append({"stage": stage, "pct": pct, "msg": msg})

    stages = [
        ("import", 10, "83 parts, 259 instances"),
        ("joints", 25, "6 joints, 7 bodies"),
        ("properties", 45, "7 bodies, 0.902 kg modelled"),
        ("collision", 70, "433 hulls, 259 visual meshes"),
        ("bundle", 85, "written"),
        ("checks", 97, "7 checks, worst fail"),
        ("done", 100, "bundle written"),
    ]
    monkeypatch.setattr("ai_cad.compiler.compile.compile_bundle", _fake_compile(stages))
    code = twin_cli.compile_bundle_cli(tmp_path / "s.step", None, tmp_path / "out", True, emit=emit)
    assert code == 0
    assert [line["stage"] for line in seen] == [
        "import", "joints", "properties", "collision", "bundle", "checks", "done"
    ]
    assert seen[-1]["stage"] == "done"
    percentages = [line["pct"] for line in seen]
    assert percentages == sorted(percentages)
    assert percentages[0] >= 0 and percentages[-1] == 100
    # The stage set is a contract: a consumer switches on these names, so only these may appear.
    assert set(stage for stage, _, _ in stages) == set(twin_cli.STAGES)


def test_a_failing_compile_ends_with_a_json_error_line_and_a_non_zero_exit(monkeypatch, tmp_path):
    seen = []

    def emit(stage, pct, msg):
        seen.append({"stage": stage, "pct": pct, "msg": msg})

    boom = ValueError("the STEP file could not be imported")
    monkeypatch.setattr(
        "ai_cad.compiler.compile.compile_bundle",
        _fake_compile([("import", 10, "reading")], boom=boom),
    )
    code = twin_cli.compile_bundle_cli(tmp_path / "s.step", None, tmp_path / "out", True, emit=emit)
    assert code == 2
    assert seen[-1]["stage"] == "error"
    assert "STEP file could not be imported" in seen[-1]["msg"]


def test_an_unknown_stage_is_refused_rather_than_smuggled_into_the_stream(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(
        "ai_cad.compiler.compile.compile_bundle",
        _fake_compile([("polish", 50, "not a real stage")]),
    )
    code = twin_cli.compile_bundle_cli(
        tmp_path / "s.step", None, tmp_path / "out", True,
        emit=lambda stage, pct, msg: seen.append(stage),
    )
    assert code == 2
    assert seen == ["error"]


def test_a_compile_whose_checks_fail_exits_three_not_zero(monkeypatch, tmp_path):
    """A GUI distinguishes "built" from "built and red", so the exit code has to distinguish them."""
    def compile_bundle(step, out, limits=None, limits_source=None, progress=None, **kwargs):
        progress("done", 100, "written")

        class _Check:
            status = "fail"

        class _Report:
            checks = [_Check()]

        return _Report()

    monkeypatch.setattr("ai_cad.compiler.compile.compile_bundle", compile_bundle)
    code = twin_cli.compile_bundle_cli(
        tmp_path / "s.step", None, tmp_path / "out", False, emit=lambda *a: None
    )
    assert code == 3


def test_limits_from_a_reviewed_joints_file_are_adopted_with_their_own_source(tmp_path):
    path = tmp_path / "robot.joints.yaml"
    path.write_text(
        "schema: robocad.twin.joints/1\n"
        "joints:\n"
        "- joint_id: joint_1\n"
        "  limits: {lower: -1.0, upper: 1.0, effort: 3.0, velocity: 5.0}\n"
        "  limits_source: the published urdf at revision abc\n"
        "- joint_id: joint_2\n"
        "  limits: {lower: -2.0, upper: 2.0, effort: 3.0, velocity: 5.0}\n"
        "  limits_source: the published urdf at revision abc\n",
        encoding="utf-8",
    )
    limits, source = twin_cli._limits_from_joints(path)
    assert limits["joint_1"]["upper"] == 1.0
    assert source == "the published urdf at revision abc"


def test_a_joints_file_with_two_sources_is_refused(tmp_path):
    """A bundle cannot say where its limits came from if the file it was handed says two things."""
    path = tmp_path / "robot.joints.yaml"
    path.write_text(
        "joints:\n"
        "- joint_id: joint_1\n"
        "  limits: {lower: -1.0, upper: 1.0}\n"
        "  limits_source: source a\n"
        "- joint_id: joint_2\n"
        "  limits: {lower: -1.0, upper: 1.0}\n"
        "  limits_source: source b\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="one source"):
        twin_cli._limits_from_joints(path)


def test_a_joints_file_without_limits_is_refused(tmp_path):
    path = tmp_path / "robot.joints.yaml"
    path.write_text("joints:\n- joint_id: joint_1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no joint limits"):
        twin_cli._limits_from_joints(path)


# ------------------------------------------------------------------------------------------------
# the page, built from the published bundle
# ------------------------------------------------------------------------------------------------
@pytest.mark.mujoco
@pytest.mark.skipif(not (BUNDLE / "model.mjcf").exists(), reason="no published bundle checked out")
def test_the_page_builds_from_the_published_bundle_and_every_link_resolves(tmp_path):
    pytest.importorskip("mujoco")
    payload = twin_cli.build_page(BUNDLE, tmp_path / "page", seconds=0.2, hz=10, triangles=50)
    assert payload["complete"], payload
    assert payload["referenced_but_absent"] == []
    assert payload["rebuilt_from_this_bundle"] == ["meshes.js", "report.js", "trajectory.js"]
    # The three that come out of this bundle carry this bundle's numbers.
    report_js = (tmp_path / "page" / "report.js").read_text(encoding="utf-8")
    assert "window.SO101_REPORT = " in report_js
    trajectory = (tmp_path / "page" / "trajectory.js").read_text(encoding="utf-8")
    assert "window.SO101_TRAJ = " in trajectory
    assert f'"triangle_budget": {payload["triangle_budget"]}' in trajectory
    # A payload the bundle does not contain is named as copied, not passed off as rebuilt.
    assert "torque.js" in payload["copied_from_page_assets"]


@pytest.mark.mujoco
@pytest.mark.skipif(not (BUNDLE / "model.mjcf").exists(), reason="no published bundle checked out")
def test_a_missing_trajectory_payload_is_a_refusal_not_a_half_page(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(FileNotFoundError, match="no model.mjcf"):
        twin_cli.build_page(empty, tmp_path / "page", seconds=0.1, hz=10, triangles=10)
    assert not (tmp_path / "page" / "index.html").exists()


# ------------------------------------------------------------------------------------------------
# unpack: the one source of truth for a shipped demo
# ------------------------------------------------------------------------------------------------
DEMO_ZIP = REPO / "docs" / "demo" / "so101_demo.zip"


def _make_zip(path: Path, members: dict[str, str]) -> Path:
    import zipfile

    with zipfile.ZipFile(path, "w") as archive:
        for name, text in members.items():
            archive.writestr(name, text)
    return path


def test_unpack_extracts_the_package_and_names_the_bundle_directory(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "report.json").write_text('{"name": "so101"}', encoding="utf-8")
    (source / "index.html").write_text("<html></html>", encoding="utf-8")
    archive = tmp_path / "demo.zip"
    with __import__("zipfile").ZipFile(archive, "w") as zf:
        for file in source.iterdir():
            zf.write(file, f"so101_demo/{file.name}")

    payload = twin_cli.unpack_zip(archive, tmp_path / "out", twin_cli.sha256_file(archive))

    assert payload["schema_version"] == "robocad.twin.unpack/1"
    assert payload["verified"] is True
    assert payload["zip"]["sha256"] == twin_cli.sha256_file(archive)
    # The zip carries one top-level folder; the caller needs the folder with the bundle in it.
    assert Path(payload["bundle"]).name == "so101_demo"
    assert (Path(payload["bundle"]) / "report.json").exists()
    assert "\\" not in payload["bundle"]


def test_unpack_refuses_a_digest_mismatch_before_writing_anything(tmp_path):
    archive = _make_zip(tmp_path / "demo.zip", {"so101_demo/report.json": "{}"})
    target = tmp_path / "out"
    with pytest.raises(twin_cli.ArchiveError, match="not the 0{4}"):
        twin_cli.unpack_zip(archive, target, "0" * 64)
    # A refusal that leaves a half-extracted directory is read as a partial success by the next step.
    assert not target.exists()


def test_unpack_refuses_an_archive_member_that_would_escape_the_target(tmp_path):
    archive = _make_zip(tmp_path / "demo.zip", {
        "so101_demo/report.json": "{}",
        "../escaped.json": "{}",
    })
    with pytest.raises(twin_cli.ArchiveError, match="parent-directory escape"):
        twin_cli.unpack_zip(archive, tmp_path / "out")
    assert not (tmp_path / "escaped.json").exists()
    assert not (tmp_path / "out").exists()


def test_unpack_refuses_a_populated_target_rather_than_merging_two_packages(tmp_path):
    archive = _make_zip(tmp_path / "demo.zip", {"so101_demo/report.json": "{}"})
    target = tmp_path / "out"
    target.mkdir()
    (target / "yesterday.json").write_text("{}", encoding="utf-8")
    with pytest.raises(twin_cli.ArchiveError, match="new directory"):
        twin_cli.unpack_zip(archive, target)
    assert sorted(p.name for p in target.iterdir()) == ["yesterday.json"]


def test_unpack_without_a_digest_says_it_did_not_check(tmp_path, capsys):
    archive = _make_zip(tmp_path / "demo.zip", {"so101_demo/report.json": "{}"})
    assert twin_cli.main([
        "unpack", "--zip", str(archive), "--out", str(tmp_path / "out"),
    ]) == 0
    out = capsys.readouterr().out
    assert "NOT CHECKED" in out


@pytest.mark.skipif(not DEMO_ZIP.exists(), reason="no shipped demo zip checked out")
def test_unpack_on_the_shipped_zip_reproduces_the_digest_the_tag_claims(tmp_path):
    digest = twin_cli.sha256_file(DEMO_ZIP)
    payload = twin_cli.unpack_zip(DEMO_ZIP, tmp_path / "out", digest)
    assert payload["zip"]["sha256"] == digest
    assert payload["zip"]["entries"] == len(payload["files"])
    bundle = Path(payload["bundle"])
    for name in ("report.json", "index.html", "manifest.json"):
        assert (bundle / name).exists(), name


def test_unpack_refuses_a_component_windows_would_strip_back_to_parent(tmp_path):
    """`".. "` is not `".."` to the name check but is `..` to Windows, so it is refused."""
    archive = _make_zip(tmp_path / "demo.zip", {
        "so101_demo/report.json": "{}",
        ".. /escaped.json": "{}",
    })
    with pytest.raises(twin_cli.ArchiveError, match="parent-directory escape"):
        twin_cli.unpack_zip(archive, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_unpack_refuses_an_archive_that_expands_past_the_cap(tmp_path, monkeypatch):
    archive = _make_zip(tmp_path / "demo.zip", {"so101_demo/report.json": "x" * 4096})
    monkeypatch.setattr(twin_cli, "MAX_EXPANDED_BYTES", 1024)
    with pytest.raises(twin_cli.ArchiveError, match="expands to"):
        twin_cli.unpack_zip(archive, tmp_path / "out")


def test_unpack_refuses_more_members_than_a_demo_can_have(tmp_path, monkeypatch):
    archive = _make_zip(
        tmp_path / "demo.zip",
        {f"so101_demo/{i}.json": "{}" for i in range(5)},
    )
    monkeypatch.setattr(twin_cli, "MAX_MEMBERS", 3)
    with pytest.raises(twin_cli.ArchiveError, match="past the 3 cap"):
        twin_cli.unpack_zip(archive, tmp_path / "out")


# ------------------------------------------------------------------------------------------------
# the demo's own numbers: the summary must carry them, not the consumer's defaults
# ------------------------------------------------------------------------------------------------
def _leaves(document, prefix=""):
    """Every leaf in the document, with its path, unwrapping the {value, kind} nodes as it goes."""
    out = []
    if isinstance(document, dict):
        if "value" in document and "kind" in document:
            out.append((prefix, document["value"], document["kind"]))
            return out
        for key, value in document.items():
            out.extend(_leaves(value, f"{prefix}.{key}" if prefix else key))
    elif isinstance(document, list):
        for index, value in enumerate(document):
            out.extend(_leaves(value, f"{prefix}[{index}]"))
    elif isinstance(document, (int, float)):
        out.append((prefix, document, None))
    return out


@pytest.mark.skipif(not (BUNDLE / "report.json").exists(), reason="no published bundle checked out")
@pytest.mark.skipif(not (BUNDLE / "torque.json").exists(), reason="no shipped torque payload")
def test_every_number_in_the_three_minute_script_appears_in_the_summary():
    """The script's figures are the acceptance test: a voice that cannot say them has not read the
    package."""
    document = twin_cli.build_summary(BUNDLE)
    values = [value for _, value, _ in _leaves(document) if isinstance(value, (int, float))]
    wanted = {
        "published total mass 0.632": 0.632,
        "axis worst 2.14": 2.140753227309615,
        "origin median 2.50": 2.5,
        "origin worst 11.25": 11.25,
        "link lengths 1.69": 1.69,
        "solid bound 1.332": 1.332012393,
        "print model 0.902": 0.901658836,
        "rest compiled torque 0.767": 0.7668,
        "rest published torque 0.538": 0.5377,
        "pose gate 70.69": 70.69,
        "stall limit 2.94": 2.941995,
        "revision mass after 0.955": 0.9554530302470398,
        "published base link 0.147": 0.147,
        "infill before 0.20": 0.2,
        "infill after 0.30": 0.3,
        "position-only SNR 0.10": 0.1,
    }
    missing = [
        name for name, number in wanted.items()
        if not any(abs(value - number) <= max(0.005, abs(number) * 1e-6) for value in values)
    ]
    assert not missing, f"the summary cannot say: {missing}"


@pytest.mark.skipif(not (BUNDLE / "report.json").exists(), reason="no published bundle checked out")
def test_synthetic_is_used_only_where_the_underlying_data_was_generated():
    """No figure outside `calibration` may be labelled synthetic: a modelled mass is not one."""
    document = twin_cli.build_summary(BUNDLE)
    offenders = [
        path for path, _, kind in _leaves(document)
        if kind == "synthetic" and not path.startswith("calibration")
    ]
    assert not offenders, offenders
    assert document["calibration"]["synthetic"] is True


@pytest.mark.skipif(not (BUNDLE / "report.json").exists(), reason="no published bundle checked out")
def test_masses_are_modelled_and_carry_the_assumptions_they_rest_on():
    document = twin_cli.build_summary(BUNDLE)
    masses = document["masses"]
    assert masses["solid_kg"]["kind"] == "modelled"
    assert masses["print_kg"]["kind"] == "modelled"
    assert masses["published_kg"]["kind"] == "stated"
    assumptions = masses["assumptions"]
    assert assumptions["wall_mm"]["value"] == 1.2
    assert assumptions["infill"]["value"] == 0.2
    assert assumptions["density_kg_m3"]["value"] > 0
    assert assumptions["servo_g"]["value"] == 55.0


@pytest.mark.skipif(not (BUNDLE / "report.json").exists(), reason="no published bundle checked out")
def test_the_torque_reason_names_the_pose_gate_in_millimetres_not_tens_of_mm():
    document = twin_cli.build_summary(BUNDLE)
    torque = document["torque"]
    gate = torque["pose_gate_mm"]["value"]
    assert f"{gate:.2f} mm" in torque["dynamic_reason"]
    assert "tens of mm" not in torque["dynamic_reason"]
    assert torque["dynamic_comparable"] is False
    # one scalar per pose, not an array a consumer could index into the wrong joint
    for row in torque["static_poses"]:
        assert isinstance(row["compiled_nm"]["value"], float)
        assert isinstance(row["published_nm"]["value"], float)


@pytest.mark.skipif(not (BUNDLE / "report.json").exists(), reason="no published bundle checked out")
def test_check_counts_are_the_report_s_own_statuses_and_each_check_carries_a_reason():
    document = twin_cli.build_summary(BUNDLE)
    statuses = [check["status"] for check in document["checks"]]
    assert document["check_counts"] == {
        status: statuses.count(status) for status in ("pass", "fail", "skipped")
    }
    for check in document["checks"]:
        assert check["reason"], check["id"]
        assert check["reason"] == check["explanation"]


@pytest.mark.skipif(not (BUNDLE / "report.json").exists(), reason="no published bundle checked out")
def test_the_revision_is_the_diff_s_own_numbers_and_has_no_default():
    document = twin_cli.build_summary(BUNDLE)
    revision = document["revision"]
    assert revision["infill_before"]["value"] == 0.2
    assert revision["infill_after"]["value"] == 0.3
    assert revision["infill_before"]["kind"] == "assumed"
    assert revision["mass_before_kg"]["value"] == pytest.approx(0.9016588355893798)
    assert revision["mass_after_kg"]["value"] == pytest.approx(0.9554530302470398)
    assert revision["links_changed"] == 7
    assert revision["added"] == []
    assert revision["removed"] == []


def test_a_bundle_without_the_demo_payloads_has_no_invented_sections(tmp_path):
    """No file, no section. A zero-filled revision would be a default, which is what F2 removes."""
    (tmp_path / "report.json").write_text(json.dumps({
        "name": "bare", "totals": {"bodies": 1}, "checks": [],
    }), encoding="utf-8")
    document = twin_cli.build_summary(tmp_path)
    for key in ("masses", "residuals", "torque", "revision", "calibration"):
        assert key not in document, key
    assert document["check_counts"] == {"pass": 0, "fail": 0, "skipped": 0}


@pytest.mark.skipif(not (BUNDLE / "report.json").exists(), reason="no published bundle checked out")
def test_calibration_carries_an_interval_for_every_recovered_parameter():
    """'Every identified parameter carries uncertainty' only holds if the interval is in the data."""
    document = twin_cli.build_summary(BUNDLE)
    params = document["calibration"]["current_channel"]["params"]
    assert params
    for param in params:
        assert param["lo"] <= param["recovered"] <= param["hi"], param
        assert param["true"] is not None
    assert document["calibration"]["position_only"]["snr"] == 0.1
    assert document["calibration"]["position_only"]["status"] == "insufficient"
