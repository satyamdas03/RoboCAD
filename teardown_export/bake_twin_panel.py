"""Turn the twin JSON artefacts into classic scripts the offline page can load.

The page is opened from file://, where fetch() and ES modules are blocked, so the data has to arrive
as a script that assigns a global. Two payloads come out of this: the synthetic preview curves, and
the identification rung results.
"""

from __future__ import annotations

import argparse
import json
import pathlib


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("preview", help="synthetic_preview.json")
    parser.add_argument("out", help="twin.js path next to the page")
    args = parser.parse_args()

    preview_path = pathlib.Path(args.preview)
    data = json.loads(preview_path.read_text(encoding="utf-8"))
    overlay = data.get("overlay", {})
    slim = {
        "label": "SYNTHETIC",
        "hz": overlay.get("hz"),
        "frames": overlay.get("frames"),
        "joints": overlay.get("joints", []),
        "measured": overlay.get("measured", []),
        "uncalibrated": overlay.get("uncalibrated", []),
        "calibrated": overlay.get("calibrated", []),
        "trajectory_rmse_mrad_uncalibrated": data.get("trajectory_rmse_mrad_uncalibrated"),
        "trajectory_rmse_mrad_calibrated": data.get("trajectory_rmse_mrad_calibrated"),
        "identified": sum(1 for e in data.get("estimates", []) if e.get("identifiable")),
        "total": len(data.get("estimates", [])),
        "not_identifiable": data.get("not_identifiable", []),
        "disclaimer": data.get("disclaimer", ""),
    }
    out = pathlib.Path(args.out)
    out.write_text("window.SO101_SYNTHETIC = " + json.dumps(slim) + ";\n", encoding="utf-8")
    print(f"{out} {out.stat().st_size} bytes, {slim['identified']} of {slim['total']} parameters identified")

    ident_path = preview_path.with_name("identification.json")
    if not ident_path.exists():
        print("no identification.json beside the preview, skipping the rung payload")
        return 0

    ident = json.loads(ident_path.read_text(encoding="utf-8"))
    payload = {
        "label": "SYNTHETIC",
        "stopped_at": ident.get("stopped_at"),
        "rungs": [
            {"rung": r.get("rung"), "name": r.get("name"), "reached": r.get("reached"),
             "note": r.get("note", ""), "error_percent": r.get("error_percent", {})}
            for r in ident.get("rungs", [])
        ],
        "disclaimer": ident.get("disclaimer", ""),
    }
    ident_out = out.parent / "identification.js"
    ident_out.write_text("window.SO101_IDENT = " + json.dumps(payload) + ";\n", encoding="utf-8")
    passed = sum(1 for r in payload["rungs"] if r["reached"])
    print(f"{ident_out} {ident_out.stat().st_size} bytes, {passed} of {len(payload['rungs'])} rungs recovered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
