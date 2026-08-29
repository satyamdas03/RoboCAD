> Task 6 brief extracted from `docs/superpowers/plans/2026-08-27-batch-a-multi-domain-foundation.md`

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

**Report file:** `.superpowers/sdd/2026-08-27-batch-a-multi-domain-foundation/task-6-report.md`

Write the report there and return only: status, commits, test summary, and any concerns.
