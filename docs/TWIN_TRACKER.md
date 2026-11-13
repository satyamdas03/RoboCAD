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

## P0-a: joint origins

| | Question | Verdict | Evidence |
|---|---|---|---|
| | Are the joint origins wrong, or is the comparison wrong? | **Same robot.** Kinematics match once five zero-pose offsets and a 38.74 mm base translation are applied. Residual at five joint origins over 100 poses: median 2.50 mm, p90 5.95, max 11.25. Offsets -88.17, +90.29, -90.31, -0.15, 0.00 deg. Zero-seed converges to the same vector, so it is a global basin. | `docs/demo/twin/p0a_confirmation.json`, reproduced independently by the monitor lane |
| | Does that clear the model? | **No.** Collision geometry, mass, inertia and contact behaviour are untouched by this verdict. The self_collision fail and 13 oversized hulls live in P0-b. | `report.json` warnings |

## Findings raised by the monitor lane

| | Finding | Evidence | Owner |
|---|---|---|---|
| | `scripts/build_installer.py:main` runs `_build_frontend()` before `_run_pyinstaller()`, so a machine without PyInstaller still pays a multi minute npm build before being told it cannot build the installer. Cheap to fix, order the check first. | `scripts/build_installer.py:163-164`, found because a test in the default tier was really running npm | unassigned, `scripts/` is outside both lane splits |
| | `tests/test_morphology_api.py::test_run_topology_search` does not finish inside its own `@pytest.mark.timeout(180)`, nor inside 900 s alone on an idle machine, so the heavy tier cannot complete while it is selected. Satyam's decision 2026-11-13: leave it, document it, do not touch frozen work. | `docs/BASELINE.md`, stack in `ai_cad/morphology.py:614` to `check_assembly_collision` | Satyam decides |

## Decisions locked

| | Decision | Value every later report cites |
|---|---|---|
| | Demo robot | SO-101, repository `TheRobotStudio/SO-ARM100`, commit `a758567c3978dfeefe282ede0500085a48fe8f78` (2026-10-06), Apache-2.0 |
| | Assembly under import | `STEP/SO101/SO101 Assembly.step`, 20,496,014 bytes, git blob `541ad0e11398e6701d006c40a032ffd67bac5369` |
| | Outside description to check against | `Simulation/SO101/so101_new_calib.urdf`, `so101_old_calib.urdf`, `so101_new_calib.xml` at the same commit |
| | Licence obligation | Apache-2.0: keep the notice, ship the licence text, state what we changed, on the page, film and report |
| | Collision backend | CoACD 1.0.14, abi3 wheel, verified installed and decomposing |
| | Licence split | Apache-2.0 at the root, `ai_cad/twin/` proprietary and excluded from the built package |

First real M1 datum, from the build session's XCAF probe of the downloaded assembly: 1 top level free
shape, 394 assembly labels, 393 component instances, 144 distinct names, bounding box 175.45 x
320.11 x 344.68 mm, header AP214 from Autodesk Translation Framework. Units are millimetres by
magnitude, and the names include PCB reference designators and anonymous numeric labels, so link
grouping cannot be name-only. `[claimed: build session probe, not yet re-run by monitor]`

## Step 1: M0-lite

| | Item | Evidence required | Owner | State |
|---|---|---|---|---|
| | Record the default-tier baseline | `docs/BASELINE.md` with command, summary line, timing | monitor | [x] |
| | Record the heavy/slow/mujoco baseline | stopped by instruction; frozen Labs test exceeds 900 s, recorded in `BASELINE.md` | monitor | [~] |
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
| | M1 | STEP import of the chosen assembly | part and instance counts, units, transforms, warnings | build | [x] |
| | M2 | Link grouping and joint inference, YAML reviewed by Satyam | 1 geometry-confirmed joint, 91 unresolved pairs; proposal **committed** 2026-11-14 as `docs/twin/so101/robot.joints.yaml` (licence question answered by Satyam's order to commit it); criteria checker 4/4 PASS, record in `docs/twin/so101/JOINT_REVIEW.md` | build | [~] |
| | M3 | Exact mass and inertia, collision hulls via CoACD | B-rep mass and inertia verified, 433 hulls; joint origins still unattributed | build | [~] |

No vendor-spread work. If a step looks like it will pass about 3 days, stop and propose a smaller
version, per the course correction.

M1 evidence, re-run by the monitor session against the pinned SO-101 file rather than taken from the
build session's report. Command `python -c "... import_step(<so101.step>)"` in the repo at `2a767cb`,
output in `docs/baseline/m1_so101_verify.log`: `label_count 394 parts 83 instances 259`, `units mm`,
`root SO101 Assembly v4`, `warnings 0`, `reused_parts 28 max_reuse 45`, `reflected 0`,
`non_proper 0`, `assembly_path_max_depth 7`. That is every number the build session reported,
reproduced by a different operator and process. Import time 48.5 s under load, 10.7 s warm cache on
an idle box; the cold-cache idle figure is still unmeasured and is the only one fit for a report.

M2 result, recorded the way the build session insisted, because it is much smaller than the milestone
name suggests. On the pinned SO-101, geometry recovers exactly **one** joint: the gripper servo to
moving jaw, radius 3.00 mm, from 120 face pairs. The six named arm links share zero coaxial bore or
shaft interfaces at any tolerance down to 0.5 mm, and loosening the rule adds screw-to-screw false
positives rather than real joints. The proposal therefore reports 1 joint and 91 unresolved pairs
across 26 body groups, and never invents a tree. This is the honest M2 acceptance result, not
"joints inferred". The row stays `[~]` because the acceptance gate is Satyam reviewing the YAML, and
the generated proposal at `docs/twin/so101/` is deliberately uncommitted until he says the derived
work may be published.

**Update 2026-11-14.** That gate is answered for publication: Satyam's order for the final sprint is
to commit the skeleton and its review record, so `docs/twin/so101/robot.joints.yaml` (the proposal's
body plus an adoption header) and `docs/twin/so101/JOINT_REVIEW.md` are committed. The review is now a
command rather than an opinion, `python scripts/check_joints_yaml.py`, and it returns 4/4 PASS on the
four criteria in `docs/DECISIONS.md` decision 2. The record distinguishes the author self-check, which
is what that output is, from the independent cross-review, which was requested from the monitor session
and had not returned a verdict when the record was written. The row is `[~]` for that one reason and
flips to `[x]` only when the verdict is in the file.

## Step 4: M4 core

| | Item | Acceptance evidence | Owner | State |
|---|---|---|---|---|
| | Bundle plus the 7 checks plus `report.html` | published at `docs/twin/so101/bundle`, 5 pass, self_collision fail, 1 skipped | build | [x] |
| | One deliberate revision | **defective**: diff compares two link identity schemes, reports 19 removals that never happened; excluded from the page | build | [!] |

## Step 5: M6 core

| | Item | Acceptance evidence | Owner | State |
|---|---|---|---|---|
| | One offline living page under 1 MB | offline, 0 network requests, 55 fps, bound to the published bundle | monitor | [x] |
| | One 20 to 30 second film | 24 s, 720 frames, recorded from the page | monitor | [~] |

## Step 6: synthetic twin preview

| | Item | Acceptance evidence | Owner | State |
|---|---|---|---|---|
| | Synthetic logs with known perturbations | covers mass, armature, joint friction, damping, latency | build | [ ] |
| | Parameter recovery with intervals | rungs 0/1/2/4 recover; rung 3 blocked at SNR 0.1 and quantified | monitor | [~] |
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
