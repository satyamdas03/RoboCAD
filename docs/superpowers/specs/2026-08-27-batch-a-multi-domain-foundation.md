# Batch A — Multi-Domain Foundation (Phases 16–17) Design Spec

**Date:** 2026-08-27  
**Scope:** Add domain detection, domain-aware feature-tree schema v2, and per-domain intent parsers to RoboCAD. Voice input is deferred. Sketch-to-constraint is included for mechanical parts and 2D airfoil profiles.  
**Goal:** A user can type a prompt like *"Design a 450 mm quadcopter frame with four motor arms and an aerodynamic center body shell"* and RoboCAD classifies it as multi-domain (mechanical + aero), routes each subsystem to the right parametric representation, and stores the intent in a versioned feature tree.

---

## 1. Background

RoboCAD currently has:
- A mechanical feature-tree schema v1.0.0 (`ai_cad/feature_tree.py`).
- A build123d transpiler (`ai_cad/transpiler.py`) for solids.
- A FastAPI backend with design persistence.
- A React frontend with prompt input, feature-tree panel, assembly panel, simulate panel, etc.

What is missing for the multi-domain vision:
- No domain classifier.
- No place to store domain tags on features/parts/assemblies.
- No representation for surfaces (aero/thermal), kinematic chains (mechanisms/humanoids), or PCB form factors (electronics).
- No per-domain intent parser that maps a prompt to the right feature-tree operations.
- No sketch-to-constraint for airfoil profiles.

This batch adds those foundations without changing existing mechanical behavior.

---

## 2. Domain taxonomy

| Domain | Tag | Typical artifacts | Notes |
|---|---|---|---|
| Mechanical | `mechanical` | solids, assemblies, mechanisms | Existing core; default if no other domain is detected. |
| Aerodynamics / propulsion | `aero` | airfoils, wings, ducts, propeller blades | Surface/shell geometry; CFD mesh export. |
| Thermal | `thermal` | heat sinks, heat spreaders, ducts, fin stacks | Often co-designed with aero. |
| Electronics / mechatronics | `electronics` | PCB outlines, enclosures, connector mounts, cable guides | Form-factor co-design only; no silicon EDA. |
| Humanoid / full robot | `humanoid` | biped, quadruped, manipulator-on-base templates | Kinematic-tree + mechanical parts. |
| Multi-domain | `multi` | a request that explicitly mixes two or more domains | Decomposition planner handles split in Batch B. |

A single feature tree can contain parts/features from multiple domains. Each part/feature carries a `domain` tag.

---

## 3. Components

### 3.1 Domain classifier

**File:** `ai_cad/domain.py`

**Responsibilities:**
- Given a user prompt, return a ranked list of domain tags plus a confidence score.
- Run offline (no cloud LLM call required for common cases).
- Fall back to a local sentence-transformer model when keyword rules are ambiguous.

**Approach:**
1. Keyword rule layer: a small dictionary of domain → keyword list. If a prompt unambiguously matches one or more domains, return those.
2. Embedding fallback: if keyword scores are within a threshold, compute cosine similarity between the prompt embedding and pre-computed domain prototype embeddings using `sentence-transformers/all-MiniLM-L6-v2`.
3. LLM fallback (optional, off by default): if the local model is unavailable, call the configured LLM with a tiny zero-shot classification prompt.

**Output model:**
```python
class DomainPrediction(BaseModel):
    primary: str
    scores: dict[str, float]
    reasoning: str
    multi_domain: bool
```

**Dependencies:**
- `sentence-transformers` as an optional dev dependency (`requirements-dev.txt`).
- Graceful degradation: if the model is not installed, keyword rules still work.

### 3.2 Domain-aware feature-tree schema v2

**File:** `ai_cad/feature_tree.py`

**Changes:**
- Add `domain: str = "mechanical"` to `Feature`, `Part`, and `Assembly`.
- Add `KinematicJoint` model with types `revolute`, `prismatic`, `spherical`, `fixed`.
- Add `SurfaceFeature` model for aero/thermal shells (NACA airfoil, extruded wing, duct, heat sink).
- Add `PCBOutline` model for electronics (board shape, mounting holes, keepout regions).
- Bump schema version to `2.0.0`.
- Keep all v1 models backward-compatible via `model_config = {"extra": "allow"}` and default `domain="mechanical"`.

**New types:**
```python
class KinematicJoint(BaseModel):
    id: str
    type: Literal["revolute", "prismatic", "spherical", "fixed"]
    parent_link: str
    child_link: str
    origin: tuple[float, float, float]
    axis: tuple[float, float, float] | None = None
    limits: tuple[float, float] | None = None

class SurfaceFeature(BaseModel):
    id: str
    type: Literal["airfoil", "wing", "duct", "heat_sink", "propeller_blade"]
    profile: dict[str, Any]  # domain-specific parameters
    domain: str = "aero"

class PCBOutline(BaseModel):
    id: str
    board_shape: list[tuple[float, float]]
    mounting_holes: list[tuple[float, float, float]]
    keepouts: list[dict[str, Any]]
    domain: str = "electronics"
```

### 3.3 Per-domain intent parser

**File:** `ai_cad/intent_parser.py`

**Responsibilities:**
- Given a prompt + primary domain, extract structured parameters for that domain.
- Return a `DomainIntent` model with `domain`, `parameters`, `features`, `constraints`, and `notes`.

**Approach:**
- Use a small LLM prompt per domain. The prompt is short, includes examples, and asks for JSON only.
- Cache results by prompt hash to avoid repeated calls.
- Validate output against the domain-specific JSON schema.

**Output model:**
```python
class DomainIntent(BaseModel):
    domain: str
    parameters: list[Parameter]
    features: list[dict[str, Any]]  # domain-specific feature stubs
    constraints: list[str]
    notes: list[str]
    confidence: float
```

**Examples:**
- Mechanical: *"A 120 mm × 80 mm bracket, 3 mm thick, four M3 holes"* → parameters `length`, `width`, `thickness`, `hole_diameter`, `hole_count`; features `extrude`, `hole_pattern`.
- Aero: *"NACA 2412 airfoil, 200 mm chord, 400 mm span"* → parameters `chord`, `span`, `naca_code`; features `airfoil_surface`.
- Electronics: *"Raspberry Pi 5 mounting plate, 4 M3 holes"* → parameters `board_length`, `board_width`, `hole_diameter`; features `pcb_outline`, `mounting_holes`.

### 3.4 Sketch-to-constraint extension

**File:** `ai_cad/sketch_solver.py` and `ai_cad/sketch.py`

**Changes:**
- Add `airfoil` sketch entity type that accepts NACA code/chord and emits a set of control points + constraints.
- Ensure mechanical sketch-to-constraint still works as before.
- Add test: an airfoil sketch solves to the expected thickness distribution.

### 3.5 Backend integration

**File:** `web/backend/main.py`

**Changes:**
- Add `POST /classify-domain` endpoint returning `DomainPrediction`.
- Modify `POST /generate` to optionally accept `detect_domain: bool = True`. When true, the backend classifies the prompt, runs the per-domain intent parser, and stores the resulting domain intent in the design metadata.
- Add `GET /designs/{id}/domain-intent`.
- Persist `domain` and `domain_intent.json` under `designs/{id}/`.

### 3.6 Frontend integration

**File:** `web/frontend/src/components/DomainBadge.jsx` and `web/frontend/src/App.jsx`

**Changes:**
- Show a domain badge next to each design in the history sidebar.
- Show domain tags in the feature-tree panel and simulate panel.
- Add a small "Domain intent" inspector card when a design has one.
- No major UI redesign; reuse existing panels.

### 3.7 Tests

**Files:**
- `tests/test_domain_classifier.py` — keyword rules, embedding fallback, multi-domain detection, graceful degradation.
- `tests/test_feature_tree_v2.py` — schema v2 serialization, backward compatibility, new domain models.
- `tests/test_intent_parser.py` — per-domain intent parsing with mocked LLM.
- `tests/test_sketch_airfoil.py` — airfoil sketch entity solves.
- `tests/test_web_backend.py` — `/classify-domain` and `/generate?detect_domain=true` endpoints.

**Acceptance:** full pytest suite passes with ≥15 new tests and no regressions.

---

## 4. Explicit boundaries

- No voice input in this batch (deferred to after the user returns).
- No actual aero/thermal/electronics/humanoid geometry generation yet — only representation and intent parsing. Generation comes in Batch B.
- No new LLM fine-tuning; reuse existing generator.
- No changes to existing mechanical transpiler behavior.

---

## 5. Dependencies to install

- `sentence-transformers>=3.0.0` (optional dev dependency).
- Pre-download `all-MiniLM-L6-v2` weights during setup so tests run offline.

---

## 6. Success criteria

1. A prompt like *"Design a NACA 2412 airfoil with 200 mm chord and 400 mm span"* is classified as `aero` with confidence ≥0.8.
2. The resulting design metadata contains a domain intent with parameters `chord`, `span`, `naca_code`.
3. The feature tree stores the part with `domain: "aero"` and a placeholder `SurfaceFeature`.
4. Mechanical prompts still work exactly as before (regression test passes).
5. Full pytest suite remains green (187 + new tests passing).
6. README and dossiers are updated to mark Phases 16–17 in progress/complete.

---

## 7. Risks and mitigations

| Risk | Mitigation |
|---|---|
| `sentence-transformers` adds heavy dependency | Optional dev dependency; tests skip embedding fallback if not installed; keyword rules remain functional. |
| LLM intent parser is flaky or slow | Cache by prompt hash; strict JSON schema validation; fallback to generic mechanical intent. |
| Schema v2 breaks v1 persistence | Default `domain="mechanical"`; keep v1 models valid under v2; migration not required because field is additive. |
| Feature tree becomes bloated | Each domain feature is a small, focused Pydantic model; no generic "bag of keys" model. |

---

*See also:* [`PLAN.md`](../../../PLAN.md) Sections 12–14, [`dossiers/robocad-end-to-end-roadmap.md`](../../../dossiers/robocad-end-to-end-roadmap.md).
