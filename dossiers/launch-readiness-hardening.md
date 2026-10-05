# Launch Readiness Hardening — Options A-D

> Scope: post-Milestone I launch-review hardening across security, reliability/resilience, honest-score verification, and frontend/UX. Sim-to-real (Milestone H) remains intentionally blocked on hardware.

---

## What changed

### 1. Emilkowalski skills install + design lock

- Installed `emilkowalski/skills` via the Claude Code skills manager.
- Copied the 14 skills into `.claude/skills/` so they are repo-tracked and usable in every checkout:
  `animate`, `animate-expo`, `animation-vocabulary`, `apple-design`, `ask-sonner`, `break-ui`, `emil-design-eng`, `find-animation-opportunities`, `improve-animations`, `mobile-native`, `pick-ui-library`, `prototype`, `review-animations`, `write-swift`.
- Added `.claude/skills/skills-lock.json` to pin the installed set.
- Added `.agents/` to `.gitignore` so the source-of-truth copy remains under `.claude/skills/`.

### 2. Launcher / `.env` reliability (Option B)

- `robocad/launcher.py` now loads `REPO_ROOT / ".env"` with `override=True` at module top, so `python start.py` on Windows sees secrets immediately.
- `robocad/health.py` loads the same repo `.env` so `python -m robocad.health` reports key presence correctly.
- Default backend host changed from `0.0.0.0` to `127.0.0.1`; reload disabled so Windows `start.py` spawns a single stable backend process.
- Added regression tests in `tests/test_launcher.py` and `tests/test_health.py` that monkeypatch `dotenv.load_dotenv`, reload the modules, and assert the repo `.env` is loaded.

### 3. Backend security hardening (Option A)

`web/backend/main.py`:

- Added ID regexes and validators for UUID-style IDs (`_validate_uuid_id`), design IDs (`_validate_design_id`), version IDs (`_validate_version_id`), and HERMES session IDs (`_validate_hermes_session_id`).
- Added `_resolve_design_dir` / `_resolve_export_path` containment helpers that reject `..` and verify the resolved path is inside `WORK_DIR` / `EXPORT_DIR`.
- Added FastAPI `_validate_path_ids` middleware that rejects malformed path params before any endpoint runs.
- Changed `/exports/{design_id}/{filename:path}` to use `_resolve_export_path`.
- Hardened `/marketplace/upload` with `_safe_extract_zip` / `_safe_extract_tar`, explicit member traversal checks, and post-extraction source-dir containment verification.
- Tightened CORS: reject `*` when `allow_credentials=True`, restrict allowed methods to `GET/POST/PUT/DELETE`, and allowed headers to `Content-Type/Authorization`.

`ai_cad/executor.py`:

- Added `_scrubbed_env()` that removes any environment key matching secret/API-key patterns.
- Generated-code subprocesses now run with `env=_scrubbed_env()` so leaked keys are not surfaced to sandboxed user code.

### 4. Frontend mobile/UX hardening (Option D)

- `web/frontend/index.html`: single valid `<div id="root">`, corrected viewport meta (`viewport-fit=cover`, `interactive-widget=resizes-content`), `color-scheme`, and `theme-color`.
- `web/frontend/src/styles/index.css`:
  - `100dvh` instead of `100vh`.
  - Hover states gated to `@media (hover: hover) and (pointer: fine)`.
  - Inputs default to `font-size: 16px` on touch, scaled down only on fine-pointer devices to prevent iOS zoom.
  - Responsive grid with `minmax(min(280px, 100%), 1fr)`.
  - Blanket `@media (prefers-reduced-motion: reduce)` disabling transforms/transitions on inspector, sidebar, buttons, list items, chips.
  - `-webkit-tap-highlight-color: transparent`, `-webkit-text-size-adjust: 100%`, `overscroll-behavior: none`.
- `WelcomePanel.jsx`: removed JS hover state and inline-style hover; replaced with CSS-only `kp-welcome-chip` hover.
- `HermesPanel.jsx`: `prefersReducedMotion()` helper for `scrollIntoView`, message bubble overflow wrapping, SVG orb icon replacing 🧿 emoji, stable audit React keys.
- `App.jsx` / `ParameterList.jsx`: reduced-motion guards on programmatic scroll; keep previous model visible while new generation loads.
- `web/frontend/src/api.js`: default 30 s `AbortController` timeout; parses JSON error `message`/`detail` before falling back to raw text.
- `web/frontend/vite.config.js`: added missing dev-server proxies for `/hermes`, `/morphology`, `/verify`, `/marketplace`, `/worlds`.

### 5. Honest-score verification (Option C)

- Re-ran the full default pytest suite after all hardening changes.
- Added launcher/health regression tests, preserving the prior default-suite coverage.
- Heavy/slow/mujoco suite is re-run after workflow completion.
- No score bump yet; score remains at **9.7/10** until the workflow closes remaining reliability and verification gaps.

---

## Test status

- **Default suite:** 412 passed, 279 deselected, 3 warnings (~6 min 30 s).
- **Heavy/slow/mujoco suite:** in progress after hardening.
- **Frontend production build:** passes.

---

## Still open

- The `/workflows` multi-agent launch-review workflow (`robocad-end-to-end-launch-review`) is still completing the honest-score/verify/apply/test phases.
- Any remaining reliability findings (long-running synchronous endpoints, health readiness, orphan-process cleanup, port preflight) will be applied after verification.
- Local end-to-end launch test with `python start.py` is pending workflow completion.

---

## Why this matters

The product is approaching launch. Options A-D close the gap between "feature-complete" and "safe to put in front of users":

- **A (security):** path traversal, archive extraction, CORS, and subprocess env scrubbing prevent common abuse vectors.
- **B (reliability/resilience):** launcher/health/.env fixes, stable backend process, and API timeouts keep the app working on real Windows laptops.
- **C (honest score):** continuous test verification keeps the 9.7/10 claim grounded.
- **D (frontend/UX):** mobile-native fixes, reduced-motion support, and polished HERMES/onboarding UI make the product feel production-grade.
