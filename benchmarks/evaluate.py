"""Run the RoboCAD Phase 1 benchmark over a curated prompt set."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

# Allow running from repo root without install.
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from ai_cad.api import RoboCADBackend
from ai_cad.models import GenerationResult


PROMPTS_PATH = Path(__file__).with_name("prompts.json")
OUTPUT_DIR = Path("output") / "benchmarks"


def load_prompts(path: Path = PROMPTS_PATH) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_benchmark(
    backend: RoboCADBackend,
    prompts: list[dict[str, Any]],
    output_dir: Path = OUTPUT_DIR,
    max_retries: int = 2,
) -> dict[str, Any]:
    """Evaluate every prompt and return a structured summary."""
    output_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []

    print(f"Running Phase 1 benchmark on {len(prompts)} prompts...\n")

    for idx, item in enumerate(prompts, start=1):
        prompt_text = item["prompt"]
        print(f"[{idx}/{len(prompts)}] {item['id']}: {prompt_text}")

        result = backend.generate(
            prompt_text,
            max_retries=max_retries,
            output_dir=output_dir,
        )

        entry = {
            "id": item["id"],
            "difficulty": item["difficulty"],
            "concept": item["concept"],
            "prompt": prompt_text,
            "success": result.success,
            "attempts_used": result.attempts_used,
            "latency_seconds": result.latency_seconds,
            "error": result.error,
            "bounds": result.validation.bounds_mm if result.validation else None,
            "volume": result.validation.volume_mm3 if result.validation else None,
            "exports": result.exports.model_dump(),
            "validation": result.validation.model_dump() if result.validation else None,
            "parameters": [p.model_dump() for p in result.parameters],
            "code": result.code,
        }
        entries.append(entry)

        status = "PASS" if result.success else "FAIL"
        print(
            f"  -> {status} (attempts={result.attempts_used}, "
            f"latency={result.latency_seconds}s)"
        )
        if result.error:
            print(f"     error: {result.error[:200]}")
        print()

    passed = sum(1 for e in entries if e["success"])
    total = len(entries)
    by_difficulty: dict[str, dict[str, int]] = {}
    for e in entries:
        diff = e["difficulty"]
        bucket = by_difficulty.setdefault(diff, {"passed": 0, "total": 0})
        bucket["total"] += 1
        if e["success"]:
            bucket["passed"] += 1

    summary = {
        "total": total,
        "passed": passed,
        "accuracy": passed / total if total else 0.0,
        "max_retries": max_retries,
        "by_difficulty": by_difficulty,
        "entries": entries,
    }

    summary_path = output_dir / "phase1_results.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"Phase 1 result: {passed}/{total} prompts passed ({summary['accuracy']:.1%})")
    for diff, stats in sorted(by_difficulty.items()):
        print(f"  {diff}: {stats['passed']}/{stats['total']} passed")
    print(f"Detailed results written to {summary_path}")

    return summary


def main() -> int:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: set ANTHROPIC_API_KEY environment variable.")
        return 1

    model = os.environ.get("ROBOCAD_MODEL")
    backend = RoboCADBackend(api_key=api_key, model=model)
    prompts = load_prompts()
    summary = run_benchmark(backend, prompts)
    return 0 if summary["accuracy"] >= 0.95 else 1


if __name__ == "__main__":
    raise SystemExit(main())
