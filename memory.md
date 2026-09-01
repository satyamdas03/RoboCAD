# 🧠 Project Memory — RoboCAD

> **Purpose:** This file is the single source of truth for session restart. Read it first if you have no other context. It records everything we have done, decided, researched, and planned — line by line — so work can resume without loss.

---

## 1. Project Identity

| Field | Value |
|---|---|
| **Project name** | RoboCAD |
| **GitHub repository** | https://github.com/satyamdas03/RoboCAD |
| **Branch** | `master` |
| **Visibility** | Public |
| **Mission** | AI-powered parametric CAD for robotics hardware: describe parts/assemblies in language, get editable manufacturable models and simulation-ready bundles. |
| **Owner** | Satyam Das (@satyamdas03, satyamdas03@gmail.com) |
| **Start date** | 2026-08-21 |
| **Current date** | 2026-09-01 |

---

## 2. Why this project exists

The user has deep AI/systems/research experience and is learning robotics from first principles in the `LearningRobotics` repo. The bottleneck for building real hardware is not theory but CAD: professional tools require weeks of sketch-extrude-mate muscle memory before a simple idea can be expressed.

RoboCAD removes that bottleneck by letting the user operate at the level of intent:

> *"A 120 mm × 80 mm × 3 mm base plate with four M3 mounting holes on a 100 mm × 60 mm grid and two NEMA-17 motor mounts."*

The AI writes the parametric code; the user edits parameters and exports to manufacturing or simulation.

---

## 3. Connection to LearningRobotics

- **LearningRobotics** (`https://github.com/satyamdas03/LearningRobotics`) teaches robot theory: C-space, rigid-body motions, kinematics, dynamics, control, RL, and the PIBench physical-intuition benchmark.
- **RoboCAD** designs the physical parts that those chapters eventually become.
- **GEDA Bridge** (Phases 14A–15B) connects RoboCAD to `LearningRobotics` by exporting verified MuJoCo/URDF bundles that `LearningRobotics` can load directly.
- Generated parts can be:
  1. Exported as STL/STEP/3MF for 3D printing or machining.
  2. Synced to Onshape for professional assemblies (Phase 5).
  3. Loaded into MuJoCo/Isaac Sim via the GEDA Bridge for skill training.
  4. Used as real hardware builds.

In short: **LearningRobotics teaches the robot. RoboCAD designs the parts. GEDA connects them.**

---

## 4. Hardware & Environment

| Component | Spec |
|---|---|
| Laptop | Lenovo LOQ |
| GPU | NVIDIA GeForce RTX 5060 (8 GB VRAM) |
| OS | Windows 11 Home |
| Python | 3.14 |
| Primary shell | PowerShell; Bash available |

---

## 5. Architecture

```
User prompt + voice/sketch edits + stylus edits
        |
        v
AI orchestrator (Claude 5 / local Ollama)
  - intent parsing
  - generates feature tree or build123d code
  - self-corrects on errors
        |
        v
CAD execution engine (build123d)
        |
        v
Geometry validation (manifold, bounds, manufacturability)
        |
        v
Feature tree / assembly / verification layers
        |
        v
Web viewer + parameter editor + simulation panels
        |
        v
Persistence + design library + remix
        |
        v
Exports: STL / STEP / 3MF / Onshape / MuJoCo / URDF bundle
        |
        v
LearningRobotics → world model → policy training → sim-to-real
```

**Core bet:** The AI writes **parametric code** (not meshes), so the output is editable, versionable, manufacturable, and simulation-ready.

---

## 6. Engineering decisions

| Decision | Choice | Rationale |
|---|---|---|
| CAD kernel | **build123d** first | Python API; LLMs write it well; no API limits |
| AI model | Claude 5 / GPT-4o / local `qwen3-coder:latest` | Best code generation; local Ollama for cost/speed |
| Output artifact | Python script + derived mesh + feature tree | Script is the editable source of truth |
| Execution | Subprocess sandbox | Isolates generated code; captures tracebacks |
| Viewer | React + three.js | Standard, lightweight |
| Storage | SQLite + JSON + Git | Simple, versionable, portable |
| API keys | Environment variables only | Never in files |
| Hosting | Local first | Runs on the RTX 5060 laptop |
| Onshape auth | HMAC-SHA256 API-key signing | Matches official Onshape Python client |
| Claude 5 SDK | httpx2/httpcore2 → standard httpx/httpcore shim | Fixes Python 3.14 recursion bug in Anthropic SDK fork |
| Simulation bridge | MuJoCo primary + URDF fallback | MuJoCo for contact-rich RL; URDF for ROS/Gazebo |

---

## 7. Phased plan

| Phase | Goal | Status |
|---|---|---|
| **0** | Validate AI → build123d → STL loop | ✅ **Complete — 8/8 prompts pass** |
| **1** | Robust generation + self-correction backend | ✅ **Complete — 19/20 prompts pass (95%)** |
| **2** | Minimal web app (prompt + viewer + export) | ✅ **Complete — FastAPI + React + three.js + persistence** |
| **3** | Parameter / stylus editing layer | ✅ **Complete — editable parameter panel + face-click parameter guessing + versioned regeneration** |
| **4** | Design library + remix | ✅ **Complete — component catalog, search/filter, tags, remix with parent linking** |
| **5** | Onshape export / sync + manufacturing reports | ✅ **Complete — HMAC-signed Onshape client, STEP upload, manufacturability report** |
| **6** | Robotics-aware component templates | ✅ **Complete — 12 standard robotics parts in `ComponentLibrary`** |
| **7** | Google Stitch Kinetic Precision UI redesign | ✅ **Complete — dark scientific engineering workstation, 56/57 tests passing** |
| **8** | Complexity benchmark + feature-tree spec | ✅ **Complete — 26/30 (86.7%) baseline; feature-tree schema v1.0.0** |
| **9** | Feature-tree backend | ✅ **Complete — structured sidecar, transpiler, store, endpoints, frontend panel; 97 tests** |
| **10** | Sketch + 2D constraint solver | ✅ **Complete — internal least-squares solver; 105 tests** |
| **11** | Assembly system | ✅ **Complete — multi-part instances + LCS mates; 112 tests** |
| **12** | Verification + physics layer | ✅ **Complete — DFM, tolerances, FEA; 125 tests** |
| **13** | Model specialization + Claude 5 integration | ✅ **Complete — dataset builder, Ollama Modelfile, QLoRA skeleton, A/B evaluator, Anthropic SDK fixes; 134 tests; Claude Sonnet 5 T1–T4 87.5% (21/24), overall 21/30 (70.0%)** |
| **14A** | **GEDA Bridge: MuJoCo / URDF exporter + bundles** | ✅ **Complete — `ai_cad/geda_bridge/`, backend endpoints, `SimulatePanel.jsx`, 152/152 tests passing, MuJoCo runtime validation** |
| **14B** | Standard manipulation scene templates | ✅ **Complete — `ai_cad/geda_bridge/scene_templates.py`, 4 templates, composition API, `POST /designs/{id}/scene`, `SceneTemplatePanel.jsx`, 160/160 tests passing** |
| **15A** | LearningRobotics handshake | ✅ **Complete — `ai_cad/geda_bridge/loader.py`, bundle contract, reference loaders, `GET /capabilities`, `POST /designs/{id}/handshake`, `CapabilitiesPanel.jsx`, 10 s wedge stability test, 170/170 tests passing** |
| **15B** | RoboCompiler asset pipeline | ✅ **Complete — skill recommendation, variant sweep, trainable push-policy smoke test, 187/187 tests passing** |
| **16** | Cross-domain input (voice/text/sketch + domain detection) | ✅ **Complete — `ai_cad/domain.py` classifier, `ai_cad/intent_parser.py`, `POST /classify-domain`, domain badges, 201/201 tests passing** |
| **17** | Domain-aware parametric representation | ✅ **Complete — feature-tree schema v2.0.0, `SurfaceFeature`, `KinematicJoint`, `PCBOutline`, NACA airfoil sketch, 201/201 tests passing** |
| **18** | Automatic decomposition + domain part families | ✅ **Complete — `ai_cad/part_families.py`, `ai_cad/decomposition.py`, `ai_cad/composer.py`, `POST /decompose`, `/generate?decompose`, `DecomposePanel.jsx`, **228/228 tests passing** |
| **19** | Mechanical assembly synthesis + verification | ✅ **Complete — `Interface` library, `mate_inference.py`, revolute/prismatic solver, `assembly_collision.py`, MJCF/URDF joints/actuators/sensors, `/synthesize-assembly`, `/assembly-collision`, `/assembly-poses`, `AssemblyReplayPanel.jsx`, **251/251 tests passing** |
| **20** | Aerodynamics, thermal, and propulsion geometry | ✅ **Complete — NACA 4-digit airfoils, straight wings, propeller blades, heat sinks, SU2/OpenFOAM CFD mesh stubs, `AeroPanel.jsx`, `ThermalPanel.jsx`, **276/276 tests passing** |
| **21** | Electronics and mechatronics integration | ✅ **Complete — `PCBOutline` transpilation, electronics part families, stack decomposition + composer layout, electronics analysis, IDF/STEP export, `ElectronicsPanel.jsx`, **299/299 tests passing** |
| **22** | Multi-physics verification engine | ✅ **Complete — `ai_cad/materials.py`, `ai_cad/verification*.py`, `ai_cad/mesh_quality.py`, closed load-case templates, mesh-quality gate, backend `/verify` endpoints, frontend `VerificationPanel`, **330/330 tests passing** |
| **23** | Humanoid and full-robot system synthesis | ✅ **Complete — biped/quadruped/manipulator-on-base templates, actuator sizing, stability/workspace/gait checks, whole-system MJCF/URDF export, backend endpoints + frontend `HumanoidPanel`, 357/357 tests passing** |
| **24** | World-model simulation builder | ⏳ Planned |
| **25** | Robot brain training loop | ⏳ Planned |
| **26** | HERMES conversational supervisor | ⏳ Planned |
| **27** | Sim-to-real feedback loop | ⏳ Planned |
| **28** | Distribution + commercialization + advanced co-design plugins | ⏳ Planned |

See `PLAN.md` for full details. See `.claude/memory/robocad-path-analysis.md` and `.claude/memory/robocad-end-to-end-roadmap.md` for the PATH1/PATH2 strategic analysis.

---

## 8. Repository layout

```
RoboCAD/
├── README.md                 # Public project overview + changelog
├── PLAN.md                   # Detailed build plan (Phases 0–28)
├── PRODUCT.md                # Product definition, users, brand commitments
├── memory.md                 # This file — restart context
├── STITCH_BRIEF.md           # Original Google Stitch design brief
├── requirements.txt          # Python dependencies
├── .gitignore
├── ai_cad/                   # Core AI-CAD package
│   ├── __init__.py           # httpx2/httpcore2 shims + public exports
│   ├── prompts/
│   │   ├── system_prompt.txt
│   │   └── examples.json
│   ├── models.py
│   ├── api.py                # RoboCADBackend.generate()
│   ├── generator.py          # LLM code generation (Claude 5 + Ollama)
│   ├── executor.py
│   ├── validator.py
│   ├── exporter.py
│   ├── parameters.py
│   ├── guess_parameter.py
│   ├── code_ops.py
│   ├── feature_tree.py       # Phase 9
│   ├── transpiler.py         # Phase 9 (plus Phase 20 SurfaceFeature transpilation)
│   ├── feature_store.py      # Phase 9
│   ├── sketch_solver.py      # Phase 10 (plus Phase 17/20 NACA airfoils)
│   ├── assembly.py           # Phase 11 / Phase 19 kinematic solver
│   ├── mate_inference.py     # Phase 19
│   ├── assembly_collision.py # Phase 19
│   ├── part_families.py      # Phase 18
│   ├── decomposition.py      # Phase 18
│   ├── composer.py           # Phase 18
│   ├── domain.py             # Phase 16
│   ├── intent_parser.py      # Phase 16
│   ├── dfm.py                # Phase 12
│   ├── tolerances.py         # Phase 12
│   ├── fea.py                # Phase 12
│   ├── electronics.py        # Phase 21
│   ├── aero.py               # Phase 20
│   ├── thermal.py            # Phase 20
│   ├── cfd.py                # Phase 20
│   ├── onshape.py            # Phase 5
│   ├── manufacturing.py      # Phase 5
│   └── geda_bridge/          # Phases 14A–15B
│       ├── exporter.py
│       ├── scene_templates.py
│       ├── runtime_validator.py
│       ├── models.py
│       ├── verifier.py
│       ├── packager.py
│       ├── loader.py
│       ├── capabilities.py
│       ├── skill_recommend.py
│       ├── variant_sweep.py
│       └── skill_smoke.py
├── benchmarks/
│   ├── prompts.json
│   ├── complexity_ladder.json
│   ├── evaluate.py
│   └── evaluate_complexity.py
├── scripts/                  # Phase 13 specialization scripts
│   ├── build_training_dataset.py
│   ├── build_ollama_modelfile.py
│   ├── finetune_model.py
│   └── evaluate_finetuned.py
├── web/                      # FastAPI + React app
│   ├── backend/
│   │   └── main.py
│   └── frontend/
│       └── src/components/
├── components/               # Phase 6 robotics part library
├── designs/                  # persisted generated designs (runtime)
└── tests/                    # pytest suite
```

---

## 9. Current status snapshot

- Repo at `https://github.com/satyamdas03/RoboCAD`; `master` pushed and in sync with local.
- Phases 0–23 committed and pushed.
- `ai_cad/` package implements generation, execution, validation, parameter extraction, self-correction, Onshape upload, manufacturing reports, face-click parameter guessing, feature trees, sketch constraints, assemblies, DFM/tolerances/FEA, Claude 5 compatibility, GEDA Bridge bundle export, scene templates, LearningRobotics handshake, RoboCompiler skill pipeline, domain classification, per-domain intent parsing, automatic decomposition/part families, mechanical assembly synthesis (mate inference, kinematic solver, collision checks, joint-aware MJCF/URDF export), aero/thermal/propulsion geometry (NACA airfoils, wings, propeller blades, heat sinks, CFD mesh stubs, lightweight aero/thermal analysis), electronics/mechatronics co-design (PCB outlines, enclosures, connectors, cable channels, fan mounts, heat spreaders, IDF/STEP export), multi-physics verification engine (closed load-case templates, solver abstraction, mesh-quality gate, material library), and humanoid/full-robot system synthesis (biped/quadruped/manipulator-on-base templates, actuator sizing, stability/workspace/gait checks, whole-system MJCF/URDF export).
- Web app has FastAPI backend + React frontend with Kinetic Precision dark workstation UI plus `AeroPanel.jsx`, `ThermalPanel.jsx`, `ElectronicsPanel.jsx`, `VerificationPanel.jsx`, and `HumanoidPanel.jsx`.
- Test suite: **357/357 passing tests**.
- Latest fixes: transpiler shell/fillet/chamfer now use the correct per-part `BuildPart` variable; duct family creates a hollow tube via outer + inner subtract instead of the fragile `shell` operation; `ai_cad/sketch_solver.py` resolves NACA airfoil parameter-name chords to avoid ZeroDivisionError; electronics stack layout places PCB on enclosure standoffs with optional heat spreader, fan mount, cable channel, and edge connectors; Phase 23 hotfix eliminated RAM/CPU hotspots (bounded verification cache, shared mesh loading, executor cleanup, part-level mesh deduplication, AABB culling, recursion guards, Three.js disposal); corrected forward-kinematics transform double-counting; added hand fixed joints; lazy reservoir sampling in workspace sweep; fallback cube meshes for placeholder robot links; post-ship robot arm hardening (commits `87c8f7b`, `980482b`, `174df8c`, `4de18d8`, `1b83561`, `69367a1`) mapped upper/forearm/gripper to `limb_segment`/`end_effector` families, aligned limb pin interfaces, fixed jaw mirroring, fixed assembly solver part-family csys lookup, corrected sketch entity placement in BuildSketch via `Locations`, added subtractive joint/pivot holes, and fixed sketch-ID / parameter-name collisions in humanoid hip/shoulder hubs so the rule-based "biped humanoid robot" prompt succeeds end-to-end; stress-test routing now documented (rule path for full systems, LLM path for single parts).
- Live end-to-end verified: `/decompose`, `/classify-domain`, `/generate?decompose=True`, `/designs/{id}/assembly-collision`, `/designs/{id}/assembly-poses`, `/designs/{id}/aero-report`, `/designs/{id}/thermal-report`, `/designs/{id}/cfd-mesh`, `/designs/{id}/electronics-report`, `/designs/{id}/idf-export`, `/robot-templates`, `/designs/{id}/robot-analysis`, and `/designs/{id}/simulate` for humanoid/quadruped/manipulator-on-base all work.
- Strategic decision maintained: PATH1 (GEDA Bridge) shipped first; PATH2 (voice/world-model-to-robot) is the long-term North Star.

**Next work:**
1. **Phase 24 — World-model simulation builder:** parameterized scenes (robot + objects + terrain + sensors + task), domain randomization, MuJoCo/Isaac Sim export, replay/inspection tools.
2. **Robot arm cosmetic/mechanical refinement (queued by user):** add deterministic fillets/chamfers, joint bosses/flanges, tapered links, and shaped gripper jaws to the rule-based `limb_segment`/`end_effector` families so the default "robot arm with gripper" looks like an engineer-grade starting point, not a first-pass block model.
3. Keep Phases 14A–23 under maintenance and the 357-test suite green.
4. Continue local-model fine-tuning (`robocad-ft:latest`) as a background experiment.

---

## 10. Commands that work

### Install and run Phase 0 validation

```powershell
cd C:\Users\point\projects\RoboCAD
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:ANTHROPIC_API_KEY = "..."          # or key for Anthropic-compatible endpoint
$env:ROBOCAD_MODEL = "qwen3-coder:latest"  # optional override; "claude-sonnet-5-20250501" for Claude 5
python validate.py
```

### Run tests

```powershell
$env:PYTHONPATH = "C:\Users\point\projects\RoboCAD"
python -m pytest tests -q
```

### Start the web app

```powershell
cd C:\Users\point\projects\RoboCAD
.venv\Scripts\Activate.ps1
$env:ANTHROPIC_API_KEY = "..."
python -m uvicorn web.backend.main:app --reload --port 8000

# Second terminal:
cd C:\Users\point\projects\RoboCAD\web\frontend
npm install
npm run dev
# Open http://localhost:5173
```

### Commit and push

```powershell
cd C:\Users\point\projects\RoboCAD
git add .
git commit -m "robocad: descriptive message"
git push origin master
```

---

## 11. Design principles

1. **Parametric code is the source of truth.** Mesh is a derived artifact.
2. **Fail visibly and correct.** Tracebacks are fed back to the LLM.
3. **No mesh dead-ends.** Always produce an editable model.
4. **Start local, integrate later.** Prove the loop before Onshape/simulation.
5. **Document every push.** README/memory/PLAN are living logs.
6. **No API keys in files.** All keys via environment variables.
7. **Ship PATH1 before PATH2.** Validate CAD-to-physics handoff before chasing the full vision.

---

## 12. Open decisions / questions

1. Which LLM provider should be the default for T4/T5? Currently Claude 5 for cloud; `qwen3-coder:latest` for local.
2. Should we also support `cadquery` as an alternate kernel? Defer until build123d is proven.
3. When should we buy hardware? Defer until GEDA Bridge produces real parts that need fabrication.
4. Should designs be tracked in Git? Yes for code; exports are gitignored.
5. Should GEDA Bridge live inside RoboCAD or as a new top-level repo? Current plan: inside RoboCAD (`ai_cad/geda_bridge/`) to reuse backend/frontend/test infrastructure.

---

## 13. Memory trigger

If the session restarts and all context is lost, read these files in order:

1. `C:\Users\point\.claude\projects\C--Users-point-projects-RoboCAD\memory\MEMORY.md`
2. Every memory file linked from it, especially:
   - `robocad-path-analysis.md`
   - `robocad-end-to-end-roadmap.md`
   - `claude5-integration-fixes.md`
   - `phase13-model-specialization.md`
3. `C:\Users\point\projects\RoboCAD\memory.md` (this file)
4. `C:\Users\point\projects\RoboCAD\README.md`
5. `C:\Users\point\projects\RoboCAD\PLAN.md`
6. `C:\Users\point\projects\RoboCAD\PRODUCT.md`

For the most recent state, also check:
- Latest commit hash (`git log --oneline -5`)
- `.claude/memory/robocad-path-analysis.md` for PATH1/PATH2 status
- `.claude/memory/claude5-integration-fixes.md` for latest benchmark numbers

To force a full sync at any time, type:

> `:POINTBREAK`

---

## 14. Summary for fast restart

If you are resuming this session with no other context:

> We are building **RoboCAD**, an AI-powered parametric CAD tool for robotics hardware. The repo is at `https://github.com/satyamdas03/RoboCAD`. **Phases 0–23 are committed and pushed** (prompt → build123d → STL/STEP → Onshape → manufacturing report → component library → dark Kinetic Precision UI → feature tree → sketch constraints → assemblies → DFM/tolerances/FEA → model specialization → Claude 5 integration → GEDA Bridge → scene templates → LearningRobotics handshake → RoboCompiler pipeline → cross-domain input → domain-aware representation → automatic decomposition + part families → mechanical assembly synthesis → aero/thermal/propulsion geometry → electronics/mechatronics co-design → multi-physics verification engine → humanoid/full-robot system synthesis, **357 tests passing**). Post-ship hardening commits `87c8f7b`, `980482b`, `174df8c`, `4de18d8`, `1b83561`, and `69367a1` fixed the rule-based `robot arm with gripper` and `biped humanoid robot` layouts end-to-end: mapped upper/forearm/gripper to `limb_segment`/`end_effector` families, aligned limb pin interfaces, fixed jaw mirroring, fixed assembly solver part-family csys lookup, corrected sketch entity placement in BuildSketch via `Locations`, added subtractive joint/pivot holes, and fixed sketch-ID / parameter-name collisions in humanoid hip/shoulder hubs. The immediate next phase is **Phase 24 — World-model simulation builder**: parameterized scenes, domain randomization, MuJoCo/Isaac Sim export, replay/inspection. **Also queued:** robot arm cosmetic/mechanical refinement (fillets, chamfers, joint bosses, tapered links, shaped jaws). Strategic decision: ship PATH1 (GEDA Bridge) before PATH2 (voice-to-CAD-to-world-model). See `.claude/memory/robocad-path-analysis.md` and `.claude/memory/robocad-end-to-end-roadmap.md`. Say `:POINTBREAK` to force a full dossier sync.

---

*Last updated: 2026-09-01 (Phases 0–23 complete; humanoid and full-robot system synthesis shipped and verified live; post-ship hardening commits `87c8f7b`, `980482b`, `174df8c`, `4de18d8`, `1b83561`, `69367a1` fix the rule-based robot arm and biped humanoid layouts end-to-end; 357/357 tests passing; robot arm cosmetic refinement queued; Phase 24 world-model simulation builder is next)*
