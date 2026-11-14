"""The cockpit stays usable at the width the HUD's blade gives it: 68 percent of the window.

V8 of the final visual stretch, from a measurement made in the blade. On a 1280x720 projector the
blade opens the page at 870 px wide, and the fixed three-column grid handed the 3D stage 198 px of
that -- a viewer two finger-widths across, with the checks rail taking more room than the robot. The
page now shrinks the rails below 1180 px and drops the right rail below 1120 px.

Asserted in pixels at each size:

* the page does not scroll,
* the stage takes at least half the page width where the right rail is dropped, and at least a third
  where all three columns fit,
* no KPI value is ellipsised,
* the right rail is hidden (not clipped) at the narrow sizes and present at the wide one.

Marked heavy: three browser runs over the 12 MB mesh payload.
"""
from __future__ import annotations

import pathlib

import pytest

pytest.importorskip("playwright", reason="playwright is needed to render the packaged page")

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = REPO_ROOT / "docs" / "demo" / "page" / "index.html"
SHOTS = REPO_ROOT / "docs" / "demo" / "screens" / "v1.4"

# (width, height, right rail expected, stage share of the page width at minimum)
SIZES = [
    (870, 680, False, 0.55),    # 1280x720 window, blade at 68 percent
    (1024, 640, False, 0.60),
    (1440, 900, True, 0.33),
]

MEASURE = """
(() => {
  const box = (id) => {
    const e = document.getElementById(id);
    if (!e) return null;
    const r = e.getBoundingClientRect();
    return {w: Math.round(r.width), h: Math.round(r.height)};
  };
  const right = document.getElementById('right');
  return {
    stage: box('stage'), left: box('left'), right: box('right'),
    rightDisplay: right ? getComputedStyle(right).display : 'absent',
    scroll: [document.scrollingElement.scrollWidth, document.scrollingElement.scrollHeight],
    viewport: [innerWidth, innerHeight],
    clipped: [...document.querySelectorAll('.kpi .v')]
      .filter((v) => v.scrollWidth > v.clientWidth + 1)
      .map((v) => v.innerText.replace(/\\s+/g, ' ').trim()),
    stageCanvas: box('stage').w > 0
  };
})()
"""


@pytest.mark.heavy
def test_the_stage_survives_the_blade_at_every_demo_width() -> None:
    from playwright.sync_api import sync_playwright

    seen = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            args=["--enable-gpu", "--use-angle=d3d11", "--ignore-gpu-blocklist"])
        for width, height, _rail, _share in SIZES:
            page = browser.new_context(viewport={"width": width, "height": height}).new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.goto(PAGE.resolve().as_uri(), wait_until="load")
            page.wait_for_function("window.SO101_PAGE !== undefined", timeout=120000)
            page.wait_for_timeout(900)
            state = page.evaluate(MEASURE)
            if SHOTS.exists():
                page.screenshot(path=str(SHOTS / f"blade-{width}x{height}.png"))
            page.close()
            assert errors == [], f"{width}x{height}: {errors[:3]}"
            seen[(width, height)] = state
        browser.close()

    for (width, height, rail, share) in SIZES:
        state = seen[(width, height)]
        where = f"{width}x{height}"
        # 1. One screen, still: no horizontal and no vertical scroll.
        assert state["scroll"][0] <= width, f"{where}: page scrolls {state['scroll'][0]} px wide"
        assert state["scroll"][1] <= height, f"{where}: page scrolls {state['scroll'][1]} px tall"
        # 2. The stage is the demo: it gets the room.
        assert state["stage"]["w"] >= width * share, \
            f"{where}: stage is {state['stage']['w']} px of {width}"
        assert state["stage"]["h"] > 200, where
        # 3. Nothing in the header is ellipsised.
        assert state["clipped"] == [], f"{where}: clipped {state['clipped']}"
        # 4. The rail is shown or dropped whole, never squeezed.
        if rail:
            assert state["rightDisplay"] != "none", where
            assert state["right"]["w"] > 240, where
        else:
            assert state["rightDisplay"] == "none", where
