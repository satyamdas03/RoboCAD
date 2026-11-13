"""Verify the packaged demo zip the way an outsider would: from the zip alone.

A6 of the final sprint. The point is not to re-run the compiler, it is to check that the artifact we
hand someone contains numbers that hold up when nothing else is available. So this extracts the zip
into a fresh empty directory and reads only what is inside it: the page, its baked JSON and the
revision payload. It never reads the working tree, so a page that was baked from a stale report is a
failure here rather than a surprise later.

Three numbers are named before any of them is computed, so the choice cannot flatter the result:

  1. printed mass ................ 0.901658836 kg, the sum of the seven body masses
  2. revision printed mass ....... 0.901658836 -> 0.955453030 kg, +5.97%
  3. check rows .................. 7 rows: 5 pass, 1 fail, 1 skipped

Each is re-derived from the artifacts in the zip and compared against what the page renders. A number
the page displays that its own JSON does not support is the failure this script exists to catch.

Run:

    python scripts/verify_demo_zip.py docs/demo/so101_demo.zip
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import tempfile
import zipfile

# Named before computing, per the sprint order.
EXPECTED_PRINTED_KG = 0.901658836
EXPECTED_REVISION_KG = (0.901658836, 0.955453030)
EXPECTED_CHECK_ROWS = {"pass": 5, "fail": 1, "skipped": 1}

# A zip an outsider hands us can lie about how much it expands to. The package is 4 MB and its
# contents are 7 MB, so anything past this is not the demo and is not read.
MAX_EXPANDED_BYTES = 512 * 1024 * 1024


def _extract(zip_path: pathlib.Path) -> pathlib.Path:
    """Unpack into a directory nobody has touched, and refuse anything that escapes it."""
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="a6_verify_"))
    with zipfile.ZipFile(zip_path) as zf:
        infos = zf.infolist()
        expanded = sum(member.file_size for member in infos)
        if expanded > MAX_EXPANDED_BYTES:
            raise SystemExit(
                f"refusing to extract: {expanded} bytes expanded is past the {MAX_EXPANDED_BYTES} cap"
            )
        for member in infos:
            name = member.filename
            if name.startswith("/") or ".." in pathlib.PurePosixPath(name).parts:
                raise SystemExit(f"refusing to extract {name!r}: it escapes the archive root")
            if member.external_attr >> 16 & 0o170000 == 0o120000:
                raise SystemExit(f"refusing to extract {name!r}: it is a symlink")
        zf.extractall(tmp)
    roots = [p for p in tmp.iterdir() if p.is_dir()]
    if len(roots) != 1:
        raise SystemExit(f"expected one top-level directory in the zip, found {[p.name for p in roots]}")
    return roots[0]


def _check_row_statuses(root: pathlib.Path) -> tuple[dict[str, int], dict]:
    """Count check statuses from the page's own baked report, not from the HTML markup."""
    payload = (root / "report.js").read_text(encoding="utf-8")
    marker = "window.SO101_REPORT = "
    data = json.loads(payload[len(marker):].rstrip().rstrip(";"))
    counts: dict[str, int] = {}
    for check in data["checks"]:
        status = check.get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts, data


def _mass_numbers(data: dict) -> tuple[float, float]:
    bodies = data["bodies"]
    return sum(b["mass_kg"] for b in bodies), data["totals"]["total_mass_kg"]


def _revision(root: pathlib.Path) -> dict | None:
    path = root / "diff.js"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8").strip()
    marker = "window.SO101_REVISION = "
    if not text.startswith(marker):
        return None
    body = text[len(marker):].rstrip().rstrip(";")
    if body in ("null", ""):
        return None
    return json.loads(body)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip", help="packaged demo zip")
    parser.add_argument("--out", default=None, help="where to write verify.json")
    args = parser.parse_args(argv)

    zip_path = pathlib.Path(args.zip)
    print(f"zip        {zip_path}")
    print(f"sha256     {hashlib.sha256(zip_path.read_bytes()).hexdigest()}")
    print(f"bytes      {zip_path.stat().st_size}")
    print()
    print("named before computing:")
    print(f"  1. printed mass {EXPECTED_PRINTED_KG:.9f} kg")
    print(f"  2. revision {EXPECTED_REVISION_KG[0]:.9f} -> {EXPECTED_REVISION_KG[1]:.9f} kg")
    print(f"  3. check rows {EXPECTED_CHECK_ROWS}")
    print()

    root = _extract(zip_path)
    failures: list[str] = []

    statuses, report = _check_row_statuses(root)
    body_sum, reported_total = _mass_numbers(report)

    print(f"extracted  {root}")
    print()

    # 1. Printed mass: the seven body masses must sum to the total the page prints.
    ok = abs(body_sum - reported_total) < 1e-6 and abs(reported_total - EXPECTED_PRINTED_KG) < 1e-6
    print(f"[{'PASS' if ok else 'FAIL'}] 1  printed mass  sum(bodies) {body_sum:.9f} kg, "
          f"totals {reported_total:.9f} kg, expected {EXPECTED_PRINTED_KG:.9f} kg")
    if not ok:
        failures.append("printed mass: the page's body masses and its own total disagree, or the total moved")

    # 2. Revision: the baked payload must carry the same totals the diff artifact states.
    revision = _revision(root)
    if revision is None:
        print("[FAIL] 2  revision       the package carries no revision payload "
              "(diff.js is missing or null)")
        failures.append("revision: no revision payload in the package")
    else:
        totals = revision.get("totals") or {}
        before = totals.get("mass_before_kg")
        after = totals.get("mass_after_kg")
        ok = (
            before is not None
            and after is not None
            and abs(before - EXPECTED_REVISION_KG[0]) < 1e-6
            and abs(after - EXPECTED_REVISION_KG[1]) < 1e-6
        )
        rows = revision.get("links") or []
        print(f"[{'PASS' if ok else 'FAIL'}] 2  revision       {before:.9f} -> {after:.9f} kg "
              f"over {len(rows)} link(s), expected {EXPECTED_REVISION_KG[0]:.9f} -> "
              f"{EXPECTED_REVISION_KG[1]:.9f} kg")
        if not ok:
            failures.append("revision: baked totals do not match the named numbers")

    # 3. Check rows: the page's own report must have seven, in the named split.
    ok = statuses == EXPECTED_CHECK_ROWS
    print(f"[{'PASS' if ok else 'FAIL'}] 3  check rows     {statuses}, expected {EXPECTED_CHECK_ROWS}")
    if not ok:
        failures.append("checks: the baked report's status split is not the named one")

    # 4. The page must open from file:// with no network and no console errors, and the revision
    #    panel must render rather than sit empty.
    from playwright.sync_api import sync_playwright

    errors: list[str] = []
    external: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_context(viewport={"width": 1280, "height": 900}, offline=True).new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on(
            "console",
            lambda m: errors.append(f"console {m.type}: {m.text}") if m.type == "error" else None,
        )
        page.on(
            "request",
            lambda r: external.append(r.url) if not r.url.startswith("file://") else None,
        )
        page.goto((root / "index.html").as_uri(), wait_until="load")
        page.wait_for_function("window.SO101_PAGE !== undefined", timeout=30000)
        checks = page.evaluate("document.querySelectorAll('#checks .check').length")
        links = page.evaluate("document.querySelectorAll('#links .row').length")
        missing = page.evaluate(
            "Array.from(document.querySelectorAll('header a')).map(a=>a.getAttribute('href'))"
        )
        browser.close()

    absent = [h for h in missing if not (root / h).exists()]
    ok = not errors and not external and not absent and checks == 7 and links >= 7
    print(f"[{'PASS' if ok else 'FAIL'}] 4  page opens    {checks} check rows rendered, "
          f"{links} link rows, {len(errors)} page error(s), {len(external)} non-file request(s), "
          f"{len(absent)} missing relative link(s)")
    for error in errors[:5]:
        print(f"        page error: {error}")
    for url in external[:5]:
        print(f"        external:   {url}")
    if not ok:
        failures.append("page: did not open clean from file:// or a panel did not render")

    result = {
        "zip": str(zip_path),
        "sha256": hashlib.sha256(zip_path.read_bytes()).hexdigest(),
        "named": {
            "printed_kg": EXPECTED_PRINTED_KG,
            "revision_kg": list(EXPECTED_REVISION_KG),
            "check_rows": EXPECTED_CHECK_ROWS,
        },
        "measured": {
            "printed_kg": reported_total,
            "body_sum_kg": body_sum,
            "revision": (revision or {}).get("totals"),
            "check_rows": statuses,
            "checks_rendered": checks,
            "links_rendered": links,
            "page_errors": errors,
            "external_requests": external,
            "missing_relative_links": absent,
        },
        "failures": failures,
        "ok": not failures,
    }
    if args.out:
        pathlib.Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"wrote      {args.out}")

    print()
    print("VERIFIED" if not failures else "FAILED: " + "; ".join(failures))
    return 0 if not failures else 2


if __name__ == "__main__":
    sys.exit(main())
