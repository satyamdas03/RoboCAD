"""Deterministic voice-to-certified-design orchestrator for HERMES.

The AutoOrchestrator ties domain classification, morphology search,
brain-training smoke tests, and simulation certification into a single
retry-capable pipeline. All heavy operations are injected via ``context``
callables so the module remains testable without real solvers or MuJoCo.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from ai_cad.hermes.explain import propose_redesign
from ai_cad.hermes.models import Session
from ai_cad.hermes.session import HermesSession
from ai_cad.hermes.tools import HermesToolRegistry
from ai_cad.robot_certification import DEFAULT_ROBOT_CERT_CASES


ROBOT_HINTS = ("robot", "walker", "humanoid", "quadruped", "biped")


END_EFFECTOR_OPTIONS: dict[str, list[list[str]]] = {
    "humanoid": [["default"], ["parallel_jaw_gripper"], ["three_finger_hand"]],
    "quadruped": [["default"], ["point_foot"], ["compliant_foot"]],
    "walker": [["default"], ["point_foot"]],
}


def _is_robot_prompt(domain: str | None, prompt: str) -> bool:
    """Return True when the domain or prompt suggests a robot design."""
    text = f"{domain or ''} {prompt}".lower()
    return any(hint in text for hint in ROBOT_HINTS)


def _infer_template(prompt: str) -> str:
    """Infer a morphology template from the user prompt."""
    p = prompt.lower()
    if "humanoid" in p or "biped" in p:
        return "humanoid"
    if "quadruped" in p or "dog" in p or "trot" in p:
        return "quadruped"
    return "walker"


def _certificate_passed(certificate: dict[str, Any] | None, threshold: float) -> bool:
    """Return True if a certificate passes the acceptance criteria."""
    if not certificate:
        return False
    cert_passed = bool(certificate.get("passed", False))
    cert_score = float(certificate.get("score", 0.0)) / 100.0
    if cert_passed or cert_score >= threshold:
        return True
    required_names = {c.value for c in DEFAULT_ROBOT_CERT_CASES}
    checks = certificate.get("checks", [])
    # Only treat robot-specific checks as a pass fallback when they are actually
    # present and not skipped (e.g., non-robot designs skip the robot cert case).
    required_checks = [
        c
        for c in checks
        if c.get("name") in required_names
        and not (c.get("details") or {}).get("skipped")
    ]
    if required_checks and all(bool(c.get("passed", False)) for c in required_checks):
        return True
    return False


def _extract_scores(certificate: dict[str, Any] | None) -> dict[str, Any]:
    """Extract a compact score summary from a certificate dict."""
    if not certificate:
        return {}
    return {
        "passed": certificate.get("passed"),
        "score": certificate.get("score"),
        "checks": [
            {"name": c.get("name"), "passed": c.get("passed"), "score": c.get("score")}
            for c in certificate.get("checks", [])
        ],
    }


def _append_audit(
    session: HermesSession,
    attempt: int,
    action: str,
    design_id: str | None,
    search_id: str | None,
    candidate_id: str | None,
    scores: dict[str, Any],
    passed: bool,
    retry_reason: str | None,
    duration_seconds: float,
) -> None:
    """Append one entry to the session's auto-audit trail and persist it."""
    audit = session.session.context.setdefault("auto_audit", [])
    if not isinstance(audit, list):
        audit = []
        session.session.context["auto_audit"] = audit
    entry: dict[str, Any] = {
        "attempt": attempt,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "design_id": design_id,
        "search_id": search_id,
        "candidate_id": candidate_id,
        "scores": scores,
        "passed": passed,
        "retry_reason": retry_reason,
        "duration_seconds": round(duration_seconds, 3),
    }
    audit.append(entry)
    session.save()


class AutoOrchestrator:
    """Deterministic pipeline from user prompt to certified design."""

    def __init__(
        self,
        session: HermesSession,
        registry: HermesToolRegistry,
        context: dict[str, Any],
        max_retries: int = 3,
        cert_threshold: float = 0.7,
        timeout_seconds: float = 1800.0,
    ) -> None:
        self.session = session
        self.registry = registry
        self.context = context
        self.max_retries = max(max_retries, 0)
        self.cert_threshold = cert_threshold
        self.timeout_seconds = timeout_seconds
        self.start_time = time.monotonic()

    def _elapsed(self) -> float:
        return time.monotonic() - self.start_time

    def _timed_out(self) -> bool:
        return self._elapsed() > self.timeout_seconds

    def _call(self, key: str, *args: Any, **kwargs: Any) -> Any:
        """Invoke a backend callable from context or return a clear error dict."""
        fn = self.context.get(key)
        if fn is None:
            return {
                "status": "error",
                "message": f"Orchestrator missing backend callable {key!r} in HERMES context",
            }
        if not callable(fn):
            return {
                "status": "error",
                "message": f"Backend callable {key!r} is not callable",
            }
        return fn(*args, **kwargs)

    def _classify_domain(self, prompt: str) -> dict[str, Any]:
        result = self._call("classify_domain", prompt)
        if isinstance(result, dict):
            return result
        return {"primary": str(result)}

    def _run_morphology_search(
        self,
        prompt: str,
        template: str,
        end_effectors: list[str] | None = None,
    ) -> dict[str, Any]:
        return self._call(
            "run_morphology_search",
            prompt=prompt,
            template=template,
            n_max=8,
            payload_kg=1.0,
            use_physics=True,
            auto_cert=False,
            end_effectors=end_effectors or [],
        )

    def _run_brain_training(self, search_id: str, candidate_id: str) -> dict[str, Any]:
        return self._call(
            "train_robot_brain_on_candidate",
            search_id=search_id,
            candidate_id=candidate_id,
            world_template="walker",
            n_iters=5,
            pop_size=20,
            eval_episodes=5,
            seed=42,
        )

    def _run_certification(self, design_id: str | None) -> dict[str, Any]:
        return self._call("run_simulation_certification", design_id=design_id)

    def _generate_design(self, prompt: str) -> dict[str, Any]:
        return self._call("generate_design", prompt=prompt)

    def _propose_redesign(self, goal: str, certificate: dict[str, Any]) -> dict[str, Any]:
        generate_fn = self.context.get("generate_fn")
        return propose_redesign(
            goal=goal,
            report=certificate,
            target="generic",
            context=self.context,
            generate_fn=generate_fn if callable(generate_fn) else None,
        )

    def run(self, prompt: str) -> dict[str, Any]:
        """Run the full orchestration pipeline."""
        attempt = 0
        design_id: str | None = None
        search_id: str | None = None
        candidate_id: str | None = None
        certificate: dict[str, Any] | None = None
        final_message = ""

        # Step 1: classify domain.
        domain_result = self._classify_domain(prompt)
        domain = domain_result.get("primary", "mechanical")

        is_robot = _is_robot_prompt(domain, prompt)

        while attempt <= self.max_retries:
            attempt += 1
            step_start = self._elapsed()

            if self._timed_out():
                final_message = "Orchestration timed out before completion"
                break

            if is_robot:
                # Vary template and end-effector set on retries.
                templates = ["walker", "humanoid", "quadruped"]
                template = _infer_template(prompt)
                if attempt > 1 and template in templates:
                    # Pick a different template on retry.
                    idx = templates.index(template)
                    template = templates[(idx + attempt - 1) % len(templates)]

                ee_options = END_EFFECTOR_OPTIONS.get(template, [["default"]])
                end_effectors = ee_options[(attempt - 1) % len(ee_options)]

                search_result = self._run_morphology_search(prompt, template, end_effectors=end_effectors)
                search_id = search_result.get("search_id")
                candidates = search_result.get("candidates", [])

                if candidates:
                    top = candidates[0]
                    candidate_id = top.get("candidate_id")
                    design_id = search_id

                    # Step 4: light brain-training smoke test.
                    brain_result = self._run_brain_training(search_id, candidate_id)
                    if brain_result.get("status") == "error":
                        final_message = f"Brain training failed: {brain_result.get('message')}"
                        break
                else:
                    # Step 3 fallback: generate a conventional design.
                    gen_result = self._generate_design(prompt)
                    design_id = gen_result.get("design_id")
                    candidate_id = None
                    search_id = None
            else:
                # Non-robot path: generate a conventional design.
                gen_result = self._generate_design(prompt)
                design_id = gen_result.get("design_id")
                candidate_id = None
                search_id = None

            # Step 5: run simulation certification.
            certification = self._run_certification(design_id)
            certificate = certification.get("certificate") if isinstance(certification, dict) else None

            # Step 6: determine pass.
            passed = _certificate_passed(certificate, self.cert_threshold)
            duration = self._elapsed() - step_start
            _append_audit(
                self.session,
                attempt=attempt,
                action="morphology_search" if is_robot and candidates else "generate_design",
                design_id=design_id,
                search_id=search_id,
                candidate_id=candidate_id,
                scores=_extract_scores(certificate),
                passed=passed,
                retry_reason=None if passed else "certification did not pass",
                duration_seconds=duration,
            )

            if passed:
                final_message = f"Certified design produced on attempt {attempt}"
                break

            # Step 7: retry with redesign if attempts remain.
            if attempt > self.max_retries:
                final_message = f"Certification failed after {attempt} attempts"
                break

            if not search_id:
                # Conventional design path: ask the LLM for parameter updates and apply them.
                redesign = self._propose_redesign(prompt, certificate or {})
                parameter_updates = redesign.get("parameter_updates") or {}
                if parameter_updates and design_id:
                    regen_result = self._call(
                        "regenerate_parameters",
                        parameter_updates=parameter_updates,
                    )
                    if regen_result.get("status") == "error":
                        final_message = f"Regeneration failed: {regen_result.get('message')}"
                        break
            # Robot path: the next loop iteration will vary the template/end-effector.

        if not final_message:
            final_message = "Orchestration completed without a passing certificate"

        success = passed if "passed" in vars() else False
        return {
            "success": success,
            "design_id": design_id,
            "search_id": search_id,
            "candidate_id": candidate_id,
            "certificate": certificate,
            "audit": list(self.session.session.context.get("auto_audit", [])),
            "attempts": attempt,
            "message": final_message,
        }


def run_auto_orchestration(
    session: HermesSession,
    prompt: str,
    registry: HermesToolRegistry,
    context: dict[str, Any],
    max_retries: int = 3,
    cert_threshold: float = 0.7,
    timeout_seconds: float = 1800.0,
) -> dict[str, Any]:
    """Run the deterministic auto-orchestration pipeline.

    Args:
        session: persisted HERMES session to update with audit state.
        prompt: natural-language design request.
        registry: HERMES tool registry (used for consistency, callables come from context).
        context: dict of backend callables: classify_domain, run_morphology_search,
            train_robot_brain_on_candidate, run_simulation_certification,
            generate_design, propose_redesign, regenerate_parameters.
        max_retries: number of redesign attempts after the first failure.
        cert_threshold: minimum overall certificate score (0..1) to accept.
        timeout_seconds: wall-clock budget for the whole pipeline.

    Returns:
        Dict with success, design_id/search_id, candidate_id, certificate, audit,
        attempts, and message.
    """
    orchestrator = AutoOrchestrator(
        session=session,
        registry=registry,
        context=context,
        max_retries=max_retries,
        cert_threshold=cert_threshold,
        timeout_seconds=timeout_seconds,
    )
    return orchestrator.run(prompt)
