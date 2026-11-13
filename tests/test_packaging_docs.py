"""Packaging and notice integrity.

Cheap tests that keep three things true at once: the package metadata parses, the console script
points at something real, and every declared dependency has a licence row in the third-party
notice. The notice is the one document that rots silently, because nothing imports it.
"""
from __future__ import annotations

import importlib
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
THIRD_PARTY = ROOT / "docs" / "THIRD_PARTY.md"


@pytest.fixture(scope="module")
def project() -> dict:
    with PYPROJECT.open("rb") as fh:
        return tomllib.load(fh)


def test_metadata_is_complete(project):
    meta = project["project"]
    assert meta["name"] == "robocad"
    assert meta["requires-python"].startswith(">=")
    assert meta["dependencies"], "a package with no dependencies is a claim, not a package"
    assert Path(ROOT / meta["license"]["file"]).is_file(), "licence file named in pyproject is missing"


def test_console_script_target_imports(project):
    scripts = project["project"]["scripts"]
    assert "robocad" in scripts
    module_path, _, attr = scripts["robocad"].partition(":")
    module = importlib.import_module(module_path)
    assert callable(getattr(module, attr))


def test_every_dependency_has_a_notice_row(project):
    text = THIRD_PARTY.read_text(encoding="utf-8").lower()
    missing = []
    for spec in project["project"]["dependencies"]:
        name = spec.split(">")[0].split("<")[0].split("=")[0].split("[")[0].strip()
        if name.lower() not in text:
            missing.append(name)
    assert not missing, f"no licence row in docs/THIRD_PARTY.md for: {missing}"


def test_proprietary_package_is_excluded_from_the_build(project):
    """A wheel must never carry ai_cad/twin under Apache-2.0 metadata.

    A licence notice inside a directory is documentation, not a distribution control. The real
    control is the package exclusion, so the test asserts the exclusion resolves to no packages
    rather than trusting the comment that sits next to it.
    """
    from setuptools import find_packages

    find = project["tool"]["setuptools"]["packages"]["find"]
    found = find_packages(
        where=str(ROOT),
        include=find.get("include", ["*"]),
        exclude=find.get("exclude", []),
    )
    assert not [p for p in found if p == "ai_cad.twin" or p.startswith("ai_cad.twin.")]


def test_proprietary_notice_is_not_the_apache_text():
    notice = (ROOT / "ai_cad" / "twin" / "LICENSE").read_text(encoding="utf-8")
    assert "proprietary" in notice.lower()
    assert "Apache License" not in notice


def test_third_party_states_the_licence_split():
    text = THIRD_PARTY.read_text(encoding="utf-8")
    assert "Apache-2.0" in text
    assert "ai_cad/twin" in text, "the proprietary engine must be named where licences are listed"


def test_labs_default_documented():
    decisions = (ROOT / "docs" / "DECISIONS.md").read_text(encoding="utf-8")
    assert "ROBOCAD_LABS" in decisions
    assert "default off" in decisions.lower() or "`0` default" in decisions.lower()
