"""The cockpit fills its screen: no dead band under the last card, and the two new cards are real.

V8.4 of the final visual stretch. The cockpit put four cards in a 340 px rail and stopped, which left
224 px of empty panel under the last one at 1440x900 and 409 px at 1920x1080. That is the band the
review called dead space. The fix is two cards -- SAME ROBOT and PROVENANCE -- plus columns whose
rows share the leftover height instead of leaving it at the bottom.

What is asserted, at all three demo sizes:

* the page does not scroll and no card scrolls inside itself,
* the band under the last card in each column is at most 40 px,
* at 1440x900 and 1920x1080 the two new cards are visible and carry the bundle's own numbers,
* at 1280x720 they are hidden rather than clipped, because there is no spare height for them,
* the mass bars and the torque chart each carry a legend naming their colours.

Marked heavy: three real browser runs over the 12 MB mesh payload.
"""
from __future__ import annotations

import pathlib

import pytest

pytest.importorskip("playwright", reason="playwright is needed to render the packaged page")

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = REPO_ROOT / "docs" / "demo" / "page" / "index.html"
SHOTS = REPO_ROOT / "docs" / "demo" / "screens" / "v1.4"

VIEWPORTS = [(1280, 720), (1440, 900), (1920, 1080)]
BAND_MAX_PX = 40

MEASURE = """(()=>{
  const cols = {};
  for (const id of ['left','right']){
    const col = document.getElementById(id);
    const cr = col.getBoundingClientRect();
    const cards = [...col.children].filter(c => getComputedStyle(c).display !== 'none');
    const rects = cards.map(c => c.getBoundingClientRect());
    const last = rects[rects.length-1];
    cols[id] = {
      band: Math.round(cr.bottom - last.bottom),
      ids: cards.map(c => c.id),
      boxes: cards.map((c,i) => ({id:c.id, top:Math.round(rects[i].top),
                                  bottom:Math.round(rects[i].bottom),
                                  scroll:c.scrollHeight, client:c.clientHeight}))
    };
  }
  return {
    cols: cols,
    scroll: [document.scrollingElement.scrollHeight, innerHeight],
    same: document.getElementById('same-grp') ? getComputedStyle(document.getElementById('same-grp')).display : 'absent',
    prov: document.getElementById('prov-grp') ? getComputedStyle(document.getElementById('prov-grp')).display : 'absent',
    sameText: document.getElementById('same-body').innerText,
    provText: document.getElementById('prov-body').innerText,
    massLegend: document.querySelector('#cmp .legend').innerText,
    torqueLegend: [...document.querySelectorAll('#torque-body .legend span')].map(s => s.innerText)
  };
})()"""


@pytest.mark.heavy
def test_cockpit_fills_its_column_at_every_demo_size() -> None:
    from playwright.sync_api import sync_playwright

    seen = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            args=["--enable-gpu", "--use-angle=d3d11", "--ignore-gpu-blocklist"])
        for width, height in VIEWPORTS:
            page = browser.new_context(viewport={"width": width, "height": height}).new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.goto(PAGE.resolve().as_uri(), wait_until="load")
            page.wait_for_function("window.SO101_PAGE !== undefined", timeout=120000)
            page.wait_for_timeout(900)
            state = page.evaluate(MEASURE)
            if SHOTS.exists():
                page.screenshot(path=str(SHOTS / f"cockpit-{width}x{height}.png"))
            page.close()
            assert errors == [], f"{width}x{height}: {errors[:3]}"
            seen[(width, height)] = state
        browser.close()

    for size, state in seen.items():
        width, height = size
        where = f"{width}x{height}"
        # 1. Nothing scrolls: the cockpit is one screen.
        assert state["scroll"] == [height, height], where
        for col_id, col in state["cols"].items():
            # 2. No dead band under the last card.
            assert col["band"] <= BAND_MAX_PX, f"{where} {col_id} leaves {col['band']} px of band"
            # 3. No card clips its own content: the stretch must not hide a row.
            for box in col["boxes"]:
                assert box["scroll"] <= box["client"] + 1, \
                    f"{where} {box['id']} clips {box['scroll'] - box['client']} px"

    # 4. The two new cards carry the bundle's own numbers where there is height for them.
    tall = seen[(1440, 900)]
    assert tall["same"] != "none" and tall["prov"] != "none"
    assert "0.902 / 0.632 kg" in tall["sameText"]
    assert "7 / 7" in tall["sameText"]
    assert "model.mjcf" in tall["provText"]
    assert "6.00 s" in tall["provText"]
    # 5. ...and are hidden, not clipped, where there is not.
    short = seen[(1280, 720)]
    assert short["same"] == "none" and short["prov"] == "none"

    # 6. The bars and the curves name their colours.
    assert "printed, this infill" in tall["massLegend"]
    assert tall["torqueLegend"] == ["compiled", "published", "±rated"]
