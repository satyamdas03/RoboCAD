"""A bundle that records per-part volume and area can weigh itself at any infill, no kernel needed.

V6 of the final visual stretch: the playground has to work offline, with no STEP file and no CAD
kernel, because the person opening the zip has neither. The kernel numbers that a shell-and-infill
model needs are a solid volume and a surface area per part, so the compile records them and this
module does the arithmetic afterwards.

The tests pin three things:

1. the arithmetic is the same ``PrintModel`` the compiler used, evaluated over the recorded rows,
2. a bought-in part does not move when the slider does, and
3. a bundle without per-part rows reports "unknown" rather than a number that looks computed.

Marked heavy: none of it opens a browser or a kernel, so it runs in the default tier.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from ai_cad.compiler.print_from_bundle import (
    BundlePrintError,
    mass_at_infill,
    part_mass_kg,
    printed_mass_from_bundle,
    records_per_part,
)
from ai_cad.compiler.print_model import PrintModel

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
RECORD_BUNDLE = REPO_ROOT / "docs" / "twin" / "so101" / "bundle" / "bundle.json"

# A 100 x 20 x 3 mm printed plate of PLA, the same numbers a kernel would return for it.
PLATE_VOLUME = 0.1 * 0.02 * 0.003
PLATE_AREA = 2 * (0.1 * 0.02 + 0.1 * 0.003 + 0.02 * 0.003)
PLA = 1240.0


def _synthetic_bundle() -> dict:
    return {
        "bodies": [
            {
                "body_id": "link_a",
                "part_properties": [
                    {
                        "part_id": "plate",
                        "instances": 3,
                        "volume_m3": PLATE_VOLUME,
                        "surface_area_m2": PLATE_AREA,
                        "density_kg_m3": PLA,
                        "printed": True,
                        "bought_in": False,
                    },
                    {
                        "part_id": "servo",
                        "instances": 2,
                        "volume_m3": 1.5e-5,
                        "surface_area_m2": 0.004,
                        "density_kg_m3": 1500.0,
                        "printed": False,
                        "bought_in": True,
                    },
                ],
            },
            {
                "body_id": "link_b",
                "part_properties": [
                    {
                        "part_id": "bracket",
                        "instances": 1,
                        "volume_m3": 2.0e-6,
                        "surface_area_m2": 0.001,
                        "density_kg_m3": PLATE_AREA * 0 + 1240.0,
                        "printed": True,
                        "bought_in": False,
                    }
                ],
            },
        ]
    }


def test_recompute_matches_the_print_model_by_hand() -> None:
    """The bundle's rows, fed through PrintModel directly, are the same number."""
    model = PrintModel(wall_thickness_m=0.0012, infill_fraction=0.30)
    got = printed_mass_from_bundle(_synthetic_bundle(), model)
    plate = 3 * PLA * model.effective_volume_m3(PLATE_VOLUME, PLATE_AREA)
    servo = 2 * 1.5e-5 * 1500.0
    bracket = 1 * 1240.0 * model.effective_volume_m3(2.0e-6, 0.001)
    assert got["total_kg"] == pytest.approx(plate + servo + bracket, rel=1e-12)
    assert got["by_body"]["link_a"] == pytest.approx(plate + servo, rel=1e-12)
    assert got["parts_modelled"] == 2
    assert got["parts_bought_in"] == 1


def test_a_bought_in_part_does_not_move_with_the_slider() -> None:
    """The servo is a datasheet mass: no infill fraction may thin it."""
    servo = {"part_id": "servo", "instances": 2, "volume_m3": 1.5e-5,
             "surface_area_m2": 0.004, "density_kg_m3": 1500.0,
             "printed": False, "bought_in": True}
    masses = [part_mass_kg(servo, PrintModel(infill_fraction=f)) for f in (0.0, 0.2, 0.3, 1.0)]
    assert len(set(round(m, 15) for m in masses)) == 1
    assert masses[0] == pytest.approx(2 * 1.5e-5 * 1500.0)


def test_infill_is_linear_between_two_compiled_states() -> None:
    """Two compiled masses at two infills determine every other infill exactly, in this model."""
    bundle = _synthetic_bundle()
    m20 = printed_mass_from_bundle(bundle, PrintModel(infill_fraction=0.20))["total_kg"]
    m30 = printed_mass_from_bundle(bundle, PrintModel(infill_fraction=0.30))["total_kg"]
    for f in (0.15, 0.25, 0.40, 0.75):
        claimed = m20 + (f - 0.20) * (m30 - m20) / 0.10
        assert mass_at_infill(bundle, f)["total_kg"] == pytest.approx(claimed, rel=1e-12)


def test_a_printed_part_without_an_area_is_refused_not_guessed() -> None:
    part = {"part_id": "plate", "instances": 1, "volume_m3": PLATE_VOLUME,
            "surface_area_m2": None, "density_kg_m3": PLA,
            "printed": True, "bought_in": False}
    with pytest.raises(BundlePrintError, match="surface_area_m2"):
        part_mass_kg(part, PrintModel())


def test_the_bundle_of_record_has_no_per_part_rows_and_says_so() -> None:
    """The shipped bundle predates this row. It must report unknown, not a computed-looking zero."""
    if not RECORD_BUNDLE.exists():
        pytest.skip("the demo bundle of record is not in this checkout")
    bundle = json.loads(RECORD_BUNDLE.read_text(encoding="utf-8"))
    assert records_per_part(bundle["bodies"][0].get("part_properties")) is False
    got = printed_mass_from_bundle(bundle, PrintModel(infill_fraction=0.30))
    assert all(value is None for value in got["by_body"].values())
    assert got["total_kg"] == 0.0
