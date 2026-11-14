"""The page renders a build-time reduction of the bundle's meshes, and the package has to say so.

The decision this file pins (R3): the bundle carries full-resolution visual meshes and stays the
source of truth; the packager decimates for the page, records the ratio in the zip's README, and
never writes a decimated mesh back into the bundle. The failure this guards against is a package
that says "renders the bundle's meshes" and quietly means one seventh of them.

The ratio is computed from the two files that hold the two figures, never quoted, and an absent
budget is reported as absent rather than guessed from the payload's largest mesh.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_PACKAGER = Path(__file__).resolve().parents[1] / "teardown_export" / "package_demo.py"


def _load_packager():
    spec = importlib.util.spec_from_file_location("robocad_package_demo", _PACKAGER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


package_demo = _load_packager()


def _fixture(tmp_path: Path, counts=(300, 200), budget=500, bundle_triangles=2000):
    repo = tmp_path / "repo"
    out = tmp_path / "out"
    (repo / "docs" / "twin" / "so101" / "bundle").mkdir(parents=True)
    out.mkdir()
    payload = [{"id": i, "name": f"m{i}", "count": c} for i, c in enumerate(counts)]
    (out / "meshes.js").write_text(
        "window.SO101_MESHES = " + json.dumps(payload) + ";\n", encoding="utf-8"
    )
    meta = {"source": "model.mjcf", "synthetic": False}
    if budget is not None:
        meta["triangle_budget"] = budget
    (out / "trajectory.js").write_text(
        "window.SO101_META = " + json.dumps(meta) + ";\n", encoding="utf-8"
    )
    (repo / "docs" / "twin" / "so101" / "bundle" / "report.json").write_text(
        json.dumps({"totals": {"visual_triangles": bundle_triangles}}), encoding="utf-8"
    )
    return repo, out


def test_the_ratio_is_computed_from_the_payload_and_the_bundle(tmp_path):
    repo, out = _fixture(tmp_path, counts=(300, 200), bundle_triangles=2000)
    text = package_demo.mesh_resolution(repo, out)
    assert "500 triangles" in text
    assert "2,000 triangles" in text
    assert "25.0%" in text


def test_the_budget_is_named_when_the_bake_recorded_one(tmp_path):
    repo, out = _fixture(tmp_path, counts=(500, 500), budget=500)
    text = package_demo.mesh_resolution(repo, out)
    assert "500-triangle budget" in text
    assert "largest mesh in the payload carries 500" in text


def test_an_absent_budget_is_stated_as_absent_rather_than_guessed(tmp_path):
    repo, out = _fixture(tmp_path, counts=(500, 500), budget=None)
    text = package_demo.mesh_resolution(repo, out)
    assert "did not record its triangle budget" in text
    assert "budget" not in text.split("did not record")[0]


def test_a_missing_payload_states_the_gap_instead_of_printing_a_ratio(tmp_path):
    repo, out = _fixture(tmp_path)
    (out / "meshes.js").unlink()
    text = package_demo.mesh_resolution(repo, out)
    assert "states no ratio" in text
    assert "%" not in text


def test_the_bundle_keeps_its_full_resolution_figures(tmp_path):
    """The packager must not rewrite the bundle's own triangle count with the page's."""
    repo, out = _fixture(tmp_path, counts=(10,), bundle_triangles=620093)
    text = package_demo.mesh_resolution(repo, out)
    assert "620,093 triangles" in text
    report = json.loads((repo / "docs" / "twin" / "so101" / "bundle" / "report.json").read_text())
    assert report["totals"]["visual_triangles"] == 620093


def test_the_bake_records_its_budget_in_the_meta():
    """bake.py has to put the budget in the payload, or the package can only guess it."""
    source = (_PACKAGER.parent / "bake.py").read_text(encoding="utf-8")
    assert '"triangle_budget": int(args.triangles)' in source


@pytest.mark.parametrize("counts", [(500, 250, 125)])
def test_the_section_never_claims_the_page_is_the_bundle(tmp_path, counts):
    repo, out = _fixture(tmp_path, counts=counts, bundle_triangles=1000)
    text = package_demo.mesh_resolution(repo, out)
    assert "source of truth" in text
    assert "No decimated mesh is ever written back into the bundle" in text
