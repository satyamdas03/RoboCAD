"""Integration tests for aero/thermal part families (Phase 20)."""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.heavy]

from ai_cad.cfd import export_cfd_mesh
from ai_cad.feature_tree import FeatureTree
from ai_cad.part_families import get_family, instantiate_family, list_families
from ai_cad.transpiler import transpile


AERO_FAMILIES = ["airfoil", "wing", "propeller_blade"]
THERMAL_FAMILIES = ["heat_sink"]


@pytest.mark.parametrize("family_name", AERO_FAMILIES)
def test_aero_family_runs_to_stl(family_name: str, tmp_path: Path):
    family = get_family(family_name)
    part = instantiate_family(family_name, f"{family_name}_1")
    tree = FeatureTree(
        design_id="test",
        prompt="test",
        parts=[part],
        parameters=family.default_parameters,
    )
    code = transpile(tree)
    ns: dict = {}
    exec(code, ns)
    shape = ns["result"]
    result = export_cfd_mesh(shape, tmp_path / f"{family_name}.stl", solver="su2_stub")
    assert result.mesh_path.exists()
    assert result.mesh_path.stat().st_size > 0


@pytest.mark.parametrize("family_name", THERMAL_FAMILIES)
def test_thermal_family_runs_to_stl(family_name: str, tmp_path: Path):
    family = get_family(family_name)
    part = instantiate_family(family_name, f"{family_name}_1")
    tree = FeatureTree(
        design_id="test",
        prompt="test",
        parts=[part],
        parameters=family.default_parameters,
    )
    code = transpile(tree)
    ns: dict = {}
    exec(code, ns)
    shape = ns["result"]
    result = export_cfd_mesh(shape, tmp_path / f"{family_name}.stl", solver="su2_stub")
    assert result.mesh_path.exists()
    assert result.mesh_path.stat().st_size > 0


def test_domain_family_coverage():
    families = list_families()
    aero = [f.name for f in families if f.domain == "aero"]
    thermal = [f.name for f in families if f.domain == "thermal"]
    assert set(AERO_FAMILIES).issubset(set(aero))
    assert set(THERMAL_FAMILIES).issubset(set(thermal))
