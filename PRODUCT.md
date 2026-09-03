# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary user is a **solo mechanical engineer, robotics researcher, or advanced maker** who designs custom robot hardware parts but does not want to spend hours in traditional sketch-extrude-mate CAD. They prototype mounts, brackets, hubs, chassis plates, and end-effectors in quick iterative loops.

Secondary audiences include **robotics students and competition teams** who need editable, manufacturable parts fast, and **technically confident hobbyists** who can read dimensions and parameters but lack CAD fluency.

## Product Purpose

RoboCAD lets users describe robot parts and assemblies in plain language (and eventually voice) and receive editable, parametric CAD models plus simulation-ready bundles. The AI generates executable build123d/FeatureScript code instead of a throwaway mesh, so the output is versionable, parameter-editable, 3D-printable/machinable, syncable to Onshape, and loadable into MuJoCo/Isaac Sim for robot skill training.

Success means a user goes from “a 120 mm × 80 mm × 3 mm base plate with four M3 holes on a 100 mm × 60 mm grid” to a verified STL/STEP export, a parameter panel, a manufacturing report, and a MuJoCo bundle in under a few minutes.

## Positioning

The meaningful difference is **parametric code, not mesh soup**. Most text-to-3D tools produce surfaces users cannot edit or dimension. RoboCAD produces feature-tree-style code that exposes named parameters, supports face-driven dimension editing, and exports clean STEP for machining and Onshape assemblies. Competitors can copy the prompt box; they cannot truthfully claim the same editability and manufacturing fidelity.

## Operating Context

- Users work on **desktop browsers** in bright offices, labs, or workshops; sessions are a mix of quick single-part generation and short iterative refinement passes.
- The core loop is: **prompt → generate → inspect 3D model → tweak parameters or click a face → regenerate → export/manufacture/upload**.
- Existing assets include generated STL/STEP files, SQLite design history, parameter dictionaries, tags, parent-child remix links, and Onshape document thumbnails.
- The browser viewport is usually large, but users may also run the app on a laptop next to hardware, so contrast and target sizes matter.

## Capabilities and Constraints

- **Capabilities:** natural-language prompt-to-CAD, parameter editing via sliders and face-click guessing, design history with search/filter/tags, component library with seeded robotics templates, remix from any prior design, manufacturing report (volume, overhangs, hole diameter, print-time heuristic), one-click STEP upload to Onshape, feature-tree editing, multi-part assembly with LCS mates, DFM/tolerance/FEA verification, Claude 5 + local Ollama model support, simulation-ready MuJoCo/URDF bundle export (Phase 14A), domain classification + per-domain intent parsing (Phase 16), automatic system decomposition into part families (Phase 18), mechanical assembly synthesis with mates/joints/collision checks (Phase 19), aero/thermal/propulsion geometry with NACA airfoils/wings/heat sinks/propellers and CFD mesh stubs (Phase 20), electronics/mechatronics co-design with PCB outlines, enclosures, connectors, cable routing, fan mounts, heat spreaders, compute modules, event camera mounts, and IDF/STEP export (Phase 21), multi-physics verification engine with structural/thermal/CFD/dynamic load-case templates and mesh-quality gate (Phase 22), humanoid and full-robot system synthesis with biped/quadruped/manipulator-on-base templates, actuator sizing, stability/workspace/gait checks, and whole-system MJCF/URDF export (Phase 23), world-model simulation builder with MuJoCo/Isaac Sim export, domain randomization, procedural terrain, and rich replay capture (Phase 24), attention-based robot brain training layer with compute-budget world-model co-design, event-driven sensing, and NumPy-only CEM policy training (Phase 25 foundation), future HERMES conversational supervisor and sim-to-real feedback loop.
- **Constraints:** backend runs locally (FastAPI + build123d + optional Ollama/Claude); the 3D viewer is three.js / react-three-fiber; exports are STL/STEP/3MF, MuJoCo/URDF bundles, SU2/OpenFOAM CFD mesh/config stubs, and IDF v3.0 `.emn`/`.emp` + STEP placeholder; local SQLite/JSON is the source of truth for history; Onshape integration requires user-provided HMAC credentials stored in `.env`; full silicon EDA and high-fidelity CFD solvers remain external tools.
- **Terminology:** prompt, design, parameters, export, regeneration, remix, face/parameter guessing, component library, manufacturing report, Onshape upload, feature tree, assembly, mate, DFM, FEA, bundle, scene template, world model, HERMES.
- **Brand:** name kept as **RoboCAD**; visual direction is *Kinetic Precision* — a dark scientific engineering workstation with surgical cyan accent (#00e5ff), near-black ground (#121315), obsidian panels, and `Inter` + `JetBrains Mono` typography. The earlier *Precision Lab Instrument* light theme was superseded by this darker, denser workstation aesthetic. No future redesign may revert to generic SaaS gradients, cartoon UI, cyberpunk neon, or military-industrial steel tropes without a new user decision.

## Brand Commitments

- Product name is **RoboCAD**.
- Current visual direction: *Kinetic Precision* — dark-first scientific engineering workstation, near-black ground (#121315), obsidian panels (#1b1c1e / #1f2022), surgical cyan accent (#00e5ff), tactical amber for warnings (#feb300), `Inter` + `JetBrains Mono` typography, instrument-grade panels and readouts.
- Previous visual direction: *Precision Lab Instrument* — light ground, teal accent (#0d9488), IBM Plex Sans type.
- No existing logo, palette, or typeface is binding beyond the redesign decisions above.
- Anti-references from the user: avoid generic SaaS purple/blue gradients, card-on-card dashboard clichés, cartoon/childish UI, heavy cyberpunk neon, and military-industrial olive/steel tropes.

## Design Context

The Google Stitch redesign was driven by `STITCH_BRIEF.md` and the generated `stitch_precision_engineering_interface/` reference files. The final implementation merged the *Kinetic Precision* dark workstation aesthetic into the existing React component tree: fixed instrument header, left sidebar (component library + history), central 3D viewport, right inspector panel (metadata / validation / selected face / quick export), and a bottom grid of manufacturing / Onshape / tags / remix panels. All `api.js` exports, backend endpoints, STLViewer face-click logic, React component props, and `standard_components.json` schema were preserved.

## Evidence on Hand

- Working end-to-end web app with FastAPI backend and a Google Stitch *Kinetic Precision* dark workstation React frontend.
- **414/414 pytest tests passing** across default, heavy/slow, and mujoco tiers.
- Frontend production build passes; live end-to-end generation verified for mechanical parts, robot-arm assemblies, NACA airfoil wings, aero/thermal/CFD reports, electronics-stack analysis/IDF export, humanoid/quadruped/manipulator-on-base robot templates with simulation-ready MJCF/URDF bundles, and attention-based brain training endpoints (`/train-brain`, `/brain-replay-attention`).
- 12 standard robotics component templates in `ComponentLibrary`.
- Feature-tree backend, sketch constraint solver, assembly system, DFM/tolerance/FEA verification, domain classification, automatic decomposition, mechanical assembly synthesis, aero/thermal/propulsion geometry, electronics/mechatronics co-design, multi-physics verification engine, humanoid/full-robot system synthesis, world-model simulation builder, and attention-based robot brain training layer all implemented and tested.
- Claude 5 integration complete with Anthropic SDK compatibility fixes; first Claude Sonnet 5 Phase 8 benchmark run reached 21/30 (70.0%), with **T1–T4 at 87.5% (21/24)**.
- Latest generator fixes harden code extraction against nested markdown fences from self-correction responses and resolve NACA airfoil parameter-name chords.
- Generated Stitch reference files (`stitch_precision_engineering_interface/`) retained for provenance.
- README-embedded end-to-end demo: `assets/robocad_kinetic_precision_demo.webm` + `assets/robocad_kinetic_precision_demo.gif` + `assets/robocad_kinetic_precision_demo_poster.jpg`, plus `scripts/record_demo.py` Playwright recorder for reproducible demos.
- README, PLAN.md, PRODUCT.md, dossiers, and memory files document current phases, architecture, design context, and the PATH1/PATH2 strategic roadmap.
- Phase 22 — multi-physics verification engine — is complete. Phase 23 — humanoid and full-robot system synthesis — is complete and shipped, including a post-ship hardening commit (`87c8f7b`) that fixes the rule-based `robot arm with gripper` layout to use real `limb_segment`/`end_effector` families and interface-aware placement. Phase 24 — world-model simulation builder — is complete and shipped with MuJoCo + Isaac Sim export, domain randomization, body-name alias resolution, procedural terrain variants (stairs/ramp/uneven), Isaac JSON schema validation, and a rich frontend replay panel. Phase 25 — robot brain training loop — foundation is complete and shipped: `ai_cad/geda_bridge/brain/` NumPy-only CEM trainer, `ComputeBudget`/`attention_regions`/`event_camera`/saliency world-model extensions, `compute_module` + `event_camera_mount` part families, `/train-brain` endpoints, and `BrainTrainingPanel`. Phase 26 — HERMES conversational supervisor — is the next build target.

## Product Principles

1. **Intent over clicks.** The interface should let users express geometry in language, numbers, and direct model interaction, not buried CAD menus.
2. **Editability first.** Every generated part is a living parameter set, not a frozen mesh; the UI must make parameters visible and tweakable immediately.
3. **Credible precision.** Robotics parts have real dimensions, tolerances, and manufacturability constraints; the surface should feel trustworthy, not playful.
4. **Fast loops win.** Users iterate repeatedly; loading, regeneration, and navigation must feel instantaneous.
5. **No dead ends.** Empty history, failed generations, and missing exports get useful next actions, not blank states.

## Accessibility & Inclusion

- Default target is mouse/trackpad desktop users; keyboard focus and visible focus rings must be present for all interactive controls.
- Color alone must never be the only signal for success/error/selection.
- Contrast should hold up in bright, possibly glare-lit workshop conditions.
