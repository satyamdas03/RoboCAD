# RoboCAD Strategic Analysis: PATH1 vs PATH2

**Date:** 2026-08-25 (updated 2026-09-01)  
**Status:** Decision made; PATH1 (Phases 14A–15B), Batch A (Phases 16–18), Phase 19, Phase 20, Phase 21, Phase 22, Phase 23, Phase 24, and Phase 25 complete; Phase 26 — HERMES cross-domain conversational supervisor — is next  
**Related:** [`PLAN.md`](../PLAN.md) Sections 12–14, [`robocad-end-to-end-roadmap.md`](robocad-end-to-end-roadmap.md)

---

## Executive summary

Two strategic directions were analyzed for RoboCAD:

- **PATH1 (GEDA Bridge):** RoboCAD → MuJoCo/URDF/inertial bundle for `LearningRobotics`.
- **PATH2 (multi-domain North Star):** voice/text/sketch → multi-domain parametric CAD (mechanical, aero/thermal, electronics, humanoid) → per-part multi-physics testing → assembly → world-model simulation → HERMES oversight → robot brain trained on synthetic data with sim-to-real feedback.

**Decision: build PATH1 first, then Batch A multi-domain foundation, then mechanical assembly synthesis.** PATH1 is technically reachable from the current codebase, addresses a real market need, and produces the exact asset format and API surface that PATH2 needs. PATH2 remains the 5–7 year North Star and is now mapped into **Phases 16–28** as a set of domain tracks (mechanical, aero/thermal/propulsion, electronics, humanoid/full-robot) layered on top of the same feature-tree and bundle core.

---

## PATH1: GEDA Bridge / Phases 14A–15B

### What it is

A delivery-infrastructure play. RoboCAD already generates parametric CAD parts and assemblies. PATH1 exports them cleanly into MuJoCo/URDF with correct inertial properties, collision meshes, DFM reports, and a bundle schema that `LearningRobotics` can load directly.

### Market context (2026)

| Segment | Size | CAGR | What RoboCAD captures |
|---|---|---|---|
| Robot skill-learning platforms | ~$4.2–5.4 B | 18–29% | Verified simulation-ready assets |
| Robot learning from demonstration | ~$3.2–4.1 B | 28% | Custom end-effectors for demos |
| Imitation learning for robotics | ~$2.1–2.8 B | 34% | Mesh + inertial data for transfer |
| AI copilots for robot programming | ~$2.75 B | 28–32% | Controller-code + verifier scaffolding |
| Physical AI simulation / digital twin | ~$3.8 B+ | 28% | Inertial-correct MJCF assets |
| Synthetic data generation for robotics | ~$2.5 B | 33% | Parametric scene-ready assets |
| Virtual commissioning | ~$1.1–1.6 B | 13–15% | DFM + stability before fabrication |
| Generative AI in product design | ~$7.0 B | 24% | Natural-language parametric CAD |

### Technical feasibility: high

RoboCAD already has:
- Parametric code generation (build123d) with self-correction.
- Feature-tree schema v1, transpiler, backend endpoints.
- Assembly system with LCS-based mates.
- DFM rule engine, tolerance/fit checks, simple FEA.
- STL/STEP export and design persistence.

PATH1 adds:
- Convert build123d `Shape` → metric mesh.
- Compute mass properties from density.
- Write MJCF with `<inertial>` tag and convex collision mesh.
- Write URDF as a compatibility layer.
- Package directory structure per bundle schema v2.0.0.

None of these are research problems.

### Competitive landscape

- **NVIDIA Isaac Sim / Isaac Lab:** photoreal, GPU-parallel. RoboCAD’s angle is small, deterministic, open-source, LLM-generated parametric parts.
- **MuJoCo ecosystem:** gold standard for contact-rich RL. No turnkey CAD importer. GEDA Bridge fills exactly that gap.
- **Gazebo/ROS 2:** URDF export makes RoboCAD compatible here.
- **Siemens/Dassault/PTC/Autodesk:** heavy PLM/CAD tools; RoboCAD is lightweight and code-first.
- **Skild AI, Physical Intelligence, etc.:** assume fixed robot morphology. RoboCAD+RoboCompiler unique angle: *design the custom part, then learn the skill.*

### Risks

| Risk | Severity | Mitigation |
|---|---|---|
| LearningRobotics does not consume the bundle | Medium | Standalone MuJoCo loader test first |
| Inertia tensor sign/frame errors | Medium | Property-based tests |
| Complex assemblies generate unstable MJCF | Medium | Start with rigid, fixed assemblies |
| Claude API costs for complex prompts | Medium | Keep Ollama path alive |
| NVIDIA dominates the market | High | Differentiate on openness, editability, affordability |

### Verdict

**Do this first.** It validates the central thesis, creates reusable assets, and gives RoboCAD a concrete integration story.

---

## PATH2: Voice/text → CAD → physical simulation → assembly → world model

### What it is

A full-stack, multi-domain robotics design operating system. It now spans **Phases 16–28** and adds four domain tracks on top of the existing mechanical core:

1. **Cross-domain input** — voice/text/sketch + domain classifier (Phase 16).
2. **Domain-aware parametric representation** — solids, surfaces, kinematic chains, PCB form factors (Phase 17).
3. **Automatic decomposition + domain part families** — mechanical, aero/thermal, electronics, humanoid (Phase 18).
4. **Mechanical assembly synthesis** — mates, kinematic loops, full-subsystem export (Phase 19).
5. **Aerodynamics, thermal, and propulsion geometry** — airfoils, wings, ducts, heat sinks, propellers (Phase 20).
6. **Electronics and mechatronics co-design** — PCB outlines, enclosures, connectors, thermal hardware (Phase 21).
7. **Multi-physics verification engine** — structural, thermal, CFD, and dynamic checks (Phase 22).
8. **Humanoid / full-robot system synthesis** — biped, quadruped, manipulator-on-base templates (Phase 23).
9. **World-model simulation builder** — manipulation, locomotion, aerial, humanoid scenes (Phase 24).
10. **Robot brain training loop** — synthetic data, RL/IL, design feedback (Phase 25).
11. **HERMES cross-domain conversational supervisor** — status, approvals, explanations (Phase 26).
12. **Sim-to-real feedback loop** — real robot deployment, failure logging, retraining (Phase 27).
13. **Distribution + ecosystem + advanced co-design plugins** — launcher, marketplace, enterprise (Phase 28).

### Market context

- Generative AI in product design & engineering: ~$7 B (2026), 24% CAGR.
- Digital twin / manufacturing simulation: ~$35–47 B (2026).
- Physical AI training platforms: ~$3.2 B base, forecast to $101 B by 2035 at 41% CAGR.
- Conversational robotics supervision: emerging academic area, no clear standalone market yet.

### Technical feasibility: mixed

| Layer | Feasibility | Hard part |
|---|---|---|
| Voice-to-text | High | Solved |
| Domain classification | Medium | Distinguishing mechanical vs aero vs electronics intent |
| Engineering intent parsing | Medium | Ambiguity; domain-specific parameter vocabularies |
| Part decomposition + domain families | Low–Medium | AI planning for arbitrary geometry; avoiding over-generalized templates |
| Mechanical assembly synthesis | Medium | Automated mate inference and kinematic loops |
| Aero / thermal / propulsion geometry | Medium | Surface mesh quality and CFD template automation |
| Electronics / mechatronics co-design | Medium | Footprint/connector accuracy; staying out of silicon EDA |
| Multi-physics verification | Medium | Automating FEA/CFD/thermal for LLM-generated geometry |
| Humanoid / full-robot synthesis | Low–Medium | Morphology, actuator sizing, dynamic stability |
| World-model simulation | Medium | Mature simulators; policy training separate |
| Robot brain training | Medium–High | RL/IL as its own discipline; start with imitation |
| HERMES supervisor | Medium | Reliable as observer, risky as sole executor |
| Sim-to-real | High | Hardware access, calibration, safety |

### Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Multi-domain scope explodes across 6+ products | High | Sequence into independent domain tracks on a shared core |
| Voice is a gimmick for engineering | Medium | Treat voice as input shortcut, not core UX |
| Physical simulation for arbitrary parts is brittle | High | Start with closed load-case templates and graceful degradation |
| Aero/thermal geometry drifts into full CFD/EDA | High | Explicit boundary: RoboCAD owns form-factor + export bridges; full solvers stay external |
| Humanoid / full-robot morphology | Medium–High | Start with parameterized templates and scaling rules |
| Training a robot brain is a full ML project | High | Leave core policy research to LearningRobotics; RoboCAD provides synthetic data + geometry feedback |
| HERMES becomes a black-box bottleneck | Medium | Supervisor/observer first; hard approval gates |

### Verdict

**The right North Star, but the wrong next milestone.** PATH2 describes the company in 3–5 years. It should guide architecture, not be the immediate build target.

---

## Direct comparison

| Dimension | PATH1 | PATH2 |
|---|---|---|
| What it is | Export + packaging layer | Full-stack robotics design OS |
| Buildable from today? | Yes — 4–6 weeks | No — 6–18 months |
| Market risk | Low | Medium |
| Technical risk | Low | High |
| Defensibility | Medium | High (if executed end-to-end) |
| Revenue path | Bundles, API usage, asset library | SaaS platform, enterprise licenses |
| Dependency on LearningRobotics | Clean API contract | Tight coupling |

---

## Recommended sequencing

1. **Phase A:** Complete Phase 13 benchmark tuning to ≥80% on T1–T4. ✅ Done — 87.5% on T1–T4 with Claude Sonnet 5.
2. **Phase B:** Build the MuJoCo exporter (Phase 14A). ✅ Done — `ai_cad/geda_bridge/`, 152/152 tests passing, MuJoCo runtime validation.
3. **Phase C:** Build standard manipulation scene templates (Phase 14B). ✅ Done — 4 templates, composition API, backend + frontend, 160/160 tests passing.
4. **Phase D:** Cross-repo handshake with LearningRobotics (Phase 15A). ✅ Done — bundle contract, reference loaders, /capabilities, 10 s stability rollout, 170/170 tests passing. Three solvable caveats fixed during acceptance (Isaac Sim skeleton, nightly CI, real wedge test seed + exporter/loader bug fixes).
5. **Phase E:** RoboCompiler asset pipeline (Phase 15B). ✅ Done — skill recommendation (`recommend-skill`), part variant sweep (`variant-sweep`), batch bundle export, and a NumPy-only CEM push-policy smoke test (`train-skill`) end-to-end on generated wedge meshes. 187/187 tests passing. Video-to-skill ingestion remains future work.
6. ✅ Add cross-domain input (16), domain-aware representation (17), and decomposition + domain part families (18) — Batch A complete, **228/228 tests passing** after post-ship hardening.
7. ✅ Mechanical assembly synthesis (19) complete, **251/251 tests passing**.
8. ✅ Aerodynamics, thermal, and propulsion geometry (20) complete, **276/276 tests passing**.
9. ✅ Electronics / mechatronics integration (21) complete, **299/299 tests passing**.
10. ✅ Multi-physics verification engine (22) complete, **330/330 tests passing**.
11. ✅ Humanoid / full-robot synthesis (23) complete, **357/357 tests passing** after post-ship hardening.
12. ✅ World-model simulation builder (24) complete, **376/376 tests passing**.
13. ✅ Attention-based robot brain training foundation (25) complete, **414/414 tests passing**.
14. **Next:** HERMES cross-domain supervisor (26), sim-to-real feedback (27), and distribution / ecosystem / advanced co-design (28) — in that order.

---

## Sources

Market figures synthesized from:

- MarketIntelo Robot Learning from Demonstration Report 2034
- MarketIntelo Imitation Learning for Robotics Report 2034
- The Business Research Company AI Copilots for Robot Programming 2026–2030
- Dataintelo Robotic Skill Learning Platforms Report 2034
- MarketIntelo Physical AI Simulation and Digital Twin for Robotics 2034
- The Business Research Company Synthetic Data Generation for Robotics 2026
- Fact.MR Virtual Commissioning Market Report 2036
- Fortune Business Insights Generative AI in Product Design & Engineering 2034
- MarketResearch.biz Generative AI in CAD Market
- RobotForge “Choosing a robotics simulator in 2026”
- Robotics Center “MuJoCo vs Isaac Sim (2026)”
- MIT “Speech to Reality” (2025)
- arXiv / CVPR 2026 video-to-skill papers
- PAL Robotics JARVIS / CO-HAND Project

---

*See also: [`robocad-end-to-end-roadmap.md`](robocad-end-to-end-roadmap.md) for the phased plan.*
