"""The self-collision label points at the two parts that touch, and goes away when they leave frame.

The page used to place the label on the wrist body's origin, which reads as a caption for the whole
wrist rather than for the pair the check failed on. The brief for V8.2 asks for the label anchored
to the projected contact point with a leader line, hidden when that point is off-screen. Both halves
are geometry, so both are asserted in pixels here:

* the anchor dot sits at the projected contact point (``window.__callout.anchor``),
* the leader line's first endpoint is that same point, and its second endpoint is on the edge of the
  label's own box -- a line that stops in mid-air is the defect this replaces,
* the label box and the anchor are inside the stage,
* the anchor is inside the colliding pair's bounding box, so the label points at those parts and not
  at some other part of the arm, and
* zooming until the pair leaves the frame hides the label, the leader and the dot.

Marked heavy: it parses the packaged mesh payload in a real browser.
"""
from __future__ import annotations

import pathlib

import pytest

pytest.importorskip("playwright", reason="playwright is needed to render the packaged page")

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = REPO_ROOT / "docs" / "demo" / "page" / "index.html"
SHOTS = REPO_ROOT / "docs" / "demo" / "screens" / "v1.4"

ANCHOR_PX = 0.6      # the dot and the line start are the anchor, to sub-pixel
EDGE_PX = 1.5        # the line ends on the label box's edge
INSIDE_PX = 0.5      # the label box is inside the stage


def open_page(pw):
    browser = pw.chromium.launch(
        args=["--enable-gpu", "--use-angle=d3d11", "--ignore-gpu-blocklist"])
    page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.goto(PAGE.resolve().as_uri(), wait_until="load")
    page.wait_for_function("window.SO101_PAGE !== undefined", timeout=120000)
    page.wait_for_timeout(900)
    # Freeze the replay: the assertions compare one frame's geometry with one frame's pixels.
    page.evaluate("document.getElementById('b-play').click()")
    page.wait_for_timeout(350)
    return browser, page, errors


@pytest.mark.heavy
def test_callout_is_anchored_to_the_contact_it_names() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser, page, errors = open_page(pw)
        state = page.evaluate("window.__callout")
        stage = page.evaluate(
            "(()=>{const r=document.getElementById('stage').getBoundingClientRect();"
            "return {w:r.width,h:r.height}})()")
        dot = page.evaluate(
            "(()=>{const d=document.getElementById('contactdot');"
            "return {x:Number(d.getAttribute('cx')),y:Number(d.getAttribute('cy')),"
            "display:d.style.display}})()")
        line = page.evaluate(
            "(()=>{const l=document.getElementById('leaderline');"
            "return {x1:+l.getAttribute('x1'),y1:+l.getAttribute('y1'),"
            "x2:+l.getAttribute('x2'),y2:+l.getAttribute('y2'),display:l.style.display}})()")
        in_pair_box = page.evaluate(
            "(()=>{const c=window.__callout, out=[];"
            "const names=(c.pair||[]).map(n=>String(n).toLowerCase());"
            "const boxes=[];"
            "for (let b=0;b<window.__pageBodies.length;b++){const nm=String(window.__pageBodies[b].name).toLowerCase();"
            "if(names.indexOf(nm)<0) continue;"
            "const g=window.__pageGroups[b]; const box=new THREE.Box3().setFromObject(g);"
            "box.expandByScalar(0.02); boxes.push(box);}"
            "const p=new THREE.Vector3(c.world[0],c.world[1],c.world[2]);"
            "return {count:boxes.length, inside:boxes.every(b=>b.containsPoint(p))};})()")
        if SHOTS.exists():
            page.screenshot(path=str(SHOTS / "callout-anchored.png"))
        browser.close()

    assert errors == []
    assert state["visible"] is True
    anchor = state["anchor"]
    # 1. The dot is the anchor.
    assert dot["display"] != "none"
    assert dot["x"] == pytest.approx(anchor["x"], abs=ANCHOR_PX)
    assert dot["y"] == pytest.approx(anchor["y"], abs=ANCHOR_PX)
    # 2. The leader starts at the anchor...
    assert line["display"] != "none"
    assert line["x1"] == pytest.approx(anchor["x"], abs=ANCHOR_PX)
    assert line["y1"] == pytest.approx(anchor["y"], abs=ANCHOR_PX)
    # ...and ends on the label box's edge, on the side the page says it laid the box out.
    box = state["callout"]
    if state["side"] in ("right", "left"):
        edge_x = box["left"] if state["side"] == "right" else box["right"]
        assert line["x2"] == pytest.approx(edge_x, abs=EDGE_PX)
        assert line["y2"] == pytest.approx(box["bottom"], abs=EDGE_PX)
    else:
        assert line["x2"] == pytest.approx(box["left"] if state["side"] == "right" else box["right"],
                                           abs=EDGE_PX)
        assert line["y2"] == pytest.approx(box["top"], abs=EDGE_PX)
    assert line["x2"] != pytest.approx(anchor["x"], abs=ANCHOR_PX) or \
        line["y2"] != pytest.approx(anchor["y"], abs=ANCHOR_PX)
    # 3. Both the label and the anchor are on the stage.
    assert box["left"] >= -INSIDE_PX and box["top"] >= -INSIDE_PX
    assert box["right"] <= stage["w"] + INSIDE_PX and box["bottom"] <= stage["h"] + INSIDE_PX
    assert 0 <= anchor["x"] <= stage["w"] and 0 <= anchor["y"] <= stage["h"]
    # 4. The anchor is inside the colliding pair's own boxes, so it labels those parts.
    assert in_pair_box["count"] == 2
    assert in_pair_box["inside"] is True


@pytest.mark.heavy
def test_callout_hides_when_the_contact_leaves_the_frame() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser, page, errors = open_page(pw)
        assert page.evaluate("window.__callout.visible") is True
        centre = page.evaluate(
            "(()=>{const r=document.getElementById('stage').getBoundingClientRect();"
            "return {x:r.x+r.width/2,y:r.y+r.height/2}})()")
        # Zoom into the wrist until the pair is past the frame. The wheel is the page's own control,
        # so this is a path a presenter can actually take.
        for _ in range(20):
            page.mouse.move(centre["x"], centre["y"])
            page.mouse.wheel(0, -100)
        page.wait_for_timeout(400)
        after = page.evaluate(
            "({visible:window.__callout.visible,"
            " callout:document.getElementById('callout').style.display,"
            " line:document.getElementById('leaderline').style.display,"
            " dot:document.getElementById('contactdot').style.display})")
        if SHOTS.exists():
            page.screenshot(path=str(SHOTS / "callout-offscreen.png"))
        browser.close()

    assert errors == []
    assert after["visible"] is False
    assert after["callout"] == "none"
    assert after["line"] == "none"
    assert after["dot"] == "none"
