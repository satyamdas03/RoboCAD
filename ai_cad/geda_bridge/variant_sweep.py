"""Phase 15B — automatic part variant sweep for the GEDA Bridge.

Given a design with a feature tree and a set of parameter ranges, generate N
variants, export each as a simulation-ready MJCF/URDF bundle, verify it, and
return a sweep report. This lets users ask "what if the wedge were 10 % taller?"
and immediately get N simulation bundles plus aggregate manufacturability /
stability scores.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import numpy as np

from ai_cad.executor import execute_code
from ai_cad.feature_tree import FeatureTree
from ai_cad.geda_bridge.exporter import export_bundle_from_tree
from ai_cad.geda_bridge.loader import stability_check_bundle
from ai_cad.geda_bridge.models import BundleManifest
from ai_cad.geda_bridge.packager import package_bundle_paths
from ai_cad.geda_bridge.verifier import verify_bundle
from ai_cad.transpiler import transpile


def linear_sweep_values(
    parameter_name: str,
    nominal: float,
    range_spec: dict[str, float],
    n_variants: int,
    rng: np.random.Generator | None = None,
) -> list[float]:
    """Generate N values for a parameter around a nominal value.

    `range_spec` can contain either:
      - `min` and `max` (absolute bounds)
      - `relative_min` and `relative_max` (fractions of nominal)
      - `step` (ignored if min/max given)
    """
    if "min" in range_spec and "max" in range_spec:
        lo, hi = float(range_spec["min"]), float(range_spec["max"])
    elif "relative_min" in range_spec and "relative_max" in range_spec:
        lo = nominal * (1.0 + float(range_spec["relative_min"]))
        hi = nominal * (1.0 + float(range_spec["relative_max"]))
    elif "step" in range_spec:
        step = float(range_spec["step"])
        lo = nominal - step * (n_variants // 2)
        hi = lo + step * (n_variants - 1)
    else:
        raise ValueError(
            f"range_spec for '{parameter_name}' must include min/max, relative_min/relative_max, or step"
        )
    if n_variants == 1:
        return [float(nominal)]
    return [float(lo + (hi - lo) * i / (n_variants - 1)) for i in range(n_variants)]


def generate_variants(
    feature_tree_path: Path,
    parameter_ranges: dict[str, dict[str, float]],
    n_variants: int = 5,
    seed: int = 0,
) -> list[FeatureTree]:
    """Create N feature-tree variants by sweeping parameter values.

    Each parameter listed in `parameter_ranges` is swept linearly across its
    range; parameters not listed keep their nominal value. If multiple
    parameters are swept, the same index is used for all of them (aligned sweep),
    producing exactly `n_variants` trees.
    """
    tree_data = json.loads(Path(feature_tree_path).read_text(encoding="utf-8"))
    base_tree = FeatureTree(**tree_data)

    # Build nominal parameter map. Parameters may not expose a default_value,
    # so we fall back to their current value.
    nominal_map: dict[str, float] = {}
    for p in base_tree.parameters:
        raw = getattr(p, "default_value", None)
        if raw is None:
            raw = p.value
        nominal_map[p.name] = float(raw) if isinstance(raw, (int, float)) else 0.0
    for name in parameter_ranges:
        if name not in nominal_map:
            raise ValueError(f"Parameter '{name}' not found in feature tree")

    rng = np.random.default_rng(seed)
    variants: list[FeatureTree] = []
    for i in range(n_variants):
        tree = base_tree.model_copy(deep=True)
        for name, spec in parameter_ranges.items():
            values = linear_sweep_values(name, nominal_map[name], spec, n_variants, rng)
            tree = tree.update_parameter(name, values[i])
            if tree is None:
                raise ValueError(f"Failed to update parameter '{name}'")
        variants.append(tree)
    return variants


def export_variant_bundle(
    tree: FeatureTree,
    output_dir: Path,
    name: str,
    tolerance: float = 0.1,
) -> dict[str, Any]:
    """Transpile a variant feature tree, execute it, and export a GEDA bundle."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        code = transpile(tree)
    except Exception as exc:
        return {"success": False, "errors": [f"Transpile failed: {exc}"]}

    exec_result = execute_code(code, timeout=60, output_dir=output_dir)
    if not exec_result.get("success"):
        return {
            "success": False,
            "errors": [exec_result.get("traceback", exec_result.get("error", "Execution failed"))],
        }

    stl_path = exec_result.get("stl_path")
    if not stl_path or not Path(stl_path).exists():
        return {"success": False, "errors": ["Variant did not produce an STL export"]}

    try:
        paths = export_bundle_from_tree(tree, output_dir, name=name, tolerance=tolerance)
        paths = package_bundle_paths(paths, output_dir / "bundle.zip")
        verification = verify_bundle(paths.directory)
    except Exception as exc:
        return {"success": False, "errors": [f"Bundle export failed: {exc}"]}

    manifest = BundleManifest(**json.loads(paths.manifest_json.read_text(encoding="utf-8")))
    return {
        "success": verification.valid,
        "bundle_dir": str(paths.directory),
        "bundle_zip": str(paths.zip),
        "manifest": manifest.model_dump(),
        "verification": verification.model_dump(),
        "errors": [],
    }


def run_variant_sweep(
    feature_tree_path: Path,
    parameter_ranges: dict[str, dict[str, float]],
    n_variants: int = 5,
    output_root: Path | None = None,
    tolerance: float = 0.1,
    run_stability: bool = True,
    seed: int = 0,
) -> dict[str, Any]:
    """Run a full variant sweep: generate, export, verify, and optionally stability-check.

    Returns a JSON-serializable report with per-variant results and aggregate
    scores (valid fraction, average manufacturability, stability success rate).
    """
    feature_tree_path = Path(feature_tree_path)
    if not feature_tree_path.exists():
        return {"success": False, "errors": [f"Feature tree not found: {feature_tree_path}"]}

    if output_root is None:
        output_root = feature_tree_path.parent / "variant_sweep"
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    variants = generate_variants(feature_tree_path, parameter_ranges, n_variants=n_variants, seed=seed)
    results: list[dict[str, Any]] = []
    for idx, tree in enumerate(variants):
        variant_dir = output_root / f"variant_{idx:03d}"
        result = export_variant_bundle(tree, variant_dir, name=f"variant_{idx:03d}", tolerance=tolerance)
        result["variant_index"] = idx
        result["parameters"] = {p.name: float(p.value) for p in tree.parameters if p.name in parameter_ranges}

        if run_stability and result["success"]:
            try:
                stability = stability_check_bundle(Path(result["bundle_dir"]), scene_template="wedge_push_block", duration_seconds=2.0)
                result["stability"] = {
                    "success": stability.get("success", False),
                    "max_penetration_mm": stability.get("rollout", {}).get("max_penetration_mm", None),
                    "max_velocity_m_s": stability.get("rollout", {}).get("max_velocity_m_s", None),
                }
                if not stability.get("success"):
                    result["success"] = False
                    result["errors"].append("Stability check failed")
            except Exception as exc:
                result["stability"] = {"success": False, "error": str(exc)}
                result["success"] = False
                result["errors"].append(f"Stability check exception: {exc}")

        results.append(result)

    valid_results = [r for r in results if r["success"]]
    aggregate = {
        "n_variants": n_variants,
        "valid_count": len(valid_results),
        "valid_fraction": len(valid_results) / n_variants if n_variants else 0.0,
        "stability_success_count": sum(1 for r in valid_results if r.get("stability", {}).get("success", False)),
    }

    report = {
        "success": aggregate["valid_fraction"] >= 0.8,
        "feature_tree_path": str(feature_tree_path),
        "output_root": str(output_root),
        "parameter_ranges": parameter_ranges,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "aggregate": aggregate,
        "variants": results,
        "errors": [],
    }

    report_path = output_root / "sweep_report.json"
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    report["report_path"] = str(report_path)
    return report
