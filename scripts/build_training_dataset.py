"""Build a supervised-finetuning dataset from RoboCAD complexity-ladder prompts.

Runs each prompt through the feature-tree generation path, keeps only successful
runs that produced a valid feature tree and manifold geometry, and writes the
result as JSONL for downstream few-shot prompting or LoRA fine-tuning.

Usage:
    python scripts/build_training_dataset.py
    python scripts/build_training_dataset.py --ladder benchmarks/complexity_ladder.json --output training/feature_tree_dataset.jsonl
    python scripts/build_training_dataset.py --limit 10 --test-split 0.2
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

# Load .env so the runner sees ROBOCAD_MODEL / ANTHROPIC_API_KEY.
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_cad.api import RoboCADBackend
from ai_cad.feature_tree import FeatureTree

LADDER_PATH = REPO_ROOT / "benchmarks" / "complexity_ladder.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "training"


def _load_ladder(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Complexity ladder not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _flatten_prompts(ladder: dict[str, Any]) -> list[dict[str, Any]]:
    flat: list[dict[str, Any]] = []
    for tier in ladder.get("tiers", []):
        tier_name = tier["name"]
        for p in tier.get("prompts", []):
            flat.append({**p, "tier": tier_name})
    return flat


def _run_single(
    backend: RoboCADBackend,
    prompt_item: dict[str, Any],
    output_dir: Path,
    timeout: int = 120,
    max_retries: int = 2,
) -> dict[str, Any] | None:
    prompt_id = prompt_item["id"]
    prompt_text = prompt_item["prompt"]
    tier = prompt_item.get("tier", "unknown")

    run_output_dir = output_dir / prompt_id
    run_output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[{tier}] {prompt_id}: {prompt_text[:70]}...", flush=True)

    # Generate a Feature-Tree JSON directly (not through the legacy code fallback).
    from ai_cad.generator import generate_feature_tree, self_correct_feature_tree

    start = dt.datetime.now(dt.timezone.utc)
    gen = generate_feature_tree(prompt_text, model=backend.model)
    attempts_used = 1

    tree: Any = None
    while True:
        if not gen["success"]:
            print(f"  -> generation failed: {gen.get('error')}", flush=True)
            return None
        json_text = gen.get("feature_tree")
        if json_text is None:
            print(f"  -> no JSON extracted", flush=True)
            return None
        try:
            tree_data = json.loads(json_text)
            tree = FeatureTree(**tree_data)
        except Exception as exc:
            print(f"  -> invalid FeatureTree JSON: {exc}", flush=True)
            if attempts_used <= max_retries:
                gen = self_correct_feature_tree(
                    prompt_text,
                    json_text,
                    f"FeatureTree validation failed: {exc}",
                    model=backend.model,
                    max_retries=1,
                )
                attempts_used += 1
                continue
            return None
        break

    elapsed = (dt.datetime.now(dt.timezone.utc) - start).total_seconds()

    print(
        f"  -> valid feature tree ({elapsed:.2f}s, {attempts_used} attempt(s), "
        f"{len(tree.parameters)} params, {len(tree.parts)} part(s))",
        flush=True,
    )

    return {
        "prompt": prompt_text,
        "feature_tree": tree.model_dump(mode="json"),
        "metadata": {
            "id": prompt_id,
            "tier": tier,
            "model": gen.get("model", backend.model),
            "attempts_used": attempts_used,
            "max_retries": max_retries,
            "latency_seconds": round(elapsed, 3),
            "parameter_count": len(tree.parameters),
            "part_count": len(tree.parts),
            "assembly_count": len(tree.assemblies),
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        },
    }


def _split_data(data: list[dict[str, Any]], test_fraction: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Simple deterministic split: take every Nth example as test."""
    if not 0 <= test_fraction < 1:
        raise ValueError("test_fraction must be between 0 and 1")
    if test_fraction == 0 or not data:
        return list(data), []
    step = max(1, int(round(1.0 / test_fraction)))
    train: list[dict[str, Any]] = []
    test: list[dict[str, Any]] = []
    for i, row in enumerate(data):
        if i % step == 0:
            test.append(row)
        else:
            train.append(row)
    return train, test


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a feature-tree training dataset.")
    parser.add_argument("--ladder", type=Path, default=LADDER_PATH, help="Path to complexity_ladder.json")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR, help="Output directory")
    parser.add_argument("--limit", type=int, default=None, help="Run only the first N prompts")
    parser.add_argument("--timeout", type=int, default=120, help="Execution timeout per prompt")
    parser.add_argument("--max-retries", type=int, default=2, help="Self-correction retries")
    parser.add_argument("--test-split", type=float, default=0.2, help="Fraction to reserve as held-out test set")
    parser.add_argument("--model", type=str, default=None, help="Override model name")
    args = parser.parse_args()

    ladder = _load_ladder(args.ladder)
    prompts = _flatten_prompts(ladder)
    if args.limit:
        prompts = prompts[: args.limit]

    output_dir = args.output
    output_dir.mkdir(parents=True, exist_ok=True)
    run_output_dir = output_dir / "runs"
    run_output_dir.mkdir(parents=True, exist_ok=True)

    model = args.model or os.environ.get("ROBOCAD_MODEL") or "unknown"
    os.environ["ROBOCAD_MODEL"] = model
    backend = RoboCADBackend(model=model)

    print(f"Building feature-tree dataset with model={model}, prompts={len(prompts)}, max_retries={args.max_retries}")
    print(f"Output directory: {output_dir}")
    print("")

    dataset: list[dict[str, Any]] = []
    for p in prompts:
        row = _run_single(backend, p, run_output_dir, timeout=args.timeout, max_retries=args.max_retries)
        if row:
            dataset.append(row)

    train, test = _split_data(dataset, args.test_split)

    dataset_path = output_dir / "feature_tree_dataset.jsonl"
    train_path = output_dir / "feature_tree_train.jsonl"
    test_path = output_dir / "feature_tree_test.jsonl"

    _write_jsonl(dataset_path, dataset)
    _write_jsonl(train_path, train)
    _write_jsonl(test_path, test)

    summary = {
        "date": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "model": model,
        "prompt_count": len(prompts),
        "successful_count": len(dataset),
        "success_rate": round(len(dataset) / max(len(prompts), 1), 3),
        "train_count": len(train),
        "test_count": len(test),
        "dataset_file": str(dataset_path.resolve().relative_to(REPO_ROOT.resolve())),
        "train_file": str(train_path.resolve().relative_to(REPO_ROOT.resolve())),
        "test_file": str(test_path.resolve().relative_to(REPO_ROOT.resolve())),
    }
    summary_path = output_dir / "dataset_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("")
    print(f"Dataset complete.")
    print(f"  Successful feature trees: {len(dataset)} / {len(prompts)} ({summary['success_rate'] * 100:.1f}%)")
    print(f"  Train: {len(train)} | Test: {len(test)}")
    print(f"  Files: {dataset_path}, {train_path}, {test_path}")
    print(f"  Summary: {summary_path}")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
