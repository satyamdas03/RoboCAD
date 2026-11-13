"""Build the emailable demo package and prove it opens from somewhere else.

"One link" actually means one zip that a recipient can open from any folder, so the test that
matters is not that the files exist here, it is that the copy opens there, from file://, with the
network off and every relative link resolving. This script does the copy, the zip, the unpack into a
fresh temporary directory, and the browser check, in that order.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import tempfile
import zipfile


def _copy(src: pathlib.Path, dest: pathlib.Path, repo: pathlib.Path) -> None:
    """Copy one artefact into the package, refusing anything that could leak out of the repo.

    A distributable archive is a publishing surface, so a symlink or a path that resolves outside
    the repository is exactly the kind of thing that would put a credential or a home-directory file
    into a zip someone emails. Both are refused loudly rather than copied.
    """
    if not src.exists():
        print(f"MISSING, skipped: {src}")
        return
    if src.is_symlink():
        raise SystemExit(f"refusing to package a symlink: {src}")
    resolved = src.resolve()
    if not resolved.is_relative_to(repo):
        raise SystemExit(f"refusing to package a path outside the repository: {resolved}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if resolved.is_dir():
        for child in resolved.rglob("*"):
            if child.is_symlink():
                raise SystemExit(f"refusing to package a symlink inside a directory: {child}")
        shutil.copytree(resolved, dest, dirs_exist_ok=True)
    else:
        shutil.copy2(resolved, dest)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--out", default="docs/demo/so101_demo")
    parser.add_argument("--zip", default="docs/demo/so101_demo.zip")
    args = parser.parse_args()

    repo = pathlib.Path(args.repo).resolve()
    out = repo / args.out
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    wanted = {
        "index.html": "docs/demo/page/index.html",
        "trajectory.js": "docs/demo/page/trajectory.js",
        "meshes.js": "docs/demo/page/meshes.js",
        "three.min.js": "docs/demo/page/three.min.js",
        "report.js": "docs/demo/page/report.js",
        "torque.js": "docs/demo/page/torque.js",
        "twin.js": "docs/demo/page/twin.js",
        "identification.js": "docs/demo/page/identification.js",
        "film.mp4": "docs/demo/film/so101_demo.mp4",
        "report.html": "docs/twin/so101/bundle/report.html",
        "report.json": "docs/twin/so101/bundle/report.json",
        "comparison.json": "docs/twin/so101/bundle/comparison.json",
        "comparison.md": "docs/demo/so101_vs_official.md",
        "identifiability.md": "docs/twin/so101/identifiability.md",
        "NOTICE.md": "docs/twin/so101/NOTICE.md",
        "diff.js": "docs/demo/page/diff.js",
    }
    for name, rel in wanted.items():
        _copy(repo / rel, out / name, repo)

    # optional artefacts: present only when the other lane has produced them
    for name, rel in {"diff.md": "docs/twin/so101/revision_f030/diff.md",
                      "diff.json": "docs/twin/so101/revision_f030/diff.json",
                      "CONVENTIONS.md": "docs/twin/so101/CONVENTIONS.md"}.items():
        _copy(repo / rel, out / name, repo)

    _copy(repo / "docs/demo/README.md", out / "README.md", repo)

    index = out / "index.html"
    if index.exists():
        html = index.read_text(encoding="utf-8")
        html = html.replace("<h1>SO-101 living page</h1>", "<h1>SO-101 living page</h1>")
        # a visible index of the packaged documents, so a recipient is not left guessing
        # append the document links AFTER the existing header: replacing it once removed the
        # provenance element the page's own script reads, and the page then failed to initialise in
        # the unpacked copy while working perfectly in the repo. That is exactly what the package
        # test exists to catch.
        nav = (
            '<div style="grid-column:1/-1;display:flex;gap:14px;flex-wrap:wrap;padding:6px 16px 8px;'
            'border-bottom:1px solid #1e2633;font-size:12px;color:#8b97a8">'
            '<span>packaged demo:</span>'
            '<a href="README.md" style="color:#57d3a0">3 minute script</a>'
            '<a href="film.mp4" style="color:#57d3a0">film</a>'
            '<a href="report.html" style="color:#57d3a0">7 check report</a>'
            '<a href="comparison.md" style="color:#57d3a0">vs official</a>'
            '<a href="identifiability.md" style="color:#57d3a0">what data we need</a>'
            '<a href="NOTICE.md" style="color:#57d3a0">notices</a>'
            '</div>'
        )
        end = html.find("</header>")
        if end != -1:
            insert_at = end + len("</header>")
            html = html[:insert_at] + chr(10) + nav + html[insert_at:]
            index.write_text(html, encoding="utf-8")

    zip_path = repo / args.zip
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(out.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(out.parent))

    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    size_mb = zip_path.stat().st_size / 1e6
    print(f"zip {zip_path} {size_mb:.1f} MB sha256 {digest}")

    # unpack somewhere else entirely and open it there
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="so101_pkg_"))
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(tmp)
    root = tmp / out.name
    if not (root / "index.html").exists():
        print("FAIL: no index.html after extract")
        return 2

    from playwright.sync_api import sync_playwright

    errors, external = [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_context(viewport={"width": 1280, "height": 900}, offline=True).new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(f"console {m.type}: {m.text}") if m.type == "error" else None)
        page.on("request", lambda r: external.append(r.url) if not r.url.startswith("file://") else None)
        page.goto((root / "index.html").as_uri(), wait_until="load")
        page.wait_for_function("window.SO101_PAGE !== undefined", timeout=30000)
        panels = page.evaluate(
            "({checks: document.querySelectorAll('#checks .check').length,"
            " links: document.querySelectorAll('#links .row').length,"
            " cmp: document.getElementById('cmp').innerText.length,"
            " torque: document.getElementById('torque-grp').innerText.length,"
            " ident: document.querySelectorAll('#ident .check').length})")
        links = page.evaluate(
            "Array.from(document.querySelectorAll('header a')).map(a=>a.getAttribute('href'))")
        missing = [h for h in links if not (root / h).exists()]
        browser.close()

    print(json.dumps({"panels": panels, "page_errors": errors, "external_requests": external,
                      "missing_relative_links": missing, "unpacked_at": str(root)}, indent=2))
    ok = not errors and not external and not missing and panels["checks"] == 7 and panels["links"] >= 7
    print("PACKAGE OK" if ok else "PACKAGE PROBLEM")
    return 0 if ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
