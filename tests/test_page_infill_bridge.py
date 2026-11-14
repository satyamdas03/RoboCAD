"""The page moves the infill switch when the voice does, and every number moves with it.

V8.1 of the final visual stretch. The switch itself was fixed to write every dependent figure from
one state, but the phrase "change infill to 30 percent" answers in chat and leaves the page showing
the other bake: a viewer reads 0.955 kg in the sentence and 0.902 kg in the card behind it. The page
now accepts ``{type: "robocad.infill", infill: 0.30}`` on the section channel, under the section
channel's origin rule (tested in ``sections.test.mjs``), and this test drives that event the way the
shell would and reads what the page shows.

It runs against the tree page (``docs/demo/page/index.html``): the packaged copy is build output, and
this test is what the bake has to agree with.
"""
from __future__ import annotations

import pathlib

import pytest

pytest.importorskip("playwright", reason="playwright is needed to drive the page")

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = REPO_ROOT / "docs" / "demo" / "page" / "index.html"
SHOTS = REPO_ROOT / "docs" / "demo" / "screens" / "release"

READ = """(()=>{
  const t = (id)=>{const e=document.getElementById(id); return e ? e.innerText.replace(/\\s+/g,' ').trim() : null;};
  return {
    kpi: t('kpi-mass'),
    masses: t('masses'),
    torque: t('torque-grp'),
    beforePressed: document.getElementById('rev-before').getAttribute('aria-pressed'),
    afterPressed: document.getElementById('rev-after').getAttribute('aria-pressed')
  };
})()"""


@pytest.mark.heavy
def test_the_infill_message_moves_every_dependent_number() -> None:
    if not PAGE.exists():
        pytest.skip("the page has not been built in this checkout")

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
        page.wait_for_timeout(600)

        before = page.evaluate(READ)

        # Exactly what sections.js dispatches after it has checked the sender and the value.
        page.evaluate("document.dispatchEvent(new CustomEvent('robocad:infill', "
                      "{detail: {infill: 0.30}}))")
        page.wait_for_timeout(400)
        after = page.evaluate(READ)
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOTS / "infill-30-page.png"))

        # A fraction the sender should never have sent changes nothing on screen.
        page.evaluate("document.dispatchEvent(new CustomEvent('robocad:infill', "
                      "{detail: {infill: 1.4}}))")
        page.wait_for_timeout(200)
        refused = page.evaluate(READ)
        browser.close()

    assert errors == [], errors[:3]

    # The page opened on the compiled bake (0.20) and the message moved it to the second one. The
    # card carries the row label, so "0.20 infill" leaving and "0.30 infill" arriving is the proof
    # that the label moved with the number rather than only the number moving.
    assert "0.902" in (before["masses"] or ""), before["masses"]
    assert "0.20 infill" in (before["masses"] or ""), before["masses"]
    assert "0.955" in (after["masses"] or ""), after["masses"]
    assert "0.30 infill" in (after["masses"] or ""), after["masses"]
    assert "0.955" in (after["kpi"] or ""), after["kpi"]
    assert after["afterPressed"] == "true" and after["beforePressed"] == "false", after
    assert "scaled" in (after["torque"] or "").lower(), after["torque"]

    # A refused value leaves the page exactly where it was: not half-applied, not reset.
    assert refused["masses"] == after["masses"]
    assert refused["torque"] == after["torque"]
