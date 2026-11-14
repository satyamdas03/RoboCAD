"""Measure the cockpit at the widths a 68% blade gives it on the demo machines.

Not a test: a measurement used once to decide the responsive rule, kept so the numbers in the CSS
comment can be re-checked.
"""
from __future__ import annotations

import json
import pathlib

from playwright.sync_api import sync_playwright

REPO = pathlib.Path(__file__).resolve().parents[1]
PAGE = (REPO / "docs" / "demo" / "page" / "index.html").resolve()
SHOTS = REPO / "docs" / "demo" / "screens" / "v1.4"

MEASURE = """
(() => {
  const r = (id) => {
    const e = document.getElementById(id);
    if (!e) return null;
    const b = e.getBoundingClientRect();
    return {w: Math.round(b.width), h: Math.round(b.height)};
  };
  const trunc = [...document.querySelectorAll('.kpi .v')].map((v) => ({
    text: v.innerText.replace(/\\s+/g, ' ').trim(),
    clipped: v.scrollWidth > v.clientWidth + 1
  }));
  const titles = [...document.querySelectorAll('.card h3, .card .cap')].slice(0, 12).map((e) => ({
    text: e.innerText.replace(/\\s+/g, ' ').trim(),
    clipped: e.scrollWidth > e.clientWidth + 1
  }));
  return {
    left: r('left'), stage: r('stage'), right: r('right'),
    scroll: [document.scrollingElement.scrollWidth, document.scrollingElement.scrollHeight],
    viewport: [innerWidth, innerHeight],
    trunc: trunc, titles: titles
  };
})()
"""


def main() -> None:
    sizes = [(870, 680), (952, 700), (1024, 640), (1088, 700)]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            args=["--enable-gpu", "--use-angle=d3d11", "--ignore-gpu-blocklist"])
        for width, height in sizes:
            page = browser.new_context(viewport={"width": width, "height": height}).new_page()
            page.goto(PAGE.as_uri(), wait_until="load")
            page.wait_for_function("window.SO101_PAGE !== undefined", timeout=120000)
            page.wait_for_timeout(700)
            state = page.evaluate(MEASURE)
            print(width, height, json.dumps(state))
            SHOTS.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(SHOTS / f"width-{width}x{height}.png"))
            page.close()
        browser.close()


if __name__ == "__main__":
    main()
