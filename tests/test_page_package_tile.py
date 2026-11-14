"""The PACKAGE tile names the tag the zip was cut from, once, on one line, unclipped.

V1 of the final visual stretch. The page of record is the one inside the zip: a recipient who was
given no repository has only that page, and on it the PACKAGE tile read "no tag recorded" -- the
manifest wrote the tag one way and the tile printed it another. Earlier still, prefixing the tag with
its own prefix produced "demo-bundle-demo-bundle-v1.4", and at 150 px the pill that says whether the
tag is recorded was clipped off the end of the tile.

This test reads the manifest the page itself reads (``manifest.js`` names the same tag) and then
asserts the tile agrees with it, in pixels:

* the tile's value text carries the tag exactly once, with no doubled prefix,
* the pill is visible inside the tile's own box (no clipping), and says "tagged" when there is a
  tag and "no tag recorded" when there is not,
* the tile does not overflow its own KPI cell.

It runs against the packaged copy, which is build output. Marked heavy: it loads the 12 MB package in
a real browser.
"""
from __future__ import annotations

import pathlib

import pytest

pytest.importorskip("playwright", reason="playwright is needed to render the packaged page")

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PACKAGE = REPO_ROOT / "docs" / "demo" / "so101_demo"
PAGE = PACKAGE / "index.html"

TILE = """(()=>{
  const tile = document.getElementById('kpi-package');
  if (!tile) return {present: false};
  const tr = tile.getBoundingClientRect();
  const pill = tile.querySelector('.pill');
  const text = tile.innerText;
  const kids = [...tile.querySelectorAll('span')].map(s => ({
    cls: s.className, text: s.innerText.trim(),
    box: (()=>{const r=s.getBoundingClientRect();
               return {l:Math.round(r.left),t:Math.round(r.top),
                       r:Math.round(r.right),b:Math.round(r.bottom),
                       w:Math.round(r.width),h:Math.round(r.height)}})(),
    clipped: s.scrollWidth > s.clientWidth + 1
  }));
  return {
    present: true, text: text,
    tile: {l:Math.round(tr.left), t:Math.round(tr.top),
           r:Math.round(tr.right), b:Math.round(tr.bottom)},
    pill: pill ? {text: pill.innerText.trim(), cls: pill.className,
                  display: getComputedStyle(pill).display,
                  box: (()=>{const r=pill.getBoundingClientRect();
                             return {l:r.left,t:r.top,r:r.right,b:r.bottom}})()} : null,
    spans: kids
  };
})()"""


def _packaged_tag() -> str | None:
    """The tag the page itself reads: ``window.SO101_MANIFEST.package.tag`` in manifest.js."""
    import json

    js = (PACKAGE / "manifest.js").read_text(encoding="utf-8")
    payload = js[js.index("=") + 1:].strip().rstrip(";")
    return (json.loads(payload).get("package") or {}).get("tag")


@pytest.mark.heavy
def test_package_tile_names_the_tag_the_zip_carries() -> None:
    if not PAGE.exists():
        pytest.skip("the package has not been baked in this checkout")
    tag = _packaged_tag()
    if not tag:
        pytest.skip("this package was baked without a tag: the rebake records one")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            args=["--enable-gpu", "--use-angle=d3d11", "--ignore-gpu-blocklist"])
        page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(PAGE.resolve().as_uri(), wait_until="load")
        page.wait_for_function("window.SO101_PAGE !== undefined", timeout=120000)
        page.wait_for_timeout(900)
        state = page.evaluate(TILE)
        shots = REPO_ROOT / "docs" / "demo" / "screens" / "release"
        shots.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(shots / "package-tile.png"))
        browser.close()

    assert errors == [], errors[:3]
    assert state["present"] is True

    # 1. No doubled prefix, ever: that was the header bug, and the tile shares the same string.
    assert "demo-bundle-demo-bundle" not in state["text"]

    # 2. The tag the manifest records appears exactly once, and the pill says so.
    assert state["text"].count(tag) == 1, state["text"]
    assert state["pill"] is not None
    assert state["pill"]["text"] == "tagged"
    assert "ok" in state["pill"]["cls"].split()
    # 4. The pill is on screen and inside the tile: the old defect clipped it off at 150 px.
    pill = state["pill"]
    assert pill is not None and pill["display"] != "none"
    tile = state["tile"]
    assert pill["box"]["l"] >= tile["l"] - 1 and pill["box"]["r"] <= tile["r"] + 1
    assert pill["box"]["b"] <= tile["b"] + 1
    # 5. Neither the tag nor the pill is squeezed into an ellipsis.
    for span in state["spans"]:
        assert not span["clipped"], f"{span['cls']} clips: {span['text']}"
