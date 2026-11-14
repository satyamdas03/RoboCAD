"""A bundle is third-party input, so every string it carries is sanitised where it is printed.

A compiled bundle arrives inside a zip someone else sent. Its body ids, its part ids and its print
model string are written by whoever built it, and three sinks consume them here:

* a terminal, where ``\\x1b[2J`` clears the screen and ``\\r`` rewrites the line that just reported a
  check,
* a markdown table, where ``|`` splits a cell in two and a newline starts whatever the next line
  spells,
* the arithmetic itself, where a string in a numeric field raises ``TypeError`` from inside a sum and
  escapes the ``except BundlePrintError`` a caller wrote.

The three are separate defects with separate fixes, so they are separate tests.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

from ai_cad.compiler.print_from_bundle import (
    BundlePrintError,
    mass_at_infill,
    printed_mass_at,
    safe_text,
)
from ai_cad.compiler.revision import LinkDelta, Revision, render_markdown
from robocad.twin_cli import main as twin_main

CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
# A newline is a control character and is also how a line-oriented report is written, so a check on
# printed output excludes it; everything that moves a cursor or rewrites a line is still caught.
CONTROL_IN_TEXT = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")
HOSTILE = "elbow\x1b[2J\x07_flex\r"          # clears a screen, rings a bell, rewrites a line


def _bundle(**body) -> dict:
    """A one-body bundle that is arithmetic-complete, so a test can break exactly one field."""
    record = {
        "body_id": "shoulder_pan",
        "printed_mass_kg": 0.5,
        "solid_mass_kg": 1.0,
        "bought_in_parts": 0,
    }
    record.update(body)
    return {"print_model": "1.20 mm wall over 20% infill", "bodies": [record]}


# --------------------------------------------------------------------------------------------
# 1. Terminal sinks: a body id cannot carry an escape sequence into a print.


def test_safe_text_strips_controls_and_bounds_length() -> None:
    assert safe_text(HOSTILE) == "elbow[2J_flex"
    assert CONTROL.search(safe_text(HOSTILE)) is None
    assert len(safe_text("x" * 500)) == 120


def test_a_hostile_body_id_is_sanitised_in_the_derived_masses() -> None:
    got = printed_mass_at(_bundle(body_id=HOSTILE), infill=0.30)
    keys = list(got["by_body"])
    assert keys, "the body still has to appear: sanitising is not dropping"
    for key in keys:
        assert CONTROL.search(key) is None, key
    assert got["warnings"] == []


def test_the_cli_prints_no_control_characters_from_a_bundle(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The summary lines and the saturation warning both carry the body id into the terminal."""
    before = tmp_path / "before"
    before.mkdir()
    # Printed at 0.9 against a 1.0 solid is a body that reaches its whole solid at 3 mm wall, so the
    # warning line -- the other print site -- is exercised as well as the summary.
    (before / "bundle.json").write_text(
        json.dumps(_bundle(body_id=HOSTILE, printed_mass_kg=0.9)), encoding="utf-8"
    )
    out = tmp_path / "out"
    code = twin_main(["revise", "--before", str(before), "--out", str(out),
                      "--wall-mm", "3.0"])
    captured = capsys.readouterr()
    assert code == 0, captured.err
    text = captured.out + captured.err
    assert CONTROL_IN_TEXT.search(text) is None, repr(text)
    assert "warning:" in captured.err, "the saturation warning has to fire for this test to mean much"


def test_a_hostile_body_id_is_still_revised_rather_than_silently_skipped(
    tmp_path: pathlib.Path
) -> None:
    """Sanitising the key must not break the lookup: the body keeps its new mass."""
    before = tmp_path / "before"
    before.mkdir()
    (before / "bundle.json").write_text(
        json.dumps(_bundle(body_id=HOSTILE)), encoding="utf-8"
    )
    out = tmp_path / "out"
    assert twin_main(["revise", "--before", str(before), "--out", str(out),
                      "--infill", "0.30", "--json"]) == 0
    after = json.loads((out / "bundle" / "bundle.json").read_text(encoding="utf-8"))
    # printed 0.5 at f=0.20 against a 1.0 solid separates into a 0.375 shell and a 0.625 interior,
    # so at f=0.30 the body weighs 0.375 + 0.3 * 0.625. A lookup that missed would leave 0.5.
    assert after["total_mass_kg"] == pytest.approx(0.5625)
    assert after["bodies"][0]["printed_mass_kg"] == pytest.approx(0.5625)


# --------------------------------------------------------------------------------------------
# 2. Markdown sinks: a link id cannot break the table it sits in.


def test_render_markdown_escapes_every_untrusted_string() -> None:
    revision = Revision(
        before="a|b",
        after="c\nd",
        links=[LinkDelta(link_id="gripper|jaw`x", status="changed",
                         quantity_before=1, quantity_after=2, quantity_delta=1)],
        notes=["note | with a pipe\nand a newline"],
    )
    markdown = render_markdown(revision)
    for line in markdown.splitlines():
        if line.startswith("|") and not line.startswith("|---"):
            # Nine columns are nine cells and ten separators; a tenth cell means a pipe in the data
            # opened one, which is what shifting the row does to a reader.
            assert len(UNESCAPED_PIPE.findall(line)) == 10, f"a cell was split: {line!r}"
    assert "| `gripper\\|jaw\\`x` |" in markdown
    assert "\nand a newline" not in markdown


def test_render_markdown_escapes_a_refusal_reason() -> None:
    revision = Revision(
        before="a", after="b", comparable=False,
        incomparable_reason="two schemes | no overlap\nsecond line",
    )
    markdown = render_markdown(revision)
    assert "two schemes \\| no overlap second line" in markdown


# --------------------------------------------------------------------------------------------
# 3. Arithmetic sinks: a type-confused bundle is the declared error, never a traceback.


@pytest.mark.parametrize(
    "field, value",
    [
        ("instances", "many"),         # a string where a count belongs
        ("instances", 1.5),            # half an instance is not a quantity
        ("instances", -1),             # neither is a negative one
        ("volume_m3", "big"),
        ("volume_m3", float("nan")),   # parses, then poisons every sum it enters
        ("density_kg_m3", float("inf")),
    ],
)
def test_a_malformed_part_row_raises_the_declared_error(field: str, value) -> None:
    row = {
        "part_id": "jaw",
        "instances": 2,
        "volume_m3": 1.0e-6,
        "surface_area_m2": 1.0e-4,
        "density_kg_m3": 1240.0,
        "printed": True,
    }
    row[field] = value
    bundle = _bundle(part_properties=[row])
    with pytest.raises(BundlePrintError):
        printed_mass_at(bundle, infill=0.30)


def test_a_part_row_that_is_not_an_object_is_refused() -> None:
    """A row list whose first entry is a row and whose later entry is not is still a broken list."""
    row = {"part_id": "jaw", "instances": 2, "volume_m3": 1.0e-6, "surface_area_m2": 1.0e-4,
           "density_kg_m3": 1240.0, "printed": True}
    bundle = _bundle(part_properties=[row, ["forearm", 2, 1.0e-6, 1240.0]])
    with pytest.raises(BundlePrintError):
        printed_mass_at(bundle, infill=0.30)


def test_a_row_list_that_is_wholly_wrong_falls_back_to_the_body_pair() -> None:
    """Not every unrecognised list is an error: no rows at all is the documented linear route."""
    bundle = _bundle(part_properties=[["jaw", 2, 1.0e-6, 1240.0]])
    got = printed_mass_at(bundle, infill=0.30)
    assert got["method"] == "body_linear"


def test_a_body_that_is_not_an_object_is_refused() -> None:
    with pytest.raises(BundlePrintError):
        printed_mass_at({"print_model": "1.20 mm wall over 20% infill",
                         "bodies": ["shoulder_pan"]}, infill=0.30)


@pytest.mark.parametrize("field", ["printed_mass_kg", "solid_mass_kg"])
def test_a_malformed_body_mass_raises_the_declared_error(field: str) -> None:
    with pytest.raises(BundlePrintError):
        printed_mass_at(_bundle(**{field: "heavy"}), infill=0.30)


@pytest.mark.parametrize("infill", [float("nan"), float("inf"), 1.0, 1.4, -0.1])
def test_a_malformed_caller_number_raises_the_declared_error(infill) -> None:
    with pytest.raises(BundlePrintError):
        printed_mass_at(_bundle(), infill=infill)


def test_mass_at_infill_refuses_rather_than_leaking_a_validation_error() -> None:
    for bad in (float("nan"), 1.4, -0.1):
        with pytest.raises(BundlePrintError):
            mass_at_infill(_bundle(), bad)
    with pytest.raises(BundlePrintError):
        mass_at_infill(_bundle(), 0.3, wall_m="thick")
