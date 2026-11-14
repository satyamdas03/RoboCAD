"""The page may not print a figure the summary does not carry.

The page and the voice read one generator, `build_summary`, so this test renders the page the way a
recipient opens it (from file://, nothing fetched) and checks every numeric token in the torque,
comparison, checks and twin panels against the summary JSON. "tens of mm" is exactly what it has to
catch: prose in place of the 70.69 mm the summary holds, and a reader with no way to reach the figure.

Marked heavy: it parses the 12 MB packaged mesh payload in a browser, which is well past the default
tier's ten-second budget.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = REPO_ROOT / "docs" / "demo" / "page" / "index.html"
SCRIPTS = REPO_ROOT / "scripts"
for path in (REPO_ROOT, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

pytest.importorskip("playwright", reason="playwright is needed to render the packaged page")


@pytest.mark.heavy
def test_page_text_matches_summary() -> None:
    """Every number printed in the figure panels exists in the summary JSON."""
    from check_page_numbers import PANELS, page_numbers, read_summary, render_texts, unmatched

    assert PAGE.exists(), "the demo page is missing"
    summary = read_summary(PAGE)
    texts = render_texts(PAGE)

    assert set(texts) == set(PANELS)
    # A panel that rendered nothing would pass the number check for the wrong reason.
    for panel, text in texts.items():
        assert page_numbers(text), f"{panel} rendered no figures at all"

    bad = unmatched(summary, texts)
    assert not bad, "numbers on the page with no source in the summary:\n" + "\n".join(bad)


@pytest.mark.heavy
def test_torque_note_quotes_the_pose_gate() -> None:
    """The moving-arm reason carries the measured figure, not a hedge."""
    from check_page_numbers import read_summary, render_texts

    gate = read_summary(PAGE)["torque"]["pose_gate_mm"]["value"]
    text = render_texts(PAGE)["torque-grp"]
    assert f"{gate:.2f} mm" in text, f"the torque note does not quote {gate:.2f} mm"
    assert "tens of mm" not in text
