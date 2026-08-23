# DESIGN BRIEF FOR STITCH — RoboCAD Web Application Redesign

## 1. Application Description

**RoboCAD** is an AI-powered parametric CAD system purpose-built for robotics hardware. A single user describes a mechanical part in plain language — *"A NEMA-17 motor mount bracket with two M3 holes and a 22 mm motor boss"* — and the system synthesizes executable Build123d code, generates a validated STL/STEP/script bundle, and exposes every numeric parameter for later editing. Engineers can click a face on the 3D model to guess which dimension controls it, adjust values in the property grid, remix earlier designs, run a manufacturability report, and push the final geometry directly to Onshape. The interface must feel like a precision engineering workstation: dense with information, responsive under load, and visually calm enough to live inside a hardware lab for hours.

---

## 2. User Persona & Daily Workflow

**Primary persona:** *Maya — a robotics mechanical engineer or research technician working in a university lab, startup, or hardware R&D team.* She designs custom brackets, mounts, pulleys, hubs, and end-effectors weekly, often switching between prototypes and small-batch parts.

**Typical session:**
1. **Discover:** Maya browses the component library or searches her history for a starting point.
2. **Specify:** She writes or pastes a prompt, optionally overrides the AI model, and sets retry tolerance.
3. **Generate & validate:** The backend streams code generation, geometry validation, and export creation.
4. **Inspect:** She orbits the STL in the central viewer, reads validation metrics, and checks manifold/watertight status.
5. **Refine:** She clicks a face in the viewer to guess its parameter, nudges values in the inspector, and regenerates.
6. **Release:** She runs the manufacturing report, downloads STL/STEP/script, or uploads to an Onshape document.
7. **Organize:** She tags the design and optionally remixes it for the next variant.

The UI must support rapid iteration loops: prompt → generate → tweak → regenerate within 30–60 seconds, with clear state feedback at every transition.

---

## 3. Visual Direction: Precision Engineering Workstation

Move away from the current generic light card UI. The new direction is **dark-first scientific instrument control software** — a blend of mission-control density, modern lab-equipment readability, and high-end CAD workstation hierarchy. The interface should feel machined: tight alignment, consistent rhythm, no decorative gradients, and color used sparingly as a signal layer.

### 3.1 Color Palette

Use a near-black foundation with cool neutral panels and a single high-saturation accent for action and measurement highlights.

| Token | Value | Usage |
|---|---|---|
| `--surface-app` | `#0B0C0F` | Application background |
| `--surface-panel` | `#13151A` | Raised panels, sidebars, inspector cards |
| `--surface-elevated` | `#1A1D24` | Inputs, hover rows, selected states |
| `--surface-active` | `#242936` | Active/pressed surfaces |
| `--border-default` | `#2A2E38` | Dividers, card outlines |
| `--border-focus` | `#4A80FF` | Focus rings, selection outlines |
| `--text-primary` | `#E8EAEF` | Headings, primary labels |
| `--text-secondary` | `#A0A8B8` | Body text, descriptions, units |
| `--text-muted` | `#6D7687` | Disabled, timestamps, metadata |
| `--accent-primary` | `#3B82F6` | Primary buttons, progress, active links |
| `--accent-glow` | `#60A5FA` | Hover highlights, face selection |
| `--accent-secondary` | `#22D3EE` | Validation success, measurement numbers |
| `--status-success` | `#34D399` | Watertight/manifold OK, online badge |
| `--status-warning` | `#FBBF24` | Warnings, overhang, small-hole issues |
| `--status-error` | `#F87171` | Errors, failed generation, offline badge |
| `--status-info` | `#93C5FD` | Info pills, model badges |

Shadows should be subtle and structural, not ornamental:

- `--shadow-panel: 0 1px 0 rgba(255,255,255,0.04) inset, 0 4px 20px rgba(0,0,0,0.35)`
- `--shadow-float: 0 8px 30px rgba(0,0,0,0.45)`

### 3.2 Typography

Use a **monospaced + sans-serif** pairing. Engineering readouts and parameter tables are monospace for alignment and trust; UI chrome and prose are sans-serif for readability.

- **Sans UI:** `Inter` — weights 400, 500, 600. Use for headers, buttons, labels, sidebar sections.
- **Monospace data:** `JetBrains Mono` — weights 400, 500. Use for parameter values, console logs, latency, version numbers, timestamps.
- **Display/logo:** `Inter` 700, letter-spacing `-0.02em`.

Type scale:

| Role | Size | Weight | Line |
|---|---|---|---|
| Logo | `20px` | 700 | 1.2 |
| Panel title | `13px` | 600 | 1.3 |
| Body / input | `13px` | 400 | 1.5 |
| Readout / metric | `24px` | 500 mono | 1.2 |
| Small metadata | `11px` | 500 | 1.3 |
| Console / code | `12px` | 400 mono | 1.6 |

---

## 4. Page Layout & Spatial System

The layout is a **three-zone engineering workstation**: fixed header, collapsible left sidebar, large central workspace, persistent right inspector panel, and a bottom status console. All dimensions below are desktop-first.

### 4.1 Global Grid

```
┌─────────────────────────────────────────────────────────────┐
│  HEADER (56px)                                              │
├──────────┬───────────────────────────────┬────────────────────┤
│          │                               │                    │
│  LEFT    │      MAIN WORKSPACE           │   RIGHT INSPECTOR  │
│  SIDEBAR │      (fluid, centered)        │   (320px fixed)    │
│  (260px) │                               │                    │
│          │                               │                    │
│          │                               │                    │
├──────────┴───────────────────────────────┴────────────────────┤
│  BOTTOM CONSOLE / STATUS (180px, resizable)                   │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Header (56px fixed)

**Left:** Logo mark + wordmark "RoboCAD", plus a muted tagline "AI parametric CAD for robotics".

**Center (optional):** Global search shortcut `Ctrl+K` (rounded pill, 32px height) showing "Search history and components".

**Right:** Backend status badge and a small "New design" icon button. Use the badge color rules:
- Online: `--status-success` dot + "Backend online"
- Offline: `--status-error` dot + "Backend offline — run uvicorn on port 8000"

### 4.3 Left Sidebar (260px fixed, scrollable)

Stack two panels vertically:
1. **Component Library** (accordion categories).
2. **History Sidebar** (search, tag filter, design list).

Add a thin vertical divider line at `border-right: 1px solid var(--border-default)`.

### 4.4 Main Workspace (fluid center)

Main content flows top-to-bottom with a max-width of `1200px` and centered. Panels use `16px` internal padding and `12px` gap between panels.

Visible components in order:
1. **Prompt Composer** — top card.
2. **Status / Console Panel** — appears immediately below prompt during generation.
3. **3D Viewer** — large central canvas (minimum 520px tall).
4. **Parameter Inspector** — below the viewer.
5. **Manufacturing Report + Onshape Upload + Tag Editor + Remix Panel** — 2-column grid below parameters.

### 4.5 Right Inspector Panel (320px fixed)

A dense, always-visible property sheet showing:
- **Current design metadata:** model used, latency, attempts, timestamp, success/fail state.
- **Validation summary:** manifold, watertight, bounds, volume.
- **Quick actions:** Download/export buttons, Onshape shortcut.
- **Selected face/parameter:** when the user clicks a face in the viewer, this area shows the guessed parameter name, suggested value, axis, and confidence.

### 4.6 Bottom Console / Status Area (180px default, resizable)

A terminal-like strip at the foot of the screen with a drag handle at the top edge. Contains:
- Generation progress (stepper: parsing → generating → validating → exporting).
- Validation results and metric chips.
- Error/warning list with expand/collapse traceback.
- Real-time backend log lines during generation.

---

## 5. Component Specifications

### 5.1 Prompt Composer

**Placement:** Top of main workspace, full width.

**Structure:**
- Header row: title "Specimen prompt", status badge "Ready" / "Running…".
- One-line subtitle explaining the AI behavior.
- Large textarea (min-height `96px`, rounded `8px`, `14px` font) with placeholder: `Describe the robot part in plain language. RoboCAD writes parametric Build123d code and validates the geometry.`
- Controls row below textarea:
  - **Retries slider** (`0–5`, labeled "Retries: {n}"), `160px` min width.
  - **Model override** text input, placeholder `default`, `180px` min width.
  - **Generate** primary button, right-aligned, `140px` min width.
- Seed suggestions row at bottom: label "Try:" + small ghost chips.

**States:**
- Empty: textarea empty, Generate disabled.
- Typing: Generate enabled when text non-empty.
- Loading: textarea disabled, button shows "Generating…" with spinner, status badge amber.
- Error: textarea border turns `--status-error`, error message appears below.
- Success: brief green border flash (200ms) on textarea, then returns to normal.

**Interaction:**
- Seed chips replace textarea content.
- `Ctrl+Enter` submits.
- Model override accepts any string; empty string sends `null`.

### 5.2 3D Viewer

**Placement:** Central, dominant canvas. Minimum height `520px`, ideally `60vh`.

**Structure:**
- Header overlay (floating inside top edge, `40px` height): filename / design ID on left, viewport controls on right.
- Canvas fills remaining space.
- Floating toolbar (bottom-left or bottom-right): reset view, toggle grid, toggle axes, wireframe/solid, screenshot.

**Visual requirements:**
- Background matches `--surface-app`.
- Grid: faint `rgba(160,168,184,0.12)` lines on the floor plane.
- Axes: X red `#F87171`, Y green `#34D399`, Z blue `#60A5FA`.
- Default lighting: hemisphere + directional, soft shadows.
- Model material: `MeshStandardMaterial`, `metalness 0.15`, `roughness 0.55`, color `#D8DCE5`.
- Selected face highlight: emissive tint `--accent-glow` at opacity `0.35`, with a `2px` `--accent-glow` outline around the face edges.

**Face-click behavior (preserve existing logic):**
- On raycast hit, send `{ faceIndex, faceNormal, centroid }` to `POST /designs/{id}/guess-parameter`.
- While waiting, cursor = `progress`.
- On success, highlight the face and scroll/focus the matching parameter row in the Parameter Inspector.
- On error, show a transient toast: "Could not guess parameter for that face."

**States:**
- Empty: canvas shows a faint instructional watermark "Generated model will appear here" + dashed border.
- Loading: centered spinner with text "Building geometry…".
- Error: centered error icon + short message.
- Success with model: model rendered.
- Hover over face: cursor `pointer`, face outline preview at `0.2` opacity.

### 5.3 Parameter Inspector

**Placement:** Below the 3D viewer, full width inside main workspace.

**Structure:**
- Header: title "Parameters", optional selected-parameter badge.
- Subtitle: "Edit values and regenerate, or click a face in the viewer to select its parameter."
- Property grid table with columns:
  - Name (monospace)
  - Value (editable number input, monospace)
  - Unit
  - Description
- Footer: "Regenerate from parameters" primary button, disabled when no changes.

**Input behavior:**
- Width `120px`.
- On `selectedParameter` change, scroll that row into view, focus input, select all text.
- Support external nudges (e.g., from face guess or a future +/- stepper).
- Show original value as muted secondary text if edited.

**States:**
- Empty: hidden if `parameters` is empty.
- Loading: inputs disabled, button shows "Regenerating…".
- Changed row: left border `3px solid var(--accent-primary)` and subtle elevated background.
- Selected row: full row background `--surface-active`, input ring `--border-focus`.

### 5.4 Status / Console Panel

**Placement:** Immediately below Prompt Composer during generation; otherwise collapsed to a compact status bar.

**Structure:**
- **Progress stepper:** 4 steps — Parse prompt, Generate code, Validate geometry, Export files. Active step uses `--accent-primary` fill; completed steps use `--status-success`; pending steps use `--border-default`.
- **Metric chips:** `manifold`, `watertight`, `bounds_mm[]`, `volume_mm3`.
- **Issues list:** errors and warnings with severity icons. Errors are `--status-error`; warnings are `--status-warning`.
- **Traceback expander:** small "Show traceback" button that reveals the monospace traceback block.

**States:**
- Idle: compact bar, green "Ready".
- Generating: stepper animates, spinner, live log lines append bottom-up.
- Success: stepper all green, metric chips populated.
- Error: failed step turns red, error card expands, traceback shown by default.

### 5.5 Manufacturing Report

**Placement:** Inside a 2-column grid below parameters, left column.

**Structure:**
- Header: "Manufacturing report".
- Metric cards in a 2×2 grid:
  - Bounds (mm)
  - Volume (cm³)
  - Surface area (cm²)
  - Estimated print time (min)
- Bars/gauges:
  - Overhang ratio (horizontal bar, red segment when > 0.25).
  - Minimum hole diameter (mm).
- **Issues list:** each issue is a row with icon, message, severity.

**States:**
- Empty: not shown until design selected.
- Loading: skeleton cards.
- Error: inline error card.
- Success: metrics render, warnings highlighted.

### 5.6 Onshape Upload Panel

**Placement:** Right column of lower grid.

**Structure:**
- Header: "Onshape".
- Mode switch: "New document" vs "Existing document".
- New doc: text input for document name, defaulting to design prompt truncated to 60 chars.
- Existing doc: searchable list of documents from `GET /onshape/documents?q=&limit=`. Each row shows document name + workspace info.
- Upload button.
- Success state: show "Open in Onshape" link using `document_url`.

**States:**
- Idle: form ready.
- Loading: list/button disabled, spinner.
- Success: link rendered, button replaced with "Uploaded".
- Error: inline error text.

### 5.7 Component Library

**Placement:** Top of left sidebar.

**Structure:**
- Header: "Component library".
- Accordion categories: Structural, Motion, Electronics, Robotics.
- Each category expands to show item cards.
- Item card: name (bold), one-line description, tag chips, "Use as seed" ghost button.
- Clicking the card or button loads its `prompt` into the Prompt Composer.

**Card states:**
- Default: `--surface-panel`.
- Hover: `--surface-elevated`, translateY `-1px`.
- Active/seed-loaded: left border `--accent-primary`.

### 5.8 History Sidebar

**Placement:** Below Component Library in left sidebar.

**Structure:**
- Header: "History" + Refresh button.
- Search input: placeholder "Search prompts or tags".
- Tag filter dropdown: populated from all tags in history.
- Design list: vertical scrollable list.
- Design card:
  - Top row: success icon (✓/✗), prompt truncated to 60 chars, latency badge.
  - Second row: timestamp, "remix of #..." if `parent_id`.
  - Third row: tag chips.

**Card states:**
- Default: `--surface-panel`.
- Hover: `--surface-elevated`.
- Selected: background `--surface-active`, left border `--accent-primary`.
- Failed: subtle red left border `--status-error`.

### 5.9 Tag Editor

**Placement:** Lower grid, compact card.

**Structure:**
- Header: "Tags".
- Inline tag input with comma/Enter creation.
- Existing tags as removable chips.
- Save button.

**States:**
- Editing chips show hover remove icon.
- Save disabled if unchanged.

### 5.10 Remix Panel

**Placement:** Lower grid, compact card.

**Structure:**
- Header: "Remix".
- Textarea for new prompt, pre-filled with original prompt.
- Same retry slider and model override as Prompt Composer.
- "Remix from design" button.

**States:**
- Loading: button disabled with spinner.
- Success: redirect/select new design.

### 5.11 Download / Export Bar

**Placement:** Right inspector panel top and/or a floating toolbar above the viewer.

**Structure:**
- Buttons for each available export:
  - STL (if `export_urls.stl`)
  - STEP (if `export_urls.step`)
  - Python script (if `export_urls.script`)
- Button disabled if URL missing.

**States:**
- Default: secondary style.
- Hover: primary style.
- Downloading: spinner on button.

---

## 6. Data Models & API Contracts

The frontend expects the following from the FastAPI backend. Base path is empty because Vite proxies `/api` or uses same origin.

### 6.1 Endpoints

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/health` | — | `{ status }` |
| POST | `/generate` | `{ prompt, max_retries, model? }` | `GenerationResult` |
| GET | `/designs` | query: `search`, `tag` | `DesignSummary[]` |
| GET | `/designs/{id}` | — | `GenerationResult` (or summary with full payload) |
| PUT | `/designs/{id}` | `{ tags? }` | Updated design |
| POST | `/designs/{id}/regenerate` | `{ parameter_updates: { name: number } }` | `GenerationResult` |
| POST | `/designs/{id}/remix` | `{ prompt, max_retries, model? }` | `GenerationResult` |
| POST | `/designs/{id}/guess-parameter` | `{ face_normal: [x,y,z], face_centroid: [x,y,z] }` | `ParameterGuessResult` |
| GET | `/designs/{id}/manufacturing-report` | — | `ManufacturingReport` |
| GET | `/onshape/documents` | query: `q`, `limit` | Document list |
| POST | `/designs/{id}/onshape` | `{ document_id?, workspace_id?, document_name? }` | `OnshapeUploadResult` |
| GET | `/exports/{design_id}/{filename}` | — | Binary file |

### 6.2 Data Shapes

**DesignSummary:**
```json
{
  "id": "uuid",
  "prompt": "string",
  "success": true,
  "model": "gpt-4o",
  "attempts_used": 1,
  "latency_seconds": 12.3,
  "created_at": "2026-08-22T12:34:56Z",
  "export_urls": { "stl": "/exports/uuid/model.stl", "step": "...", "script": "..." },
  "parent_id": "uuid-or-null",
  "tags": ["mounting", "bracket"]
}
```

**GenerationResult:**
```json
{
  "design_id": "uuid",
  "prompt": "string",
  "success": true,
  "code": "python-string",
  "parameters": [
    { "name": "length", "value": 80, "unit": "mm", "description": "Overall length" }
  ],
  "validation": {
    "manifold": true,
    "watertight": true,
    "bounds_mm": [0, 0, 0, 80, 40, 3],
    "volume_mm3": 9600,
    "errors": [],
    "warnings": ["Thin wall at corner"]
  },
  "export_urls": { "stl": "...", "step": "...", "script": "..." },
  "attempts_used": 1,
  "max_retries": 2,
  "model": "gpt-4o",
  "latency_seconds": 12.3,
  "traceback": "string-or-null",
  "tags": []
}
```

**ParameterGuessResult:**
```json
{
  "guessed_parameter": "length",
  "suggested_value": 80,
  "unit": "mm",
  "axis": "x",
  "confidence": 0.92
}
```

**ManufacturingReport:**
```json
{
  "bounds_mm": [0, 0, 0, 80, 40, 3],
  "volume_cm3": 9.6,
  "surface_area_cm2": 125.4,
  "estimated_print_time_min": 48,
  "overhang_ratio": 0.12,
  "min_hole_diameter_mm": 4.0,
  "issues": [
    { "type": "overhang", "message": "Overhang exceeds 45° on face 4", "severity": "warning" }
  ]
}
```

**OnshapeUploadResult:**
```json
{
  "document_url": "https://cad.onshape.com/documents/...",
  "element_url": "https://cad.onshape.com/documents/.../w/.../e/..."
}
```

---

## 7. Interaction Patterns & Motion Design

- **Transition duration:** `150–250ms` for all UI state changes. No bounce, no elastic easing. Use `cubic-bezier(0.4, 0, 0.2, 1)` for enter, `cubic-bezier(0.4, 0, 1, 1)` for exit.
- **Button feedback:** active scale `0.98`, background darkens.
- **Focus rings:** uniform `2px` outline using `--border-focus`, offset `2px`.
- **Loading:** skeleton panels use shimmering `linear-gradient` animation on `--surface-panel` → `--surface-elevated`.
- **Progress stepper:** step fill animates width `0% → 100%` over `250ms`.
- **Console log:** new lines slide up `8px` and fade in over `150ms`.
- **Face selection:** highlight fades in `200ms`; parameter row scrolls smoothly into view.
- **Panels appear/disappear:** fade + translateY `8px`. No pop or overshoot.
- **Badges/pills:** scale `1.0 → 1.02` on hover.
- **Resizable bottom console:** drag handle `8px` tall, cursor `ns-resize`, real-time height update.

---

## 8. Responsive Behavior

**Desktop first.** The target environment is a lab workstation with at least 1440px width.

**Collapse rules:**
- **≤1280px:** Right inspector panel collapses into a drawer toggled by a button in the header. Main workspace expands to fill space.
- **≤1024px:** Left sidebar collapses into a drawer. Header gains a hamburger/section toggle.
- **≤768px:** Switch to single-column stacking. Bottom console becomes a full-screen modal when expanded. 3D viewer height drops to `360px`.
- **Touch targets:** minimum `40px` on all interactive elements.

---

## 9. Accessibility Requirements

- Color is not the only signal: use icons + text for success/error/warning states.
- All form inputs have visible labels and `aria-labelledby`.
- Focus order follows visual layout: header → sidebar → main workspace → right panel → bottom console.
- The 3D viewer is a focusable region with `aria-label` describing its purpose; face-click results are announced via a live region.
- Console errors are announced via `aria-live="polite"`.
- Sufficient contrast: all text meets WCAG 4.5:1 against backgrounds.
- Keyboard shortcuts:
  - `Ctrl+Enter` submit prompt.
  - `Ctrl+K` focus global search.
  - `Esc` clear face selection / close modals.
- Reduced motion: if `prefers-reduced-motion: reduce`, disable all transitions and animations except opacity fades under `100ms`.

---

## 10. Anti-Patterns to Avoid

- No generic Bootstrap/Material light cards with heavy drop shadows.
- No rounded "friendly" buttons with gradients; keep buttons flat and machined.
- No decorative illustrations or mascot characters.
- No modal dialogs for routine status; use inline panels and the bottom console.
- No infinite scrolling in history; use a scrollable list with clear selection.
- No separate "light mode" default; dark is the default, with a manual toggle for bright-lab use.
- No tooltips on disabled buttons without explanation.
- No full-page reload on generation; everything must be async.
- No face-click guess result shown only in a transient toast; it must also update the right inspector and parameter table.

---

## 11. Integration Notes for the Developer

### 11.1 Preserve from the existing implementation

**`api.js`:** Keep all exported functions and signatures intact. They already map cleanly to the backend. Do not change `API_BASE`, `apiFetch` error handling, or request body shapes.

- `checkHealth`
- `generateDesign`, `regenerateDesign`, `remixDesign`
- `listDesigns`, `loadDesign`
- `updateDesignTags`
- `guessParameter`
- `getManufacturingReport`
- `listOnshapeDocuments`, `uploadToOnshape`
- `exportUrl`

**STLViewer face-click logic:** Preserve the raycaster-to-mesh intersection that returns `{ faceIndex, faceNormal, centroid }`, and the parent callback `onFaceClick`. Keep the current normal/centroid calculation exactly as-is because it feeds `/designs/{id}/guess-parameter`. The new design only changes visual styling of the highlight and adds a hover preview.

**Backend endpoints:** Do not add, remove, or rename endpoints. The FastAPI contract listed above is the source of truth.

**Component library JSON:** Load `standard_components.json` from the existing path. Categories and item fields (`id`, `name`, `description`, `prompt`, `tags`) remain the same.

### 11.2 React component mapping

The generated output should map to these existing component files. It is acceptable to rename CSS classes but the component hierarchy and props must remain compatible:

- `App.jsx` — orchestrator; keep state variables (`result`, `error`, `loading`, `designs`, `selectedId`, `seedPrompt`, `selectedFace`, `selectedParameter`, `guessResult`, `nudge`) and handler names.
- `PromptInput.jsx` — props: `onGenerate({ prompt, max_retries, model })`, `loading`, `seedPrompt`.
- `STLViewer.jsx` — props: `url`, `onFaceClick({ faceIndex, faceNormal, centroid })`, `selectedFace`, `guessResult`.
- `ParameterList.jsx` — props: `parameters`, `selectedParameter`, `onRegenerate(updates)`, `loading`, `nudge`.
- `StatusPanel.jsx` — props: `result`, `error`, `loading`.
- `ManufacturingReport.jsx` — receives `designId` and fetches internally via `getManufacturingReport`.
- `OnshapeUpload.jsx` — props: `designId`, `prompt`; uses `listOnshapeDocuments` and `uploadToOnshape`.
- `HistorySidebar.jsx` — props: `designs`, `selectedId`, `onSelect(id)`, `onRefresh`.
- `TagEditor.jsx` — props: `tags`, `onUpdate(tags)`.
- `RemixPanel.jsx` — props: `designId`, `onRemix({ prompt, max_retries, model })`, `loading`.
- `ComponentLibrary.jsx` — props: `onPrompt(prompt)`, `loading`.
- `DownloadLinks.jsx` — props: `exportUrls`.

### 11.3 CSS migration guidance

- Replace the current CSS class namespace `rc-*` with a new prefix (e.g., `stitch-*` or `robocad-*`) to avoid collisions.
- Use CSS custom properties for the color tokens listed in section 3.1.
- Avoid global font-size resets that shrink form controls; keep `font-size: 13–14px` minimum.
- Keep the 3D viewer canvas renderer isolated in its own container; do not apply `backdrop-filter` or heavy compositing over it.

### 11.4 What the AI must deliver

The final generated artifact should be a single-file React application (or modular files) containing:
- Restyled components matching this brief.
- A CSS file with the token palette and layout grid.
- No changes to backend Python code.
- No changes to `api.js` logic beyond possible import path adjustments.
- Working integration with the existing face-click parameter guessing flow.

---

## 12. Deliverable Summary

Produce a dark-first, precision-engineering UI for RoboCAD that:

1. Centers the 3D viewer as the primary workspace.
2. Surrounds it with a prompt composer, parameter inspector, manufacturing report, Onshape export, history, and component library.
3. Uses a disciplined color system (`#0B0C0F`, `#13151A`, `#3B82F6`, `#34D399`, `#F87171`).
4. Employs `Inter` + `JetBrains Mono` typography.
5. Provides clear state feedback for idle, loading, success, error, hover, focus, active, and disabled states.
6. Preserves all existing React component contracts and backend API endpoints.
7. Supports desktop-first responsive collapse and full keyboard/accessibility coverage.

The result should feel less like a web form and more like the control software for a high-end desktop CNC or lab instrument: dense, fast, trustworthy, and engineered.
