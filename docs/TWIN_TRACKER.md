# RoboCAD Twin tracker

Plan: `docs/designs/robocad-twin-deep-plan.md` (APPROVED 2026-11-13, then course-corrected the same
day to the demo slice)
Report: `docs/reports/robocad-twin-plan.html`
Updated: 2026-11-13
Owner of this file: monitor session. A row gets `[x]` only when the evidence exists and was run,
with the command and output recorded in `docs/BASELINE.md` or named in the row.

Status legend: `[ ]` not started, `[~]` in progress or evidence incomplete, `[x]` done with
evidence, `[!]` blocked

## Current goal (course correction, 2026-11-13)

A demo that gets robotics engineers and hardware partners interested, not the full build. Quote from
Satyam: "I can send someone a link and a film of a real outside robot compiled from its own CAD and
checked, a version diff, and a clearly labelled synthetic calibration preview. Then I can ask them,
'What would you need to trust this on your robot?'"

Nothing past the demo slice gets built until Satyam says so. M5, M7, M8 to M12 and Phase 2 are
PARKED, not deleted.

## Step 1: M0-lite

| | Item | Evidence required | Owner | State |
|---|---|---|---|---|
| | Record the default-tier baseline | `docs/BASELINE.md` with command, summary line, timing | monitor | [ ] |
| | Record the heavy/slow/mujoco baseline | `docs/BASELINE.md`, raw log kept, command shown | monitor | [~] |
| | CI exits green | workflow file, and the pytest invocations proven locally | monitor | [~] |
| | Apache-2.0 at the root | `LICENSE`, canonical text, decision recorded | build | [x] |
| | `ai_cad/twin/` kept out of the open licence | nested licence plus an exclusion that a wheel build respects | build | [~] |
| | Labs modules behind a flag, off by default | `ROBOCAD_LABS=0` hides frozen panels, a test proves both states | build | [~] |
| | `docs/DECISIONS.md` | present, newest first, with reasons | monitor | [x] |
| | `docs/THIRD_PARTY.md` | every dependency and licence, dev deps included | monitor | [~] |
| | `pyproject.toml` | `pip install -e .` succeeds | build | [~] |

Notes, honestly tagged. `LICENSE` is the canonical 202-line Apache text and the licence split is
written into `ai_cad/twin/LICENSE` `[verified: read]`. CoACD 1.0.14 is installed and importable
`[verified: ran]`. The CI evidence is honest about its limit: the workflow file parses, and the two
pytest invocations were proven locally (default addopts gives exit 5 with `7 deselected`, cleared
addopts gives exit 0 with `7 tests collected`) `[verified: ran]`, but no run has happened on GitHub
Actions, so the row stays `[~]` until a real CI run exists.

## Step 2: week-1 robot search

| | Item | Evidence required | Owner | State |
|---|---|---|---|---|
| | 3 to 5 outside robots with published CAD and a clear licence | `docs/demo/robot_shortlist.md`, every claim checked at source | monitor | [x] |
| | Ranked by open motion or torque log availability | ranking table with the log gaps named | monitor | [x] |
| | Satyam picks one | named robot plus its licence terms | Satyam | [x] |

Shortlist written at `docs/demo/robot_shortlist.md` `[verified: read]`. Satyam picked SO-101 on
2026-11-13. Pinned revision: `TheRobotStudio/SO-ARM100` at
`a758567c3978dfeefe282ede0500085a48fe8f78`, Apache-2.0 confirmed through the GitHub licence API,
assembly `STEP/SO101/SO101 Assembly.step` at 20,496,014 bytes, outside description
`Simulation/SO101/so101_new_calib.urdf` plus `so101_new_calib.xml` `[verified: api]`. Apache-2.0
notice and a statement of changes are required on the page, film and report.

## Step 3: thin M1 to M3, one robot only, SO-101

| | ID | Deliverable | Acceptance evidence | Owner | State |
|---|---|---|---|---|---|
| | M1 | STEP import of the chosen assembly | part and instance counts, units, transforms, warnings | build | [ ] |
| | M2 | Link grouping and joint inference, YAML reviewed by Satyam | proposals versus his edited YAML, axes correct | build | [ ] |
| | M3 | Exact mass and inertia, collision hulls via CoACD | analytic part checks, CoACD hulls, MuJoCo loads clean | build | [ ] |

No vendor-spread work. If a step looks like it will pass about 3 days, stop and propose a smaller
version, per the course correction.

## Step 4: M4 core

| | Item | Acceptance evidence | Owner | State |
|---|---|---|---|---|
| | Bundle plus the 7 checks plus `report.html` | report on the chosen robot, every check carrying a measured value | build | [ ] |
| | One deliberate revision | a changed part or link mass, diff names what changed and by how much | build | [ ] |

## Step 5: M6 core

| | Item | Acceptance evidence | Owner | State |
|---|---|---|---|---|
| | One offline living page under 1 MB | opens from `file://`, no network, every number read from `report.json` | build | [ ] |
| | One 20 to 30 second film | baked MuJoCo trajectory drives it | build | [ ] |

## Step 6: synthetic twin preview

| | Item | Acceptance evidence | Owner | State |
|---|---|---|---|---|
| | Synthetic logs with known perturbations | covers mass, armature, joint friction, damping, latency | build | [ ] |
| | Parameter recovery with intervals | recovered values against known truth, unidentifiable ones flagged | build | [ ] |
| | Sim versus synthetic-real overlay | on the page, and every screen and file labelled SYNTHETIC | build | [ ] |

## Step 7: demo package

| | Item | Acceptance evidence | Owner | State |
|---|---|---|---|---|
| | `docs/demo/README.md` | 3 minute walkthrough script | Satyam and build | [ ] |
| | Page, film, report collected | one link that opens cold | build | [ ] |
| | One paragraph, what is real versus synthetic | names every synthetic artefact by file | build | [ ] |

## Customer lane (parallel, week 1)

| | Item | Evidence required | Owner | State |
|---|---|---|---|---|
| | 15 conversations booked | named list, first-hour calls | Satyam | [ ] |
| | Week-4 go/no-go | 5 of 15 report recurrent sim-to-real drift after a hardware revision, 2 of 15 will share CAD and logs | Satyam | [ ] |

## Parked until Satyam says otherwise

M5 outside-robot case studies as a milestone, M7 CLI launch, PyPI, the compile-on-PR GitHub Action,
multi-vendor CAD coverage, Gazebo and USD export, generated biped work, the real-data half of M8 to
M12, and the weekly heavy-tier CI job. Frozen Labs features stay frozen and get no new work.
