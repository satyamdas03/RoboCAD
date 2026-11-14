"""Turn a compiled bundle's report into the page payload: checks, totals, comparison, revision.

The page is opened from file://, so this data arrives as a classic script that assigns a global.
Nothing here recomputes a number; every value is copied from report.json so the page and the report
cannot disagree.
"""

from __future__ import annotations

import argparse
import json
import pathlib


def _checks(report: dict) -> list[dict]:
    out = []
    for c in report.get("checks", []):
        out.append({
            "id": c.get("id"),
            "status": c.get("status"),
            "measured": c.get("measured", {}),
            "threshold": c.get("threshold", {}),
            "explanation": c.get("explanation", ""),
        })
    return out


def _bodies(report: dict) -> list[dict]:
    out = []
    for b in report.get("bodies", []):
        out.append({
            "name": b.get("name"),
            "mass_kg": b.get("mass_kg"),
            "assumed_density": b.get("assumed_density", False),
            "parts": b.get("parts"),
            "instances": b.get("instances"),
            "hulls": b.get("hulls"),
            "solid_volume_m3": b.get("solid_volume_m3"),
            "com_m": b.get("com_m"),
        })
    return out


def _comparison(comp: dict | None) -> dict | None:
    if not comp:
        return None
    return {
        "ours_total_kg": comp.get("ours_total_kg"),
        "theirs_total_kg": comp.get("theirs_total_kg"),
        "delta_kg": comp.get("delta_kg"),
        "delta_percent": comp.get("delta_percent"),
        "bodies": [
            {
                "ours": b.get("ours"),
                "theirs": b.get("theirs"),
                "ours_kg": b.get("ours_kg"),
                "ours_solid_mass_kg": b.get("ours_solid_mass_kg"),
                "ours_printed_upper_kg": b.get("ours_printed_upper_kg"),
                "theirs_kg": b.get("theirs_kg"),
                "delta_percent": b.get("delta_percent"),
                "assumed_density": b.get("assumed_density", False),
                "implied_fill": b.get("implied_fill"),
                "printed_fill": b.get("printed_fill"),
                "bought_in_parts": b.get("bought_in_parts"),
                "servos_on_body": b.get("servos_on_body"),
            }
            for b in comp.get("bodies", [])
        ],
        "alignment": comp.get("alignment"),
        "link_spacings": comp.get("link_spacings", []),
        "ours_solid_total_kg": sum(b.get("ours_solid_mass_kg") or 0.0 for b in comp.get("bodies", [])),
        "ours_print_total_kg": sum(b.get("ours_kg") or 0.0 for b in comp.get("bodies", [])),
        "joints": [
            {
                "ours": j.get("ours"),
                "theirs": j.get("theirs"),
                "axis_angle_deg": j.get("axis_angle_deg"),
            }
            for j in comp.get("joints", [])
        ],
        "notes": comp.get("notes", []),
    }


def _revision(rev: dict | None) -> dict | None:
    if not rev:
        return None
    changed = [l for l in rev.get("links", []) if l.get("status") != "unchanged"]
    return {
        "before": rev.get("before"),
        "after": rev.get("after"),
        "changed": [
            {
                "name": l.get("name"),
                "status": l.get("status"),
                "mass_before_kg": l.get("mass_before_kg"),
                "mass_after_kg": l.get("mass_after_kg"),
                "mass_delta_percent": l.get("mass_delta_percent"),
                "volume_delta_percent": l.get("volume_delta_percent"),
            }
            for l in changed
        ],
        "notes": rev.get("notes", []),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", help="report.json from a compiled bundle")
    parser.add_argument("out", help="report.js next to the page")
    parser.add_argument("--bundle", default=None, help="bundle.json, for the model name and warnings")
    args = parser.parse_args(argv)

    report = json.loads(pathlib.Path(args.report).read_text(encoding="utf-8"))
    bundle = {}
    if args.bundle:
        bundle = json.loads(pathlib.Path(args.bundle).read_text(encoding="utf-8"))

    checks = _checks(report)
    worst = "pass"
    order = {"pass": 0, "skipped": 1, "warn": 2, "fail": 3}
    for c in checks:
        if order.get(c["status"], 0) > order.get(worst, 0):
            worst = c["status"]

    payload = {
        "schema": report.get("schema") or report.get("schema_version"),
        "name": report.get("name") or bundle.get("name"),
        "generated_at": report.get("generated_at"),
        "totals": report.get("totals", {}),
        "worst_check": worst,
        "checks": checks,
        "bodies": _bodies(report),
        # kept apart: one list concatenated onto the other reads as a doubled count, and a reader
        # has no way to tell which warnings belong to the report and which to the assembly import
        "warnings": report.get("warnings", []),
        "assembly_warnings": bundle.get("warnings", []),
        "warnings_total": len(report.get("warnings", [])) + len(bundle.get("warnings", [])),
        "notes": report.get("notes", []),
        "comparison": _comparison(report.get("comparison")),
        "revision": _revision(report.get("revision")),
        "source": report.get("source", {}),
        "compiled": True,
    }
    out = pathlib.Path(args.out)
    out.write_text("window.SO101_REPORT = " + json.dumps(payload) + ";\n", encoding="utf-8")
    print(f"{out} {out.stat().st_size} bytes")
    print(f"checks {len(checks)}, worst {worst}, comparison "
          f"{'yes' if payload['comparison'] else 'no'}, revision {'yes' if payload['revision'] else 'no'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
