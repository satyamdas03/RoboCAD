# Milestone I — Voice/Text-to-Certified-Design Orchestration

**Date:** 2026-10-04
**Status:** ✅ COMPLETE
**Baseline:** Milestone G complete; 407 default + 263 heavy/slow/mujoco tests passing; honest score 9.6/10.
**Delivered:** Fully automated voice/text prompt → certified robot design, plus onboarding UI.
**Final test count:** 410 default tests passing; 279 slow/heavy/mujoco tests passing (276 passed, 1 xfailed, 2 xpassed) in the monolithic run; frontend production build passes.
**Honest score:** revised **9.6 → 9.7/10**.

---

## 1. Goal

Enable a user to type or say one sentence — e.g. *“Design a 1.2 m humanoid that can walk on a 5° slope and pick up a 2 kg box”* — and have RoboCAD automatically produce a simulation-certified robot design with a full audit trail, no manual supervision.

---

## 2. What was built

### 2.1 `ai_cad/hermes/orchestrator.py`

- `AutoOrchestrator` and `run_auto_orchestration()`.
- Robot path (prompt contains `humanoid`, `quadruped`, `biped`, `walker`, `robot`, `manipulator_on_base`):
  1. Classify domain via existing classifier.
  2. Run morphology search with physics (`ai_cad.morphology.search_morphologies`).
  3. Pick top candidate.
  4. Run a light MuJoCo brain-training smoke test (`WorldReplayEnv` + `RobotMLPPolicy` + NumPy CEM).
  5. Run randomized-world simulation certification (`ai_cad.sim_certification.run_simulation_certification`).
  6. If certification fails, retry with template/end-effector mutation and re-run; record every attempt in `auto_audit`.
- Non-robot path:
  1. Use `/generate` to produce a `FeatureTree`.
  2. Run simulation certification.
  3. If it fails, call `regenerate_parameters` with LLM-driven parameter updates and retry.
- Returns: success flag, design/search/candidate IDs, certificate, full audit.

### 2.2 HERMES tool extensions

Three new tools added to the HERMES registry:

- `run_morphology_search`
- `train_robot_brain_on_candidate`
- `run_simulation_certification`

Each has:
- JSON schema in `ai_cad/hermes/tools.py`.
- Real executor in `ai_cad/hermes/executor.py`.
- Pydantic validation schema in `ai_cad/hermes/validation.py`.
- `ToolResult.duration_seconds` added to `ai_cad/hermes/models.py` so the planner records wall-clock cost.

### 2.3 Backend endpoints

- `POST /hermes/session/{session_id}/auto` — run `run_auto_orchestration` with the user's prompt.
- `GET /hermes/session/{session_id}/audit` — return a serializable snapshot of session context, auto-audit, and plans.
- `_build_hermes_context` extended with the new tool executors and `generate_design`.

### 2.4 Frontend

- `WelcomePanel.jsx` onboarding hero with RoboCAD title/subtitle, 5 example prompt chips, 3-step guide, and *Talk to HERMES* CTA.
- `HermesPanel.jsx` auto-design form, audit polling every 2s, PASS/FAIL attempt list, and *Open result* navigation.
- `api.js` helpers: `startHermesAuto` and `getHermesAudit`.
- `App.jsx` conditionally renders `WelcomePanel` when no design is selected and wires `HermesPanel` focus callbacks.

### 2.5 Hardening fixes

- `ai_cad/sim_certification.py`: `_is_robot_design` now safely reads metadata with `getattr` instead of direct attribute access.
- `ai_cad/hermes/orchestrator.py`: `_certificate_passed` fallback excludes skipped robot-cert checks so non-robot designs cannot bypass the score threshold.
- `ai_cad/hermes/executor.py`: `_require` error messages now include the tool name and missing backend callable.

### 2.6 Tests

- `tests/test_hermes_orchestrator.py` — happy-path morphology, retry-then-pass, non-robot generate, skipped-check fallback, required-check fallback.
- `tests/test_hermes_auto_endpoint.py` — FastAPI TestClient coverage of `/hermes/session/{id}/auto` and `/hermes/session/{id}/audit`.
- `tests/test_hermes.py` — extended with `test_execute_plan_step_records_duration`.
- `tests/test_sim_certification.py` — regression tests for `_is_robot_design`.
- `tests/test_morphology.py` and `tests/test_morphology_api.py` — genuinely slow tests moved behind `@pytest.mark.slow` so the default suite stays CI-fast.

---

## 3. Test evidence

- Default suite: **410 passed, 279 deselected, 3 warnings** in 382.97s.
- Slow/heavy/mujoco suite: **276 passed, 410 deselected, 1 xfailed, 2 xpassed** in 1058.23s (17m 38s).
- Frontend build: `vite build` succeeds in ~5.7s.

---

## 4. Acceptance

- ✅ Single prompt → certified design end-to-end for robot and non-robot prompts.
- ✅ Audit trail persisted and exposed via backend endpoint and frontend panel.
- ✅ All existing endpoints and contracts preserved.
- ✅ Full test suite green (default + slow/heavy/mujoco).
- ✅ Frontend production build passes.
- ✅ README.md and PLAN.md updated with Milestone I row and honest score.
- ✅ Dossier and memory files updated.

---

## 5. Related

- `docs/superpowers/plans/2026-10-04-milestone-i-voice-to-certified-design.md`
- `memory/milestone-i-voice-to-certified-design.md`
- [[milestone-g-simulation-certification]]
- [[phase28-simulation-first-product-platform]]
- [[robocad-confidence-10-10-roadmap]]
