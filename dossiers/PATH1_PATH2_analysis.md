# RoboCAD Strategic Analysis: PATH1 vs PATH2

**Date:** 2026-08-25  
**Status:** Decision made; PATH1 first, PATH2 as North Star  
**Related:** [`PLAN.md`](../PLAN.md) Section 14, [`robocad-end-to-end-roadmap.md`](robocad-end-to-end-roadmap.md)

---

## Executive summary

Two strategic directions were analyzed for RoboCAD:

- **PATH1 (GEDA Bridge):** RoboCAD → MuJoCo/URDF/inertial bundle for `LearningRobotics`.
- **PATH2 (full vision):** voice/text → parametric CAD → per-part physical testing → assembly → world-model simulation → HERMES oversight → robot brain trained on synthetic data.

**Decision: build PATH1 first.** It is technically reachable from the current codebase, addresses a real market need, and produces the exact asset format and API surface that PATH2 needs. PATH2 remains the 5–7 year North Star and is now mapped into Phases 16–24.

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

A full-stack robotics design operating system. It bundles six serious sub-products:

1. Voice/text engineering-intent parser.
2. Automatic part decomposition.
3. Per-part physical simulation (FEA).
4. Automated assembly synthesis.
5. World-model simulation + robot brain training.
6. HERMES conversational supervisor.

### Market context

- Generative AI in product design & engineering: ~$7 B (2026), 24% CAGR.
- Digital twin / manufacturing simulation: ~$35–47 B (2026).
- Physical AI training platforms: ~$3.2 B base, forecast to $101 B by 2035 at 41% CAGR.
- Conversational robotics supervision: emerging academic area, no clear standalone market yet.

### Technical feasibility: mixed

| Layer | Feasibility | Hard part |
|---|---|---|
| Voice-to-text | High | Solved |
| Engineering intent parsing | Medium | Ambiguity |
| Part decomposition | Low | AI planning for arbitrary geometry |
| Physical simulation | Medium | Automating FEA for LLM-generated parts |
| Assembly synthesis | Medium | Automated mate inference |
| World-model simulation | Medium | Mature simulators; policy training separate |
| HERMES supervisor | Medium | Reliable as observer, risky as sole executor |

### Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Scope explodes across 6 products | High | Sequence into independent phases |
| Voice is a gimmick for engineering | Medium | Treat voice as input shortcut, not core UX |
| Physical simulation for arbitrary parts is brittle | High | Start with load-case templates |
| Training a robot brain is a full ML project | High | Leave policy training to LearningRobotics |
| HERMES becomes a black-box bottleneck | Medium | Supervisor/observer first |

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
5. **Phase E:** RoboCompiler asset pipeline (Phase 15B). 🚧 In progress — video → custom part → trained skill.
6. **Phase F:** Add voice, decomposition, physical testing, assembly synthesis, world models, and HERMES — in that order.

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
