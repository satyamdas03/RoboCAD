# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary user is a **solo mechanical engineer, robotics researcher, or advanced maker** who designs custom robot hardware parts but does not want to spend hours in traditional sketch-extrude-mate CAD. They prototype mounts, brackets, hubs, chassis plates, and end-effectors in quick iterative loops.

Secondary audiences include **robotics students and competition teams** who need editable, manufacturable parts fast, and **technically confident hobbyists** who can read dimensions and parameters but lack CAD fluency.

## Product Purpose

RoboCAD lets users describe a robot part in plain language and receive an editable, parametric CAD model. The AI generates executable build123d/FeatureScript code instead of a throwaway mesh, so the output is versionable, parameter-editable, 3D-printable/machinable, and syncable to Onshape for professional assembly work.

Success means a user goes from “a 120 mm × 80 mm × 3 mm base plate with four M3 holes on a 100 mm × 60 mm grid” to a verified STL/STEP export, a parameter panel, and an optional manufacturing report in under a minute.

## Positioning

The meaningful difference is **parametric code, not mesh soup**. Most text-to-3D tools produce surfaces users cannot edit or dimension. RoboCAD produces feature-tree-style code that exposes named parameters, supports face-driven dimension editing, and exports clean STEP for machining and Onshape assemblies. Competitors can copy the prompt box; they cannot truthfully claim the same editability and manufacturing fidelity.

## Operating Context

- Users work on **desktop browsers** in bright offices, labs, or workshops; sessions are a mix of quick single-part generation and short iterative refinement passes.
- The core loop is: **prompt → generate → inspect 3D model → tweak parameters or click a face → regenerate → export/manufacture/upload**.
- Existing assets include generated STL/STEP files, SQLite design history, parameter dictionaries, tags, parent-child remix links, and Onshape document thumbnails.
- The browser viewport is usually large, but users may also run the app on a laptop next to hardware, so contrast and target sizes matter.

## Capabilities and Constraints

- **Capabilities:** natural-language prompt-to-CAD, parameter editing via sliders and face-click guessing, design history with search/filter/tags, component library with seeded robotics templates, remix from any prior design, manufacturing report (volume, overhangs, hole diameter, print-time heuristic), one-click STEP upload to Onshape.
- **Constraints:** backend runs locally (FastAPI + build123d + optional Ollama); the 3D viewer is three.js / react-three-fiber; exports are STL/STEP/3MF; local SQLite is the source of truth for history; Onshape integration requires user-provided HMAC credentials stored in `.env`.
- **Terminology:** prompt, design, parameters, export, regeneration, remix, face/parameter guessing, component library, manufacturing report, Onshape upload.
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
- 56/57 pytest tests passing. The single failure (`test_generate_missing_api_key`) passes because `.env` configures a local Ollama model (`ROBOCAD_MODEL=qwen3-coder:latest`), so the backend no longer fails on a missing Anthropic key.
- Frontend production build passes; live end-to-end generation verified (base plate and NEMA-17 mount both succeeded with manifold/watertight geometry and full parameter panels).
- 12 standard robotics component templates in `ComponentLibrary`.
- Generated Stitch reference files (`stitch_precision_engineering_interface/`) retained for provenance.
- README, PLAN.md, and PRODUCT.md document current phases, architecture, and design context.

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
