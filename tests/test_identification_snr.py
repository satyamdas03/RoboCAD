"""One signal-to-noise number, one definition, everywhere it is quoted.

The page, the scenario table and `docs/twin/so101/identifiability.md` all print the ratio of the
friction signal to the actuator torque error of one encoder count. They disagreed (0.04 against
0.10) because the generator divided by the peak speed of one particular log while the document
divided by a stated reference speed. These tests pin the definition: the note computes the ratio at
`REFERENCE_SPEED_RAD_S`, names that speed in the sentence, and agrees with the published scenario
table.
"""

from __future__ import annotations

import json
import math
import pathlib
import re

from ai_cad.twin import identification


REPO = pathlib.Path(__file__).resolve().parent.parent
SCENARIOS = REPO / "docs" / "demo" / "twin" / "identifiability_scenarios.json"

# The published SO-101 figures the document's arithmetic uses.
KP = 998.0
QUANT = 2.0 * math.pi / 4096.0


def note(**over) -> str:
    kw = {"kp": KP, "quant": QUANT, "damping": 0.08, "log_hz": 62, "cond": 12.0}
    kw.update(over)
    return identification.rung3_note(**kw)


def ratios(text: str) -> list[float]:
    """Every number the note attributes to a signal to noise ratio."""
    return [float(m) for m in re.findall(r"signal to noise ratio of ([0-9.]+)", text)]


class TestOneDefinition:
    def test_note_carries_exactly_one_ratio(self):
        assert len(ratios(note())) == 1

    def test_ratio_is_signal_over_one_count_at_the_reference_speed(self):
        expected = (0.08 * identification.REFERENCE_SPEED_RAD_S) / (KP * QUANT)
        assert ratios(note())[0] == round(expected, 2)

    def test_note_names_the_speed_it_divided_by(self):
        text = note()
        assert f"{identification.REFERENCE_SPEED_RAD_S:.1f} rad/s" in text

    def test_ratio_does_not_follow_the_log_peak_speed(self):
        # The bug: the ratio was taken from one log's peak speed, so the same physics printed a
        # different number depending on which log was described. The definition must not move when
        # the log rate or the excitation changes.
        assert ratios(note(log_hz=62)) == ratios(note(log_hz=250))


class TestAgreesWithPublishedTable:
    def test_matches_status_quo_scenario(self):
        rows = json.loads(SCENARIOS.read_text(encoding="utf-8"))
        if isinstance(rows, dict):
            rows = rows.get("scenarios", rows.get("scenarios_snr", []))
        status_quo = next(r for r in rows if "status quo" in r["scenario"])
        assert abs(ratios(note())[0] - status_quo["snr"]) <= 0.005

    def test_reference_speed_is_the_documented_one(self):
        doc = (REPO / "docs" / "twin" / "so101" / "identifiability.md").read_text(encoding="utf-8")
        assert f"{identification.REFERENCE_SPEED_RAD_S:.1f} rad/s" in doc
