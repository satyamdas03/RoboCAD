# SDD ledger — plan: docs/superpowers/plans/2026-08-27-batch-a-multi-domain-foundation.md

## Preflight scan

| Check | Finding | Ruling |
|---|---|---|
| Task 2 (domain classifier) vs Task 3 (feature tree v2) | Task 2 produces `DomainPrediction` consumed only by Task 4/6; Task 3 adds `domain` fields. No direct conflict. | None needed. |
| Task 4 (intent parser) vs Task 6 (backend) | Task 4 defines `parse_domain_intent`; Task 6 wires it into `/generate` and `/designs/{id}/domain-intent`. Signatures match plan. | None needed. |
| Task 5 (airfoil sketch) vs existing sketch tests | New entity type must not break existing `SketchEntity` Literal validation. Plan uses existing transpiler pattern. | None needed. |
| Task 6 (backend) vs Task 7 (frontend) | Backend adds `domain` to design summary; frontend consumes it. Need to ensure `listDesigns` returns `domain`. | Frontend implementation must handle missing domain gracefully. |
| Task 1 installs heavy dependency | `sentence-transformers` optional; tests must pass without it. | Keyword-only path is the baseline; embedding path is enhancement. |
| Plan internal consistency | Tests in Task 2 use `classify_domain` with mocked embeddings off; Task 4 mocks `_llm_extract`. Consistent. | None needed. |

**Scan result:** clean. Proceeding to Task 1.

## Todos

- [x] Task 1: Install optional embedding dependency — complete (commits 8baa418..ab5b9f3, review clean)
- [ ] Task 2: Create domain classifier
- [ ] Task 3: Extend feature tree to schema v2 with domain tags
- [ ] Task 4: Add per-domain intent parser
- [ ] Task 5: Add airfoil sketch entity
- [ ] Task 6: Backend endpoints for domain classification and intent
- [ ] Task 7: Frontend domain badges and inspector card
- [ ] Task 8: Documentation update for Phases 16–17
- [ ] Task 9: Final verification and push

## Rulings

None yet.

## Task log

