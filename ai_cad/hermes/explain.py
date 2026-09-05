"""Explanation engine — convert RoboCAD reports into plain language."""
from __future__ import annotations

from typing import Any


REPORT_TYPES = ("dfm", "verification", "brain", "world_replay", "generic")


def explain_report(target: str, report: dict[str, Any] | None = None) -> str:
    """Produce a concise, plain-language explanation of a RoboCAD report."""
    report = report or {}
    target = target.lower()

    if target == "dfm":
        return _explain_dfm(report)
    if target == "verification":
        return _explain_verification(report)
    if target == "brain":
        return _explain_brain(report)
    if target == "world_replay":
        return _explain_world_replay(report)
    if target == "generic":
        return _explain_generic(report)
    return f"No explainer available for report type {target!r}. Ask for one of: {', '.join(REPORT_TYPES)}."


def _explain_dfm(report: dict[str, Any]) -> str:
    overall = "pass" if report.get("pass", report.get("valid", False)) else "fail"
    issues = report.get("issues", report.get("violations", []))
    metrics = report.get("metrics", {})
    lines = [f"DFM report: {overall.upper()}."]
    if metrics:
        for key, value in metrics.items():
            lines.append(f"  {key}: {value}")
    if issues:
        lines.append("Issues found:")
        for issue in issues[:5]:
            if isinstance(issue, dict):
                lines.append(f"  - {issue.get('severity', 'info')}: {issue.get('message', issue)}")
            else:
                lines.append(f"  - {issue}")
    if not issues:
        lines.append("No manufacturability issues detected.")
    return "\n".join(lines)


def _explain_verification(report: dict[str, Any]) -> str:
    load_case = report.get("load_case", report.get("case", "unknown"))
    passed = report.get("passed", report.get("success", False))
    metrics = report.get("metrics", {})
    lines = [f"Verification report for load case {load_case!r}: {'PASS' if passed else 'FAIL'}."]
    for key, value in metrics.items():
        lines.append(f"  {key}: {value}")
    notes = report.get("notes", report.get("summary", []))
    if isinstance(notes, str):
        notes = [notes]
    for note in notes:
        lines.append(f"  Note: {note}")
    return "\n".join(lines)


def _explain_brain(report: dict[str, Any]) -> str:
    success = report.get("success", False)
    success_rate = report.get("success_rate")
    mean_reward = report.get("mean_reward")
    policy = report.get("policy_architecture", {})
    lines = [f"Brain training: {'success' if success else 'below threshold'}."]
    if success_rate is not None:
        lines.append(f"  Success rate: {success_rate * 100:.1f}%")
    if mean_reward is not None:
        lines.append(f"  Mean reward: {mean_reward:.3f}")
    if policy:
        lines.append(f"  Policy shape: {policy.get('input_dim')}→{policy.get('hidden_dim')}→{policy.get('output_dim')}")
    return "\n".join(lines)


def _explain_world_replay(report: dict[str, Any]) -> str:
    duration = report.get("duration_seconds", report.get("duration", "unknown"))
    bodies = report.get("body_count", report.get("tracked_bodies", 0))
    saliency = report.get("saliency", {})
    lines = [f"World replay captured {duration}s across {bodies} tracked bodies."]
    if saliency:
        top = sorted(saliency.items(), key=lambda kv: max(kv[1].values()) if isinstance(kv[1], dict) else 0, reverse=True)[:3]
        lines.append("Most salient bodies (max velocity/acceleration/force):")
        for name, values in top:
            lines.append(f"  - {name}: {values}")
    return "\n".join(lines)


def _explain_generic(report: dict[str, Any]) -> str:
    summary = report.get("summary", report.get("message", report.get("detail", str(report)[:200])))
    return f"Report summary: {summary}"
