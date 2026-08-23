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
- **Undecided:** brand name may be kept as “RoboCAD” or evolved by the chosen visual direction; no existing color or typography commitments.

## Brand Commitments

- Product name is currently **RoboCAD**; visual direction has authority to refine or replace it if the world demands it, but the functional promise stays the same.
- No existing logo, palette, or typeface is binding.
- Anti-references from the user: avoid generic SaaS purple/blue gradients, card-on-card dashboard clichés, cartoon/childish UI, heavy cyberpunk neon, and military-industrial olive/steel tropes.

## Evidence on Hand

- Working end-to-end web app with FastAPI backend and React frontend.
- 57 passing pytest tests covering generation, regeneration, parameter editing, design library, manufacturing, and Onshape upload.
- 12 standard robotics component templates in `ComponentLibrary`.
- README and PLAN.md document current phases and architecture.

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
