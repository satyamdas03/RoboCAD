"""Tests for ai_cad.electronics run_electronics_analysis."""
from __future__ import annotations

from pathlib import Path

import pytest

from ai_cad.composer import compose_feature_tree
from ai_cad.decomposition import DecomposedPart, DecompositionResult
from ai_cad.electronics import run_electronics_analysis
from ai_cad.feature_tree import Parameter
from ai_cad.part_families import get_family


def _make_electronics_result() -> DecompositionResult:
    """Build a DecompositionResult for a Raspberry-Pi-style electronics stack."""
    parts: list[DecomposedPart] = []
    for family_name in ("pcb", "enclosure", "fan_mount", "connector"):
        family = get_family(family_name)
        params = [
            Parameter(name=p.name, value=p.value) for p in family.default_parameters
        ]
        parts.append(
            DecomposedPart(
                id=family_name,
                domain="electronics",
                family=family_name,
                name=family.name,
                sub_prompt=f"{family_name} for raspberry pi electronics enclosure",
                parameters=params,
            )
        )
    return DecompositionResult(
        prompt="raspberry pi electronics enclosure",
        primary_domain="electronics",
        multi_domain=False,
        parts=parts,
    )


def test_electronics_analysis_produces_pcb_summary(tmp_path: Path) -> None:
    result = _make_electronics_result()
    tree = compose_feature_tree(result)
    assert tree.assemblies, "Composer should create an electronics assembly"

    report = run_electronics_analysis(tree, tmp_path)
    dumped = report.model_dump()

    assert dumped["design_id"] == tree.design_id
    assert dumped["pcb"] is not None
    pcb = dumped["pcb"]
    assert pcb["board_area_mm2"] > 0
    assert pcb["board_thickness_mm"] > 0
    assert pcb["layer_count"] >= 2


def test_electronics_analysis_counts_components(tmp_path: Path) -> None:
    result = _make_electronics_result()
    tree = compose_feature_tree(result)
    report = run_electronics_analysis(tree, tmp_path)
    dumped = report.model_dump()

    assert dumped["component_count"] >= 4
    part_ids = {c["part_id"] for c in dumped["components"]}
    assert {"pcb", "enclosure", "fan_mount", "connector"}.issubset(part_ids)


def test_electronics_analysis_bounding_box_and_volume(tmp_path: Path) -> None:
    result = _make_electronics_result()
    tree = compose_feature_tree(result)
    report = run_electronics_analysis(tree, tmp_path)
    dumped = report.model_dump()

    bbox = dumped["bounding_box_mm"]
    assert bbox["max_x"] > bbox["min_x"]
    assert bbox["max_y"] > bbox["min_y"]
    assert bbox["max_z"] > bbox["min_z"]
    assert dumped["total_volume_mm3"] > 0
    assert dumped["estimated_cable_length_mm"] >= 0


def test_electronics_analysis_no_critical_warnings(tmp_path: Path) -> None:
    result = _make_electronics_result()
    tree = compose_feature_tree(result)
    report = run_electronics_analysis(tree, tmp_path)
    dumped = report.model_dump()

    assert all("missing" not in w.lower() for w in dumped["warnings"])
    assert all("failed" not in w.lower() for w in dumped["warnings"])
