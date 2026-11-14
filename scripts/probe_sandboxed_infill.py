"""Does an infill message reach the page when the page is embedded the way the HUD embeds it?

The HUD loads ``/robocad/page/`` in ``<iframe sandbox="allow-scripts">`` -- no ``allow-same-origin``.
That makes the frame's document origin opaque, and ``sections.js`` refuses an opaque origin on
purpose. This probe builds that exact embed from a parent page on the same origin, posts the same
message the HUD posts, and reads what the frame shows. It is a probe, not a gate: run it to find out,
then decide.
"""
from __future__ import annotations

import functools
import http.server
import pathlib
import socketserver
import threading

PAGE_DIR = pathlib.Path(__file__).resolve().parents[1] / "docs" / "demo" / "page"

PARENT = """<!doctype html><meta charset="utf-8"><title>parent</title>
<iframe id="f" sandbox="allow-scripts" src="/index.html" width="1200" height="900"></iframe>
<script>
  window.post = function (msg) {
    document.getElementById('f').contentWindow.postMessage(msg, '*')
  }
</script>"""

READ = """(()=>{const t=(id)=>{const e=document.getElementById(id);
  return e?e.innerText.replace(/\\s+/g,' ').trim():null};
  return {masses:t('masses'), kpi:t('kpi-mass'),
          after:document.getElementById('rev-after').getAttribute('aria-pressed')}})()"""


def serve(directory: pathlib.Path):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    socketserver.TCPServer.allow_reuse_address = True
    server = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main() -> int:
    import tempfile

    from playwright.sync_api import sync_playwright

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        (root / "parent.html").write_text(PARENT, encoding="utf-8")
        (root / "index.html").write_text((PAGE_DIR / "index.html").read_text(encoding="utf-8"),
                                        encoding="utf-8")
        for source in PAGE_DIR.iterdir():
            if source.is_file() and source.name != "index.html":
                (root / source.name).write_bytes(source.read_bytes())
        server = serve(root)
        port = server.server_address[1]
        print(f"serving {root} on 127.0.0.1:{port}")

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_context(viewport={"width": 1440, "height": 1000}).new_page()
            logs: list[str] = []
            page.on("console", lambda m: logs.append(f"{m.type}: {m.text}"))
            page.goto(f"http://127.0.0.1:{port}/parent.html", wait_until="load")
            frame = page.frame_locator("#f")
            frame.locator("body").wait_for(timeout=60000)
            page.wait_for_timeout(1500)

            # The frame's own report of what it thinks its origin is.
            frame_origin = page.evaluate("""() => {
              const f = document.getElementById('f');
              try { return f.contentWindow.location.origin } catch (e) { return 'blocked: ' + e.message }
            }""")
            print("frame location.origin as seen by parent:", frame_origin)

            before = frame.locator("body").evaluate(READ)
            print("before:", before)
            print("frame's own view:", frame.locator("body").evaluate(
                "() => ({origin: location.origin, href: location.href,"
                " sandboxed: !(document.domain && self.origin)})"))

            page.evaluate("window.post({type:'robocad.infill', infill:0.30})")
            page.wait_for_timeout(800)
            after = frame.locator("body").evaluate(READ)
            print("after message:", after)

            moved = after != before
            print("PAGE MOVED:", moved)
            print("console:", *(logs[-6:] or ["(none)"]), sep="\n  ")
            browser.close()
        server.shutdown()
        return 0 if moved else 1


if __name__ == "__main__":
    raise SystemExit(main())
