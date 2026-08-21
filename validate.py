"""Phase 0 validation script: prompt -> build123d code -> STL."""
from __future__ import annotations

import json
import os
from pathlib import Path

from ai_cad.executor import execute_code
from ai_cad.generator import generate_model, self_correct
from ai_cad.validator import validate_model


PROMPTS = [
    "A 120 mm × 80 mm × 3 mm rectangular plate with four M3 mounting holes on a 100 mm × 60 mm grid.",
    "An L-bracket 40 mm tall, 40 mm wide, 30 mm deep, 3 mm thick, with four 4 mm mounting holes on one face.",
    "A simple wheel hub for a 6 mm shaft with four M3 bolt holes on a 30 mm PCD.",
    "A motor mount bracket for a NEMA-17 with two M3 mounting holes and a 22 mm boss for the motor face.",
    "A differential-drive robot chassis base, 150 mm × 100 mm, with two NEMA-17 motor mounts and a caster clearance hole.",
    "A 50-tooth GT2 pulley with 6 mm belt width and a 5 mm bore.",
    "A rectangular spacer, 10 mm OD, 5 mm ID, 8 mm long.",
    "A simple robot arm link, 120 mm long, 20 mm wide, 5 mm thick, with a 6 mm hole at each end.",
]


def main() -> int:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: set ANTHROPIC_API_KEY environment variable.")
        return 1

    output_dir = Path("output") / "phase0"
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []

    print(f"Running Phase 0 validation on {len(PROMPTS)} prompts...\n")

    for idx, prompt in enumerate(PROMPTS, start=1):
        print(f"[{idx}/{len(PROMPTS)}] {prompt}")

        # First attempt
        gen = generate_model(prompt, api_key=api_key)
        attempt = 1

        while not gen["success"] or (gen["success"] and gen.get("code")):
            if gen["success"]:
                exec_result = execute_code(gen["code"], output_dir=output_dir)
                if exec_result["success"]:
                    break

                # Self-correct on execution error
                if attempt <= 2:
                    print(f"  Execution failed, attempting self-correction (attempt {attempt})...")
                    gen = self_correct(
                        prompt,
                        gen["code"],
                        exec_result.get("traceback", exec_result.get("error", "unknown error")),
                        api_key=api_key,
                    )
                    attempt += 1
                    continue
                else:
                    break
            else:
                break

        # Final evaluation
        if gen["success"]:
            exec_result = execute_code(gen["code"], output_dir=output_dir)
            validation = validate_model(exec_result.get("stl_path"))
        else:
            exec_result = {"success": False, "error": gen.get("error"), "traceback": gen.get("raw_response")}
            validation = {"valid": False, "errors": [gen.get("error", "Generation failed")]}

        entry = {
            "prompt": prompt,
            "success": exec_result.get("success", False),
            "attempts": attempt,
            "error": exec_result.get("error") or validation.get("errors", [None])[0],
            "bounds": exec_result.get("bounds"),
            "volume": exec_result.get("volume"),
            "valid": validation.get("valid", False),
            "warnings": validation.get("warnings", []),
            "code": gen.get("code") if gen["success"] else None,
            "stl_path": str(exec_result.get("stl_path")) if exec_result.get("stl_path") else None,
        }
        results.append(entry)

        status = "PASS" if entry["success"] and entry["valid"] else "FAIL"
        print(f"  -> {status} (attempts={entry['attempts']}, bounds={entry['bounds']}, volume={entry['volume']})")
        if entry["warnings"]:
            print(f"     warnings: {entry['warnings']}")
        if status == "FAIL":
            print(f"     error: {entry['error'][:200]}")
        print()

    passed = sum(1 for r in results if r["success"] and r["valid"])
    total = len(results)
    print(f"Phase 0 result: {passed}/{total} prompts passed ({passed / total:.1%})")

    summary_path = output_dir / "phase0_results.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Detailed results written to {summary_path}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
