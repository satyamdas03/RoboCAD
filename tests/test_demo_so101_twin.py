"""Tests for the SO-101 demo's limit provenance.

The demo takes travel limits from a third-party published model and writes a source string beside
them. That string is the only thing a reader has to check the numbers against, so it must not claim
a revision for a file whose bytes were never checked.
"""
from __future__ import annotations

import hashlib
import importlib.util
import textwrap
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "demo_so101_twin.py"

URDF = textwrap.dedent(
    """\
    <robot name="toy">
      <link name="base_link"><inertial><mass value="0.2"/></inertial></link>
      <link name="arm_link"><inertial><mass value="0.1"/></inertial></link>
      <joint name="shoulder_pan" type="revolute">
        <parent link="base_link"/><child link="arm_link"/>
        <origin xyz="0 0 0.1" rpy="0 0 0"/>
        <axis xyz="0 0 1"/>
        <limit lower="-1.5" upper="1.5" effort="3" velocity="2"/>
      </joint>
    </robot>
    """
)


@pytest.fixture()
def demo():
    spec = importlib.util.spec_from_file_location("demo_so101_twin", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def urdf(tmp_path):
    path = tmp_path / "so101_new_calib.urdf"
    path.write_text(URDF, encoding="utf-8")
    return path


class TestLimitProvenance:
    def test_the_limits_are_read_and_the_source_says_they_are_not_from_the_cad(self, demo, urdf):
        limits, source = demo.limits_from_official(urdf)
        assert limits["joint_1"]["lower"] == pytest.approx(-1.5)
        assert "Not derived from the CAD" in source

    def test_an_unpinned_file_does_not_claim_the_pinned_revision(self, demo, urdf):
        # The digest is what makes the revision checkable. A run handed a different file must say so
        # rather than paste the revision into its report and call it verified.
        _, source = demo.limits_from_official(urdf)
        assert "at revision" not in source
        assert "no pinned revision" in source
        recorded = hashlib.sha256(urdf.read_bytes()).hexdigest()
        assert recorded in source

    def test_the_pinned_revision_is_claimed_only_for_the_pinned_digest(self, demo, urdf, monkeypatch):
        digest = hashlib.sha256(urdf.read_bytes()).hexdigest()
        monkeypatch.setattr(demo, "PINNED_LIMITS_SHA256", digest)
        monkeypatch.setattr(demo, "PINNED_LIMITS_REVISION", "deadbeef")
        _, source = demo.limits_from_official(urdf)
        assert "at revision deadbeef" in source
        assert digest in source
