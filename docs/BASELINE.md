# Baseline

Measured on Satyam's Windows laptop, 2026-11-13. Python 3.14.0, pytest 9.1.0, pytest-timeout 2.4.0,
MuJoCo 3.11.0, build123d 0.11.1, 28 logical cores.

Rules this file follows, because earlier numbers in this repo drifted for exactly the opposite
reasons:

- Every row names the commit it was measured at, the command, and the collected count. No row
  carries a total forward from another row.
- A deselected or excluded test is named, not quietly dropped.
- Every timing states its cache state. "Warm" means OCP and MuJoCo imports were already in the OS
  cache from an earlier run in the same session, which flatters the number. No warm number is
  quoted to a customer.
- Numbers measured on an isolated git worktree say so, and any failure that comes from the worktree
  missing the untracked `.env` is attributed to that, with the re-run that proves it.

The isolated worktree used for the pinned rows is a detached checkout at the named commit, at
`C:\Users\point\projects\RoboCAD-baseline`. It is used because the live tree moves while two
sessions work in it, and a baseline measured against a moving tree is not a baseline.

## Default tier

| Commit | Command | Collected | Result | Time | Cache |
|---|---|---|---|---|---|
| `c7a6544` | `python -m pytest -q` in the pinned worktree | 520 of 808 (288 deselected) | 518 passed, 2 failed, 3 warnings | 745.94 s | warm |
| `c7a6544` | the two failing tests, `-q`, in the live repo | 2 | 2 passed | 37.25 s | warm |
| `33e30d1` | collect only, `--collect-only -q` | 521 of 809 (288 deselected) | n/a | 27.20 s | warm |

The two failures at `c7a6544` had **two different causes**, and my first write of this file said both
were `.env`. That was wrong and the build session corrected it. Correct account, each verified in
source:

- `test_onboarding.py::test_backend_health_endpoint` asserted `status in {"ok", "healthy"}`, which is
  true only when `ANTHROPIC_API_KEY` is set. `/health` correctly reports `degraded` without one, and
  the worktree has no `.env` because it is gitignored. Test was wrong about the endpoint, not the
  other way round. It now pins the environment in both directions.
- `test_build_installer.py::test_main_without_pyinstaller_exits_with_message` was not `.env` at all.
  `scripts/build_installer.py:main` calls `_build_frontend()` (line 163) before `_run_pyinstaller()`
  (line 164), so the test ran a real `npm run build` first. The worktree has no
  `web/frontend/node_modules` because it is gitignored, so npm failed before the PyInstaller branch
  was ever reached. Confirmed: `no node_modules in worktree`, and the live repo has it, which is why
  the live re-run passed.

`33e30d1` fixes both so they no longer read the developer's machine. The end-to-end figure for that
commit has not been run by me yet, so this row is a collected count and nothing more.

For comparison, the build session measured 520 passed, 288 deselected, 3 warnings, 281.60 s at
`c7a6544` on the live tree, and 521 passed at `33e30d1`. Two operators, same test outcome; the 2.6x
timing difference is load, not code, since my run shared the machine with import probes and a second
pytest. Neither timing is a performance claim.

## Heavy, slow and mujoco tier

| Commit | Command | Collected | Result | Time | Cache |
|---|---|---|---|---|---|
| `ffd9449` | `python -m pytest -m "heavy or slow or mujoco" -o addopts="--timeout=600 --tb=short" -q` | 288 of 735 | aborted, exit 1 | 29 min to abort | warm |
| `c7a6544` | same, plus `--deselect tests/test_morphology_api.py::test_run_topology_search` | 288 of 808 | stopped on instruction at 25%, no failures seen | 23 min | warm |

**Heavy tier not run for the demo sprint.** Satyam's instruction on 2026-11-13: stop the baseline and
do not spend more time on it, because the frozen Labs topology test exceeds 900 s and the run eats
the machine the sprint needs. The `ffd9449` attempt below is the evidence for why.

The `ffd9449` run did not complete. After about 57 tests and 29 minutes it hit the per-test timeout
and the session aborted with exit 1. The test was
`tests/test_morphology_api.py::test_run_topology_search`, stack inside
`ai_cad/morphology.py:614 search_morphologies` calling `score_candidate_collision` into
`check_assembly_collision`, which rebuilds meshes per pose.

That test was then run alone, on an otherwise idle machine, with `--timeout=900`, and it still hit
the timeout and exited 1, so contention is ruled out. It also declares `@pytest.mark.timeout(180)`
on itself, which means the code was written believing it fits in three minutes; on this machine it
does not finish in fifteen. It is frozen Labs code, and Satyam's decision on 2026-11-13 was to leave
it, document it and not touch frozen work for the demo slice.

Consequence, stated the way it must be stated: **the heavy tier cannot be completed on this machine
while that test is selected.** Any claim of the form "Frozen Labs stays green" is unsupported.
The heavy row at `c7a6544` therefore excludes exactly one named test, and its count is a count of the
tier minus that test, not a green tier.

## Import timing, SO-101

| Command | Result | Time | Cache |
|---|---|---|---|
| `import_step(<so101.step>)` at `2a767cb`, heavy tier running concurrently | 83 parts, 259 instances | 48.5 s | cold, under load |
| same, build session, idle box | 83 parts, 259 instances | 10.7 s | warm |

The number fit for any external use is the cold-cache figure on an idle machine, and it has not been
measured yet. It is the first thing to measure before any demo timing appears in a report.

## Collected counts, as a check rather than a headline

| Commit | Collected | Deselected |
|---|---|---|
| `ffd9449` | 735 | 288 |
| `2a767cb` | 760 | 288 |
| `35023a1` | 765 | 288 |
| `302d065` | 803 | 288 |
| `c7a6544` | 808 | 288 |
| `33e30d1` | 809 | 288 |
| `af75fdd` plus in-flight edits | 968 | 300 |

The `af75fdd` run is labelled with that caveat on purpose. It ran while Lane A had three files modified
but uncommitted in the same tree, so it measures the commit plus those edits, not the commit alone. The
collected count measured afterwards is 668 of 968, against 664 passed and 298 deselected during the run,
and the difference is those edits landing mid-run. A clean single-command run of exactly `af75fdd` has
not been done, and pretending otherwise would be the drift this file exists to prevent.

Each of these was read with `python -m pytest --collect-only -q -p no:cacheprovider` at the commit,
not derived by arithmetic from the row above.
