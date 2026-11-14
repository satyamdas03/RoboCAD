"""Pin the pose gate that ships inside the demo package.

The gate is the number that makes "the moving-arm comparison is not comparable" specific instead of
hand-wavy, and it lives in a payload baked by a script rather than in code with its own test. Two
harnesses agreed on it (8.6, 24.87, 56.65, 56.57, 70.69 mm) after one of them was wrong by 26 mm from
a missing translation, so the value is pinned here against the artifact that ships rather than against
a recomputation: if the bake changes, this fails and someone has to say why.

Reads the committed zip, never rebuilds it, so adding this test cannot change the digest a verifier
has already recorded.
"""

from __future__ import annotations

import json
import pathlib
import zipfile

import pytest

ZIP = pathlib.Path("docs/demo/so101_demo.zip")


@pytest.fixture(scope="module")
def torque_payload() -> dict:
    if not ZIP.exists():
        pytest.skip("no packaged demo zip to inspect")
    with zipfile.ZipFile(ZIP) as zf:
        names = zf.namelist()
        entry = next((n for n in names if n.endswith("torque.js")), None)
        assert entry is not None, f"package carries no torque.js: {names}"
        raw = zf.read(entry).decode("utf-8")
    body = raw.split("window.SO101_TORQUE = ", 1)[1].rstrip().rstrip(";")
    return json.loads(body)


def test_pose_gate_ships_with_the_panel_it_explains(torque_payload):
    assert "pose_gate_worst_mm" in torque_payload, (
        "the 'not comparable' verdict travels without the number that justifies it")
    worst = torque_payload["pose_gate_worst_mm"]
    assert isinstance(worst, (int, float)) and worst > 0


def test_pose_gate_is_the_worst_of_its_own_samples(torque_payload):
    samples = torque_payload.get("pose_gate_samples_mm") or []
    assert len(samples) == 5, f"expected five timesteps, got {samples}"
    assert abs(max(samples) - torque_payload["pose_gate_worst_mm"]) < 0.01


def test_pose_gate_matches_the_two_harness_agreement(torque_payload):
    """Both harnesses landed on 70.69 mm once the base translation was applied."""
    assert abs(torque_payload["pose_gate_worst_mm"] - 70.69) < 0.05


def test_dynamic_comparison_is_refused_when_the_poses_differ(torque_payload):
    assert torque_payload["dynamic_comparable"] is False
    assert torque_payload["pose_gate_worst_mm"] > 11.25, (
        "the anchor residual is 11.25 mm; a tip disagreement below that would mean the poses agree")
