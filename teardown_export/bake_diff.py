"""Turn the revision diff into a payload the offline page can render.

The diff compares two compilations of the same robot at different print settings, keyed only on the
link names from the joints skeleton. Nothing is recomputed here: if the diff says a link got heavier,
that is what the page shows.
"""

from __future__ import annotations

import argparse
import json
import pathlib


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("diff", help="diff.json from the revision run")
    parser.add_argument("out", help="diff.js next to the page")
    args = parser.parse_args()

    data = json.loads(pathlib.Path(args.diff).read_text(encoding="utf-8"))
    links = data.get("links") or data.get("changes") or []

    rows = []
    for link in links:
        rows.append({
            "name": link.get("name") or link.get("link") or link.get("link_id"),
            "status": link.get("status", "changed"),
            "mass_before_kg": link.get("mass_before_kg"),
            "mass_after_kg": link.get("mass_after_kg"),
            "mass_delta_percent": link.get("mass_delta_percent"),
            "volume_delta_percent": link.get("volume_delta_percent"),
            "com_delta_mm": link.get("com_delta_mm"),
            "inertia_delta_percent": link.get("inertia_delta_percent"),
        })

    payload = {
        "schema": data.get("schema_version") or data.get("schema"),
        "before": data.get("before"),
        "after": data.get("after"),
        "totals": {"before_kg": data.get("total_before_kg"), "after_kg": data.get("total_after_kg")},
        "notes": data.get("notes", []),
        "links": rows,
    }
    out = pathlib.Path(args.out)
    out.write_text("window.SO101_REVISION = " + json.dumps(payload) + ";\n", encoding="utf-8")

    changed = [r for r in rows if r["status"] != "unchanged"]
    print(f"{out} {out.stat().st_size} bytes, {len(rows)} links, {len(changed)} changed")
    if rows and not changed:
        print("WARNING: a revision with no changed links is suspicious; the diff may be comparing a "
              "run against itself")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
