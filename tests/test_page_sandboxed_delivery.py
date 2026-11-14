"""The page moves when the HUD embeds it the way the HUD really embeds it.

A page that accepts ``{type: "robocad.infill"}`` from its own origin is not yet a page that moves on
stage: the HUD loads it in ``<iframe sandbox="allow-scripts">``, whose document origin is opaque.
That has two consequences this test pins down, both of them silent failures before 2026-11-14:

* the host has to post with a wildcard target -- a message addressed to the daemon's origin is
  dropped by the browser's target-origin check before the page's own listener ever runs;
* the page's own ``location.origin`` still reads the served origin inside that sandbox, so the
  origin rule in ``sections.js`` accepts the delivery rather than refusing it as "null".

The test builds the embed itself (parent page on one origin, sandboxed frame on the same origin),
so it proves the pair rather than either half. It runs against the tree page.

    python -m pytest tests/test_page_sandboxed_delivery.py -m ""
"""
from __future__ import annotations

import functools
import http.server
import pathlib
import socketserver
import threading

import pytest

pytest.importorskip("playwright", reason="playwright is needed to drive the page")

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE_DIR = REPO_ROOT / "docs" / "demo" / "page"

PARENT = """<!doctype html><meta charset="utf-8"><title>parent</title>
<iframe id="f" sandbox="allow-scripts" src="/index.html" width="1200" height="900"></iframe>
<script>
  window.post = function (msg, target) {
    document.getElementById('f').contentWindow.postMessage(msg, target)
  }
</script>"""

READ = """(()=>{
  const t = (id)=>{const e=document.getElementById(id);
    return e ? e.innerText.replace(/\\s+/g,' ').trim() : null};
  return {mass: t('kpi-mass'), masses: t('masses'),
          after: document.getElementById('rev-after').getAttribute('aria-pressed')};
})()"""


@pytest.fixture()
def embed(tmp_path):
    """A parent page and the tree page, both served from one origin, in the real sandbox."""
    for source in PAGE_DIR.iterdir():
        if source.is_file():
            (tmp_path / source.name).write_bytes(source.read_bytes())
    (tmp_path / "parent.html").write_text(PARENT, encoding="utf-8")

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path))
    socketserver.TCPServer.allow_reuse_address = True
    server = socketserver.TCPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.heavy
def test_a_sandboxed_frame_moves_only_when_the_host_posts_with_a_wildcard_target(embed) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_context(viewport={"width": 1440, "height": 1000}).new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(embed + "/parent.html", wait_until="load")

        frame = page.frames[1]
        frame.wait_for_selector("body", timeout=60000)
        # Asked from inside the frame, because the parent cannot read its window at all: that
        # refusal is the same opaque origin the wildcard target exists for.
        frame.wait_for_function("() => window.SO101_PAGE !== undefined", timeout=120000)
        page.wait_for_timeout(600)
        before = frame.evaluate(READ)

        # What the HUD used to do: address the frame's origin. The frame's document origin is
        # opaque, so the browser drops this before any listener in the page sees it.
        page.evaluate(f"window.post({{type:'robocad.infill', infill:0.30}}, '{embed}')")
        page.wait_for_timeout(600)
        dropped = frame.evaluate(READ)

        # What the HUD does now. This is the only target an opaque frame accepts.
        page.evaluate("window.post({type:'robocad.infill', infill:0.30}, '*')")
        page.wait_for_timeout(600)
        after = frame.evaluate(READ)
        browser.close()

    assert errors == [], errors[:3]
    assert "0.902" in (before["masses"] or "") and "0.20 infill" in (before["masses"] or ""), before
    assert dropped == before, f"an explicitly addressed post must not reach the frame: {dropped}"
    assert "0.955" in (after["masses"] or ""), after
    assert "0.30 infill" in (after["masses"] or ""), after
    assert "0.955" in (after["mass"] or ""), after
    assert after["after"] == "true", after
