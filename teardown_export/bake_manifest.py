"""Turn the bundle's manifest.json into a script the offline page can load.

The page needs two things out of the manifest: the conventions block it must apply rather than keep
a private copy of, and the tag the package was cut from. It cannot fetch the JSON: the page is opened
from file://, where fetch() and ES modules are blocked and a plain <script> is not. So the manifest is
baked into a script assignment, next to the other payloads.

The tag is written by the packager (`--tag`, which it checks against the repository's own tag ref)
rather than by this script guessing it. A page that prints a tag nobody created is worse than a page
that says it does not know one, so with no tag the field is null and the page says so.
"""

from __future__ import annotations

import argparse
import json
import pathlib


def bake(manifest_path: pathlib.Path, out: pathlib.Path, tag: str | None) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload = dict(manifest)
    payload["package"] = {"tag": tag, "manifest_digest_source": manifest_path.name}
    out.write_text("window.SO101_MANIFEST = " + json.dumps(payload) + ";\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", help="the bundle's manifest.json")
    parser.add_argument("out", help="manifest.js path next to the page")
    parser.add_argument("--tag", default=None, help="the tag this package is cut from, if any")
    args = parser.parse_args(argv)
    payload = bake(pathlib.Path(args.manifest), pathlib.Path(args.out), args.tag)
    print(f"{args.out} {pathlib.Path(args.out).stat().st_size} bytes, "
          f"tag {payload['package']['tag'] or 'not recorded'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
