"""Turn the synthetic preview JSON into a classic script the offline page can load.

The page is opened from file://, where fetch() and ES modules are blocked, so the data has to arrive
as a script that assigns a global. Same constraint as the trajectory payload.
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

    data = json.loads(pathlib.Path(args.preview).read_text(encoding="utf-8"))
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
