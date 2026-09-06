"""Build a compact, LLM-friendly context summary from a persisted design."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


MAX_REPORT_LENGTH = 2000
MAX_PARAMETERS = 30
MAX_MESSAGES = 20


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _compact(value: Any, max_len: int = MAX_REPORT_LENGTH) -> Any:
    """Recursively trim long strings and large lists."""
    if isinstance(value, str):
        return value if len(value) <= max_len else value[:max_len] + "..."
    if isinstance(value, list):
        return [_compact(v) for v in value[:20]]
    if isinstance(value, dict):
        return {k: _compact(v) for k, v in value.items()}
    return value


def _latest_report(reports: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    if not reports:
        return None
    latest = max(reports, key=lambda r: r.get("created_at", ""))
    return _compact(latest)


def build_design_context(design_id: str, designs_dir: Path | str) -> dict[str, Any]:
    """Read a design's sidecar files and return a compact LLM context.

    The context includes:
      - prompt, domain, success, model
      - editable parameters
      - latest DFM, verification, brain, and world-replay reports
      - available HERMES actions
      - recent failures/errors
    """
    design_dir = Path(designs_dir) / design_id
    if not design_dir.exists():
        return {"error": f"Design directory {design_dir} not found"}

    metadata = _load_json(design_dir / "metadata.json") or {}
    feature_tree = _load_json(design_dir / "feature_tree.json")
    parameters = _load_json(design_dir / "parameters.json") or []
    domain_intent = _load_json(design_dir / "domain_intent.json") or {}
    decomposition = _load_json(design_dir / "decomposition.json")

    summary: dict[str, Any] = {
        "design_id": design_id,
        "prompt": metadata.get("prompt", ""),
        "domain": metadata.get("domain") or domain_intent.get("domain"),
        "success": metadata.get("success", False),
        "model": metadata.get("model", "unknown"),
        "created_at": metadata.get("created_at"),
        "tags": metadata.get("tags", []),
    }

    # Editable parameters (limit to keep context short).
    editable_params: list[dict[str, Any]] = []
    for p in parameters[:MAX_PARAMETERS]:
        if isinstance(p, dict):
            editable_params.append(
                {
                    "name": p.get("name"),
                    "value": p.get("value"),
                    "description": p.get("description", "")[:120],
                }
            )
    summary["parameters"] = editable_params

    # Latest reports.
    latest_reports: dict[str, Any] = {}
    dfm_report = metadata.get("dfm_report")
    if dfm_report:
        latest_reports["dfm"] = _compact(dfm_report)
    verification_reports = metadata.get("verification_reports", [])
    if verification_reports:
        latest_reports["verification"] = _latest_report(verification_reports)
    brain_report = metadata.get("brain")
    if brain_report:
        latest_reports["brain"] = _compact(brain_report)
    world_replays = metadata.get("world_replays", {})
    if world_replays:
        latest_reports["world_replay"] = _compact(next(iter(world_replays.values())))
    summary["latest_reports"] = latest_reports

    # Feature tree preview.
    if feature_tree:
        n_assemblies = len(feature_tree.get("assemblies", []))
        n_parts = len(feature_tree.get("parts", []))
        summary["feature_tree_preview"] = {
            "assemblies": n_assemblies,
            "parts": n_parts,
            "schema_version": feature_tree.get("schema_version"),
        }

    # Decomposition preview.
    if decomposition:
        parts = decomposition.get("parts", [])
        summary["decomposition_preview"] = {
            "n_parts": len(parts),
            "domains": list({p.get("domain") for p in parts if isinstance(p, dict)}),
        }

    # Recent failures/errors.
    recent_failures: list[str] = []
    if not summary["success"]:
        recent_failures.append("Design generation did not succeed.")
    validation = metadata.get("validation")
    if isinstance(validation, dict) and validation.get("errors"):
        recent_failures.extend(str(e) for e in validation["errors"][:5])
    summary["recent_failures"] = recent_failures[:5]

    # Actions that make sense for this design.
    summary["available_actions"] = _available_actions(summary)

    return _compact(summary)


def _available_actions(summary: dict[str, Any]) -> list[str]:
    """Suggest HERMES tools based on design state."""
    actions = [
        "get_design_summary",
        "explain_last_failure",
        "propose_redesign",
        "run_dfm_report",
        "run_verification",
    ]
    reports = summary.get("latest_reports") or {}
    if reports.get("brain") or reports.get("world_replay"):
        actions.extend(["replay_world", "train_brain"])
    if summary.get("domain") in {"mechanical", "aero", "thermal", "electronics", "humanoid"}:
        actions.extend(["regenerate_parameters", "synthesize_assembly"])
    if reports.get("dfm") or reports.get("verification"):
        actions.append("build_world")
    return list(dict.fromkeys(actions))


def build_global_context(
    design_id: str | None,
    designs_dir: Path | str,
    backend_callables: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge design context with backend-callable bindings.

    This is the context dict passed to HERMES agent.run and planner.execute_plan_step.
    """
    ctx: dict[str, Any] = dict(backend_callables or {})
    ctx["design_id"] = design_id
    if design_id:
        ctx["design_summary"] = build_design_context(design_id, designs_dir)
    else:
        ctx["design_summary"] = None
    return ctx
