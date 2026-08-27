# Batch A — Multi-Domain Foundation (Phases 16–17) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add domain classification, domain-aware feature-tree schema v2, per-domain intent parsing, and sketch-to-airfoil support to RoboCAD, with backend/frontend wiring and documentation updates.

**Architecture:** A lightweight local domain classifier (`ai_cad/domain.py`) feeds a per-domain LLM intent parser (`ai_cad/intent_parser.py`). The parsed intent is stored in an extended feature-tree schema v2 (`ai_cad/feature_tree.py`) that tags parts/features by domain and adds placeholders for aero/thermal surfaces, electronics PCBs, and kinematic joints. Backend endpoints expose classification and domain-intent retrieval; the frontend shows domain badges. Tests cover classification, schema evolution, intent parsing, sketch airfoils, and endpoint wiring.

**Tech Stack:** Python 3.11, Pydantic v2, FastAPI, React, build123d, pytest, `sentence-transformers` (optional dev dependency), local embeddings for offline domain classification.

**Spec:** `docs/superpowers/specs/2026-08-27-batch-a-multi-domain-foundation.md`

## Global Constraints

- `sentence-transformers>=3.0.0` is an optional dev dependency; all functionality must degrade gracefully to keyword-only classification if not installed.
- Existing mechanical feature-tree v1 models and transpiler behavior must remain backward-compatible.
- No voice input in this batch.
- No actual aero/thermal/electronics/humanoid geometry generation in this batch — only representation and intent parsing.
- No changes to existing LLM fine-tuning scripts.
- Every task ends with a passing test and a commit.
- README, dossiers, and memory files must be updated when Phases 16–17 are marked complete.

---

### Task 1: Install optional embedding dependency

**Files:**
- Modify: `requirements-dev.txt`

**Interfaces:**
- Consumes: nothing
- Produces: dev environment with `sentence-transformers` available for offline tests

- [ ] **Step 1: Add optional dependency**

Append to `requirements-dev.txt`:

```text
sentence-transformers>=3.0.0
```

- [ ] **Step 2: Verify install**

Run:

```bash
pip install -r requirements-dev.txt
```

Expected: installs without error; `python -c "from sentence_transformers import SentenceTransformer; print('ok')"` prints `ok`.

- [ ] **Step 3: Commit**

```bash
git add requirements-dev.txt
git commit -m "chore(deps): add sentence-transformers as optional dev dependency"
```

---

### Task 2: Create domain classifier

**Files:**
- Create: `ai_cad/domain.py`
- Create: `tests/test_domain_classifier.py`

**Interfaces:**
- Consumes: nothing
- Produces: `classify_domain(prompt: str) -> DomainPrediction`

- [ ] **Step 1: Write failing test**

In `tests/test_domain_classifier.py`:

```python
from ai_cad.domain import classify_domain


def test_mechanical_prompt():
    result = classify_domain("A 120 mm bracket with four M3 holes")
    assert result.primary == "mechanical"
    assert result.scores["mechanical"] > 0.7
    assert not result.multi_domain


def test_aero_prompt():
    result = classify_domain("NACA 2412 airfoil with 200 mm chord")
    assert result.primary == "aero"
    assert result.scores["aero"] > 0.7


def test_multi_domain_prompt():
    result = classify_domain("450 mm quadcopter frame with motor arms and aerodynamic shell")
    assert result.multi_domain
    assert "mechanical" in result.scores
    assert "aero" in result.scores
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_domain_classifier.py -v
```

Expected: `ModuleNotFoundError: No module named 'ai_cad.domain'`.

- [ ] **Step 3: Implement keyword + embedding classifier**

In `ai_cad/domain.py`:

```python
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

DOMAIN_KEYWORDS = {
    "mechanical": ["bracket", "plate", "mount", "gear", "pulley", "hub", "chassis", "wheel", "gripper", "assembly", "mate", "hole", "extrude"],
    "aero": ["airfoil", "wing", "duct", "propeller", "blade", "naca", "chord", "span", "sweep", "twist", "aerodynamic"],
    "thermal": ["heat sink", "heatsink", "fin", "cooler", "spreader", "thermal", "heat"],
    "electronics": ["pcb", "board", "raspberry", "arduino", "connector", "enclosure", "mounting hole", "cable guide", "component"],
    "humanoid": ["biped", "quadruped", "humanoid", "robot arm", "leg", "torso", "joint", "link", "end effector"],
}


class DomainPrediction(BaseModel):
    primary: str
    scores: dict[str, float]
    reasoning: str
    multi_domain: bool = Field(default=False)


def _keyword_scores(prompt: str) -> dict[str, float]:
    text = prompt.lower()
    scores: dict[str, float] = {}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        scores[domain] = score / max(len(keywords), 1)
    return scores


def _normalize(scores: dict[str, float]) -> dict[str, float]:
    total = sum(scores.values()) or 1.0
    return {k: round(v / total, 4) for k, v in scores.items()}


def classify_domain(prompt: str, *, use_embeddings: bool = True) -> DomainPrediction:
    scores = _keyword_scores(prompt)
    normalized = _normalize(scores)
    primary = max(normalized, key=normalized.get)

    # Optional embedding fallback if keyword scores are close
    if use_embeddings:
        try:
            from sentence_transformers import SentenceTransformer, util

            model = SentenceTransformer("all-MiniLM-L6-v2")
            prototypes = {
                "mechanical": "mechanical part bracket plate mount gear assembly",
                "aero": "airfoil wing propeller duct aerodynamic surface",
                "thermal": "heat sink thermal fin cooler heat spreader",
                "electronics": "pcb board raspberry pi connector enclosure electronics",
                "humanoid": "humanoid robot biped quadruped arm leg joint",
            }
            prompt_emb = model.encode(prompt, convert_to_tensor=True)
            emb_scores = {
                domain: float(util.cos_sim(prompt_emb, model.encode(text, convert_to_tensor=True))[0][0])
                for domain, text in prototypes.items()
            }
            if emb_scores[primary] < 0.35:
                # blend keyword and embedding scores
                blended = {k: 0.5 * normalized.get(k, 0.0) + 0.5 * max(0.0, emb_scores.get(k, 0.0)) for k in DOMAIN_KEYWORDS}
                normalized = _normalize(blended)
                primary = max(normalized, key=normalized.get)
        except Exception:
            pass

    threshold = 0.25
    top = [d for d, s in normalized.items() if s >= threshold]
    multi = len(top) > 1
    if multi and primary not in top:
        primary = top[0]

    reasoning = f"Keyword matches plus optional embedding fallback; primary={primary}"
    return DomainPrediction(primary=primary, scores=normalized, reasoning=reasoning, multi_domain=multi)
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
pytest tests/test_domain_classifier.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add ai_cad/domain.py tests/test_domain_classifier.py
git commit -m "feat(domain): add local keyword + embedding domain classifier"
```

---

### Task 3: Extend feature tree to schema v2 with domain tags

**Files:**
- Modify: `ai_cad/feature_tree.py`
- Create: `tests/test_feature_tree_v2.py`

**Interfaces:**
- Consumes: existing v1 schema and models
- Produces: backward-compatible v2 models with `domain`, `KinematicJoint`, `SurfaceFeature`, `PCBOutline`

- [ ] **Step 1: Write failing test**

In `tests/test_feature_tree_v2.py`:

```python
from ai_cad.feature_tree import FeatureTree, Feature, Part, Assembly, KinematicJoint, SurfaceFeature, PCBOutline


def test_default_domain_is_mechanical():
    tree = FeatureTree(
        design_id="d1",
        prompt="bracket",
        parameters=[{"name": "thickness", "value": 3.0}],
        features=[{"type": "extrude", "id": "f1", "sketch_id": "s1", "depth": 10.0}],
    )
    assert tree.features[0].domain == "mechanical"


def test_aero_surface_feature():
    tree = FeatureTree(
        design_id="d2",
        prompt="airfoil",
        parameters=[{"name": "chord", "value": 200.0}],
        features=[SurfaceFeature(id="af1", type="airfoil", profile={"naca": "2412", "chord_param": "chord"}).model_dump()],
    )
    assert tree.features[0].domain == "aero"


def test_kinematic_joint_in_assembly():
    asm = Assembly(
        id="a1",
        name="arm",
        parts=[],
        mates=[],
        joints=[KinematicJoint(id="j1", type="revolute", parent_link="base", child_link="link1", origin=(0, 0, 0), axis=(0, 0, 1))],
    )
    assert asm.joints[0].type == "revolute"


def test_pcb_outline():
    pcb = PCBOutline(id="pcb1", board_shape=[(0, 0), (85, 0), (85, 56), (0, 56)], mounting_holes=[(3.5, 3.5, 3.0)])
    assert pcb.domain == "electronics"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_feature_tree_v2.py -v
```

Expected: failures due to missing `domain`, `SurfaceFeature`, `KinematicJoint`, `PCBOutline`.

- [ ] **Step 3: Extend models**

Modify `ai_cad/feature_tree.py`:

1. Add to imports: `Literal` already imported; no change needed.
2. Add after `Parameter`:

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
    profile: dict[str, Any]
    domain: str = "aero"


class PCBOutline(BaseModel):
    id: str
    board_shape: list[tuple[float, float]]
    mounting_holes: list[tuple[float, float, float]] = Field(default_factory=list)
    keepouts: list[dict[str, Any]] = Field(default_factory=list)
    domain: str = "electronics"
```

3. Add `domain: str = "mechanical"` to `Feature`, `Part`, and `Assembly`.

4. Add `joints: list[KinematicJoint] = Field(default_factory=list)` to `Assembly`.

5. Add `domain: str = "mechanical"` to `FeatureTree`.

6. Bump docstring to reference schema v2.0.0.

- [ ] **Step 4: Run tests**

Run:

```bash
pytest tests/test_feature_tree_v2.py tests/test_feature_tree.py tests/test_transpiler.py -v
```

Expected: all pass with no regressions.

- [ ] **Step 5: Commit**

```bash
git add ai_cad/feature_tree.py tests/test_feature_tree_v2.py
git commit -m "feat(feature-tree): schema v2 with domain tags, aero surfaces, joints, PCB outlines"
```

---

### Task 4: Add per-domain intent parser

**Files:**
- Create: `ai_cad/intent_parser.py`
- Create: `tests/test_intent_parser.py`

**Interfaces:**
- Consumes: `ai_cad.feature_tree.Parameter`
- Produces: `parse_domain_intent(prompt: str, domain: str | None = None) -> DomainIntent`

- [ ] **Step 1: Write failing test**

In `tests/test_intent_parser.py`:

```python
from ai_cad.intent_parser import parse_domain_intent


def test_mechanical_intent(mocker):
    mocker.patch("ai_cad.intent_parser._llm_extract", return_value={
        "parameters": [{"name": "length", "value": 120.0, "unit": "mm"}],
        "features": [{"type": "extrude", "id": "f1"}],
        "constraints": [],
        "notes": [],
        "confidence": 0.9,
    })
    intent = parse_domain_intent("A 120 mm bracket", domain="mechanical")
    assert intent.domain == "mechanical"
    assert intent.parameters[0].name == "length"


def test_fallback_to_mechanical():
    intent = parse_domain_intent("some random text")
    assert intent.domain == "mechanical"
    assert intent.confidence == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_intent_parser.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement intent parser**

In `ai_cad/intent_parser.py`:

```python
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from ai_cad.api import RoboCADBackend
from ai_cad.domain import classify_domain
from ai_cad.feature_tree import Parameter


class DomainIntent(BaseModel):
    domain: str
    parameters: list[Parameter]
    features: list[dict[str, Any]]
    constraints: list[str]
    notes: list[str]
    confidence: float


_PROMPT_TEMPLATES: dict[str, str] = {
    "mechanical": """Extract structured parameters and features for a mechanical part from the user prompt.
Return JSON with keys: parameters, features, constraints, notes, confidence.
Example parameters: length, width, thickness, hole_diameter, hole_count, material.
""",
    "aero": """Extract structured parameters and features for an aerodynamic/thermal surface from the user prompt.
Return JSON with keys: parameters, features, constraints, notes, confidence.
Example parameters: chord, span, naca_code, sweep, twist, fin_count, fin_height.
""",
    "thermal": """Extract structured parameters and features for a thermal part from the user prompt.
Return JSON with keys: parameters, features, constraints, notes, confidence.
Example parameters: fin_count, fin_height, base_length, base_width, thermal_load.
""",
    "electronics": """Extract structured parameters and features for an electronics/mechanical co-design part from the user prompt.
Return JSON with keys: parameters, features, constraints, notes, confidence.
Example parameters: board_length, board_width, mounting_hole_diameter, connector_count.
""",
    "humanoid": """Extract structured parameters and features for a humanoid/robot subsystem from the user prompt.
Return JSON with keys: parameters, features, constraints, notes, confidence.
Example parameters: height, mass, dof, link_length, payload.
""",
}


def _llm_extract(prompt: str, domain: str) -> dict[str, Any]:
    backend = RoboCADBackend()
    system = _PROMPT_TEMPLATES.get(domain, _PROMPT_TEMPLATES["mechanical"])
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Prompt: {prompt}\n\nReturn only JSON."},
    ]
    try:
        response = backend.generator.client.messages.create(
            model=backend.generator.model,
            max_tokens=2048,
            messages=messages,
        )
        text = "".join(b.text for b in response.content if hasattr(b, "text"))
        return json.loads(text)
    except Exception:
        return {"parameters": [], "features": [], "constraints": [], "notes": ["LLM fallback failed"], "confidence": 0.0}


def parse_domain_intent(prompt: str, domain: str | None = None) -> DomainIntent:
    target = domain or classify_domain(prompt).primary
    raw = _llm_extract(prompt, target)
    params = [Parameter(**p) for p in raw.get("parameters", [])]
    return DomainIntent(
        domain=target,
        parameters=params,
        features=raw.get("features", []),
        constraints=raw.get("constraints", []),
        notes=raw.get("notes", []),
        confidence=raw.get("confidence", 0.0),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
pytest tests/test_intent_parser.py -v
```

Expected: tests pass.

- [ ] **Step 5: Commit**

```bash
git add ai_cad/intent_parser.py tests/test_intent_parser.py
git commit -m "feat(intent): per-domain LLM intent parser with fallback"
```

---

### Task 5: Add airfoil sketch entity

**Files:**
- Modify: `ai_cad/sketch.py`
- Modify: `ai_cad/sketch_solver.py`
- Create: `tests/test_sketch_airfoil.py`

**Interfaces:**
- Consumes: existing sketch solver framework
- Produces: `airfoil` entity type that yields a set of points and a thickness parameter

- [ ] **Step 1: Write failing test**

In `tests/test_sketch_airfoil.py`:

```python
from ai_cad.sketch import SketchEntity
from ai_cad.sketch_solver import solve_sketch


def test_airfoil_entity():
    entities = [
        SketchEntity(type="airfoil", id="af1", naca="2412", chord=200.0)
    ]
    result = solve_sketch(entities, [])
    assert "af1" in result.points
    assert len(result.points["af1"]) > 10
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_sketch_airfoil.py -v
```

Expected: failure because `airfoil` is not handled.

- [ ] **Step 3: Implement airfoil entity**

In `ai_cad/sketch.py` add `airfoil` to `SketchEntity.type` Literal and add fields:

```python
naca: str | None = None
chord: NumericOrString | None = None
```

In `ai_cad/sketch_solver.py`, in the solver loop, add handling for `type == "airfoil"`:

```python
def _naca_4digit_points(code: str, chord: float, n: int = 40) -> list[tuple[float, float]]:
    # Simplified NACA 4-digit thickness form
    m = int(code[0]) / 100.0
    p = int(code[1]) / 10.0
    tt = int(code[2:4]) / 100.0
    pts = []
    for i in range(n + 1):
        x = (i / n) * chord
        xc = x / chord
        yt = 5 * tt * (0.2969 * xc**0.5 - 0.1260 * xc - 0.3516 * xc**2 + 0.2843 * xc**3 - 0.1015 * xc**4)
        pts.append((x, yt))
    for i in range(n, -1, -1):
        x = (i / n) * chord
        xc = x / chord
        yt = 5 * tt * (0.2969 * xc**0.5 - 0.1260 * xc - 0.3516 * xc**2 + 0.2843 * xc**3 - 0.1015 * xc**4)
        pts.append((x, -yt))
    return pts
```

Store the resulting points in the solver state under the entity id.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
pytest tests/test_sketch_airfoil.py tests/test_sketch_solver.py -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add ai_cad/sketch.py ai_cad/sketch_solver.py tests/test_sketch_airfoil.py
git commit -m "feat(sketch): add NACA 4-digit airfoil sketch entity"
```

---

### Task 6: Backend endpoints for domain classification and intent

**Files:**
- Modify: `web/backend/main.py`
- Modify: `tests/test_web_backend.py`

**Interfaces:**
- Consumes: `ai_cad.domain.classify_domain`, `ai_cad.intent_parser.parse_domain_intent`
- Produces: `POST /classify-domain`, `GET /designs/{id}/domain-intent`, updated `POST /generate`

- [ ] **Step 1: Write failing endpoint test**

In `tests/test_web_backend.py`, append:

```python
def test_classify_domain_endpoint(client):
    resp = client.post("/classify-domain", json={"prompt": "NACA 2412 airfoil"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["primary"] == "aero"


def test_generate_with_domain_detection(client, tmp_path, monkeypatch):
    monkeypatch.setenv("ROBOCAD_DESIGNS_DIR", str(tmp_path))
    from ai_cad.intent_parser import _llm_extract
    original = _llm_extract
    monkeypatch.setattr("ai_cad.intent_parser._llm_extract", lambda p, d: {
        "parameters": [{"name": "chord", "value": 200.0, "unit": "mm"}],
        "features": [{"type": "airfoil", "id": "af1"}],
        "constraints": [],
        "notes": [],
        "confidence": 0.9,
    })
    resp = client.post("/generate", json={"prompt": "NACA 2412 airfoil", "detect_domain": True, "max_retries": 0})
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("domain") == "aero"
    assert (tmp_path / data["design_id"] / "domain_intent.json").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_web_backend.py::test_classify_domain_endpoint tests/test_web_backend.py::test_generate_with_domain_detection -v
```

Expected: 404 / missing `domain`.

- [ ] **Step 3: Implement endpoints**

In `web/backend/main.py`:

1. Import `classify_domain` and `parse_domain_intent`:

```python
from ai_cad.domain import classify_domain
from ai_cad.intent_parser import parse_domain_intent
```

2. Add request models:

```python
class ClassifyDomainRequest(BaseModel):
    prompt: str


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    max_retries: int = Field(default=2, ge=0, le=5)
    model: str | None = Field(default=None)
    use_assembly: bool = Field(default=False)
    detect_domain: bool = Field(default=False)
```

3. Add endpoint:

```python
@app.post("/classify-domain")
def classify_domain_endpoint(req: ClassifyDomainRequest):
    return classify_domain(req.prompt).model_dump()
```

4. In the existing `generate_design` helper (or inside `POST /generate`), if `detect_domain` is true:
   - Call `classify_domain(prompt)`.
   - Call `parse_domain_intent(prompt, domain=domain)`.
   - Write `design_dir / "domain_intent.json"`.
   - Add `domain` and `domain_intent` to the response.

5. Add endpoint:

```python
@app.get("/designs/{id}/domain-intent")
def get_domain_intent(id: str):
    path = DESIGNS_DIR / id / "domain_intent.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="No domain intent for this design")
    return JSONResponse(content=json.loads(path.read_text()))
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
pytest tests/test_web_backend.py -v
```

Expected: all backend tests pass.

- [ ] **Step 5: Commit**

```bash
git add web/backend/main.py tests/test_web_backend.py
git commit -m "feat(api): classify-domain endpoint and domain-intent persistence"
```

---

### Task 7: Frontend domain badges and inspector card

**Files:**
- Create: `web/frontend/src/components/DomainBadge.jsx`
- Modify: `web/frontend/src/components/HistorySidebar.jsx`
- Modify: `web/frontend/src/App.jsx`
- Modify: `web/frontend/src/api.js`

**Interfaces:**
- Consumes: `GET /designs` summary now includes `domain`
- Produces: `DomainBadge` component, `loadDomainIntent` API helper

- [ ] **Step 1: Add API helper**

In `web/frontend/src/api.js`, add:

```javascript
export async function classifyDomain(prompt) {
  const resp = await fetch(`${API_BASE}/classify-domain`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt }),
  })
  if (!resp.ok) throw new Error('domain classification failed')
  return resp.json()
}

export async function loadDomainIntent(id) {
  const resp = await fetch(`${API_BASE}/designs/${id}/domain-intent`)
  if (resp.status === 404) return null
  if (!resp.ok) throw new Error('failed to load domain intent')
  return resp.json()
}
```

- [ ] **Step 2: Create DomainBadge component**

In `web/frontend/src/components/DomainBadge.jsx`:

```jsx
const DOMAIN_COLORS = {
  mechanical: '#00e5ff',
  aero: '#76ff03',
  thermal: '#ff9100',
  electronics: '#d500f9',
  humanoid: '#ff4081',
  multi: '#ffd600',
}

export default function DomainBadge({ domain, multi }) {
  const color = DOMAIN_COLORS[multi ? 'multi' : domain] || '#ffffff'
  const label = multi ? 'multi-domain' : domain
  return (
    <span style={{ color, border: `1px solid ${color}`, borderRadius: 4, padding: '2px 6px', fontSize: 11, textTransform: 'uppercase' }}>
      {label}
    </span>
  )
}
```

- [ ] **Step 3: Show badge in history sidebar**

In `web/frontend/src/components/HistorySidebar.jsx`, import `DomainBadge` and render it next to each design item if `item.domain` exists.

- [ ] **Step 4: Add domain-intent inspector card in App.jsx**

In `web/frontend/src/App.jsx`:
- Add state `domainIntent`.
- In `handleGenerate`, after generation, call `classifyDomain` and store result if `detect_domain` enabled.
- In `handleSelect`, call `loadDomainIntent` and store it.
- Render a small inspector card (reuse existing right-panel style) showing `domainIntent.domain`, parameters, and notes.

- [ ] **Step 5: Verify frontend build**

Run:

```bash
cd web/frontend
npm run build
```

Expected: build succeeds.

- [ ] **Step 6: Commit**

```bash
git add web/frontend/src/components/DomainBadge.jsx web/frontend/src/components/HistorySidebar.jsx web/frontend/src/App.jsx web/frontend/src/api.js
git commit -m "feat(ui): domain badges, classify API, and domain-intent inspector card"
```

---

### Task 8: Documentation update for Phases 16–17

**Files:**
- Modify: `README.md`
- Modify: `dossiers/robocad-end-to-end-roadmap.md`
- Modify: `.claude/projects/C--Users-point-projects-RoboCAD/memory/phase16-17-multi-domain-foundation.md` (create)
- Modify: `.claude/projects/C--Users-point-projects-RoboCAD/memory/MEMORY.md`

**Interfaces:**
- Consumes: completed code + tests
- Produces: updated docs, dossiers, memory

- [ ] **Step 1: Update README.md roadmap table**

Mark Phase 16 and 17 as ✅ with one-line summary of what shipped: domain classifier + intent parser + schema v2 + airfoil sketch entity.

- [ ] **Step 2: Update dossiers/robocad-end-to-end-roadmap.md**

Set Phase 16 and 17 status to ✅ complete and update deliverables list with actual file names (`ai_cad/domain.py`, `ai_cad/intent_parser.py`, `ai_cad/feature_tree.py` v2, `ai_cad/sketch_solver.py` airfoil).

- [ ] **Step 3: Create memory file**

Create `.claude/projects/C--Users-point-projects-RoboCAD/memory/phase16-17-multi-domain-foundation.md` with frontmatter:

```markdown
---
name: phase16-17-multi-domain-foundation
description: Batch A completion — domain classifier, schema v2, intent parser, airfoil sketch entity, backend/frontend wiring.
metadata:
  node_type: memory
  type: project
---
```

Body: date, deliverables, test count, next action (open Batch B).

- [ ] **Step 4: Update MEMORY.md index**

Add:

```markdown
- [Phase 16–17 multi-domain foundation](phase16-17-multi-domain-foundation.md) — Domain classifier + intent parser + feature-tree v2 + airfoil sketch entity; backend/frontend wired; N/N tests passing.
```

- [ ] **Step 5: Commit docs**

```bash
git add README.md dossiers/robocad-end-to-end-roadmap.md .claude/projects/C--Users-point-projects-RoboCAD/memory/
git commit -m "docs(scope): mark Phases 16-17 complete and update memory/README/dossiers"
```

---

### Task 9: Final verification and push

**Files:**
- All modified files

**Interfaces:**
- Consumes: completed batch
- Produces: green test suite, pushed commit

- [ ] **Step 1: Run full test suite**

Run:

```bash
python -m pytest -q
```

Expected: 187 + new tests passing.

- [ ] **Step 2: Push to origin**

```bash
git push origin master
```

Expected: push succeeds.

---

## Spec coverage self-review

| Spec section | Task |
|---|---|
| Domain classifier (3.1) | Task 2 |
| Feature-tree v2 (3.2) | Task 3 |
| Per-domain intent parser (3.3) | Task 4 |
| Sketch-to-constraint airfoil (3.4) | Task 5 |
| Backend integration (3.5) | Task 6 |
| Frontend integration (3.6) | Task 7 |
| Tests (3.7) | Tasks 2–6 |
| Boundaries | Global constraints |
| Dependencies | Task 1 |
| Success criteria | Task 9 |
| Documentation | Task 8 |

No placeholders remain.
