"""The committed revision diff has to keep saying what it says.

The artifact at ``docs/twin/so101/revision_f030/diff.json`` is quoted in the demo README, the final
status and the packaged page. If someone recompiles at a different infill and overwrites it, or edits
the totals by hand, every one of those documents silently becomes wrong. These assertions are the
cheap guard: they check the file's own arithmetic and the four sanity claims the sprint required, and
they need nothing but the file.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DIFF = REPO / "docs" / "twin" / "so101" / "revision_f030" / "diff.json"


def _diff() -> dict:
    return json.loads(DIFF.read_text(encoding="utf-8"))


def test_no_links_added_or_removed():
    data = _diff()
    assert data["added"] == []
    assert data["removed"] == []
    assert data["comparable"] is True
    assert data["sanity_failures"] == []


def test_every_printed_link_got_heavier():
    for row in _diff()["links"]:
        if row["printed_parts"]:
            assert row["mass_after_kg"] > row["mass_before_kg"], row["link_id"]
            assert row["mass_delta_kg"] > 0.0, row["link_id"]
            assert row["mass_delta_percent"] > 0.0, row["link_id"]


def test_servos_unchanged():
    unchanged = _diff()["unchanged"]
    assert unchanged["actuators_identical"] is True
    assert unchanged["joints_identical"] is True
    assert unchanged["actuators_before"] == unchanged["actuators_after"] == 6


def test_totals_are_the_sum_of_the_links():
    data = _diff()
    totals = data["totals"]
    assert abs(sum(r["mass_before_kg"] for r in data["links"]) - totals["mass_before_kg"]) < 1e-12
    assert abs(sum(r["mass_after_kg"] for r in data["links"]) - totals["mass_after_kg"]) < 1e-12


def test_reported_percentages_recompute():
    data = _diff()
    for row in data["links"]:
        expected = (row["mass_after_kg"] / row["mass_before_kg"] - 1.0) * 100.0
        assert abs(expected - row["mass_delta_percent"]) < 1e-9, row["link_id"]
        for i in range(3):
            inertia = (row["inertia_after_6"][i] / row["inertia_before_6"][i] - 1.0) * 100.0
            assert abs(inertia - row["inertia_diagonal_delta_percent"][i]) < 1e-9, row["link_id"]


def test_solid_bound_did_not_move():
    totals = _diff()["totals"]
    assert totals["solid_mass_before_kg"] == totals["solid_mass_after_kg"]


def test_effort_check_moves_with_the_mass():
    effort = _diff()["effort"]
    assert effort["before"]["joint"] == effort["after"]["joint"] == "joint_2"
    assert effort["after"]["demand_nm"] > effort["before"]["demand_nm"]
    assert effort["after"]["percent"] >= effort["before"]["percent"]
