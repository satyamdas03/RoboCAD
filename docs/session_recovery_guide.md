# RoboCAD Session Recovery Guide

**If the conversation restarts and all context is lost, read this file first, then read every file listed below in order.**

This guide exists because RoboCAD has grown across many phases and redesigns. The conversation state is not enough; the canonical state lives in files. Read them line by line to recover the full picture before writing code.

---

## Step 1 — Read the project memory index

File: `C:\Users\point\.claude\projects\C--Users-point-projects-RoboCAD\memory\MEMORY.md`

This lists all memory files. Read every linked memory file next.

---

## Step 2 — Read every memory file in order

These files are in `C:\Users\point\.claude\projects\C--Users-point-projects-RoboCAD\memory\`:

1. `phase3-phase4-completion.md` — Phases 0–4 done; parameter editing, face-click guessing, design library, remix/tags.
2. `phase5-phase6-completion.md` — Onshape export/sync, manufacturing reports, 12 robotics component templates.
3. `impeccable-ui-redesign.md` — First full UI redesign (Precision Lab Instrument light theme).
4. `google-stitch-ui-redesign.md` — Second/current UI redesign (Kinetic Precision dark workstation); demo video + README walkthrough.
5. `engineer-grade-roadmap.md` — Strategic decision and Phases 8–14 roadmap for complex, high-precision, multi-part CAD.

---

## Step 3 — Read the canonical repo dossiers

These files are at the repo root `C:\Users\point\projects\RoboCAD\`:

1. `README.md` — Mission, architecture, tech stack, current phase table (Phases 0–14), UI demo, quickstart.
2. `PLAN.md` — Full end-to-end build plan, completed milestones, risks, and detailed Phase 8–14 definitions.
3. `PRODUCT.md` — Product definition, users, brand commitments, design context, evidence on hand.
4. `STITCH_BRIEF.md` — Original brief fed to Google Stitch for the Kinetic Precision UI.

---

## Step 4 — Read the core source files (line by line)

### Backend / AI-CAD pipeline (`ai_cad/`)

Read every file in this directory:

- `__init__.py`
- `api.py` — `RoboCADBackend.generate()` orchestrates code gen → execution → validation.
- `code_ops.py` — Parameter replacement in generated code.
- `executor.py` — Safely runs generated build123d Python in a subprocess.
- `exporter.py` — STL/STEP/3MF export helpers.
- `generator.py` — LLM code generation (Claude API or OpenAI-compatible local models).
- `guess_parameter.py` — Face-normal → parameter heuristic.
- `manufacturing.py` — Manufacturing report generation.
- `models.py` — Pydantic models: `CADParameter`, `ExportPaths`, `ValidationReport`, `ManufacturingReport`, `GenerationResult`.
- `onshape.py` — HMAC-signed Onshape REST API client.
- `parameters.py` — AST-based numeric parameter extraction from generated code.
- `validator.py` — STL manifold/watertight validation.
- `prompts/system_prompt.txt` — System prompt the LLM sees.
- `prompts/examples.json` — Few-shot examples.

### Web backend (`web/backend/`)

- `main.py` — All FastAPI endpoints: `/generate`, `/designs`, `/designs/{id}`, `/regenerate`, `/remix`, `/guess-parameter`, `/manufacturing-report`, `/onshape/*`, `/exports/*`.

### Frontend (`web/frontend/src/`)

- `App.jsx` — Root layout and state management.
- `api.js` — All frontend API calls.
- `styles/index.css` — `kp-*` Kinetic Precision token system.
- `index.html` — Font loading and direction contract.

### Frontend components (`web/frontend/src/components/`)

Read every component file:

- `ComponentLibrary.jsx`
- `DownloadLinks.jsx`
- `HistorySidebar.jsx`
- `ManufacturingReport.jsx`
- `OnshapeUpload.jsx`
- `ParameterList.jsx`
- `PromptInput.jsx`
- `RemixPanel.jsx`
- `STLViewer.jsx`
- `StatusPanel.jsx`
- `TagEditor.jsx`
- `standard_components.json` — Component library seed data.

---

## Step 5 — Read the test files

All files in `C:\Users\point\projects\RoboCAD\tests\`:

- `test_api.py`
- `test_code_ops.py`
- `test_design_library.py`
- `test_executor.py`
- `test_generator.py`
- `test_guess_parameter.py`
- `test_manufacturing.py`
- `test_onshape.py`
- `test_parameters.py`
- `test_validator.py`
- `test_web_backend.py`

---

## Step 6 — Read configuration and helper files

- `.env.example` — Required environment variables (no secrets).
- `.gitignore`
- `requirements.txt`
- `web-start.ps1` — Windows backend launcher.
- `package.json` (root)
- `web/frontend/package.json`
- `web/frontend/vite.config.js`

---

## Step 7 — Inspect the working tree and recent git history

Run these commands before doing anything else:

```powershell
cd C:\Users\point\projects\RoboCAD
git status
git log --oneline -20
git diff HEAD~1 --stat
```

---

## Step 8 — Start the servers and verify

Once the files above are understood, run the smoke tests:

```powershell
# Backend
"/c/Users/point/AppData/Local/hermes/hermes-agent/venv/Scripts/python" -m uvicorn web.backend.main:app --host 127.0.0.1 --port 8000

# Frontend (second terminal)
cd web/frontend
npm run dev
```

Then:

```powershell
# Run tests
"/c/Users/point/AppData/Local/hermes/hermes-agent/venv/Scripts/python" -m pytest tests -q

# Build frontend
cd web/frontend
npm run build
```

---

## What each phase proved

| Phase | What works now | Key files |
|---|---|---|
| 0–1 | AI → build123d → STL pipeline; self-correction; benchmark | `ai_cad/generator.py`, `ai_cad/executor.py`, `validate.py` |
| 2 | FastAPI web backend + React frontend + 3D viewer | `web/backend/main.py`, `web/frontend/src/App.jsx`, `web/frontend/src/components/STLViewer.jsx` |
| 3 | Editable parameters, versioned regeneration, face-click parameter guessing | `ai_cad/code_ops.py`, `ai_cad/guess_parameter.py`, `ParameterList.jsx`, `STLViewer.jsx` |
| 4 | Design library, search/filter, tags, remix | `ComponentLibrary.jsx`, `TagEditor.jsx`, `RemixPanel.jsx`, `tests/test_design_library.py` |
| 5 | Onshape export/sync, manufacturing reports | `ai_cad/onshape.py`, `ai_cad/manufacturing.py`, `ManufacturingReport.jsx`, `OnshapeUpload.jsx` |
| 6 | 12 robotics component templates | `standard_components.json`, `ComponentLibrary.jsx` |
| 7 | Kinetic Precision dark workstation UI | `web/frontend/src/styles/index.css`, `App.jsx`, all component files |
| 8–14 | Engineer-grade roadmap (not started) | `README.md`, `PLAN.md`, `memory/engineer-grade-roadmap.md` |

---

## If you are resuming after a crash

1. Read `MEMORY.md`.
2. Read every memory file linked from it.
3. Read `README.md` and `PLAN.md` fully.
4. Run `git status` and `git log --oneline -20`.
5. Run the pytest suite and the frontend build.
6. Only then continue the current phase.

**Current active phase:** Phase 8 — Complexity benchmark + feature-tree schema. See `PLAN.md` section 9 and `memory/engineer-grade-roadmap.md`.
