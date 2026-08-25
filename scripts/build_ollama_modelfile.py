"""Build an Ollama Modelfile specialized for RoboCAD Feature-Tree generation.

Reads a feature-tree dataset (e.g. training/feature_tree_train.jsonl), embeds the
best N examples into the system prompt, and writes an Ollama Modelfile. The
resulting model can be created with:

    ollama create robocad-ft -f models/robocad-ft/Modelfile

Usage:
    python scripts/build_ollama_modelfile.py
    python scripts/build_ollama_modelfile.py --dataset training/feature_tree_train.jsonl --examples 8
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = REPO_ROOT / "ai_cad" / "prompts"
MODEL_DIR = REPO_ROOT / "models" / "robocad-ft"


def _load_dataset(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _load_base_system_prompt() -> str:
    path = PROMPTS_DIR / "feature_tree_system_prompt.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "You are a parametric CAD data-modeling assistant. Output only Feature-Tree JSON."


def _select_examples(rows: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    """Pick a diverse set of examples across tiers, preferring ones with more parameters."""
    # Sort by tier complexity and parameter count.
    def score(r: dict[str, Any]) -> tuple[int, int]:
        tier_order = {"T1 - Primitive": 1, "T2 - Basic part": 2, "T3 - Intermediate": 3, "T4 - Advanced": 4, "T5 - Expert": 5}
        meta = r.get("metadata", {})
        tier = meta.get("tier", "")
        params = meta.get("parameter_count", 0)
        return (tier_order.get(tier, 0), params)

    sorted_rows = sorted(rows, key=score, reverse=True)
    # Take top from each tier for diversity.
    by_tier: dict[str, list[dict[str, Any]]] = {}
    for r in sorted_rows:
        tier = r.get("metadata", {}).get("tier", "unknown")
        by_tier.setdefault(tier, []).append(r)

    selected: list[dict[str, Any]] = []
    tiers = ["T1 - Primitive", "T2 - Basic part", "T3 - Intermediate", "T4 - Advanced", "T5 - Expert"]
    for tier in tiers:
        selected.extend(by_tier.get(tier, [])[:2])

    # Fill remaining slots with highest-scoring overall.
    remaining = [r for r in sorted_rows if r not in selected]
    while len(selected) < count and remaining:
        selected.append(remaining.pop(0))
    return selected[:count]


def _format_examples(examples: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for ex in examples:
        prompt = ex["prompt"]
        tree_json = json.dumps(ex["feature_tree"], ensure_ascii=False, indent=2)
        parts.append(f"Prompt: {prompt}\n\nOutput the Feature-Tree JSON.")
        parts.append(f"```json\n{tree_json}\n```")
    return "\n\n".join(parts)


def _build_system_prompt(base_prompt: str, examples: list[dict[str, Any]]) -> str:
    if not examples:
        return base_prompt
    example_block = _format_examples(examples)
    return (
        f"{base_prompt}\n\n"
        f"Below are example prompt -> Feature-Tree pairs. Study them and produce similar JSON for new prompts.\n\n"
        f"{example_block}"
    )


def _build_modelfile(base_model: str, system_prompt: str) -> str:
    # Escape triple quotes inside the system prompt by using single quotes around the
    # delimiters where possible, or by normalizing. Modelfile syntax uses triple-double
    # quotes; we replace any internal """ with a marker to avoid premature closing.
    safe_prompt = system_prompt.replace('"""', '""\\"')
    lines = [
        f"FROM {base_model}",
        "",
        "PARAMETER temperature 0.0",
        "PARAMETER num_predict 4096",
        "",
        f'SYSTEM """{safe_prompt}"""',
    ]
    return "\n".join(lines) + "\n"


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build an Ollama Modelfile for RoboCAD.")
    parser.add_argument("--dataset", type=Path, default=REPO_ROOT / "training" / "feature_tree_train.jsonl", help="Training dataset JSONL")
    parser.add_argument("--base-model", type=str, default="qwen3-coder:latest", help="Base Ollama model")
    parser.add_argument("--examples", type=int, default=10, help="Number of few-shot examples to embed")
    parser.add_argument("--output", type=Path, default=MODEL_DIR / "Modelfile", help="Output Modelfile path")
    parser.add_argument("--name", type=str, default="robocad-ft", help="Ollama model name")
    return parser


def main_with_args(args: argparse.Namespace) -> None:
    rows = _load_dataset(args.dataset)
    if not rows:
        raise ValueError(f"Dataset is empty: {args.dataset}")

    examples = _select_examples(rows, args.examples)
    base_prompt = _load_base_system_prompt()
    system_prompt = _build_system_prompt(base_prompt, examples)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    modelfile_text = _build_modelfile(args.base_model, system_prompt)
    args.output.write_text(modelfile_text, encoding="utf-8")

    # Write a companion create script for convenience.
    create_script = args.output.parent / "create_model.bat"
    create_script.write_text(f"ollama create {args.name} -f \"{args.output}\"\n", encoding="utf-8")

    print(f"Wrote Modelfile: {args.output}")
    print(f"Examples embedded: {len(examples)}")
    print(f"System prompt length: {len(system_prompt)} chars")
    print(f"Create model with: ollama create {args.name} -f {args.output}")


def main() -> None:
    parser = _build_arg_parser()
    args = parser.parse_args()
    main_with_args(args)


if __name__ == "__main__":
    main()
