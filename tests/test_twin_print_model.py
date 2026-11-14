"""The print model a compile states, and the revision that measures one against it.

These are the rules behind "change the infill to 30 percent": the assumption is announced before the
compiler runs, a value no printer could hold is refused rather than turned into a mass, and a diff
whose solid bound moved is refused because that means something other than the print model changed.

Everything here drives the CLI with a stand-in compiler. The real compile needs the SO-ARM100 STEP
and several minutes of convex decomposition, and none of that is what these tests are about.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from robocad import twin_cli


def _passing_compile(**received):
    class _Check:
        status = "pass"

    class _Report:
        checks = [_Check()]

    return _Report()


def test_the_print_model_is_announced_before_the_compiler_runs(monkeypatch, tmp_path):
    """A mass is only as good as the assumptions under it, so the stream says them first."""
    seen, received = [], {}

    def compile_bundle(step, out, limits=None, limits_source=None, print_model=None, **kwargs):
        received.update(kwargs)
        received["print_model"] = print_model
        return _passing_compile()

    monkeypatch.setattr("ai_cad.compiler.compile.compile_bundle", compile_bundle)
    model = twin_cli.print_model_from_cli(0.30, 1.2)
    code = twin_cli.compile_bundle_cli(
        tmp_path / "s.step", None, tmp_path / "out", True, model,
        emit=lambda stage, pct, msg: seen.append((stage, pct, msg)),
    )
    assert code == 0
    assert seen[0][0] == twin_cli.TOOLING_STAGE
    # Before the compiler's own first stage (import, 10%), not squeezed in among them.
    assert seen[0][1] < 10
    assert "1.20 mm wall" in seen[0][2] and "0.30 infill" in seen[0][2]
    assert received["print_model"] is model


def test_the_tooling_stage_is_a_known_stage_not_an_unknown_one(monkeypatch, tmp_path):
    """The emitter refuses unknown stages; tooling lines must pass that check on their own merit."""
    assert twin_cli.TOOLING_STAGE not in twin_cli.STAGES
    assert twin_cli.TOOLING_STAGE in twin_cli.KNOWN_STAGES
    seen = []
    monkeypatch.setattr(
        "ai_cad.compiler.compile.compile_bundle",
        lambda *a, **k: _passing_compile(),
    )
    code = twin_cli.compile_bundle_cli(
        tmp_path / "s.step", None, tmp_path / "out", False,
        twin_cli.print_model_from_cli(0.30, None),
        emit=lambda stage, pct, msg: seen.append(stage),
    )
    assert code == 0
    assert seen == [twin_cli.TOOLING_STAGE]


@pytest.mark.parametrize(
    "infill, wall, message",
    [
        (0.05, None, "infill 0.05 is outside 0.1-1"),
        (1.4, None, "infill 1.4 is outside 0.1-1"),
        (0.30, 0.4, "wall 0.4 mm is outside 0.8-3"),
        (0.30, 4.0, "wall 4 mm is outside 0.8-3"),
    ],
)
def test_a_print_model_no_printer_could_hold_is_refused(infill, wall, message):
    """0 percent infill and a 0.1 mm wall are numbers, not parts; the mass they imply is a number."""
    with pytest.raises(ValueError, match=message):
        twin_cli.print_model_from_cli(infill, wall)


def test_no_print_model_flag_means_the_bundle_default_not_zero():
    """Silence is not an assumption: a caller who says nothing gets the stated 1.2 mm / 0.20."""
    assert twin_cli.print_model_from_cli(None, None) is None
    model = twin_cli.print_model_from_cli(0.30, None)
    assert model.wall_thickness_m == pytest.approx(0.0012)
    assert model.infill_fraction == pytest.approx(0.30)
    other = twin_cli.print_model_from_cli(None, 2.0)
    assert other.wall_thickness_m == pytest.approx(0.002)
    assert other.infill_fraction == pytest.approx(0.20)


def test_an_out_of_range_infill_exits_two_without_compiling(monkeypatch, tmp_path, capsys):
    called = []
    monkeypatch.setattr(
        "ai_cad.compiler.compile.compile_bundle",
        lambda *a, **k: called.append(1),
    )
    code = twin_cli.main([
        "compile", "--step", str(tmp_path / "s.step"), "--out", str(tmp_path / "out"),
        "--infill", "0.02",
    ])
    assert code == 2
    assert called == []
    assert "outside 0.1-1" in capsys.readouterr().err


def _bundle_document(mass: float, solid: float, infill: str, bought_in: int = 0) -> dict:
    return {
        "schema_version": "robocad.twin.bundle/1",
        "total_mass_kg": mass,
        "total_solid_mass_kg": solid,
        "print_model": infill,
        "bodies": [
            {"body_id": "base", "name": "Base", "mass_kg": mass, "solid_mass_kg": solid,
             "instances": 1, "parts": 2, "bought_in_parts": bought_in},
        ],
    }


def _before_bundle(tmp_path: Path) -> Path:
    directory = tmp_path / "before"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "bundle.json").write_text(
        json.dumps(_bundle_document(0.9017, 1.3320, "1.20 mm wall over 20% infill")),
        encoding="utf-8",
    )
    return directory


def _compile_writing(document: dict):
    """A stand-in for compile_bundle_cli that writes the bundle the diff will read."""

    def compile_bundle_cli(step, joints, out, json_progress, *args, **kwargs):
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "bundle.json").write_text(json.dumps(document), encoding="utf-8")
        return 0

    return compile_bundle_cli


def test_revise_prints_the_modelled_mass_and_writes_the_diff(monkeypatch, tmp_path, capsys):
    """The spoken line is the whole point: printed mass before, after, and the percent between."""
    before = _before_bundle(tmp_path)
    monkeypatch.setattr(
        twin_cli, "compile_bundle_cli",
        _compile_writing(_bundle_document(0.9555, 1.3320, "1.20 mm wall over 30% infill")),
    )
    code = twin_cli.revise_cli(
        tmp_path / "s.step", before, tmp_path / "rev", 0.30, None, None, False, False,
    )
    printed = capsys.readouterr().out
    assert code == 0
    assert "printed mass 0.9017 kg -> 0.9555 kg (+6.0%)" in printed
    assert "solid bound  1.3320 kg -> 1.3320 kg" in printed
    document = json.loads((tmp_path / "rev" / "diff.json").read_text(encoding="utf-8"))
    assert document["comparable"] is True
    assert (tmp_path / "rev" / "diff.md").read_text(encoding="utf-8").startswith("## Revision diff")


def test_revise_refuses_a_diff_where_the_solid_bound_moved(monkeypatch, tmp_path, capsys):
    """A print assumption cannot move the solid. If it did, the mass change is not the revision."""
    before = _before_bundle(tmp_path)
    monkeypatch.setattr(
        twin_cli, "compile_bundle_cli",
        _compile_writing(_bundle_document(0.6485, 1.0413, "1.20 mm wall over 30% infill")),
    )
    code = twin_cli.revise_cli(
        tmp_path / "s.step", before, tmp_path / "rev", 0.30, None, None, False, False,
    )
    printed = capsys.readouterr().out
    assert code == 3
    assert "NOT COMPARABLE" in printed
    assert "solid bound moved" in printed
    # The table is still written -- a refused diff is evidence -- and it carries the refusal itself.
    assert "solid bound moved" in (tmp_path / "rev" / "diff.md").read_text(encoding="utf-8")


def test_revise_refuses_an_out_of_range_print_model_before_compiling(monkeypatch, tmp_path, capsys):
    called = []
    monkeypatch.setattr(twin_cli, "compile_bundle_cli", lambda *a, **k: called.append(1))
    code = twin_cli.main([
        "revise", "--step", str(tmp_path / "s.step"), "--before", str(tmp_path),
        "--out", str(tmp_path / "rev"), "--infill", "1.5",
    ])
    assert code == 2
    assert called == []
    assert "outside 0.1-1" in capsys.readouterr().err
    assert not (tmp_path / "rev").exists()


def test_revise_with_json_prints_the_totals_a_caller_can_speak(monkeypatch, tmp_path, capsys):
    before = _before_bundle(tmp_path)
    monkeypatch.setattr(
        twin_cli, "compile_bundle_cli",
        _compile_writing(_bundle_document(0.9555, 1.3320, "1.20 mm wall over 30% infill")),
    )
    code = twin_cli.revise_cli(
        tmp_path / "s.step", before, tmp_path / "rev", 0.30, None, None, False, True,
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["schema_version"] == "robocad.twin.revise/1"
    assert payload["totals"]["printed_mass_before_kg"] == pytest.approx(0.9017)
    assert payload["totals"]["printed_mass_after_kg"] == pytest.approx(0.9555)
    assert payload["totals"]["printed_mass_change_percent"] == pytest.approx(5.966, abs=0.01)
    assert payload["print_model"] == {"wall_thickness_m": 0.0012, "infill_fraction": 0.30}
    assert payload["comparable"] is True


def test_the_help_names_revise_because_a_caller_scripts_against_the_help(capsys):
    """A verb that only exists in a changelog is a verb a subprocess caller cannot find."""
    with pytest.raises(SystemExit) as exitinfo:
        twin_cli.main(["--help"])
    assert exitinfo.value.code == 0
    printed = capsys.readouterr().out
    for command in ("summary", "page", "compile", "revise", "unpack"):
        assert command in printed


def _bought_in_bundle(tmp_path: Path, bought_in: int = 3) -> Path:
    directory = tmp_path / "frozen"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "bundle.json").write_text(
        json.dumps(_bundle_document(0.9017, 1.3320, "1.20 mm wall over 20% infill", bought_in)),
        encoding="utf-8",
    )
    return directory


def test_revise_refuses_in_milliseconds_a_frozen_bundle_whose_bought_in_parts_have_no_mass(
        monkeypatch, tmp_path, capsys):
    """The guard downstream catches this after 26 minutes of compiling. It can be caught here for free."""
    called = []
    monkeypatch.setattr(twin_cli, "compile_bundle_cli", lambda *a, **k: called.append(1))
    code = twin_cli.revise_cli(
        tmp_path / "s.step", _bought_in_bundle(tmp_path), tmp_path / "rev", 0.30, None, None,
        False, False,
    )
    assert code == 2
    assert called == []
    error = capsys.readouterr().err
    assert "3 bought-in part(s)" in error
    assert "--servo-mass-kg" in error and "--servo-source" in error
    assert not (tmp_path / "rev" / "bundle").exists()


def test_revise_refuses_a_servo_mass_without_its_source(monkeypatch, tmp_path, capsys):
    """A mass without a datasheet behind it is the claim this project does not make."""
    called = []
    monkeypatch.setattr(twin_cli, "compile_bundle_cli", lambda *a, **k: called.append(1))
    code = twin_cli.revise_cli(
        tmp_path / "s.step", _bought_in_bundle(tmp_path), tmp_path / "rev", 0.30, None, None,
        False, False, 0.055, "   ",
    )
    assert code == 2
    assert called == []
    assert "without its source" in capsys.readouterr().err


def test_revise_passes_the_mass_and_its_source_to_the_compiler(monkeypatch, tmp_path):
    """Both flags travel together, so the compile holds the assumption the frozen bundle made."""
    received = {}

    def compile_bundle_cli(step, joints, out, json_progress, print_model, mass, source, emit=None):
        received.update(mass=mass, source=source, print_model=print_model)
        return 2  # stop after the handoff; this test is about what the compiler receives

    monkeypatch.setattr(twin_cli, "compile_bundle_cli", compile_bundle_cli)
    code = twin_cli.revise_cli(
        tmp_path / "s.step", _bought_in_bundle(tmp_path), tmp_path / "rev", 0.30, None, None,
        False, False, 0.055, "Feetech STS3215: weight 55 +/- 1 g",
    )
    assert code == 2
    assert received["mass"] == pytest.approx(0.055)
    assert "55 +/- 1 g" in received["source"]
    assert received["print_model"].infill_fraction == pytest.approx(0.30)
