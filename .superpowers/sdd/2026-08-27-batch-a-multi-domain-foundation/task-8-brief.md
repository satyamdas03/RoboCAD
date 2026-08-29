> Task 8 brief extracted from `docs/superpowers/plans/2026-08-27-batch-a-multi-domain-foundation.md`

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

**Report file:** `.superpowers/sdd/2026-08-27-batch-a-multi-domain-foundation/task-8-report.md`

Write the report there and return only: status, commits, test summary, and any concerns.
