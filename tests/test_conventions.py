"""The zero-pose convention has to travel with the bundle, not with the reader's source.

The defect this file exists to prevent is quiet: a comparison that reads the offsets out of its own
constants keeps producing numbers after the bundle is recompiled with a different convention, and the
numbers are wrong with nothing to show for it. So the strongest test here is a mutation. It reads the
convention out of a bundle, edits the bundle's own manifest, and requires the second read to return
the edited values. A reader that answered from module constants would pass every round-trip test in
this file and fail that one.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from ai_cad.compiler import conventions as cv
from ai_cad.compiler.conventions import NONE, SO101, Conventions, from_bundle, write_manifest
from ai_cad.compiler.twin_bundle import BodyModel, BundleModel, write_mjcf

REPO = Path(__file__).resolve().parents[1]
PUBLISHED_BUNDLE = REPO / "docs" / "twin" / "so101" / "bundle"


def _manifest(**overrides) -> dict:
    data = SO101.to_manifest()
    data.update(overrides)
    return data


# ------------------------------------------------------------------------------------------------
# the module's own contract
# ------------------------------------------------------------------------------------------------
def test_the_measured_convention_round_trips_through_the_manifest():
    back = Conventions.from_manifest(SO101.to_manifest())
    assert back == SO101


def test_the_offsets_are_the_measured_ones_and_not_a_rounded_copy():
    # Named here so a silent edit to the constant is a test failure rather than a new number.
    assert SO101.zero_pose_offsets_deg == {
        "joint_1": -88.17,
        "joint_2": 90.29,
        "joint_3": -90.31,
        "joint_4": -0.15,
        "joint_5": 0.00,
    }
    assert SO101.base_translation_mm == (38.74, 6.64, -2.86)
    assert SO101.residual_mm == {"median": 2.50, "p90": 5.95, "max": 11.25}
    assert SO101.measured is True


def test_a_measured_convention_without_its_residual_is_refused():
    with pytest.raises(ValueError, match="residual"):
        Conventions(
            zero_pose_offsets_deg={"joint_1": 1.0},
            residual_mm={"median": 2.5},
            measured=True,
            source="somewhere",
        )


def test_a_measured_convention_without_a_source_is_refused():
    with pytest.raises(ValueError, match="source"):
        Conventions(
            zero_pose_offsets_deg={"joint_1": 1.0},
            residual_mm={"median": 2.5, "p90": 3.0, "max": 4.0},
            measured=True,
        )


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("schema_version", "robocad.twin.conventions/0", "schema_version"),
        ("zero_pose_offsets_deg", {"joint_1": True}, "expected a number"),
        ("zero_pose_offsets_deg", {"joint_1": float("nan")}, "not finite"),
        ("base_translation_mm", [1.0, 2.0], "three numbers"),
        ("base_translation_mm", [1.0, 2.0, float("inf")], "not finite"),
        ("residual_mm", {"median": "2.5"}, "expected a number"),
        ("measured", "yes", "true or false"),
        ("source", 7, "must be a string"),
    ],
)
def test_a_malformed_convention_block_raises_instead_of_defaulting(field, value, message):
    with pytest.raises(ValueError, match=message):
        Conventions.from_manifest(_manifest(**{field: value}))


def test_a_conventions_block_that_is_not_an_object_raises():
    with pytest.raises(ValueError, match="must be an object"):
        Conventions.from_manifest([])


# ------------------------------------------------------------------------------------------------
# mapping a joint state
# ------------------------------------------------------------------------------------------------
def test_the_offsets_are_added_in_radians_and_velocity_passes_through():
    qpos = np.zeros(6)
    qvel = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
    qacc = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    mapped, v, a = SO101.apply_to_compiled(qpos, qvel, qacc)
    expected = np.radians([-88.17, 90.29, -90.31, -0.15, 0.00, 0.0])
    assert np.allclose(mapped, expected, atol=1e-12)
    # Constant offsets do not change a derivative, and the caller must not have to infer that.
    assert np.array_equal(v, qvel)
    assert np.array_equal(a, qacc)


def test_a_vector_for_another_chain_is_refused_rather_than_partly_offset():
    with pytest.raises(ValueError, match="not for the same chain"):
        SO101.apply_to_compiled(np.zeros(5))


def test_an_unmeasured_convention_maps_qpos_unchanged():
    # Identity because nothing is known, which is a different claim from "the poses agree".
    qpos = np.array([0.3, -0.2, 1.1, 0.0, 0.05, 0.0])
    mapped, v, a = NONE.apply_to_compiled(qpos)
    assert np.array_equal(mapped, qpos)
    assert v is None and a is None


def test_a_qvel_of_the_wrong_length_is_refused():
    with pytest.raises(ValueError, match="qvel has shape"):
        SO101.apply_to_compiled(np.zeros(6), np.zeros(5))


# ------------------------------------------------------------------------------------------------
# the bundle side: write it, then read it back from the file
# ------------------------------------------------------------------------------------------------
def test_the_reader_takes_the_offsets_from_the_bundle_not_from_the_module(tmp_path):
    write_manifest(tmp_path, "so101", SO101)
    assert from_bundle(tmp_path) == SO101

    # Mutate the bundle's own copy. This is the whole test: a reader that answered from SO101 would
    # still return the module's numbers here.
    path = tmp_path / "manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["conventions"]["zero_pose_offsets_deg"]["joint_2"] = 12.5
    data["conventions"]["base_translation_mm"] = [1.0, 2.0, 3.0]
    data["conventions"]["residual_mm"] = {"median": 9.0, "p90": 9.5, "max": 10.0}
    path.write_text(json.dumps(data), encoding="utf-8")

    changed = from_bundle(tmp_path)
    assert changed.joint_offset_deg("joint_2") == 12.5
    assert changed.joint_offset_deg("joint_2") != SO101.joint_offset_deg("joint_2")
    assert changed.base_translation_mm == (1.0, 2.0, 3.0)
    assert changed.residual_mm["median"] == 9.0


def test_the_bundle_reader_refuses_a_bundle_with_no_manifest(tmp_path):
    with pytest.raises(FileNotFoundError, match="manifest.json"):
        from_bundle(tmp_path)


def test_the_bundle_reader_refuses_a_manifest_with_no_conventions_block(tmp_path):
    (tmp_path / "manifest.json").write_text(
        json.dumps({"schema_version": cv.MANIFEST_SCHEMA, "name": "so101"}), encoding="utf-8"
    )
    with pytest.raises(KeyError, match="conventions"):
        from_bundle(tmp_path)


# ------------------------------------------------------------------------------------------------
# the model file carries the same convention, rendered from the same object
# ------------------------------------------------------------------------------------------------
def _one_body_model() -> BundleModel:
    body = BodyModel(
        body_id="base",
        name="base",
        mass_kg=0.5,
        com_m=(0.0, 0.0, 0.0),
        inertia_6=(1e-5, 1e-5, 1e-5, 0.0, 0.0, 0.0),
    )
    return BundleModel(name="fixture", bodies=[body], total_mass_kg=0.5, total_solid_mass_kg=0.5)


def test_the_mjcf_comment_states_the_offsets_it_was_handed(tmp_path):
    path = write_mjcf(_one_body_model(), tmp_path / "model.mjcf", conventions=SO101)
    text = path.read_text(encoding="utf-8")
    comment = SO101.mjcf_comment()
    assert comment in text
    for joint, value in SO101.zero_pose_offsets_deg.items():
        assert f"{joint} {value:+.2f} deg" in text
    assert "(38.74, 6.64, -2.86) mm at identity rotation" in text
    # Before the compiler directive: a reader should meet the convention before the model body.
    assert text.index("conventions:") < text.index("<compiler")


def test_the_mjcf_comment_says_none_measured_rather_than_printing_zeros(tmp_path):
    path = write_mjcf(_one_body_model(), tmp_path / "model.mjcf", conventions=NONE)
    text = path.read_text(encoding="utf-8")
    assert "none measured" in text
    assert "0.00 deg" not in text.split("<body")[0]


def test_no_conventions_argument_writes_no_comment(tmp_path):
    path = write_mjcf(_one_body_model(), tmp_path / "model.mjcf")
    assert "conventions:" not in path.read_text(encoding="utf-8")


# ------------------------------------------------------------------------------------------------
# the published bundle, if it is checked out: the two copies must be the same convention
# ------------------------------------------------------------------------------------------------
@pytest.mark.skipif(
    not (PUBLISHED_BUNDLE / "manifest.json").exists(),
    reason="the published bundle is not checked out here",
)
def test_the_published_bundle_states_the_same_convention_in_both_files():
    stated = from_bundle(PUBLISHED_BUNDLE)
    assert stated.measured is True
    mjcf = (PUBLISHED_BUNDLE / "model.mjcf").read_text(encoding="utf-8")
    assert stated.mjcf_comment() in mjcf
    for joint, value in stated.zero_pose_offsets_deg.items():
        assert f"{joint} {value:+.2f} deg" in mjcf
    assert not math.isnan(stated.residual_mm["median"])
