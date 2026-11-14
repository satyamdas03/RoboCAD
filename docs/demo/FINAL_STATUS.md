# Final status, demo sprint

Owner of this file: build session (Lane A, `robocad-61`), with the show-path rows contributed by the
monitor session (Lane B) and every one of them re-derived before it was written here. Updated
2026-11-14, 11:00. Every claim carries a tag:
`verified-ran`, `verified-read`, `claimed`. Deadline: hard freeze Sat 14 Nov 2026, 13:15 Sydney.

## Open this first, in this order

1. `docs/demo/page/index.html` — open it directly from disk. No server, no network. Living page.
2. `docs/demo/film/so101_demo.mp4` — 24 s, recorded from that same page.
3. `docs/demo/twin/identification.json` then the page's "Twin method" panel — the identification
   rungs and exactly which one is blocked.
4. `docs/demo/README.md` — the 3 minute walkthrough and the real-versus-synthetic table.
5. `docs/twin/so101/bundle/report.json` and `docs/twin/so101/revision_f030/diff.md`, then
   `docs/twin/so101/CONVENTIONS.md` — the checks, the revision's before/after, and the five zero-pose
   offsets without which the joint origins appear to disagree by centimetres.

## What the page shows today

| Element | Source | State |
|---|---|---|
| 3D view | **the compiled bundle's own 259 visual meshes** | `verified-ran`, offline, 56 fps, 128k triangles |
| Masses: solid 1.332 kg, print model 0.902 kg, published 0.632 kg | compiled bundle `comparison.json` | `verified-ran`, tagged `demo-bundle-v1` |
| Seven checks: 5 pass, `self_collision` fail, 1 skipped | compiled bundle `report.json` | `verified-ran` |
| Required torque per joint | inverse dynamics, both models | `verified-ran` |
| Kinematics vs official | sense-searched datum fit | `verified-ran` |
| Twin method rungs | `identification.json` | `verified-ran` |
| Provenance line | states every split above on screen | `verified-ran` |

## Verified numbers

- Page loads from `file://` with the browser context offline: **zero non-file requests**. `verified-ran`
- Page geometry matches MuJoCo to **0.000 to 0.001 mm** on three mesh geoms. `verified-ran`
- Render 54 to 56 fps headless at the shipped page's 128,073 triangles over 600 frames, zero network
  requests, zero console errors. `verified-ran`
- Compiled bundle, frozen tag `demo-bundle-v1` at `f202c12`: 7 bodies, 6 hinge joints, 692 mesh files
  (433 collision hulls + 259 visual meshes), **0.9017 kg** printed / **1.3320 kg** solid bound. Checks:
  `meshes_load` pass,
  `inertia_valid` pass, `pose_equivalence` pass at 0.000 m over 100 configurations, `mujoco_load`
  pass, `self_collision` **fail**, `limits_and_effort` **pass** (0.652 N·m on `joint_2`, 22% of the
  servo's 2.942 N·m stall, contacts disabled), `free_base_stand` skipped. `verified-read` from
  `report.json` at the tag, and re-derived from the packaged zip's own `report.js` by
  `scripts/verify_demo_zip.py` `verified-ran`
- Default test tier at the tag, measured in a worktree checked out at `demo-bundle-v1`:
  **745 passed, 300 deselected, 3 warnings, 391.13 s, exit 0**, collected 1045. `verified-ran`. The
  three warnings are pre-existing `InsecureKeyLengthWarning`s. Recorded in `docs/BASELINE.md` with no
  caveat, because the tree was the tag and not the tag plus edits.
- Joint axes agree with the published model within **2.14 degrees** (rms 1.05) after a
  sense-searched datum fit over all 64 sense combinations. `verified-ran`
- Joint **origins** do not agree. Bounded metric, anchor to the other joint's axis: **94.2, 110.3,
  54.0, 54.7, 27.7, 54.5 mm**. `verified-ran`. The infinite-line minimum is NOT used: five of six
  joints attain it more than 250 mm along the axis and one at 9.64 m, which is meaningless for a
  robot. No clustering claim is made; the offsets sit between 28 and 110 mm.
- **P0-a verdict, reproduced independently: same robot, missing conventions.** With five constant
  zero-pose offsets applied to the compiled model by joint name, a base translation of (38.74, 6.64,
  -2.86) mm and no rotation, the residual at the five joint origins over 100 poses is **median 2.50
  mm, p90 5.95, max 11.25**, and the fitted offsets are -88.17, +90.29, -90.31, -0.15, 0.00 degrees.
  Both a seeded and a zero start converge to the same vector, so it is not a local basin. `verified-ran`
  Data: `docs/demo/twin/p0a_confirmation.json`.
- Superseded by that verdict, and kept here so the record is honest: the earlier median 168 mm at the
  same joint vector compared two models whose zero poses and base frames differ; the 38 mm after a
  tip-centroid fit was dominated by the jaw frame, which disagrees by 5.74 mm at rest, so five-anchor
  fitting is the correct residual; and the 27.6 to 94.5 mm line-distance family was partly a
  degenerate metric, five of six minima being attained more than 250 mm along the axis.
- What P0-a does **not** clear: collision geometry, mass, inertia, contact behaviour. The
  `self_collision` fail and the 13 oversized hulls live in P0-b and are untouched by this verdict.
- Self-collision: hulls overlap **7.9 mm** at rest. The B-rep solids touch and share **0.52 mm³**
  across 47 of 47 shape pairs, which is contact-scale, not a statement that the parts fit together,
  against a 32.27 cm³ wrist and 20.69 cm³ jaw. Hull overlap is real for the simulator; the solids
  do not interfere. `verified-read` from Lane A, corrected after their unit bug
- Identification rungs 0, 1, 2 and 4 recover (0.57, 1.6/0.86, latency exact, 0.12/0.56 percent).
  Rung 3 is blocked. `verified-ran`
- The freeze run, over every test the default selection collects: **752 passed, 300 deselected, 3
  warnings, 367.27 s, exit 0**, collected 752 of 1052, on the tree at `4af81f5`. This is the row that
  covers the seven artifact tests the earlier post-tag run missed. `verified-ran`, in
  `docs/BASELINE.md` under "The freeze commit".

## Cross-verification of Lane A's published bundle

Three targets were named before computing them, so the choice could not flatter the result.

1. **Hashes, quoted so that they mean the same thing on any machine.** Git blob ids at the tag:
   `model.mjcf` `1f18f38adf3e...`, `model.urdf` `760c668dff45...`; sha256 of the repository blobs
   (LF line endings, as `git show` emits them): `model.mjcf`
   `5aa5912b34f79cdfda2fb4d358716c0bf6cfc0e393d2b6b7ffa8c8de7810c2d7`, `model.urdf`
   `50c8cbc66e06961f8bf41df31e3d942d2156262594f2dcb20fb6b39b702030fd`. `verified-ran`. The earlier
   values here (`c427c3e1...`, `86ce5502...`) are withdrawn: they were sha256 of a working-tree copy
   of an earlier bundle, and a working-tree hash depends on `core.autocrlf` — this machine checks
   those files out with CRLF, the repository stores LF, so the same commit produces different bytes
   in different checkouts. That is the same defect as a path printing its producer's separator, and
   it is why the byte-identity argument the earlier text rested on no longer holds: the bundle was
   deliberately regenerated at `f202c12` to add actuators and visual meshes, so its digest moved for
   a stated reason, not an unexplained one.
2. **Pose equivalence**, re-derived on the frozen bundle rather than read: both models loaded in
   MuJoCo, bodies keyed by name, world position and rotation compared at the zero pose and at 20
   random configurations inside the joint limits. 147 body comparisons, worst error
   **0.000e+00** everywhere on both position and rotation. `verified-ran`
3. **Mass consistency**, re-derived from `bundle.json` rather than read: the seven `solid_mass_kg`
   values sum to 1.3320123928506593 kg, equal to `total_solid_mass_kg` to the last bit, and the seven
   `mass_kg` values sum to 0.9016588355893798 kg, equal to `total_mass_kg`. Implied density is
   **1240.0 kg/m³ exactly** on the two all-printed bodies (`upper_arm_so101`, `moving_jaw_so101`) and
   **1476.6 to 2048.9** on the others, which is the datasheet-density path doing its job: a body that
   carries bought-in servos is heavier than PLA alone would explain. The earlier version of this line
   claimed "exactly 1240.0" and a 1.04134 kg total for every body; both were true of the bundle before
   the print model existed and neither is true of the frozen one. `verified-ran`

**The revision diff that shipped.** The `revision.json` published earlier
with the bundle compared `robot.joints.proposed.yaml` against `so101_demo` and reported **19 links
removed, 7 changed, 0 added**, an artefact of two different link identity schemes rather than a
revision. It was excluded from the page and flagged. `ai_cad/compiler/revision.py` now records each
document's link scheme and returns `comparable=False` with a reason instead of a table, and the two
files were removed from the published bundle. A diff that reports deletions that never happened is
worse than a missing panel.

That gap is closed by a real one. Same pipeline, same STEP file, one input changed: the print model's
infill fraction, 0.20 to 0.30, keyed only on the link names `robot.joints.yaml` declares.

| | before (f = 0.20) | after (f = 0.30) | change |
|---|---|---|---|
| printed mass | 0.9017 kg | 0.9555 kg | +0.0538 kg, **+6.0%** |
| solid bound | 1.3320 kg | 1.3320 kg | unchanged, the solid is not a print assumption |
| effort demand | 0.652 N·m on `joint_2` | 0.687 N·m on `joint_2` | 22% to 23% of the 2.942 N·m stall |

Sanity, all re-derived by `python scripts/diff_revision_f030.py` rather than asserted: **0 links
added, 0 links removed**, all **7** printed links heavier (biggest relative movers `upper_arm_so101`
+16.2% and `moving_jaw_so101` +8.3%), and the actuator and joint blocks **byte-identical** between
the two bundles, which is what "servos unchanged" means when a bundle states its hardware in those
blocks. `verified-ran`. Artifacts: `docs/twin/so101/revision_f030/diff.json` and `diff.md`, with the
`f = 0.30` bundle committed beside them (2.5 MB, hulls only) so the diff can be re-derived by someone
who does not trust this machine.

## Identification: the rung reached and why it stopped

Rung 3, 62 Hz with sensor noise and 4096 count quantisation, does not recover. The reason is
arithmetic, not tuning: one count of position error is 1.53 mrad, the published servo is about
998 N m per rad, so a single count is roughly **1.53 N m of actuator torque noise** against a
friction signal of about **0.15 N m**. A signal to noise ratio of 0.1 is not a fitting problem. A
partner's bench log with a real torque or current channel escapes this; a 62 Hz position log does not.

Rung 0 failed at first and the cause was mine: zeroing the other joints' damping removed what keeps
a very stiff position servo stable, the simulation diverged, and the divergence was being fitted as
friction. That is the kind of bug this harness exists to expose, and it is written down because the
same mistake will be made again.

## Assumptions Satyam must confirm

1. **The print model's two inputs: wall 1.2 mm, infill 0.20.** Printed mass is `0.9017 kg` at those
   settings, against a `1.3320 kg` solid bound on the same geometry with no print model at all. Both
   are the model's stated
   assumptions, not measurements, and the bundle prints both figures side by side so the range is
   visible: `print_model` reads `"1.20 mm wall over 20% infill"` in `bundle.json`. The infill value
   is live code, not prose — the `f = 0.30` revision in this report was produced by passing it to the
   compiler. `verified-read` and `verified-ran`. **What Satyam must confirm:** that 1.2 mm and 0.20
   describe how the partner would print this, because every mass here moves with them.
2. **Servo mass, 55 g plus or minus 1 g**, sourced to the Feetech STS3215 product specification
   document (feetech.cn); the code carries the document name, not a URL. It enters the
   comparison only, as the figure that reconciles our mass against the published mass. It does **not**
   enter the bundle's mass properties, which is why `actuator_mass_kg` is null; a reader who assumes
   55 g is already inside our body masses would overstate every body. `verified-read` from Lane A.
   **What Satyam must confirm:** that the STS3215 variant cited is the one the partner ships, because
   a different servo changes the comparison against the published model and not the compiled masses.
3. **Publishing `docs/twin/so101/`.** Satyam authorised this in the sprint directive, verbatim:
   "Publish docs/twin/so101/: YES. Add docs/twin/so101/NOTICE.md crediting the SO-101 project, its
   Apache-2.0 licence, the pinned commit, and a list of what we changed." **Done:** the directory is
   committed, `NOTICE.md` is written, and the tag `demo-bundle-v1` exists at `f202c12`. The earlier
   licence caution on derived CAD is resolved for this directory by that instruction. `verified-ran`
   (`git tag --list`, `git ls-files docs/twin/so101 | wc -l`).
4. **M2 joint skeleton review:** reviewed by the session that did not write it, against four written
   criteria, **PASS 4/4**, with the official URDF's sha256 re-checked against the digest the checker
   pins before the check ran. The skeleton and the review record are committed
   (`docs/twin/so101/robot.joints.yaml`, `docs/twin/so101/JOINT_REVIEW.md`), and the tracker row is
   `[x]`. `verified-ran`.
5. **Actuator gains are assumptions.** `kp` = 20 and `kv` = 1 are labelled as assumptions in the
   bundle; the real servo closes its own loop and publishes no stiffness. The live hold in
   `docs/twin/so101/live_hold.md` fails at those gains and the failure is kept. **What Satyam must
   confirm:** whether the partner can supply measured gains, which is Phase 2 calibration.

## What is deliberately not shipped

- **Collision-hull rendering on the page.** The bundle carries 692 mesh files: 433 collision hulls
  and 259 visual meshes. The shipped page renders the visual meshes, decimated to a 500-triangle
  budget by `teardown_export/bake.py`, which prints `unique meshes 259 triangles 128073 across 259
  mesh geoms`; the bundle's source geometry is 620,093 triangles from `report.json`. The hull bake
  exists at `docs/demo/page_compiled/` (433 hulls, 0.8 MB) and is not shipped, because a printed
  part's hulls render as a block. `verified-read` for the file inventory, `verified-ran` for the
  triangle sum.
- **Official-model toggle**, cut by the sprint's own cut order.
- **Heavy test tier**, stopped by instruction; one frozen Labs test exceeds 900 s.

## Next three steps after the demo

1. Attribute the ~54 mm perpendicular joint-origin offset. The hypothesis on the table is that the
   axis point is taken on a mating cylindrical face rather than at the bore centre, which would make
   the offset look like a radius. Lane A is testing it against the six bore radii.
2. Measure what the page's 500-triangle-per-mesh decimation costs in millimetres against the bundle
   meshes. The bundle's own budget was held to 1.20 mm worst vertex displacement under a stated
   measurement; the page goes coarser without one, and a partner who compares the page to the CAD
   will be the one who notices.
3. Widen the identification to a real torque or current channel so a partner's bench log can be
   identified at 62 Hz, which is the only way the Twin's central claim becomes checkable outside
   this machine.

## Film and page

The packaged film is the 10:52 re-record, taken after the page settled and after the revision panel
was wired. `verified-ran`: the film inside the zip is byte-identical to `docs/demo/film/so101_demo.mp4`
(2,199,551 bytes, sha256 `31ac62e76d43bf35...`). The earlier `so101_demo_new.mp4` (10:40) is not
shipped. The earlier note here about a two-word provenance difference is withdrawn: the shipped
`twin.js` contains no "being regenerated" string, so there was nothing for the film to differ on.

## Security review findings, and where each stands

Five findings were raised; three of them changed what an artifact says rather than what an attacker
can do. All three have since been fixed in source, and each is listed with the code path that would
have to regress and the artifact that would show it. Verified by reading the source and the
artifacts, not by taking the report's word.

1. **Assumed-density disclosure was suppressed in the comparison.** `bundle.json` bodies carry
   `rests_on_an_assumed_density`; `compare.py` read only `assumed_density`, so every body read
   False. **Fixed** at `ai_cad/compiler/compare.py:568`, which reads the short spelling and falls
   back to the bundle's long one. Evidence in the frozen artifact: all seven comparison bodies now
   read True, which is the correct answer and the one the old code could not produce.
   `verified-ran`
2. **`limits_and_effort` passed on provenance, not measurement.** It ended with
   `status = "pass" if source else "warn"`. **Fixed** in `ai_cad/compiler/bundle_checks.py:616`: a
   joint whose inverse-dynamics demand exceeds its `forcerange` now **fails** the check; actuators
   that state no force limit **warn**, because a command range is not an effort limit; and `pass`
   requires travel limits, stated force limits, a source, and every sampled pose under the ceiling.
   The bundle's pass reads "largest demand ... 0.652 N*m on joint_2, 22% of its 2.942 N*m limit,
   measured with contacts disabled". `verified-ran`
3. **The limits provenance stamped a pinned revision it never verified.** `scripts/demo_so101_twin.py`
   wrote `a758567...` unconditionally. **Fixed**: the revision is claimed only for the bytes whose
   sha256 equals `PINNED_LIMITS_SHA256`, and any other file gets a provenance string that says it is
   not that file and names the digest it does have. `verified-read`

The withdrawal that stands: the earlier sentence "the compiled robot moves wrongly by seven
centimetres" is withdrawn. It described the same-q difference without first removing the zero-pose
and base-frame difference, which is exactly what `CONVENTIONS.md` now prevents.

## Freeze state, Sat 14 Nov

- Package: `docs/demo/so101_demo.zip`, 3,892,730 bytes, 20 files, sha256
  `fff730639bc40ca7e4f7efc924a092fed0bebae4f01ec659291da1ea8920c26f`, built by
  `teardown_export/package_demo.py` from commit `430c77e` (the packager's statement; nothing in this
  repo can check a zip against a commit, so it is recorded as a claim), which copies the artefacts,
  zips them, extracts the zip into a fresh temporary directory and opens that copy from `file://` with
  the network off. The package test is the deliverable, not the folder.
- Frozen bundle tag: **`demo-bundle-v1` at `f202c12`**. Nothing inside `docs/twin/so101/bundle/`
  changed after the tag; the revision compile and the diff live in sibling directories.
- Independent verification of the package: `scripts/verify_demo_zip.py` names three numbers before
  computing any of them (printed mass 0.901658836 kg; revision 0.901658836 to 0.955453030 kg; seven
  check rows at 5 pass / 1 fail / 1 skipped), extracts the zip to a fresh directory, and re-derives
  each from the zip's own baked JSON. It also asserts the page opens from `file://` with zero page
  errors and zero non-file requests, that the revision panel renders its seven rows, and that the
  rendered panel prints no Windows path separator. All four pass on this package, exit 0:
  **VERIFIED**. Result in `docs/demo/verify.json`. `verified-ran`. The separator check earned its
  place: the 10:52 package passed the other three and failed that one, because `diff.json` had been
  written with `str(path)`; the artifact was fixed at `cdb1662` and the page rebaked, and the check
  is what forced the rebake rather than a reader noticing a `\` in a document.
- Live viewer: `python -m robocad.demo so101 --bundle docs/twin/so101/bundle --mode replay` replays
  the bundle's trajectory. **Hold fails and the failure ships as documentation, not as a caveat**:
  573.26 mrad steady error, all six joints at the 2.942 N·m force limit, because `kp` = 20 asks for
  10 N·m to take a 0.5 rad step. Per-joint numbers in `docs/twin/so101/live_hold.md`. `verified-ran`
- Page rendered from the bundle's own visual meshes at 128,073 triangles, 56 fps, zero network
  requests. The triangle count is `verified-ran` two ways: decoded here out of `page/meshes.js`, where
  each mesh's packed index buffer sums to exactly 128,073 triangles across 259 meshes, and the
  bundle's own 620,093 source triangles from `report.json` `verified-read`.
- Comparison panel states solid upper bound, print model, published figure, the gap between the last
  two, and the conventions note with the 1.69 mm frame-free link-length agreement.
- Torque panel reads its limit from the bundle's actuators, 2.94 N·m, and is not saturated on this
  trajectory: peak 1.26 N·m official against 0.63 N·m compiled.
- Not pushed. `master` is 67 commits ahead of `origin/master` and stays local until Satyam says
  otherwise: the sprint order authorised publishing `docs/twin/so101/` but said nothing about pushing
  the branch, and a push is the one action here that cannot be taken back. The freeze commit is
  `be74ebd`; `git push origin master` is his call.
- M2 review recorded as PASS by the lane that did not write it, 4 of 4 criteria, with the official
  URDF's sha256 verified against the pinned digest before the check ran.

## Five things Satyam has to confirm

1. **Wall thickness 1.2 mm** — the print model's first input, and every printed mass scales with it.
2. **Infill 0.20** — the second input; today's revision exists to show what moving it to 0.30 costs.
3. **The 55 g servo mass and its source** (Feetech STS3215 specification) — it drives the comparison
   against the published model and not the compiled masses.
4. **Actuator `kp` = 20 / `kv` = 1** — labelled assumptions, and the reason the live hold fails
   honestly rather than passing quietly.
5. **Publishing `docs/twin/so101/`** — done under the sprint directive; confirming it keeps the
   licence statement and the pinned commit on the page, film and report.
