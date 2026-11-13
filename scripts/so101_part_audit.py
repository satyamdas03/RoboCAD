"""Per-part audit of an imported STEP assembly: volume, collision fill, and role.

Two questions this answers, both of which the twin report otherwise asserts without showing:

* How much bigger is the collision mesh than the part it stands for? A fill many times the solid's
  volume is an over-approximation, and an overlap between two such hulls may be an artefact of the
  approximation rather than an interference in the CAD. The report says which parts are inflated and
  by how much instead of only naming the overlapping pair.
* What is each part, as far as its name says? Printed link, actuator, or fastener decides what the
  density assumption means for that part's mass.

Run:

    python scripts/so101_part_audit.py --step path/to/so101.step --out audit.json
    python scripts/so101_part_audit.py --step ... --only jaw,wrist   # hull building is the slow part
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ai_cad.compiler.collision import collision_mesh
from ai_cad.importers.joints import classify_part
from ai_cad.importers.step_import import import_step


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--step", required=True)
    parser.add_argument("--out", default="so101_part_audit.json")
    parser.add_argument(
        "--only",
        default=None,
        help="comma separated part-name fragments; skips the rest (hull building is the slow part)",
    )
    args = parser.parse_args(argv)

    assembly = import_step(args.step)
    wanted = [s.strip().lower() for s in args.only.split(",")] if args.only else None
    rows = []
    for part in assembly.parts.values():
        row = {
            "part_id": part.part_id,
            "name": part.name,
            "role": classify_part(part.name),
            "solid_volume_m3": part.signature.volume_m3,
        }
        if wanted is None or any(w in part.name.lower() for w in wanted):
            mesh = collision_mesh(part)
            row.update(
                {
                    "hulls": mesh.hull_count,
                    "method": mesh.method,
                    "hull_volume_m3": sum(h.volume_m3 for h in mesh.hulls),
                    "fill": mesh.fill_ratio,
                    "closed": mesh.closed,
                }
            )
        rows.append(row)
    rows.sort(key=lambda r: (r.get("fill") is None, -(r.get("fill") or 0.0)))
    Path(args.out).write_text(json.dumps(rows, indent=2), encoding="utf-8")
    for row in rows[:25]:
        fill = row.get("fill")
        print(
            f"{row['part_id']:>9}  {row['role']:<12} {row['name'][:44]:<44} "
            f"{row['solid_volume_m3'] * 1e6:8.1f} cm3  "
            f"{'—' if fill is None else f'{fill:6.2f}x'}"
        )
    print(f"{len(rows)} parts, written to {Path(args.out).resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
