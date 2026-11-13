"""Open the living page from file:// with no network, then report errors, fps and a screenshot.

The page contract is that it works from a null origin: no fetch, no ES modules, no server. This
script proves or disproves that on the real file, rather than asserting it in a docstring.
"""

from __future__ import annotations

import argparse
import json
import pathlib


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("page", help="path to index.html")
    parser.add_argument("--shot", default=None, help="write a screenshot here")
    parser.add_argument("--frame", type=int, default=120)
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright

    page_path = pathlib.Path(args.page).resolve().as_uri()
    errors: list[str] = []
    requests: list[str] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        context = browser.new_context(viewport={"width": 1280, "height": 800}, offline=True)
        page = context.new_page()
        page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("request", lambda r: requests.append(r.url))

        page.goto(page_path, wait_until="load")
        page.wait_for_function("window.SO101_PAGE !== undefined", timeout=30000)
        page.evaluate("window.SO101_PAGE.setFrame(%d)" % args.frame)
        fps = page.evaluate("window.SO101_PAGE.fps()")
        meta = page.evaluate("({frames: window.SO101_PAGE.frames, hz: window.SO101_PAGE.hz, body: window.SO101_PAGE.meta.nbody})")
        if args.shot:
            page.screenshot(path=args.shot)
        browser.close()

    local = [r for r in requests if not r.startswith("file://")]
    print(json.dumps({
        "page": page_path,
        "frames": meta["frames"],
        "hz": meta["hz"],
        "bodies": meta["body"],
        "fps": fps,
        "network_requests": local,
        "errors": errors,
        "screenshot": args.shot,
    }, indent=2))
    return 0 if not local and not [e for e in errors if e.startswith(("error", "pageerror"))] else 1


if __name__ == "__main__":
    raise SystemExit(main())
