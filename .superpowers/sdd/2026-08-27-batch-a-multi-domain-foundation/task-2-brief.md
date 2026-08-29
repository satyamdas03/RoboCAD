> Task 2 brief extracted from `docs/superpowers/plans/2026-08-27-batch-a-multi-domain-foundation.md`

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

**Report file:** `.superpowers/sdd/2026-08-27-batch-a-multi-domain-foundation/task-2-report.md`

Write the report there and return only: status, commits, test summary, and any concerns.
