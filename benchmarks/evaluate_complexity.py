"""RoboCAD complexity benchmark runner (Phase 8).

Runs the prompts in benchmarks/complexity_ladder.json through the current
AI → build123d pipeline and writes a structured baseline report.

Usage:
    python benchmarks/evaluate_complexity.py
    python benchmarks/evaluate_complexity.py --tier T3 --limit 3
    python benchmarks/evaluate_complexity.py --model qwen3-coder:latest --max-retries 2
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

# Load .env so the runner sees ROBOCAD_MODEL / ANTHROPIC_API_KEY.
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

# Ensure repo root is on sys.path for ai_cad imports.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_cad.api import RoboCADBackend


LADDER_PATH = Path(__file__).resolve().parent / "complexity_ladder.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "output" / "benchmarks"


def _load_ladder(path: Path = LADDER_PATH) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Complexity ladder not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _flatten_prompts(ladder: dict[str, Any]) -> list[dict[str, Any]]:
    """Return every prompt across all tiers as a flat list with tier context."""
    flat: list[dict[str, Any]] = []
    for tier in ladder.get("tiers", []):
        tier_name = tier["name"]
        for p in tier.get("prompts", []):
            flat.append({**p, "tier": tier_name})
    return flat


def _classify_failure(error: str | None, traceback: str | None, success: bool) -> str:
    if success:
        return "success"
    text = " ".join([error or "", traceback or ""]).lower()
    if "timed out" in text or "timeout" in text:
        return "timeout"
    if "anthropic_api_key" in text or "api key" in text or "not configured" in text:
        return "config"
    if "syntax" in text or "indent" in text or "parse" in text:
        return "syntax"
    if "no stl" in text or "watertight" in text or "manifold" in text or "could not compute" in text:
        return "geometry"
    if traceback and traceback.strip():
        return "runtime"
    if error:
        return "runtime"
    return "unknown"


def _estimate_feature_count(code: str | None) -> int:
    """Very rough heuristic for how many modeling operations the generated script contains."""
    if not code:
        return 0
    markers = [
        r"\bBox\s*\(",
        r"\bCylinder\s*\(",
        r"\bSphere\s*\(",
        r"\bCone\s*\(",
        r"\bextrude\s*\(",
        r"\bfillet\s*\(",
        r"\bchamfer\s*\(",
        r"\bshell\s*\(",
        r"\bGridLocations\s*\(",
        r"\bPolarLocations\s*\(",
        r"\bLocations\s*\(",
    ]
    total = 0
    for marker in markers:
        total += len(re.findall(marker, code))
    return total


def _run_single(
    backend: RoboCADBackend,
    prompt_item: dict[str, Any],
    max_retries: int,
    output_dir: Path,
    timeout: int = 90,
) -> dict[str, Any]:
    prompt_id = prompt_item["id"]
    prompt_text = prompt_item["prompt"]
    tier = prompt_item.get("tier", "unknown")

    run_output_dir = output_dir / prompt_id
    run_output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[{tier}] {prompt_id}: {prompt_text[:70]}...", flush=True)
    start = time.time()

    try:
        result = backend.generate(
            prompt_text,
            max_retries=max_retries,
            output_dir=run_output_dir,
            timeout=timeout,
        )
    except Exception as exc:
        return {
            "id": prompt_id,
            "tier": tier,
            "prompt": prompt_text,
            "success": False,
            "error": f"Runner crashed: {exc}",
            "traceback": None,
            "failure_mode": "runner_crash",
            "latency_seconds": round(time.time() - start, 3),
            "attempts_used": 0,
            "model": os.environ.get("ROBOCAD_MODEL", "unknown"),
            "parameter_count": 0,
            "estimated_features": 0,
            "manifold": None,
            "watertight": None,
            "validation_errors": [],
            "validation_warnings": [],
            "export_stl": None,
            "export_step": None,
            "export_script": None,
        }

    failure_mode = _classify_failure(result.error, result.traceback, result.success)
    validation = result.validation
    exports = result.exports

    return {
        "id": prompt_id,
        "tier": tier,
        "prompt": prompt_text,
        "success": result.success,
        "error": result.error,
        "traceback": result.traceback,
        "failure_mode": failure_mode,
        "latency_seconds": result.latency_seconds or round(time.time() - start, 3),
        "attempts_used": result.attempts_used,
        "model": result.model,
        "parameter_count": len(result.parameters),
        "estimated_features": _estimate_feature_count(result.code),
        "manifold": validation.manifold if validation else None,
        "watertight": validation.watertight if validation else None,
        "validation_errors": validation.errors if validation else [],
        "validation_warnings": validation.warnings if validation else [],
        "export_stl": str(exports.stl) if exports and exports.stl else None,
        "export_step": str(exports.step) if exports and exports.step else None,
        "export_script": str(exports.script) if exports and exports.script else None,
    }


def _summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    successes = sum(1 for r in results if r["success"])
    by_tier: dict[str, dict[str, Any]] = {}
    by_failure: dict[str, int] = {}
    latencies: list[float] = []

    for r in results:
        tier = r["tier"]
        if tier not in by_tier:
            by_tier[tier] = {"total": 0, "successes": 0, "latencies": []}
        by_tier[tier]["total"] += 1
        if r["success"]:
            by_tier[tier]["successes"] += 1
            latencies.append(r["latency_seconds"])
            by_tier[tier]["latencies"].append(r["latency_seconds"])
        by_failure[r["failure_mode"]] = by_failure.get(r["failure_mode"], 0) + 1

    tier_summary = {}
    for tier, data in by_tier.items():
        tier_summary[tier] = {
            "total": data["total"],
            "successes": data["successes"],
            "failures": data["total"] - data["successes"],
            "pass_rate": round(data["successes"] / max(data["total"], 1), 3),
            "avg_latency_s": round(sum(data["latencies"]) / max(len(data["latencies"]), 1), 2),
        }

    return {
        "total": total,
        "successes": successes,
        "failures": total - successes,
        "overall_pass_rate": round(successes / max(total, 1), 3),
        "avg_latency_s": round(sum(latencies) / max(len(latencies), 1), 2),
        "by_tier": tier_summary,
        "by_failure_mode": by_failure,
    }


def _write_markdown_report(
    results: list[dict[str, Any]],
    summary: dict[str, Any],
    output_path: Path,
    ladder: dict[str, Any],
) -> None:
    lines: list[str] = []
    lines.append("# RoboCAD Complexity Benchmark Report")
    lines.append("")
    lines.append(f"**Date:** {dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00', 'Z')}")
    lines.append(f"**Model:** {os.environ.get('ROBOCAD_MODEL', 'unknown')}")
    lines.append(f"**Max retries:** {ladder.get('max_retries', 'N/A')}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Total prompts:** {summary['total']}")
    lines.append(f"- **Successes:** {summary['successes']}")
    lines.append(f"- **Failures:** {summary['failures']}")
    lines.append(f"- **Overall pass rate:** {summary['overall_pass_rate'] * 100:.1f}%")
    lines.append(f"- **Average successful latency:** {summary['avg_latency_s']:.2f} s")
    lines.append("")
    lines.append("### By tier")
    lines.append("")
    lines.append("| Tier | Total | Successes | Failures | Pass rate | Avg latency (s) |")
    lines.append("|---|---|---|---|---|---|")
    for tier, data in summary["by_tier"].items():
        lines.append(
            f"| {tier} | {data['total']} | {data['successes']} | {data['failures']} | "
            f"{data['pass_rate'] * 100:.1f}% | {data['avg_latency_s']:.2f} |"
        )
    lines.append("")
    lines.append("### Failure modes")
    lines.append("")
    lines.append("| Failure mode | Count |")
    lines.append("|---|---|")
    for mode, count in summary["by_failure_mode"].items():
        lines.append(f"| {mode} | {count} |")
    lines.append("")
    lines.append("## Per-prompt results")
    lines.append("")
    lines.append(
        "| ID | Tier | Success | Mode | Attempts | Latency (s) | Params | Est. features | Manifold | Watertight |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in results:
        manifold = "✓" if r["manifold"] else ("✗" if r["manifold"] is False else "—")
        watertight = "✓" if r["watertight"] else ("✗" if r["watertight"] is False else "—")
        lines.append(
            f"| {r['id']} | {r['tier']} | {'✓' if r['success'] else '✗'} | {r['failure_mode']} | "
            f"{r['attempts_used']} | {r['latency_seconds']:.2f} | {r['parameter_count']} | "
            f"{r['estimated_features']} | {manifold} | {watertight} |"
        )
    lines.append("")
    lines.append("## Failure details")
    lines.append("")
    failures = [r for r in results if not r["success"]]
    if not failures:
        lines.append("No failures recorded.")
    for r in failures:
        lines.append(f"### {r['id']} ({r['tier']})")
        lines.append("")
        lines.append(f"**Prompt:** {r['prompt']}")
        lines.append("")
        lines.append(f"**Failure mode:** {r['failure_mode']}")
        if r["error"]:
            lines.append("")
            lines.append(f"**Error:** {r['error']}")
        if r["traceback"]:
            lines.append("")
            lines.append("```")
            lines.append(r["traceback"])
            lines.append("```")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the RoboCAD complexity benchmark.")
    parser.add_argument("--ladder", type=Path, default=LADDER_PATH, help="Path to complexity_ladder.json")
    parser.add_argument("--output", type=Path, default=None, help="Output directory")
    parser.add_argument("--model", type=str, default=None, help="Override model name")
    parser.add_argument("--max-retries", type=int, default=None, help="Override max retries")
    parser.add_argument("--tier", type=str, default=None, help="Run only prompts in this tier")
    parser.add_argument("--limit", type=int, default=None, help="Run only the first N prompts")
    parser.add_argument("--timeout", type=int, default=90, help="Execution timeout per prompt")
    args = parser.parse_args()

    ladder = _load_ladder(args.ladder)
    prompts = _flatten_prompts(ladder)

    if args.tier:
        prompts = [p for p in prompts if p["tier"] == args.tier]
        if not prompts:
            raise ValueError(f"No prompts found for tier: {args.tier}")
    if args.limit:
        prompts = prompts[: args.limit]

    max_retries = args.max_retries if args.max_retries is not None else ladder.get("max_retries", 2)
    model = args.model or os.environ.get("ROBOCAD_MODEL") or "unknown"
    os.environ["ROBOCAD_MODEL"] = model

    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_dir = args.output or DEFAULT_OUTPUT_DIR / f"run_{timestamp}"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    backend = RoboCADBackend(model=model)

    print(f"Running complexity benchmark with model={model}, max_retries={max_retries}, prompts={len(prompts)}")
    print(f"Results will be saved to: {output_dir}")
    print("")

    results: list[dict[str, Any]] = []
    for p in prompts:
        result = _run_single(backend, p, max_retries, output_dir, timeout=args.timeout)
        results.append(result)
        status = "OK" if result["success"] else result["failure_mode"]
        print(f"  -> {result['id']}: {status} ({result['latency_seconds']:.2f}s, {result['attempts_used']} attempt(s))", flush=True)

    summary = _summarize(results)

    # Save structured JSON.
    json_path = output_dir / "results.json"
    json_path.write_text(
        json.dumps(
            {
                "meta": {
                    "date": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
                    "model": model,
                    "max_retries": max_retries,
                    "prompt_count": len(prompts),
                    "schema_version": ladder.get("schema_version", "1.0.0"),
                },
                "summary": summary,
                "results": results,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # Save human-readable Markdown report.
    md_path = output_dir / "report.md"
    _write_markdown_report(results, summary, md_path, ladder)

    print("")
    print(f"Benchmark complete. JSON: {json_path}")
    print(f"Report: {md_path}")
    print("")
    print(f"Overall pass rate: {summary['overall_pass_rate'] * 100:.1f}% ({summary['successes']}/{summary['total']})")


if __name__ == "__main__":
    main()
