# Decisions

Newest first. One entry per decision, with the date, what was decided, why, and what it rules out.
A decision without a reason is a preference; it does not belong here.

## 2026-11-13 Sprint decisions (demo deadline Sat 14 Nov 22:00 Sydney)

Satyam is unavailable until the deadline, and these were made so the sprint does not wait. Each is
one line of reasoning, as the sprint rule requires.

1. **Publish `docs/twin/so101/`.** Apache-2.0 permits derived files when attribution is kept and
   changes are marked. `docs/twin/so101/NOTICE.md` names the SO-101 project, the licence, the pinned
   commit `a758567`, and what we changed.
2. **M2 YAML is cross-reviewed, not auto-inferred.** The session that did not write
   `robot.joints.yaml` checks it against the written criteria (every instance assigned exactly once,
   six revolute joints within 1 degree of the servo shaft axis, limits sourced and stated, tree
   matching official topology) and records PASS or FAIL in this file. Satyam confirms afterwards.
3. **Collision: CoACD for at most 30 minutes.** Then convex hulls or primitives, with the reason
   recorded. Debugging installs is not product work.
4. **Heavy test tier stopped for the sprint.** One frozen Labs test exceeds 900 s, so the tier cannot
   finish, and the machine is needed for the demo. `BASELINE.md` records the stop and the evidence.
5. **Living page built on three.js directly, not a vendored teardown kit.** No teardown kit exists in
   this repo and none was named by version, so the page uses the three.js already pinned in the app
   (MIT, credited in `THIRD_PARTY.md`), which keeps the licence story and the dependency count
   unchanged.

Rules out: reopening scope, waiting on Satyam, or claiming a heavy tier result that does not exist.



## 2026-11-13 Licence split: Apache-2.0 compile layer, proprietary calibration engine

Decided: the repository root carries Apache-2.0. `ai_cad/twin/` carries its own licence file and
stays proprietary until the customer-interview gate at week 4 clears.

Why: the compile layer is commoditised (Onshape publishes sim models, Jointly exists), so
open-sourcing it buys adoption rather than giving away the moat. The calibration engine and the
revision-regression loop are the part a customer pays for, and that part is unproven until
customers have described the drift in their own words.

Rules out: publishing `ai_cad/twin/` under the root licence by accident. Anything distributed from
that directory must keep its own notice; `docs/THIRD_PARTY.md` lists both licences so the split is
visible instead of discovered.

## 2026-11-13 CLI first, web flow deferred past M7

Decided: Phase 1 ships a CLI (`robocad compile`, `joints propose`, `joints diff`, `diff`, `page`,
`film`). Upload, joint review UI, report viewer and page server arrive after M7.

Why: every Phase 1 acceptance gate in the plan is measurable on the command line, and a multi-mesh
review UI is new frontend work, not a reuse of the existing single-STL viewer. Building it first
would spend the thin Phase 1 budget on the surface instead of the checks.

Rules out: counting "the web app shows the report" as evidence for M4 or M6. Evidence is CLI
output and a generated file.

## 2026-11-13 MuJoCo is the only measured simulator claim

Decided: MuJoCo loads and replays every bundle, and its numbers are the ones reported. URDF gets
structural validation only. Gazebo, ROS 2 and Isaac Sim are documented, not claimed.

Why: none of the others is installed here, and an unvalidated export is worse than no export
because it looks like a promise. MuJoCo also reads URDF natively, verified on this machine, so the
URDF-versus-MJCF pose check needs no extra parser.

Rules out: "works in Gazebo" and "imports into Isaac" anywhere in README, docs or a report until
someone installs it and pastes the load output.

## 2026-11-13 Labs toggle shape: `ROBOCAD_LABS`, default off

Decided: one environment flag, `ROBOCAD_LABS` (`0` default), read by the backend and the frontend.
Frozen features (aero, thermal, electronics, morphology search, gait, brain training, HERMES,
marketplace, Isaac JSON) mount only when it is `1`.

Why: the pivot is only real if the old product stops competing for attention. A flag keeps the code
alive without keeping it on the critical path, and makes "is this in scope" a one-line answer.

Rules out: deleting the multi-domain work (it stays, frozen) and adding features to it. New work in
a frozen area needs a written reason in this file.

## 2026-11-13 Collision backend: CoACD first, vhacdx second, primitives third

Decided: install-test CoACD on Python 3.14 this week. Take it if it installs; otherwise vhacdx;
otherwise fit primitive shapes per link.

Why: sw2robot uses CoACD in practice, so it is the path with the most real-world evidence behind
it. The install test is cheap now and expensive at M3.

Status: **resolved 2026-11-13, CoACD adopted.** `python -m pip install coacd` resolves to
`coacd-1.0.14-cp39-abi3-win_amd64.whl`, an abi3 wheel, so Python 3.14 is covered without a source
build. Import plus a real decomposition on a two-box L-shape:

```
coacd ok
[CoACD] [info] # Convex Hulls: 2
hulls 2
vertices_in 16 hull_verts [40, 68]
```

vhacdx is not installed and no longer needed. Primitive fitting stays as the fallback for links
where decomposition is slower than it is worth, and the choice is recorded per link in the report.
