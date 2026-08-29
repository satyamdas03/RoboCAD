> Task 1 brief extracted from `docs/superpowers/plans/2026-08-27-batch-a-multi-domain-foundation.md`

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

**Report file:** `.superpowers/sdd/2026-08-27-batch-a-multi-domain-foundation/task-1-report.md`

Write the report there and return only: status, commits, test summary, and any concerns.
