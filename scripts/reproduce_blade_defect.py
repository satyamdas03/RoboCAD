"""Put the pre-fix cockpit grid back, at the width the blade gives it, and photograph the result.

V8 says the page has to stay usable at 68 percent of a 1280x720 projector, which is an 870 px page.
The fix is three CSS rules, so the defect can be reproduced exactly by injecting the rule set the
page had before them: the fixed 300 / 1fr / 340 grid, the KPI row with no shrink allowance, and no
narrow-header padding rule. Not a test -- a reproduction, so the before-picture exists next to the
after-picture.
"""
from __future__ import annotations

import json
import pathlib

from playwright.sync_api import sync_playwright

REPO = pathlib.Path(__file__).resolve().parents[1]
PAGE = (REPO / "docs" / "demo" / "page" / "index.html").resolve()
SHOTS = REPO / "docs" / "demo" / "screens" / "v1.4"

# The rules the page carried before the fix, restored in the order the stylesheet would have them.
PRE_FIX_CSS = """
#app{grid-template-columns:300px minmax(0,1fr) 340px}
#kpis{gap:12px}
.kpi{padding:3px 10px}
#right{display:flex !important}
"""

MEASURE = """
(() => {
  const r = (id) => {
    const e = document.getElementById(id);
    if (!e) return null;
    const b = e.getBoundingClientRect();
    return {w: Math.round(b.width), h: Math.round(b.height)};
  };
  return {
    left: r('left'), stage: r('stage'), right: r('right'),
    scroll: [document.scrollingElement.scrollWidth, document.scrollingElement.scrollHeight],
    viewport: [innerWidth, innerHeight],
    clipped: [...document.querySelectorAll('.kpi .v')]
      .filter((v) => v.scrollWidth > v.clientWidth + 1)
      .map((v) => v.innerText.replace(/\\s+/g, ' ').trim())
  };
})()
"""


def main() -> None:
    width, height = 870, 680
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            args=["--enable-gpu", "--use-angle=d3d11", "--ignore-gpu-blocklist"])
        page = browser.new_context(viewport={"width": width, "height": height}).new_page()
        page.goto(PAGE.as_uri(), wait_until="load")
        page.wait_for_function("window.SO101_PAGE !== undefined", timeout=120000)
        page.add_style_tag(content=PRE_FIX_CSS)
        page.wait_for_timeout(900)
        state = page.evaluate(MEASURE)
        print(json.dumps(state))
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOTS / f"defect-blade-{width}x{height}.png"))
        browser.close()


if __name__ == "__main__":
    main()
