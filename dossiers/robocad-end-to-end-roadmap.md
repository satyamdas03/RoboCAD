# RoboCAD End-to-End Vision Roadmap

**Date:** 2026-08-25  
**Horizon:** ~5–7 years  
**North Star:** voice/text → parametric CAD → per-part physical testing → assembly → world-model simulation → HERMES oversight → robot brain trained on synthetic data with retraining loops.  
**First commercial milestone:** PATH1 / GEDA Bridge (Phases 14A–15B).  
**Related:** [`PLAN.md`](../PLAN.md) Sections 10–14, [`PATH1_PATH2_analysis.md`](PATH1_PATH2_analysis.md)

---

## Cross-cutting foundation

Maintained across the entire roadmap:

- **Benchmark discipline:** keep the 30-prompt complexity suite green; publish scores after every model or prompt change.
- **Test pyramid:** unit → integration → simulation-load → end-to-end skill.
- **Model zoo:** maintain both local (Ollama) and cloud (Claude 5) generation paths.
- **Schema governance:** version feature-tree, assembly, bundle, and world-model schemas; provide migration tools.
- **CI/CD + git hygiene:** every change committed, every phase demo recorded.
- **Documentation:** keep `README.md`, `PLAN.md`, `PRODUCT.md`, and memory files in sync.

---

## Phase 13 — Robust generation + local model specialization

**Goal:** Get the Phase 8 complexity benchmark to ≥80% on T1–T4 and close extractor/self-correction edge cases.

**Current state:** 134/134 unit tests pass; 30-prompt benchmark at 70% with Claude Sonnet 5; Ollama fine-tuning scaffolding in place.

**Deliverables:**
- Claude Sonnet 5 run at ≥80% on T1–T4.
- Root-cause report for remaining T5 failures.
- Clean self-correction prompt that prevents nested markdown fences.
- Local model dataset completion and first fine-tuned checkpoint.
- Updated `PLAN.md` declaring Phase 13 complete.

**Timeline:** 1–2 months.

---

## Phase 14A — GEDA Bridge: MuJoCo / URDF exporter

**Goal:** Convert any RoboCAD part or assembly into a simulation-ready bundle.

**Deliverables:**
- `ai_cad/geda_bridge/exporter.py` with `export_to_mujoco()` and `export_to_urdf()`.
- Bundle schema v2.0.0: manifest, meshes, inertial JSON, MJCF, URDF, DFM report.
- Backend endpoints: `POST /designs/{id}/simulate`, `GET /designs/{id}/bundle`, `GET /designs/{id}/simulation`.
- Frontend "Simulate" button + download bundle panel.
- Verification: mass > 0, positive-definite inertia, CoM inside convex hull.
- Tests: cube, cylinder, L-bracket, 2-part assembly, gripper jaw.

**Timeline:** 2–3 months.

---

## Phase 14B — Standard manipulation scene templates

**Goal:** Provide reusable scene templates so `LearningRobotics` can drop a RoboCAD asset into a task.

**Deliverables:**
- Scene templates: `gripper_cube_grasp`, `bracket_hook_hang`, `wedge_push_block`, `peg_insertion`.
- Template composition API: add object, add end-effector, define goal region.
- Example notebooks for MuJoCo and Isaac Sim loaders.

**Timeline:** 1 month.

---

## Phase 15A — LearningRobotics handshake

**Goal:** `LearningRobotics` consumes a RoboCAD bundle, loads it into a standard scene, and runs a physics stability check.

**Deliverables:**
- Shared OpenAPI / JSON-Schema contract for bundle ingestion.
- Reference loader in Python for MuJoCo + Isaac Sim.
- End-to-end test: RoboCAD exports wedge → `LearningRobotics` loads scene → runs 10 s stability rollout.
- Capability registry: `/capabilities` endpoint.

**Timeline:** 1–2 months.

---

## Phase 15B — RoboCompiler asset pipeline

**Goal:** When a human demonstrates a skill on video, RoboCAD suggests/generates a custom end-effector and `LearningRobotics` trains on it.

**Deliverables:**
- Skill-to-part recommendation.
- Auto-generated part variants.
- Batch bundle export for variant sweeps.
- Integration test: human video → generated wedge → trained push policy.

**Timeline:** 2–3 months.

---

## Phase 16 — Voice/text + sketch input

**Goal:** Add voice and multimodal input as first-class modalities; keep text as the debuggable source of truth.

**Deliverables:**
- Whisper/local STT integration.
- Intent parser mapping speech/text to feature-tree operations and constraints.
- Ambiguity resolution UI.
- Sketch-to-constraint.
- Voice prompt templates.

**Timeline:** 2–3 months.

---

## Phase 17 — Automatic part decomposition

**Goal:** For complex prompts, generate a feature tree per part plus an assembly plan.

**Deliverables:**
- Decomposition planner (LLM + heuristics).
- Standard joint interfaces.
- Fastener/surface-join suggestions.
- Manufacturing method hints.
- Validation: statically determined assembly, no intersections.

**Timeline:** 3–4 months. **High risk** — start with parameterized part families.

---

## Phase 18 — Per-part physical testing

**Goal:** Test each part under realistic load cases before assembly.

**Deliverables:**
- Load-case templates: static load, drop test, thermal expansion, fatigue, fastener pull-out.
- Integration with CalculiX/FEBio for linear/static FEA.
- Material library.
- Failure report with redesign suggestions.
- Mesh-quality pre-checker.

**Timeline:** 2–3 months. **High risk** — start with closed templates.

---

## Phase 19 — Assembly synthesis and verification

**Goal:** Combine decomposed parts into a coherent assembly and export the full robot.

**Deliverables:**
- Mate inference.
- Kinematic loop solver for closed chains.
- Assembly-level collision and clearance checks.
- Full-robot MJCF export with joints, actuators, sensors.
- Assembly replay in the browser.

**Timeline:** 3–4 months.

---

## Phase 20 — World-model simulation

**Goal:** Drop the assembled robot into a parameterized scene with domain randomization.

**Deliverables:**
- World builder API.
- Domain randomization.
- Scene templates for pick-place, push, locomotion, insertion.
- Export to MuJoCo and Isaac Sim.
- Replay and inspection tools.

**Timeline:** 3–4 months.

---

## Phase 21 — Robot brain training loop

**Goal:** Generate training data, train a policy, evaluate in sim, feed performance back into design.

**Deliverables:**
- Synthetic dataset generator (RGB, depth, segmentation, state, action).
- RL training harness.
- Evaluation metrics.
- Design feedback loop.
- First closed-loop demo: design → train → evaluate → redesign → retrain.

**Timeline:** 4–6 months. **High risk** — start with imitation learning.

---

## Phase 22 — HERMES conversational supervisor

**Goal:** User can talk to RoboCAD like a colleague: status, changes, approvals, explanations.

**Deliverables:**
- HERMES agent with tool use across design/simulation/training APIs.
- Status dashboard.
- Approval gates for expensive/dangerous operations.
- Explanation engine.
- Memory of project context.

**Timeline:** 3–4 months. **High risk** — use deterministic execution paths.

---

## Phase 23 — Sim-to-real feedback loop

**Goal:** Deploy trained policy on real robot, collect failure data, close loop back into sim/design.

**Deliverables:**
- ROS 2 / micro-ROS / hardware bridge.
- Real-world failure logger.
- Automatic sim parameter calibration.
- Retraining pipeline.
- Safety monitoring.

**Timeline:** 6–12 months.

---

## Phase 24 — Distribution and commercialization

**Goal:** Product packaging, licensing, and community.

**Deliverables:**
- Open-source core with paid cloud simulation/training tier.
- Asset marketplace.
- Enterprise features.
- Community benchmarks and competitions.
- One-command launcher / desktop installer.

**Timeline:** Ongoing.

---

## Dependencies and critical path

| Phase | Hard dependencies | Unlocks |
|---|---|---|
| 13 | Phases 0–12 | Confidence to build bridge |
| 14A | Phase 13 | 14B, 15A |
| 14B | 14A | 15A |
| 15A | 14A, 14B | 15B, revenue/validation |
| 15B | 15A | PATH1 monetization |
| 16 | Phase 13 | 17, 22 |
| 17 | Phase 13, 16 | 18, 19 |
| 18 | 17 | 19, 21 |
| 19 | 14A, 17, 18 | 20 |
| 20 | 15A, 19 | 21 |
| 21 | 20 | 23 |
| 22 | 16, 19, 20 | Full UX layer |
| 23 | 21, hardware access | Commercial deployment |
| 24 | PATH1 proven | SaaS + marketplace |

---

## Why this plan is realistic

- **Ship-first milestones:** every phase produces something runnable.
- **PATH1 funds PATH2:** bridge is marketable in 6–9 months.
- **Explicit dependencies:** decomposition needs single-part generation; brain training needs world simulation.
- **Risks front-loaded:** high-risk layers get conservative timelines.
- **Human in the loop:** HERMES proposes/explains; humans approve safety-critical actions.

---

## Immediate next action

Start **Phase 13 completion** by re-running the complexity benchmark, confirming 70%+ holds, then closing remaining T4/T5 extractor issues. Once stable, open a branch for **Phase 14A: the MuJoCo exporter**.

---

*See also: [`PATH1_PATH2_analysis.md`](PATH1_PATH2_analysis.md) for the market and technical rationale.*
