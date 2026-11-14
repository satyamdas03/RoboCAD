"""The release journey, typed into the real HUD and photographed at every step.

This is the evidence the final brief asks for, in the order it names it: "walk me through it", then
"next" three times, "show me the torque", "what failed", "change infill to 30 percent", and finally
Escape. Nine phrases exist in the peer harness; this one is the seven-step release path plus the key a
presenter actually presses when they are done, and it writes each frame to
``docs/demo/screens/release/``.

It drives a daemon that is already running, so the thing under the camera is whatever ``start_demo``
started -- in the release run, that is a fresh clone with the tagged package unpacked, not the tree.

    python scripts/release_journey.py --base http://127.0.0.1:7345 --out docs/demo/screens/release
"""

from __future__ import annotations

import argparse
import pathlib
import time

STEPS = [
    ("01-walk-me-through-it", "walk me through it"),
    ("02-next-checks", "next"),
    ("03-next-comparison", "next"),
    ("04-next-torque", "next"),
    ("05-show-torque", "show me the torque"),
    ("06-what-failed", "what failed"),
    ("07-infill-30", "change infill to 30 percent"),
]

GPU_ARGS = ["--enable-gpu", "--use-angle=d3d11", "--ignore-gpu-blocklist"]
BUDGET_MS = 1500  # a phrase an audience waits more than a second and a half for is a phrase that hung

# The frame reads its own card. A chat answer alone does not prove the page moved: the sentence
# "printed mass went from 0.902 to 0.955" lands in chat whether or not the card behind it follows,
# and that mismatch is exactly the defect v1.6 shipped. The host posts to the frame with a wildcard
# target because a sandboxed frame's document origin is opaque; if that delivery regresses, the chat
# still answers and only this read changes. See docs/demo/screens/release/07-infill-30.png.
BLADE_READ = """(()=>{
  const t = (id)=>{const e=document.getElementById(id);
    return e ? e.innerText.replace(/\\s+/g,' ').trim() : null};
  return {mass: t('kpi-mass'), masses: t('masses'),
          after: document.getElementById('rev-after')?.getAttribute('aria-pressed') ?? null};
})()"""


def blade_frame(page):
    """The embedded page, or None when the HUD has not opened the blade."""
    for frame in page.frames:
        if "/robocad/page/" in (frame.url or ""):
            return frame
    return None


def read_blade(page):
    frame = blade_frame(page)
    if frame is None:
        return None
    try:
        return frame.evaluate(BLADE_READ)
    except Exception:
        return None



def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="the running HUD, e.g. http://127.0.0.1:7345")
    parser.add_argument("--out", default="docs/demo/screens/release")
    args = parser.parse_args()

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright

    over_budget = 0
    silent = 0
    started = time.time()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=GPU_ARGS)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(args.base + "/", wait_until="domcontentloaded")
        page.wait_for_selector(".command-open", state="visible", timeout=20000)

        for name, phrase in STEPS:
            before = page.locator(".chat-bubble-ev").count()
            t0 = time.time()
            page.keyboard.press("/")
            page.wait_for_selector(".command-input", state="visible", timeout=5000)
            page.fill(".command-input", phrase)
            page.keyboard.press("Enter")
            arrived = True
            try:
                page.wait_for_function(
                    "n => document.querySelectorAll('.chat-bubble-ev').length > n",
                    arg=before, timeout=8000)
            except Exception:
                arrived = False
            elapsed = (time.time() - t0) * 1000
            page.wait_for_timeout(700)  # let the page draw the answer's own panels
            page.screenshot(path=str(out / f"{name}.png"))

            bubbles = page.locator(".chat-bubble-ev")
            answer = bubbles.last.inner_text()[:160].replace("\n", " ") if bubbles.count() > before else ""
            print(f"{phrase:28s} {elapsed:7.1f} ms  {answer or '(no new answer)'}")
            if not arrived:
                silent += 1
            elif elapsed > BUDGET_MS:
                over_budget += 1

            # After the infill sentence the card has to show what the sentence said. A chat answer
            # that names 0.955 kg while the card still reads 0.902 is the v1.6 defect, and it is
            # invisible to every assertion that only reads chat.
            if name.endswith("infill-30"):
                card = read_blade(page)
                ok = bool(card and "0.955" in (card.get("mass") or "")
                          and "0.30 infill" in (card.get("masses") or "")
                          and card.get("after") == "true")
                print(f"{'  page after the sentence':28s} {'':>10s}  "
                      f"{'PASS' if ok else 'FAIL'}  {card}")
                if not ok:
                    silent += 1

        # Escape is part of the journey: the presenter presses it when a question lands that they did
        # not want to ask, and the page has to go back to a state they can type into again. So the
        # frame is taken, then "/" is pressed: a closed input that cannot be reopened is a dead page.
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
        page.screenshot(path=str(out / "08-escape.png"))
        input_visible = page.locator(".command-input").is_visible()
        page.keyboard.press("/")
        page.wait_for_timeout(400)
        reopened = page.locator(".command-input").is_visible()
        page.screenshot(path=str(out / "09-escape-then-typing.png"))
        page.keyboard.press("Escape")
        print(f"{'Escape':28s} {'':>10s}  input after Escape: {input_visible}, "
              f"reopens on '/': {reopened}")
        if reopened is False:
            silent += 1

        context.close()
        browser.close()

    print(f"\n{len(STEPS)} phrases in {time.time() - started:.1f} s, {silent} unanswered, "
          f"{over_budget} over the {BUDGET_MS} ms budget, {len(errors)} console error(s)")
    for error in errors[:5]:
        print(f"  page error: {error}")
    return 0 if not silent and not over_budget and not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
