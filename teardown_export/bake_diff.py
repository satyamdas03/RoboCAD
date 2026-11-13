"""Turn the revision diff into a payload the offline page can render.

Fails closed. If the producer says the two runs are not comparable, or lists sanity failures, this
bakes nothing and exits non-zero: a revision panel showing numbers from an incomparable pair is worse
than no panel, because it looks like evidence.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("diff", help="diff.json from the revision run")
    parser.add_argument("out", help="diff.js next to the page")
    args = parser.parse_args()

    data = json.loads(pathlib.Path(args.diff).read_text(encoding="utf-8"))

    comparable = data.get("comparable")
    failures = data.get("sanity_failures") or []
    if comparable is False or failures:
        print("refusing to bake: the producer says this revision is not comparable", file=sys.stderr)
        for failure in failures:
            print(f"  sanity failure: {failure}", file=sys.stderr)
        return 2

    added = data.get("added") or []
    removed = data.get("removed") or []
    links = data.get("links") or []

    rows = []
    for link in links:
        rows.append({
            "name": link.get("link_id") or link.get("name"),
            # no default: a row whose status the producer did not state is unknown, not "changed"
            "status": link.get("status"),
            "printed_parts": link.get("printed_parts"),
            "mass_before_kg": link.get("mass_before_kg"),
            "mass_after_kg": link.get("mass_after_kg"),
            "mass_delta_kg": link.get("mass_delta_kg"),
            "mass_delta_percent": link.get("mass_delta_percent"),
            "com_delta_mm": link.get("com_delta_mm"),
            "inertia_diagonal_delta_percent": link.get("inertia_diagonal_delta_percent"),
            "inertia_delta_percent": link.get("inertia_delta_percent",
                                              link.get("inertia_diagonal_delta_percent")),
        })

    payload = {
        "schema": data.get("schema_version") or data.get("schema"),
        "before": data.get("before"),
        "after": data.get("after"),
        "keyed_on": data.get("keyed_on"),
        "added": added,
        "removed": removed,
        "comparable": comparable,
        "sanity": data.get("sanity", []),
        "sanity_failures": failures,
        # keep the producer's totals and add the flat names a verifier will look for
        "totals": {
            **(data.get("totals") or {}),
            "mass_before_kg": (data.get("totals") or {}).get("mass_before_kg"),
            "mass_after_kg": (data.get("totals") or {}).get("mass_after_kg"),
        },
        "effort": data.get("effort", {}),
        "notes": data.get("notes", []),
        "links": rows,
    }
    out = pathlib.Path(args.out)
    out.write_text("window.SO101_REVISION = " + json.dumps(payload) + ";\n", encoding="utf-8")

    deltas = [r["mass_delta_percent"] for r in rows if isinstance(r.get("mass_delta_percent"), (int, float))]
    print(f"{out} {out.stat().st_size} bytes, {len(rows)} links, "
          f"{len(added)} added, {len(removed)} removed")
    if deltas:
        print(f"mass delta percent: min {min(deltas):+.2f}, max {max(deltas):+.2f}")
    if not deltas:
        print("WARNING: no numeric mass deltas in this diff; the panel will show link names only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
