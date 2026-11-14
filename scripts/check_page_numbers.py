"""Every number on the demo page has to be a number the summary already carries.

The page and the voice read one generator (`build_summary`), so a figure the page prints that the
summary does not hold is a second source of truth waiting to drift -- which is exactly what happened
when the torque panel printed "tens of mm" while the summary carried 70.69 mm.

This checker renders the page, takes the text of the panels that quote figures (torque, comparison,
checks, twin), and requires every numeric token in them to match a number somewhere in the summary
JSON: in a leaf value, inside an array, or inside one of the summary's own sentences. Rounding to the
precision the page prints is allowed, and so are the unit scales the page legitimately applies
(metres to millimetres, a fraction to a percentage). Anything else is a failure, and it names the
token and the panel it came from so the fix is a number, not a hunt.

Usage: python scripts/check_page_numbers.py [--page docs/demo/page/index.html]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re

PANELS = ("torque-grp", "cmp", "checks", "twin-grp")

# A hex digest is a value in its own right, not a bag of decimal numbers: without this, the sha256
# in the limits note would be read as a dozen unrelated figures and could make a wrong page pass.
_HEX = re.compile(r"\b[0-9a-f]{16,}\b")
_NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w])")


def summary_numbers(summary) -> set[float]:
    """Every number the summary states, at the scales the page is allowed to present it."""
    values: set[float] = set()

    def add(n) -> None:
        if isinstance(n, bool) or not isinstance(n, (int, float)):
            return
        f = float(n)
        for scale in (1.0, 1000.0, 0.001, 100.0, 0.01):
            scaled = f * scale
            if abs(scaled) > 1e-12:
                values.add(round(abs(scaled), 9))
                values.add(round(abs(f), 9))

    def walk(node) -> None:
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif isinstance(node, str):
            for tok in _NUMBER.findall(_HEX.sub(" ", node)):
                add(float(tok))
        else:
            add(node)

    walk(summary)
    return values


def page_numbers(text: str) -> list[tuple[str, int]]:
    """Numeric tokens in a panel's text, with their printed precision, minus hex digests."""
    clean = _HEX.sub(" ", text)
    out = []
    for tok in _NUMBER.findall(clean):
        precision = len(tok.split(".")[1]) if "." in tok else 0
        out.append((tok, precision))
    return out


def matches(token: str, precision: int, values: set[float]) -> bool:
    """A token matches if some summary number rounds to it at the precision the page printed."""
    t = abs(float(token))
    if precision == 0:
        return any(abs(round(v) - t) < 0.5 for v in values)
    for v in values:
        if abs(round(v, precision) - t) <= 10 ** (-precision) / 2 + 1e-12:
            return True
    return False


def unmatched(summary: dict, texts: dict[str, str]) -> list[str]:
    values = summary_numbers(summary)
    bad = []
    for panel, text in texts.items():
        for token, precision in page_numbers(text):
            if not matches(token, precision, values):
                bad.append(f"{panel}: {token}")
    return bad


def read_summary(page_html: pathlib.Path) -> dict:
    summary_js = page_html.with_name("summary.js")
    text = summary_js.read_text(encoding="utf-8").strip()
    marker = "window.SO101_SUMMARY = "
    if not text.startswith(marker):
        raise SystemExit(f"{summary_js} is not a summary assignment")
    return json.loads(text[len(marker):].rstrip().rstrip(";"))


def render_texts(page_html: pathlib.Path) -> dict[str, str]:
    from playwright.sync_api import sync_playwright

    texts: dict[str, str] = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(page_html.resolve().as_uri(), wait_until="load")
        page.wait_for_function("window.SO101_PAGE !== undefined", timeout=60000)
        page.wait_for_timeout(1500)
        for panel in PANELS:
            texts[panel] = page.inner_text(f"#{panel}")
        browser.close()
    if errors:
        raise SystemExit("page raised: " + "; ".join(errors))
    return texts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--page", default="docs/demo/page/index.html")
    args = parser.parse_args(argv)
    page_html = pathlib.Path(args.page)
    summary = read_summary(page_html)
    texts = render_texts(page_html)
    bad = unmatched(summary, texts)
    if bad:
        print("numbers on the page with no source in the summary:")
        for line in bad:
            print(" ", line)
        return 1
    total = sum(len(page_numbers(t)) for t in texts.values())
    print(f"{total} numeric tokens across {', '.join(PANELS)} all trace to the summary")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
