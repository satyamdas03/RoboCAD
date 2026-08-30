"""Tests for Phase 21 electronics part families."""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.heavy]

from ai_cad.feature_tree import Part
from ai_cad.part_families import get_family, instantiate_family, list_families


def test_pcb_family_in_registry():
    part = instantiate_family("pcb", "p1")
    assert isinstance(part, Part)
    assert part.domain == "electronics"
    assert len(part.sketches) == 2
    assert len(part.features) == 2


def test_enclosure_family_hollow_with_standoffs():
    part = instantiate_family("enclosure", "e1")
    assert part.domain == "electronics"
    sketch_ids = {s.id for s in part.sketches}
    assert "enc_outer" in sketch_ids
    assert "enc_inner" in sketch_ids
    assert "standoff_posts" in sketch_ids
    feature_ids = {f.id for f in part.features}
    assert "enc_body" in feature_ids
    assert "enc_hollow" in feature_ids
    assert "standoffs" in feature_ids


def test_connector_family():
    part = instantiate_family("connector", "c1")
    assert part.domain == "electronics"
    family = get_family("connector")
    assert len(family.interfaces) >= 1


def test_cable_channel_family():
    part = instantiate_family("cable_channel", "cc1")
    assert part.domain == "electronics"
    feature_ids = {f.id for f in part.features}
    assert "chan_body" in feature_ids
    assert "chan_cavity" in feature_ids


def test_fan_mount_family():
    part = instantiate_family("fan_mount", "f1")
    assert part.domain == "electronics"
    sketch_ids = {s.id for s in part.sketches}
    assert "fan_outer" in sketch_ids
    assert "fan_opening" in sketch_ids
    assert "fan_holes" in sketch_ids


def test_heat_spreader_family():
    part = instantiate_family("heat_spreader", "hs1")
    assert part.domain == "electronics"
    family = get_family("heat_spreader")
    iface = next(i for i in family.interfaces if i.id == "thermal_face")
    assert iface.mate_hint == "fixed"


def test_pcb_family_executes():
    from ai_cad.executor import execute_code
    from ai_cad.feature_tree import FeatureTree, Parameter
    from ai_cad.part_families import get_family
    from ai_cad.transpiler import transpile

    part = instantiate_family("pcb", "p1")
    params = [Parameter(name=p.name, value=p.value, unit=p.unit) for p in get_family("pcb").default_parameters]
    tree = FeatureTree(design_id="pcb_exec", prompt="pcb", parameters=params, parts=[part])
    code = transpile(tree)
    result = execute_code(code, timeout=60)
    assert result["success"], result.get("traceback", result.get("error"))
    assert result["stl_path"] is not None


def test_enclosure_family_executes():
    from ai_cad.executor import execute_code
    from ai_cad.feature_tree import FeatureTree, Parameter
    from ai_cad.part_families import get_family
    from ai_cad.transpiler import transpile

    part = instantiate_family("enclosure", "e1")
    params = [Parameter(name=p.name, value=p.value, unit=p.unit) for p in get_family("enclosure").default_parameters]
    tree = FeatureTree(design_id="enc_exec", prompt="enclosure", parameters=params, parts=[part])
    code = transpile(tree)
    result = execute_code(code, timeout=60)
    assert result["success"], result.get("traceback", result.get("error"))
    assert result["stl_path"] is not None


def test_list_electronics_families():
    families = list_families("electronics")
    names = {f.name for f in families}
    assert names >= {"pcb", "pcb_bracket", "enclosure", "connector", "cable_channel", "fan_mount", "heat_spreader"}
