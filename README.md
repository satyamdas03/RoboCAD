# 🤖 RoboCAD — AI-Powered Parametric CAD for Robotics

> **Mission:** Let robotics builders design real, editable, manufacturable hardware parts by describing them in plain language — no months of sketch-extrude-mate training required.
>
> **Core bet:** The AI writes **parametric CAD code** (build123d / FeatureScript), not throwaway meshes. The model you get is editable, versionable, and exportable for 3D printing, machining, or Onshape.
>
> **Latest milestone:** Phase 0 benchmark passes **8/8 (100%)** — the AI → build123d → STL loop is validated.

---

## 🧑‍💻 Author

**Satyam Das** — CS grad, quant/AI engineer, aspiring roboticist.

* GitHub: [@satyamdas03](https://github.com/satyamdas03)
* Sister project: [LearningRobotics](https://github.com/satyamdas03/LearningRobotics) — where the theory behind these parts is learned chapter by chapter.
* Motto: *"Think in systems, design in language, build in hardware."*

---

## 🔗 Why this exists / connection to LearningRobotics

`LearningRobotics` is a public learning journal that walks through robotics fundamentals — C-space, rigid-body motions, kinematics, dynamics, and eventually control + RL. The natural next step after *understanding* a robot is to *build* it. But professional CAD has a steep activation energy: weeks of UI muscle memory before you can express a simple idea like:

> *"A 120 mm × 80 mm × 3 mm base plate with four M3 mounting holes on a 100 mm × 60 mm grid and two NEMA-17 motor mounts."*

RoboCAD closes that gap. It lets me (and anyone else) operate at the level of intent, not clicks. Designs produced here can be:

1. Printed or machined directly (STL / STEP / 3MF export).
2. Synced to Onshape later for professional assemblies and mates (Phase 5).
3. Reused as parts in `LearningRobotics` simulations and hardware builds.

In short: **LearningRobotics teaches the robot. RoboCAD designs the parts.**

---

## ✨ What makes this different

| Tool category | Examples | Output | Editable? | Manufacturable? |
|---|---|---|---|---|
| Text-to-mesh | Meshy, Shap-E | mesh (STL-like) | ❌ no | ⚠️ limited |
| Text-to-SDF/voxel | research demos | implicit field | ❌ no | ❌ no |
| Parametric template filling | Onshape configs | existing parametric model | ✅ yes | ✅ yes |
| **RoboCAD (this repo)** | **LLM → build123d code → feature tree** | **parametric CAD script** | **✅ yes** | **✅ yes** |

The key insight: **CAD is code.** Modern parametric kernels (OpenCASCADE via build123d/CADQuery, Onshape's FeatureScript) are programming environments. LLMs are already excellent at code generation. RoboCAD turns hardware design into a code-generation + execution problem, which is exactly the right shape for an AI researcher.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  User layer                                                 │
│  • natural-language prompt                                  │
│  • parameter sliders / stylus reference points              │
│  • design history + remix                                   │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  AI orchestrator (Claude / GPT-4 + structured output)       │
│  • intent parsing (chassis, bracket, gripper, pulley...)    │
│  • emits parametric build123d / FeatureScript code          │
│  • self-corrects on execution / validation failures         │
│  • explains what it built and why                           │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  CAD execution engine                                       │
│  • build123d / CADQuery (local, Phase 0–4)                │
│  • optional Onshape REST API + FeatureScript (Phase 5)    │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  Geometry validation layer                                  │
│  • build success / traceback capture                        │
│  • watertight / manifold check (manifold3d / trimesh)       │
│  • bounding-box, mass, CoM sanity                            │
│  • manufacturability hints (overhangs, fastener clearances) │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  Viewer + edit layer                                        │
│  • web-based 3D viewer (three.js / react-three-fiber)       │
│  • expose named parameters from generated code              │
│  • point-and-type dimension editing (v1)                    │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  Persistence + reuse                                          │
│  • design = {prompt, code, parameters, exports, versions}   │
│  • searchable library                                         │
│  • remix: old design becomes seed for new prompt              │
└─────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Tech stack

| Layer | Technology | Rationale |
|---|---|---|
| CAD kernel | **build123d** | Clean Python API on OpenCASCADE; LLMs write it well; open-source |
| Mesh validation | `trimesh`, `manifold3d` | Watertight checks, mass properties |
| AI model | Claude / GPT-4 via API | Best-in-class code generation and self-correction |
| Backend (Phase 2+) | FastAPI | Python-native, easy to invoke build123d |
| Frontend (Phase 2+) | React + three.js / react-three-fiber | Standard web 3D viewer |
| Storage | SQLite + JSON files + Git | Simple, versioned, portable |
| Export formats | STL, STEP, 3MF | 3D printing + machining + Onshape |
| Onshape sync (Phase 5) | Onshape REST API + FeatureScript | Professional assemblies and mates |

---

## 🚀 Current phase

| Phase | Goal | Status |
|---|---|---|
| **0** | Validate the AI → parametric-code loop in Python | ✅ **Complete — 8/8 prompts pass** |
| **1** | Robust generation + self-correction backend | ✅ **Complete — 19/20 prompts pass (95%)** |
| 2 | Minimal web app (prompt + viewer + export) | ⏳ Planned |
| 3 | Parameter / stylus editing layer | ⏳ Planned |
| 4 | Design library + remix | ⏳ Planned |
| 5 | Onshape export / sync + manufacturing reports | ⏳ Planned |
| 6 | Robotics-aware component templates | ⏳ Planned |

See [`PLAN.md`](PLAN.md) for the complete end-to-end build plan.

---

## 🧪 Phase 0 quickstart

```bash
cd RoboCAD
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
export ANTHROPIC_API_KEY=...  # Windows: $env:ANTHROPIC_API_KEY=...
python validate.py
```

`validate.py` runs a small benchmark of prompts through the AI → build123d → STL pipeline and reports which ones succeed. It is the riskiest-assumption test for the whole project.

---

## 🧪 Phase 1 quickstart — structured backend + 20-prompt benchmark

```bash
cd RoboCAD
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
export ANTHROPIC_API_KEY=...  # Windows: $env:ANTHROPIC_API_KEY=...
export ROBOCAD_MODEL=qwen3-coder:latest  # optional; defaults to Claude

# Run the pytest suite
python -m pytest tests -q

# Run the 20-prompt Phase 1 benchmark
python benchmarks/evaluate.py
```

`ai_cad.api.generate()` returns a structured `GenerationResult` with:
- `code` — the generated build123d script,
- `parameters` — editable named numeric parameters extracted from the code,
- `exports` — paths to STEP + STL files,
- `validation` — watertight/manifold/bounds report,
- `attempts_used` — how many LLM calls were needed.

---

## 🧱 Repository layout

```
RoboCAD/
├── README.md                 # This file — project overview + changelog
├── PLAN.md                   # Detailed build plan
├── requirements.txt          # Python dependencies
├── .gitignore
├── ai_cad/                   # Core AI-CAD package
│   ├── __init__.py           # Public exports
│   ├── prompts/
│   │   ├── system_prompt.txt # LLM system prompt
│   │   └── examples.json     # Few-shot build123d examples
│   ├── models.py             # Pydantic response models
│   ├── api.py                # Unified RoboCADBackend.generate()
│   ├── generator.py          # prompt → code
│   ├── executor.py           # run build123d safely
│   ├── validator.py          # geometry sanity checks
│   ├── exporter.py           # STL / STEP / 3MF export
│   └── parameters.py         # AST-based parameter extraction
├── benchmarks/               # Phase 1 curated prompt set + runner
│   ├── prompts.json          # 20 robotics prompts
│   └── evaluate.py           # python benchmarks/evaluate.py
├── web/                      # (Phase 2) FastAPI + React app
├── components/               # (Phase 6) robotics part library
├── designs/                  # (Phase 4) saved designs
└── tests/                    # pytest suite
```

---

## 🧠 Design principles

1. **Parametric code is the source of truth.** The prompt and generated script are saved; the mesh is a derived artifact.
2. **Fail visibly and correct.** Every generated script is executed; tracebacks are fed back to the LLM for self-repair.
3. **No mesh dead-ends.** Always produce an editable model, even if simple.
4. **Start local, integrate later.** Prove the loop with build123d before wrestling with Onshape API limits.
5. **Document every push.** The README is a living project log; each commit syncs the current phase and decisions.

---

## 🗺️ Roadmap to "extraordinary"

The long-term vision is not a chatbot that draws shapes. It is a **robotics design companion** that understands:

- Standard robot components (NEMA-17/23, bearings, belts, pulleys, fasteners).
- Kinematic constraints (motor shaft spacing, pulley ratios, link lengths).
- Manufacturability (print orientation, tolerance, material).
- Assembly intent (mates, constraints, BOM).

A user should eventually be able to say:

> *"Design a 2-DOF robot arm: shoulder NEMA-17, elbow NEMA-17, 200 mm link, belt drive, base mountable on 2040 aluminum extrusion."*

and receive a folder of editable parts ready for printing, assembly in Onshape, and simulation export to `LearningRobotics` / MuJoCo.

---

## 🤝 Relationship to other work

* **LearningRobotics** ([repo](https://github.com/satyamdas03/LearningRobotics)) — theory, kinematics, dynamics, and the PIBench physical-intuition benchmark. RoboCAD designs parts that can be loaded there.
* **PIBench** — physical common-sense benchmark. RoboCAD could generate the 3D assets for new PIBench scenes from prompts.
* **Hardware BOM** from LearningRobotics — will be imported as the component library so RoboCAD designs are cost-aware.

---

## 📝 Changelog

### 2026-08-22 — Phase 1 complete: robust backend + 20-prompt benchmark (19/20 = 95%)

* Added structured response models in `ai_cad/models.py` (`GenerationResult`, `CADParameter`, `ValidationReport`, `ExportPaths`).
* Added AST-based parameter extraction in `ai_cad/parameters.py` so generated dimensions can be edited later.
* Added unified `ai_cad/api.py` with `RoboCADBackend.generate()` and `generate()` convenience function.
  * Orchestrates `generate_model → execute_code → validate_model → extract_parameters`.
  * Self-corrects on both execution/runtime failures and geometry validation failures, up to `max_retries`.
* Hardened `ai_cad/executor.py` to write metadata as JSON (no stdout parsing), include `script_path` in results, and improve error capture.
* Added `benchmarks/prompts.json` with 20 curated robotics prompts and `benchmarks/evaluate.py` runner.
* Phase 1 benchmark result: **19/20 prompts passed (95.0%)** within two retries.
  * 7/8 easy, 9/9 medium, 3/3 hard.
  * Known failure: `pendulum_bob` (sphere with a blind threaded-insert hole) remains non-watertight after two self-correction retries.
* Added pytest tests: `test_executor.py`, `test_validator.py`, `test_parameters.py`, `test_api.py`.
* Total test suite: **18 passing tests**.

### 2026-08-22 — Phase 0 validation complete (8/8 pass)

* Ran `validate.py` against 8 robotics-flavored prompts; **100% produced valid STL/STEP** on first attempt.
* Fixed runtime issues discovered during validation:
  * `ai_cad/generator.py` — added Anthropic Python SDK ≥1.0 compatibility (`temperature` via `extra_body`) and `ROBOCAD_MODEL` env override.
  * `ai_cad/executor.py` — fixed f-string escaping for volume metadata in generated scripts.
  * `validate.py` — fixed error-message extraction when validation returns empty warnings.
* Rewrote `ai_cad/prompts/system_prompt.txt` and `ai_cad/prompts/examples.json` with working build123d patterns:
  * Pattern A: `Locations`/`GridLocations`/`PolarLocations` + `Cylinder(..., mode=Mode.SUBTRACT)` inside one `BuildPart`.
  * Pattern B: `BuildSketch(face)` + `Circle` + `extrude(amount=-depth, mode=Mode.SUBTRACT)` for side-face holes.
  * Pattern C: explicit solid subtraction (`part.part = part.part - bore`) for central bores.
  * Pattern D: raised bosses/mounts to avoid coplanar non-manifold geometry.
* Phase 0 success criteria exceeded: target was ≥90% after self-correction; achieved 100% on first attempt.

### 2026-08-21 — Repo created, Phase 0 scaffold

* Created `satyamdas03/RoboCAD` repository.
* Wrote `README.md` and `PLAN.md` capturing the full project context, architecture, and connection to `LearningRobotics`.
* Scaffolded the `ai_cad/` package:
  * `generator.py` — prompt → LLM → build123d code extraction.
  * `executor.py` — safe subprocess execution of generated code.
  * `validator.py` — manifold / bounding-box sanity checks.
  * `exporter.py` — STL / STEP export.
  * `prompts/system_prompt.txt` and `prompts/examples.json` — few-shot examples.
* Added `validate.py` for the first riskiest-assumption test.
* Committed and pushed to GitHub.

---

## 📬 Contact & follow along

* GitHub: [@satyamdas03](https://github.com/satyamdas03)
* Project updates will be pushed to this repo as phases are completed.

---

**License:** MIT — use it, fork it, improve it.

> *"The goal is not to replace CAD experts. The goal is to let people who understand systems and robotics express hardware ideas without fighting a sketcher."*
