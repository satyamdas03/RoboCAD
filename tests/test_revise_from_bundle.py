"""The demo's own phrase "change the infill to 30 percent" works with no STEP file and no kernel.

V6 of the final visual stretch. ``start_demo`` never sets ``ROBOCAD_STEP``, and the person opening
the zip has neither a STEP file nor a CAD kernel, so a revision that needs either is a phrase that
cannot work on stage. The bundle records, per body, what it weighs at its own print model and what
it would weigh cast solid, and the compiler's model (``printed = shell + f * interior``) turns those
two into any other infill.

The checks here are against an independent compile, not against the arithmetic's own output:

* the shipped bundle at 1.20 mm / 20 percent predicts the f=0.30 compile's total to within a gram,
  and that compile is a separate run of the kernel, committed under ``revision_f030``,
* the same phrase through the CLI, with ``--step`` absent, writes a bundle and a diff and reports
  the same figure,
* a wall change is answered by scaling the shell, and a body that goes solid at that wall says so
  instead of quietly reporting an infill that no longer exists.

Marked heavy: the arithmetic is cheap, but the bundle is 66 KB of real data and these tests exist to
pin the demo path, so they run with the heavy tier alongside the other package checks.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from ai_cad.compiler.print_from_bundle import BundlePrintError, printed_mass_at
from robocad.twin_cli import main as twin_main

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
BUNDLE = REPO_ROOT / "docs" / "twin" / "so101" / "bundle"
F030 = REPO_ROOT / "docs" / "twin" / "so101" / "revision_f030" / "bundle"

# The f=0.30 compile, written by a kernel run that had nothing to do with this arithmetic.
F030_CLAIM_KG = 0.9554530302470398
ONE_GRAM = 0.001


def _bundle(path: pathlib.Path) -> dict:
    return json.loads((path / "bundle.json").read_text(encoding="utf-8"))


def test_bundle_arithmetic_reproduces_an_independent_compile_to_a_gram() -> None:
    if not (BUNDLE / "bundle.json").exists() or not (F030 / "bundle.json").exists():
        pytest.skip("the so101 bundles are not in this checkout")
    before = _bundle(BUNDLE)
    after = _bundle(F030)
    got = printed_mass_at(before, infill=0.30)
    assert got["method"] == "body_linear"
    assert abs(got["total_kg"] - after["total_mass_kg"]) < ONE_GRAM
    # ...and the per-body split lands too, so a link row is not averaging another's error away.
    for body in before["bodies"]:
        expected = next(b for b in after["bodies"] if b["body_id"] == body["body_id"])
        assert got["by_body"][body["body_id"]] == pytest.approx(
            expected["printed_mass_kg"], abs=ONE_GRAM
        ), body["body_id"]


def test_asking_for_the_bundles_own_assumption_returns_its_own_mass() -> None:
    if not (BUNDLE / "bundle.json").exists():
        pytest.skip("the so101 bundle is not in this checkout")
    before = _bundle(BUNDLE)
    got = printed_mass_at(before)
    assert got["total_kg"] == pytest.approx(before["total_mass_kg"], rel=1e-12)


def test_a_wall_that_makes_a_body_solid_is_reported_not_hidden() -> None:
    if not (BUNDLE / "bundle.json").exists():
        pytest.skip("the so101 bundle is not in this checkout")
    before = _bundle(BUNDLE)
    got = printed_mass_at(before, wall_mm=2.0)
    assert got["warnings"], "a 2.0 mm wall saturates these parts and must say so"
    assert all("solid" in warning for warning in got["warnings"])
    # A saturated body weighs its solid mass at 20 percent infill, not less than it.
    for body in before["bodies"]:
        body_id = body["body_id"]
        if any(w.startswith(body_id + ":") for w in got["warnings"]):
            assert got["by_body"][body_id] >= body["solid_mass_kg"] * 0.999


def test_a_bundle_with_neither_rows_nor_a_print_model_is_refused() -> None:
    with pytest.raises(BundlePrintError, match="print model"):
        printed_mass_at({"bodies": [{"body_id": "x", "printed_mass_kg": 1.0,
                                     "solid_mass_kg": 2.0}]})


def test_the_cli_revises_a_bundle_with_no_step_file(tmp_path: pathlib.Path) -> None:
    if not (BUNDLE / "bundle.json").exists():
        pytest.skip("the so101 bundle is not in this checkout")
    out = tmp_path / "rev30"
    code = twin_main(["revise", "--before", str(BUNDLE), "--out", str(out),
                      "--infill", "0.30", "--json"])
    assert code == 0, "a bundle-only revision of a readable bundle must succeed"
    payload = json.loads((out / "diff.json").read_text(encoding="utf-8"))
    assert payload is not None
    derived = _bundle(out / "bundle")
    assert abs(derived["total_mass_kg"] - F030_CLAIM_KG) < ONE_GRAM
    assert derived["derivation"]["kernel"] is False
    assert derived["derivation"]["step"] is None
    assert derived["derivation"]["method"] == "body_linear"
    # The solid bound is untouched: this is a print assumption, not a geometry change.
    assert derived["total_solid_mass_kg"] == _bundle(BUNDLE)["total_solid_mass_kg"]
    assert (out / "diff.md").read_text(encoding="utf-8").startswith("## Revision diff")
