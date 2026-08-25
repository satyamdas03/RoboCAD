"""A/B evaluate a specialized/fine-tuned model against the base model.

Runs the Phase 8 complexity benchmark twice (base vs specialized) and writes
a comparison report. Uses the test split from the training dataset by default,
otherwise runs the full complexity ladder.

Usage:
    python scripts/evaluate_finetuned.py --base-model qwen3-coder:latest --specialized-model robocad-ft:latest
    python scripts/evaluate_finetuned.py --dataset training/feature_tree_test.jsonl --base-model qwen3-coder:latest --specialized-model robocad-lora:latest
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_cad.api import RoboCADBackend
from benchmarks.evaluate_complexity import (
    _classify_failure,
    _flatten_prompts,
    _load_ladder,
    _summarize,
    _write_markdown_report,
)

LADDER_PATH = REPO_ROOT / "benchmarks" / "complexity_ladder.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "output" / "benchmarks"


def _load_test_prompts(dataset_path: Path | None) -> list[dict[str, Any]]:
    if dataset_path is None or not dataset_path.exists():
        ladder = _load_ladder(LADDER_PATH)
        return _flatten_prompts(ladder)
    rows: list[dict[str, Any]] = []
    with dataset_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            rows.append({
                "id": row["metadata"]["id"],
                "tier": row["metadata"]["tier"],
                "prompt": row["prompt"],
            })
    return rows


def _run_benchmark(
    model: str,
    prompts: list[dict[str, Any]],
    output_dir: Path,
    max_retries: int = 2,
    timeout: int = 120,
) -> list[dict[str, Any]]:
    backend = RoboCADBackend(model=model)
    results: list[dict[str, Any]] = []
    for p in prompts:
        prompt_id = p["id"]
        prompt_text = p["prompt"]
        tier = p.get("tier", "unknown")
        run_dir = output_dir / model.replace(":", "_") / prompt_id
        run_dir.mkdir(parents=True, exist_ok=True)

        print(f"[{model}] [{tier}] {prompt_id}: {prompt_text[:60]}...", flush=True)
        start = dt.datetime.now(dt.timezone.utc)
        try:
            result = backend.generate(
                prompt_text,
                max_retries=max_retries,
                output_dir=run_dir,
                timeout=timeout,
                use_feature_tree=True,
                use_assembly=False,
            )
        except Exception as exc:
            results.append({
                "id": prompt_id,
                "tier": tier,
                "prompt": prompt_text,
                "success": False,
                "error": f"Runner crashed: {exc}",
                "traceback": None,
                "failure_mode": "runner_crash",
                "latency_seconds": 0.0,
                "attempts_used": 0,
                "model": model,
            })
            continue

        failure_mode = _classify_failure(result.error, result.traceback, result.success)
        results.append({
            "id": prompt_id,
            "tier": tier,
            "prompt": prompt_text,
            "success": result.success,
            "error": result.error,
            "traceback": result.traceback,
            "failure_mode": failure_mode,
            "latency_seconds": result.latency_seconds or 0.0,
            "attempts_used": result.attempts_used,
            "model": result.model,
        })
        status = "OK" if result.success else failure_mode
        print(f"  -> {status} ({result.latency_seconds or 0:.2f}s)", flush=True)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="A/B evaluate a fine-tuned RoboCAD model.")
    parser.add_argument("--base-model", type=str, default="qwen3-coder:latest", help="Base Ollama model")
    parser.add_argument("--specialized-model", type=str, required=True, help="Specialized Ollama model")
    parser.add_argument("--dataset", type=Path, default=REPO_ROOT / "training" / "feature_tree_test.jsonl", help="Held-out test dataset JSONL")
    parser.add_argument("--output", type=Path, default=None, help="Output directory")
    parser.add_argument("--max-retries", type=int, default=2, help="Max retries per prompt")
    parser.add_argument("--timeout", type=int, default=120, help="Execution timeout per prompt")
    args = parser.parse_args()

    prompts = _load_test_prompts(args.dataset)
    if not prompts:
        raise ValueError("No test prompts found.")

    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_dir = args.output or DEFAULT_OUTPUT_DIR / f"finetune_eval_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"A/B evaluation: {len(prompts)} prompts")
    print(f"Base:        {args.base_model}")
    print(f"Specialized: {args.specialized_model}")
    print(f"Output:      {output_dir}")
    print("")

    base_results = _run_benchmark(args.base_model, prompts, output_dir, args.max_retries, args.timeout)
    spec_results = _run_benchmark(args.specialized_model, prompts, output_dir, args.max_retries, args.timeout)

    base_summary = _summarize(base_results)
    spec_summary = _summarize(spec_results)

    base_rate = base_summary["overall_pass_rate"]
    spec_rate = spec_summary["overall_pass_rate"]
    delta = spec_rate - base_rate

    comparison = {
        "meta": {
            "date": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
            "base_model": args.base_model,
            "specialized_model": args.specialized_model,
            "prompt_count": len(prompts),
            "dataset": str(args.dataset) if args.dataset else None,
        },
        "base_summary": base_summary,
        "specialized_summary": spec_summary,
        "delta": round(delta, 3),
        "target_met": delta >= 0.10,
        "base_results": base_results,
        "specialized_results": spec_results,
    }

    json_path = output_dir / "comparison.json"
    json_path.write_text(json.dumps(comparison, indent=2), encoding="utf-8")

    md_path = output_dir / "comparison_report.md"
    _write_comparison_markdown(md_path, comparison, base_results, spec_results)

    print("")
    print(f"Base pass rate:        {base_rate * 100:.1f}%")
    print(f"Specialized pass rate: {spec_rate * 100:.1f}%")
    print(f"Delta:                 {delta * 100:+.1f} percentage points")
    print(f"Target (>=+10pp):       {'MET' if comparison['target_met'] else 'NOT MET'}")
    print(f"JSON: {json_path}")
    print(f"Report: {md_path}")


def _write_comparison_markdown(
    path: Path,
    comparison: dict[str, Any],
    base_results: list[dict[str, Any]],
    spec_results: list[dict[str, Any]],
) -> None:
    meta = comparison["meta"]
    base = comparison["base_summary"]
    spec = comparison["specialized_summary"]
    delta = comparison["delta"]

    lines: list[str] = []
    lines.append("# RoboCAD Fine-Tuned Model A/B Evaluation")
    lines.append("")
    lines.append(f"**Date:** {meta['date']}")
    lines.append(f"**Base model:** {meta['base_model']}")
    lines.append(f"**Specialized model:** {meta['specialized_model']}")
    lines.append(f"**Prompts:** {meta['prompt_count']}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"| Model | Pass Rate | Successes | Failures | Avg Latency (s) |")
    lines.append("|---|---|---|---|---|")
    lines.append(
        f"| {meta['base_model']} | {base['overall_pass_rate'] * 100:.1f}% | {base['successes']} | {base['failures']} | {base['avg_latency_s']:.2f} |"
    )
    lines.append(
        f"| {meta['specialized_model']} | {spec['overall_pass_rate'] * 100:.1f}% | {spec['successes']} | {spec['failures']} | {spec['avg_latency_s']:.2f} |"
    )
    lines.append("")
    lines.append(f"**Delta:** {delta * 100:+.1f} percentage points")
    lines.append(f"**Target (>=+10pp):** {'[OK] MET' if comparison['target_met'] else '[FAIL] NOT MET'}")
    lines.append("")
    lines.append("## Per-prompt comparison")
    lines.append("")
    lines.append("| ID | Tier | Base | Specialized | Delta | Base mode | Specialized mode |")
    lines.append("|---|---|---|---|---|---|---|")
    for b, s in zip(base_results, spec_results):
        b_ok = "+" if b["success"] else "-"
        s_ok = "+" if s["success"] else "-"
        row_delta = (1 if s["success"] else 0) - (1 if b["success"] else 0)
        lines.append(
            f"| {b['id']} | {b['tier']} | {b_ok} | {s_ok} | {'+' if row_delta > 0 else ''}{row_delta} | {b['failure_mode']} | {s['failure_mode']} |"
        )
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
