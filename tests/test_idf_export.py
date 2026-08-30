"""Tests for ai_cad.electronics export_idf."""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.heavy]

from ai_cad.composer import compose_feature_tree
from ai_cad.decomposition import DecomposedPart, DecompositionResult
from ai_cad.electronics import export_idf
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


def _parse_simple_idf(path: Path) -> dict[str, list[str]]:
    """Very small IDF parser for test validation."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("."):
            current = stripped
            sections.setdefault(current, [])
        elif current:
            sections[current].append(stripped)
    return sections


def test_idf_export_creates_three_files(tmp_path: Path) -> None:
    result = _make_electronics_result()
    tree = compose_feature_tree(result)

    paths = export_idf(tree, tmp_path, "test_elec")
    assert set(paths.keys()) == {"emn", "emp", "step"}
    for p in paths.values():
        assert p.exists()
        assert p.stat().st_size > 0


def test_idf_emn_structure(tmp_path: Path) -> None:
    result = _make_electronics_result()
    tree = compose_feature_tree(result)
    paths = export_idf(tree, tmp_path, "test_emn")

    emn = _parse_simple_idf(paths["emn"])
    assert ".BOARD_OUTLINE EMCIDF" in emn
    assert ".PLACEMENT" in emn
    assert ".END_BOARD_OUTLINE" in emn

    header = emn[".BOARD_OUTLINE EMCIDF"]
    assert header[0].upper() in ("MM", "THOU")
    assert len(header) >= 2


def test_idf_emp_contains_packages(tmp_path: Path) -> None:
    result = _make_electronics_result()
    tree = compose_feature_tree(result)
    paths = export_idf(tree, tmp_path, "test_emp")

    emp = _parse_simple_idf(paths["emp"])
    assert ".ELECTRICAL_MECHANICAL_DATA" in emp
    pkg_sections = [k for k in emp if k.startswith(".PACKAGE")]
    assert len(pkg_sections) >= 3


def test_idf_step_placeholder_valid(tmp_path: Path) -> None:
    result = _make_electronics_result()
    tree = compose_feature_tree(result)
    paths = export_idf(tree, tmp_path, "test_step")

    text = paths["step"].read_text(encoding="utf-8")
    assert text.startswith("ISO-10303-21;")
    assert "END-ISO-10303-21;" in text
