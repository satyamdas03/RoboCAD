> Task 4 brief extracted from `docs/superpowers/plans/2026-08-27-batch-a-multi-domain-foundation.md`

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

**Report file:** `.superpowers/sdd/2026-08-27-batch-a-multi-domain-foundation/task-4-report.md`

Write the report there and return only: status, commits, test summary, and any concerns.
