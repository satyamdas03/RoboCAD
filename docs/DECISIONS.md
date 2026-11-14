# Decisions

Newest first. One entry per decision, with the date, what was decided, why, and what it rules out.
A decision without a reason is a preference; it does not belong here.

## 2026-11-14 The voice keeps calling RoboCAD as a subprocess, and eats 0.9 s of startup per call

Decided: Hi-EV's `src/ev/tools/robocad_tool.py` keeps spawning `python -m robocad twin revise`
instead of calling `twin_cli.main` in-process, even though the second is ~0.27 s against ~1.22 s. The
margin is documented in their runbook and module docstring rather than removed.

Why: the file's whole design rests on the repository boundary — argv lists, one killable process per
call with a timeout, and no RoboCAD import that can take the voice down. A bundle that hangs inside
`twin_cli.main` cannot be timed out in-process, because Python cannot safely kill a thread. The
measured split made the choice explicit rather than accidental: 0.75–0.77 s interpreter start on this
machine (`python -S -c pass` is 0.07 s, so a site-packages `.pth` owns it), 0.003 s to import
`robocad.twin_cli`, 0.27 s of work.

Rules out: blaming RoboCAD imports for the slow phrase. There is nothing there to shave, and the
release result does not depend on it. It also rules out a per-phrase in-process shortcut as a demo
optimisation: if the boundary is ever traded, it needs a worker process with its own timeout, not a
library call on the daemon thread.

## 2026-11-14 The HUD half of the release needs `demo-v1.2`; `demo-v1.1` stays where it is

Decided: `demo-v1.1` in Hi-EV stays on `2b46fa0`, even though it predates the sender fix at
`870d48f`. The pair's HUD half gets a later tag, `demo-v1.2`, on the Hi-EV commit that holds the
release pass; RoboCAD follows with `demo-v1.2` at whatever commit records that pass as evidence.

Why: the tag was cut before the visual gate for the third time this sprint. The gate that caught it
is new — `tests/test_page_sandboxed_delivery.py`, which embeds the page the way the HUD does and
shows that an infill message addressed to the frame's origin is dropped by the browser while a
wildcard target moves the card. Until that test existed, every journey run passed with the message
dead, which is why a tag cut from journey evidence could not have caught this.

Rules out: deleting and re-creating `demo-v1.1`. It is pushed, and the no-move rule is what makes
`verify.json` worth reading. It also rules out trusting a chat-only journey result as a visual gate:
`scripts/release_journey.py` now reads the embedded card after the infill sentence and fails when the
card disagrees with the sentence.

## 2026-11-14 `demo-v1.1` is the sprint's release tag, and it is not the package tag

Decided: the sprint is tagged `demo-v1.1` in both repos — RoboCAD at `b941e5e` (the commit that holds
`FINAL_STATUS.md`, so the tag carries its own gate table), Hi-EV at `2b46fa0` (the fixture export).
The artifact tag stays `demo-bundle-v1.7` on RoboCAD `656d244`.

Why two tags: they answer different questions. `demo-bundle-v1.7` answers "which bytes are the
package", and `scripts/verify_demo_zip.py --tag` proves that answer byte for byte. `demo-v1.1` answers
"which state of the two repositories is the thing we handed over", and it has to name commits in both
repos, which a bundle tag cannot. Pointing `demo-v1.1` at `656d244` instead would have made the
release tag precede its own evidence: `verify.json` lands at `83ecc0f` and this status file at
`b941e5e`, both after the package commit.

Rules out: treating `demo-v1.1` as a rebuild signal. Nothing is baked from it, and a reader who needs
the bytes follows `demo-bundle-v1.7`, which is the only tag `verify_demo_zip.py` accepts.

## 2026-11-13 A check called `limits_and_effort` needs an effort limit to pass

Decided: `bundle_checks.check_limits_and_effort` passes only when every joint carries a travel limit,
every actuator states a force range (`actuator_forcelimited`), and the limits carry a provenance
string. It reports warn when the file declares no actuators, when an actuator states only a
`ctrlrange`, and when no source is recorded.

Why: the status was `pass if source else warn`, so pass meant "a provenance string existed". The
published SO-101 bundle has no `<actuator>` element at all — `nu` is 0 — and the check passed, which
made "limits_and_effort  pass" a statement nobody had checked. `ctrlrange` is worse than missing: for
a position servo it is the command in radians, and reading it as the effort limit turns a model that
never states a torque green. A peer's review caught both. The published bundle now reads warn, 4 of 7
checks passing, because the compiler writes no actuator section and therefore cannot claim to have
checked effort.

Rules out: counting a check as evidence of something it read but never compared, and treating a
command range as a specification.

## 2026-11-13 The collision hull is bounded before it is built, not after

Decided: `collision_mesh` reduces the tessellated point cloud to `MAX_HULL_POINTS` (1,000,000) with
`bound_point_cloud` before `convex_hull` runs, and records the grid it snapped to in the part's
warnings.

Why: `COACD_TRIANGLE_LIMIT` was documented as the cap that keeps a pathological part from reaching a
decomposition whose cost is unbounded, but the hull is built first, from the whole cloud, and the
triangle cap is consulted afterwards. So the cap bounded the second operation and not the first, and
the first is the one that holds the whole tessellation in memory. A review flagged the ordering.

Rules out: citing a downstream cap as a bound on an upstream operation. The bound now sits where the
work happens, and a part that hits it says so in the bundle.

## 2026-11-13 Correction: the published bundle does ship derived meshes

Commit `541e712` says "no upstream geometry, mesh or binary is redistributed". That sentence was
true when it was written and false when the commit landed: the same commit carries 433 convex
collision hulls as OBJ files, 2.4 MB in `docs/twin/so101/bundle/meshes/`. Those are derived from the
SO-101 CAD, not copies of it, but they are geometry that travels.

What is true: the upstream STEP file is not in this repository, no upstream file is modified, the
hulls are generated by `ai_cad/compiler/collision.py`, and `docs/twin/so101/NOTICE.md` sits beside
them carrying the attribution, the pinned revision and the change list the Apache-2.0 licence asks
for. `docs/THIRD_PARTY.md` now says all of that instead of the sentence that was wrong.

Rules out: describing a derived work by what was not copied. The question a licence asks is what
ships, not what was left behind.

## 2026-11-13 A revision diff refuses two link identity schemes instead of inventing removals

Decided: `ai_cad/compiler/revision.py` returns `comparable=False` with a reason, and no link rows,
when the two documents do not name their links the same way. `from_joints_yaml` and `from_bundle`
return a `LinkTable` that records its scheme — part family or body — and `diff_links` refuses a
mismatch. As a backstop for plain dictionaries, it also refuses when fewer than half of the smaller
side's link ids appear on both. The renderers print the refusal as text, never a table.

Why: the published SO-101 bundle carried a `revision.json` comparing `robot.joints.proposed.yaml`
(26 part families) with the compiled bundle (7 merged bodies). Seven names coincide — `base_so101`
is a family of four parts on one side and a body of 150 instances on the other — and by name the
diff reported nineteen links removed, none of which had gone anywhere. A peer caught it. Name-only
overlap is not enough to detect the mismatch: the overlap there was 7 of 7. The scheme is.

Rules out: putting a link-by-link table on a page unless both sides are the same kind of document,
and answering "what changed" by diffing a proposal against a compile. This bundle ships without a
revision diff and its NOTICE says why.

## 2026-11-13 B-rep measurement converts shapes to metres before placing them

Decided: `bundle_checks._placed_solids` scales each distinct part shape from millimetres to metres
once per call, then applies the instance transform (metres). Distances come out in metres and
boolean-common volumes in cubic metres, which is what the field names `distance_m` and
`intersection_m3` claim.

Why: the STEP reader keeps OCP shapes in millimetres and converts only the reported numbers and the
instance translations (`ai_cad/importers/step_import.py`). The previous code applied a metre
translation to a millimetre shape, so every part was placed a thousand times too close to its own
origin — the assembly collapsed onto itself. The failure did not look like a unit error: it looked
like a plausible interference. The wrist/jaw pair read 0.0 m distance and 2200 mm3 shared, about
10.6% of the jaw, and that number was quoted to a peer as a real design interference. After the fix
the same pair reads 0.0 m distance and **0.52 mm3** shared over 47 of 47 shape pairs, against solids
of 32.27 cm3 and 20.69 cm3 — contact, not occupied space.

Rules out: quoting any B-rep distance or shared volume produced before this fix, and building test
fixtures from metre-sized shapes, which is what let the bug through the suite: a 10 mm cube built in
metres moves by the right amount under a metre transform and never exercises the conversion.

## 2026-11-13 The inverse-dynamics torque caveat hangs off the hull overlap, not the B-rep

Decided: when the self-collision check finds a non-adjacent overlap, the report always says that an
inverse-dynamics torque includes the contact forces MuJoCo applies to separate the hulls, and that
such a torque is not the actuator load. It no longer conditions that sentence on the CAD solids
really intersecting.

Why: MuJoCo collides the convex hulls. The overlap the check found is an overlap of those hulls, and
the solver pushes them apart whether or not the CAD solids do. Gating the caveat on a shared volume
switched it off for a hull overlap whose B-rep turned out to be a tangency, which is precisely the
case where a reader most needs the warning.

Rules out: reading a "no real interference" B-rep note as "inverse dynamics gives clean actuator
torques". The two sentences answer different questions.

## 2026-11-13 The frame rotation is fitted to axis directions, not to joint anchors

Decided: the rotation that carries our world frame onto theirs is fitted to the joint axis
directions, with a search over each joint's axis sense; the translation is the offset between the two
anchor centroids. Anchors do not vote on the rotation. When several sense combinations fit the
directions within 0.25° of each other, the anchors break that tie and the number of tied rotations is
printed.

Why: the previous entry fitted the rotation over anchors and reported 6.2°–12.4° on the same six
joints that read 1.05° RMS and 2.14° worst when the rotation was fitted to directions. Both numbers
come from the same two files. An anchor is a poor constraint: a revolute joint's origin is free to
sit anywhere on its axis line, and a difference in the pose each file was stored in moves every
anchor at once, so an anchor cloud constrains a rotation through two things that are not its axes and
charges both to the robot. Directions-only also has a weakness — on this arm several joints repeat a
direction, so a quarter turn and a half turn both fit within 1.05° and the tie is real (4
combinations within 0.25°). That is why the tie count is printed rather than the winner alone.

Rules out: quoting the anchor-fit axis angles as the robot's axis agreement, and presenting the
anchor residual as an axis error. The anchor residual is its own number, split along the joint's axis
and perpendicular to it, and only the perpendicular part is a statement about position.

## 2026-11-13 Joint-to-joint spacing is reported before any frame is fitted

Decided: the comparison prints the distance between consecutive joint origins before the frame
alignment, labelled as needing no frame. Measured on the pinned SO-101 file: ours 66.0 / 116.1 /
134.2 / 62.0 / 36.7 mm against theirs 64.8 / 116.0 / 135.0 / 63.7 / 36.2 mm, largest difference
1.7 mm.

Why: a rigid transform moves both ends of a segment by the same amount, so a spacing survives any
choice of datum. Every other joint number in that table depends on the fitted transform being right;
this one does not, which makes it the honest statement of link agreement and the first thing a reader
should be able to check. It also constrains the pose question: a large difference in stored pose would
change these spacings by tens of millimetres, and they agree to within 1.7, so the two files describe
much the same configuration. That leaves the 27.7–110.3 mm perpendicular origin offsets unexplained,
which is how the report states them — measured, not attributed.

Rules out: claiming link agreement and joint-origin agreement from the same fitted table, as if both
rested on the same evidence.

## 2026-11-13 Joint axes are compared after one fitted frame change, never across two datums

Decided: before any axis angle is computed, a single rigid transform (Kabsch, least squares) is
fitted over the joint anchors both files place, and our axes are carried into their world frame by
it. The transform and its residuals — RMS and worst anchor distance, worst axis angle — are printed
with the table. Fewer than three shared anchors means no fit, and the report says the angles below
are read across two independent datums.

Why: a CAD assembly and a published URDF each pick their own origin and world axes. The first raw
comparison of the pinned SO-101 file reported about 90° on five of six joints — one rotation of the
CAD world explains all of them, so the table was measuring the datum, not the robot. After the fit
the same six joints read 6.2°–12.4° with 76 mm RMS anchor residual, which is a difference worth
arguing about and the raw table was not.

Rules out: quoting axis agreement or disagreement from a comparison that has not stated which frame
each side was read in, and presenting the fitted transform as a correction of either model. It is a
change of frame; the residual is the finding.

Superseded above, same day: the rotation is now fitted to axis directions rather than to anchors.
The 6.2°–12.4° this entry records was an artefact of fitting a rotation over anchors; the same six
joints read 1.05° RMS under a directions fit. The rule that survives — one fitted frame, printed with
its residuals — is unchanged.

## 2026-11-13 Printed-only mass counts links, not name-less parts

Decided: the "printed only" mass applies PLA at 100% fill to parts whose CAD names classify them as
links. Parts with generic names are reported as a separate `unclassified_volume_m3` and never folded
into the printed figure.

Why: on the pinned SO-101 file the servos are named `SOLID`, `ZK_122`, `XG-ZIJI_16` and `SG-ZIJI_15`,
so the name classifier cannot place them. Folding that volume into "printed" would count bought
actuators as printed plastic and inflate the one column that exists to isolate printed plastic. 64 of
83 parts classify as links, 13 as unclassified, 5 as fasteners, 1 as an actuator. The compile carries
no actuator mass at all (`actuator_mass_kg: null`): that field is for a weighed servo, and the compile
does not read documentation. The comparison beside it does add one from a catalogue — the Feetech
STS3215 specification, 55 +/- 1 g — states the figure and the source next to it, and leaves the
bundle's own masses untouched.

Rules out: presenting the printed-only column as a measurement of printed mass. It is printed
plastic at an assumed density, at 100% fill, over the parts the names could place.

## 2026-11-13 Collision hulls are capped at 96 vertices by grid snapping, not by decimation

Decided: a convex hull with more than **96 vertices** is rebuilt from its own points snapped to a
grid, doubling the grid until it fits, and the grid size travels with the hull as a stated error
bound. The first run without this cap wrote a **169 MB** bundle with one 15.8 MB OBJ.

Why: the tessellator hands back a dense point cloud, so `convex_hull` of it is a hull as detailed as
the tessellation — 503,054 vertices and 1,006,104 faces for a 20 mm sphere. MuJoCo will load that and
then grind against it on every contact query. Decimation was tried first and does not work here:
`simplify_quadric_decimation(face_count=192)` returned **31,840 faces**, and `percent=0.001` returned
**1,005,096**. Both keep the mesh as detailed as the input because the input is already a hull with
no interior left to collapse. Snapping to a grid and re-hulling removes near-duplicate points
instead, which is what a collision hull actually needs. Each vertex of the reduced hull is within
half the grid cell of the true hull surface, and that number is written into the part's warning.

Measured: the same SO-101 assembly now writes **433 hulls in 2.4 MB**, down from 169 MB, with no
change to the reported fill ratios.

Rules out: shipping a bundle whose collision meshes are larger than the model they describe, and any
reduction that does not state how far the reduced shape sits from the true one.

## 2026-11-13 Forward-kinematics agreement: 1e-6 m, not the plan's 1e-5 m

Decided: the URDF-versus-MJCF pose check fails above **1e-6 m**, measured at rest and over 100 random
configurations drawn from a seeded generator, with bodies matched by name.

Why: the plan set 1e-5 m on the assumption that the writers round coordinates at 1e-6, so the
rounding error alone could reach roughly 7e-6 m over a 14-joint chain and a tighter tolerance would
have measured the formatter rather than the kinematics. The writers here print nine decimals, so a
coordinate's error is at most 5e-10 m. The tolerance can therefore sit at 1e-6 m and mean what it
says. If a future run fails, the failure is kinematics, not formatting.

Rules out: widening the tolerance to make a run go green. A failure at 1e-6 is a real disagreement
between the two files and has to be traced to the joint that produced it.

## 2026-11-13 Collision: convex-hull shortcut before CoACD, with the reason recorded per part

Decided: a part within 1.25x of its own convex hull is given that hull and no decomposition; a part
above 6,000 triangles that is not that close is also given its hull, and the part's record says so.
Everything else goes to CoACD with a pinned seed.

Why: CoACD has no timeout. It is a blocking C call whose cost is unbounded in the triangle count, and
it was measured on this robot at **543 s for one part** — the 19,440-triangle PCB `part_014`, which
covers 1.03x its own volume with a single hull, so the 543 s bought nothing. Thirty-five of the 83
parts carry 6,000+ triangles; at defaults that is hours, against a 30-minute sprint cap.

Measured on the pinned SO-101 file: 83 parts tessellate in 156.6 s, hull in 26.8 s. 20 parts are
within 1.25x of their hull, 28 need CoACD and every one of those is under 4,404 triangles, 35 exceed
the triangle cap and are recorded as hull-only.

Rules out: an unbounded decomposition pass, and any silent substitution of a hull for a
decomposition. Every part carries `method` and, when the hull was substituted, a warning naming the
triangle count and the concave features that are therefore not collided.

## 2026-11-13 Sprint decisions (demo deadline Sat 14 Nov 22:00 Sydney)

Satyam is unavailable until the deadline, and these were made so the sprint does not wait. Each is
one line of reasoning, as the sprint rule requires.

1. **Publish `docs/twin/so101/`.** Apache-2.0 permits derived files when attribution is kept and
   changes are marked. `docs/twin/so101/NOTICE.md` names the SO-101 project, the licence, the pinned
   commit `a758567`, and what we changed.

   **Status 2026-11-13: BLOCKED, not published.** The licence reasoning above is sound, but the
   authorisation is not mine to give. Satyam's standing instruction is to ask him before publishing
   anything derived from a third-party robot licence, and that instruction has not been withdrawn in
   this session. A peer session reports a verbatim authorisation typed to it ("Publish
   docs/twin/so101/: YES. Add docs/twin/so101/NOTICE.md ..."). That may well be exactly what
   happened, and this session cannot verify it: a quote relayed through another session is not the
   same evidence as hearing it. Nothing is committed, no NOTICE.md is written, no tag exists, and
   the demo ships without the committed derived bundle until Satyam confirms here. Writing the
   notice or committing the directory on the strength of the relay, or asking the peer to do it as
   a way around this session's block, would both be the same error.

   **Unblocked 2026-11-13, same session: Satyam answered "go ahead from me" in direct reply to the
   question above.** That is the authorisation, heard here rather than relayed, so it satisfies the
   standing instruction. What ships: `docs/twin/so101/` with a single notice, `NOTICE.md` — richer
   than the `NOTICE.txt` it replaces, carrying the upstream URL, the blob sha and size of the input
   STEP, and the bullet list of what RoboCAD changed, which is what makes it satisfy Apache-2.0
   section 4 rather than gesture at it. `NOTICE.txt` is deleted: two notices describing one derived
   work are two documents that drift, and the one a recipient forwards is the one they happened to
   open. So the pipeline reads the same file a reader does — `compile.read_notice()` prefers
   `NOTICE.md` and falls back to `NOTICE.txt`, and the text it takes is the text carried into the
   header of `robot.joints.yaml`. The peer's report is recorded above because it was real input, not
   because it was the authorisation.

   **The first published bundle was stale and had to be replaced.** Peer commit `cbf869d` added a
   bundle compiled at 09:23Z, before the unit fix, together with a notice quoting the corrected
   0.52 mm3 that the report beside it did not contain. A notice describing a different artifact
   from the one in its own directory is the failure this file exists to prevent. `docs/twin/so101/
   bundle/` was regenerated from the fixed code (report generated 11:48Z), its `robot.joints.yaml`
   re-emitted with the notice in its header because the scratch run directory had none, and the
   notice re-read against the new report before it was committed.
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



## 2026-11-13 Publishing the derived SO-101 bundle: authorised, and by whom

Decided: `docs/twin/so101/` is published in this repository with `NOTICE.md` crediting the SO-101
project, its Apache-2.0 licence, the pinned commit `a758567`, and the list of what RoboCAD changed.

Why: the compile layer is useless as a demo if its output cannot be inspected, and Apache-2.0 permits
derived work with attribution and a statement of changes, which `NOTICE.md` provides. The authorisation
is Satyam's, given directly and quoted here: "Publish docs/twin/so101/: YES. Add docs/twin/so101/NOTICE.md
crediting the SO-101 project, its Apache-2.0 licence, the pinned commit, and a list of what we changed."

Two facts worth keeping together, because they were argued about for an hour. The build session holds a
standing instruction to ask Satyam before publishing anything derived from third-party robot licences,
and it declined to act on a relayed quote, which is the correct reading of that instruction. The
authorisation above was given in the monitor session and acted on there, so the commit is made by the
session that received the instruction.

Rules out: publishing further derived robots on anyone's relayed word. The next one needs Satyam's own
message in the session that commits it.

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

## 2026-11-14 P0-a verdict: the compiled chain is the same robot, and the bundle omits three conventions

Decided: the compiled SO-101 chain reproduces the published URDF chain. The large pointwise
disagreement between `docs/twin/so101/bundle/model.mjcf` and `so101_new_calib.urdf` is a missing
convention, not a wrong robot. The bundle must state, and the compiler must emit:

1. **Per-joint zero offsets.** Applying five constant offsets makes the five upstream joints agree
   to 2.50 mm median (p90 5.95, max 11.25) over 500 joint positions. The fitted offsets, base first,
   are -88.17, +90.28, -90.31, -0.15, 0.00 degrees.
2. **A base-frame translation.** With a pure translation of (38.74, 6.63, -2.86) mm, |t| = 39.40 mm,
   and **no rotation at all**. Forcing a rotation makes the fit worse, not better.
3. **The jaw frame definition.** The compiled jaw origin is placed differently from the published
   jaw link origin: 5.74 mm apart at rest, and no gripper zero offset reduces that (the best scan
   still leaves 40.21 mm across pose). The jaw-to-wrist spacing itself matches, 36.73 mm against
   36.18 mm, so the arm is right and the jaw's own frame is the outlier.

Why this is the answer and not a fit artifact. Three measurements that use no registration at all:

- Consecutive joint-origin spacing is a link length, constant in q and invariant under any rigid
  transform. Official against compiled, mm: 64.775 / 66.007, 116.000 / 116.058, 135.000 / 134.219,
  63.725 / 62.038, 36.181 / 36.731. Worst disagreement 1.69 mm. Spread within each model is 0.000 um.
- Joint sense, from a frame-free triple product, agrees on all six joints: the compiled joint turns
  the way the published joint turns.
- The angle between consecutive joint axes agrees to 0.00, 0.50, 0.71, 0.00, 0.00 degrees.

A fit residual of 2.50 mm is inside those measurement errors. The link error alone is 1.7 mm, and
0.7 degrees of axis error over a 0.35 m reach is about 4 mm.

Rejected: the 10.303 degree base rotation from the ICP registration in the earlier note. That
registration fitted convex hulls of a mostly planar base to the published base meshes, so it could
not constrain rotation about the plane normal, and it reported 4.000 mm median / 9.927 mm rms on
its own data. Pinning the frame to that rotation gives a 13.61 mm fit residual; pinning it to
identity gives 2.50 mm. Identity is the better model of the frame, so the ICP rotation is a
registration bias, not a measurement of the bundle.

What this does **not** establish. The comparison is of joint origins to 2.50 mm. It says nothing
about collision geometry, mass, inertia or contact behaviour, which is P0-b's subject and where the
`self_collision` fail and the 13 oversized hulls live. It is also one robot from one CAD source;
generalisation to another third-party model is untested.

Consequence for the page and the report: the sentence "the compiled robot moves wrongly by roughly
seven centimetres" is not supportable and is withdrawn. The supportable statement is that the
compiled model reproduces the published kinematics within its own link-length and axis-direction
error once its zero pose and base translation are applied, and that the bundle does not currently
state either, so a naive comparison against the published model is meaningless.

## 2026-11-14 A link mass is a range, and the solid figure is never replaced

Decided: the compiler keeps reporting the kernel's solid-volume mass as the upper bound, and adds a
separate printed-part model beside it rather than substituting one for the other.

`ai_cad/compiler/print_model.py` computes `shell = min(V, A*w)` and
`effective = shell + f * max(0, V - shell)` with a 1.2 mm wall (three perimeters at a 0.4 mm nozzle)
and 20 percent infill. `link_properties` takes an optional `print_model`; with none supplied it
behaves exactly as before, which is why the change is additive and every existing mass test is
unchanged.

The `min(V, A*w)` cap is the part that is easy to get wrong. A part thinner than two wall
thicknesses has no interior; a shell model without the cap would report it heavier than its own
solid, which is impossible. It is tested directly.

Why keep both numbers. The solid figure cannot be wrong in the direction that matters: nothing
weighs more than its casting. The printed figure is a model, and a 20 percent infill on a part that
was printed solid is a 5x error in the other direction. A report that shows one number has to choose
which error to hide; showing both makes the range visible. The model also exposes `sensitivity()`,
which sweeps infill at 0.15, 0.20 and 0.30 so a reader can see how much of the answer is that
choice.

What the model does not claim, and what the link's warnings now say in words: each part's centre of
mass is held at its solid centre of mass, and its inertia tensor is scaled by the same factor as its
mass. Hollowing a part moves its centre of mass toward its shell, and a hollow part's inertia is not
a scalar multiple of its solid inertia. That approximation is stated in the report rather than left
inside the arithmetic.

Applies only to materials that are printed. `is_printed_material` covers PLA, PETG, ABS, nylon and
resin, and excludes aluminium, steel, brass and carbon fibre. Applying an infill model to a bought
aluminium bracket would understate it by several times, in the direction that makes a robot look
lighter and safer than it is.

Bought-in parts, delivered in the same change. The SO-101's six servos are modelled in the CAD as
homogenous blocks, so a density applied to their envelope made them weigh whatever that envelope
displaced. `materials.datasheet_density` now takes a datasheet mass and the part's CAD volume and
returns the density that reproduces the mass through the kernel, flagged `bought_in`; the print model
skips any part carrying that flag, because nobody printed a servo. `compile.actuator_densities`
builds those densities for every part the name classifier calls an actuator, and returns one sentence
per part it could not satisfy — a servo whose envelope cannot hold its own datasheet mass stays on the
assumed density, disclosed, rather than being handed an invented number.

What is still not evidence. Every figure here is a model over a CAD solid at an assumed density. The
servo mass is one datasheet number applied to all six, without a scale; the infill fraction is a
slicer default; the wall thickness is three perimeters at a nozzle size nobody stated for this robot.
The bundle now carries `solid_mass_kg` and `printed_mass_kg` side by side, and the comparison carries
both columns and says they move with the infill setting, so the range is visible rather than the
midpoint. Nothing in this entry makes a link mass a measurement, and only a scale does.

## v1.1, 2026-11-14: the hold fails on collision geometry, and replay ships instead

The question v1.1 asked was whether the live hold fails on gains or on limits. It fails on neither,
and the answer came out of a measurement rather than a reading of the numbers.

At the commanded pose the gravity torque is at most 0.254 N·m against a 2.942 N·m actuator limit, so
the servo is not short of torque to hold the arm up. The force the position servo asks for is
`kp * error` = 11.46 N·m on joint_1, which it cannot supply, so it saturates — and what is eating the
difference is the collision solver: 64 contacts active at the last step, `qfrc_constraint` up to
3.29 N·m on joint_1, above the actuator's own limit. This is the bundle's `self_collision` check
(reported **fail**, deepest overlap −7.939e−03 m) reproduced under a controller. The hold is not a
control question at all; it is a geometry question wearing one.

**Decision: replay only for the demo, hold retained as a diagnostic.** The alternative — raising gains
or torque until the arm appears to hold — would buy a shivering model that spends its whole torque
budget pushing its own hulls apart, in front of an audience. The honest fix is better collision
geometry (per-part groups, adjacent pairs disabled, tighter hulls), which is a compile-side change that
changes the bundle, and the demo sprint is frozen: `demo-bundle-v1` stays as it is and v1.1 adds none
of that.

**Decision: the diagnostic prints its own reason, and is tested.** Three different causes produce the
same steady error and have three different fixes, so the run now measures all three — `qfrc_bias` at
rest for the load, `kp * error` for the demand, `qfrc_constraint` and the live contact count for the
solver — and names the binding one. Two earlier versions of that measurement printed confident wrong
answers (the actuator forcerange on every joint; then exactly zero), which is worse than printing
nothing, so `tests/test_demo_static_load.py` pins that the reported load equals the real gravity term,
does not scale with the forcerange, does not pick up a limit force at a pose outside the joint range,
and goes to zero when gravity is off.

**One caveat on the residual.** None of this changes R1's other half: the dynamic torque comparison is
not comparable at the jaw tip, because the jaw frame is a separate known-unknown (5.74 mm off at rest,
and no constant gripper offset fixes a translation). The 11.25 mm figure is the anchor residual over
100 poses, not a jaw-tip residual, and a tip gate cannot be met with the offsets this bundle carries.

## v1.1, 2026-11-14: the CLI contract, and fail-closed provenance

**Decision: Hi-EV calls a subprocess, never an import.** The two repos stay separate, so the contract
is `python -m robocad twin …` and JSON on stdout. The cost is a process spawn per call; the benefit is
that a renamed field is a visible schema failure instead of an import that still resolves and silently
returns something else.

**Decision: every figure in a summary carries a provenance label, and an unanticipated one defaults to
`synthetic`.** The summary's job is to be readable by a consumer that will render it in a panel, and
the panel is where an assumption gets read as a measurement. So `provenance` covers every key of
`totals` — with a fallback entry for any figure no rule anticipates — and the `synthetic` flag is
computed from `kind` rather than written by hand, so a new figure cannot arrive unflagged and an entry
cannot disagree with its own label. Nine of thirty-one figures on this bundle come out `derived`, which
is the honest count: the two masses are a CAD volume at an assumed density.

**Decision: the progress stream has a fixed stage set and a JSON error line.** A GUI that scrapes text
breaks when the text changes; a GUI that waits on a stream hangs when the process dies. So the stages
are a closed list (`import|joints|properties|collision|bundle|checks|done`), an unknown stage is
refused rather than passed through, a failure is emitted through the same sink as the stages, and the
exit code distinguishes built (0) from built-and-red (3) from failed (2).

**Decision: `twin page` says which payloads it rebuilt and which it copied.** The torque comparison
needs the published model as well as the compiled one, so a bundle alone cannot regenerate it. Copying
it silently would put last week's number beside this week's bundle; refusing to build without it would
make the command useless offline. It copies, names what it copied, and checks that every local `src`
the page links exists before calling the page complete.

**Decision: the blade treats its own iframe as untrusted.** It is a local page on a local port, but it
is a separate document, so `src` is restricted to the `/robocad/page/` mount (no `..`, backslashes,
schemes or control characters), the frame is sandboxed `allow-scripts` without `allow-same-origin`,
and messages from it are accepted only from that frame's window at the expected origin in the expected
shape. All three checks are tested; any one alone would be enough to be fooled.

**Decision: the twin CLI rides on `feat/v1.1` rather than opening `feat/twin-cli`.** The order names
two branches, but Lane B is already pulling `feat/v1.1` for the blade handoff, and a second branch
from the same commit would mean two histories carrying the same files, with the risk that her
integration lands on one and my fixes on the other. One branch, linear, pushed, is the smaller risk
while two lanes share the tree. If Satyam wants the split for review, `feat/twin-cli` can be created
at `84fd2bf` afterwards without rewriting anything, because nothing has been rebased or forced.

**Decision: `twin unpack` is the only way a consumer obtains a shipped demo, and it fails closed.**
The v1.2 review found three artifacts claiming to be the demo: the zip, a working-tree page the blade
served, and a bundle directory. Two of them disagreed, one injected `<div>` apart. Rather than tell a
consumer which copy to trust, the CLI now produces the copy: it checks the archive's sha256 before
writing anything, refuses an archive whose member names would escape the target, refuses a populated
target instead of merging two packages into one directory, and reports the `bundle` path (the
directory holding the shipped `report.json`) so `ROBOCAD_BUNDLE_DIR` has one obvious value. A refused
unpack leaves the target untouched, because a half-populated directory reads as a partial success.

**Decision: torque in the summary is one number per pose, not a per-joint array, plus name-keyed
detail.** The page reads a peak per pose and the narration speaks a peak per pose. An array indexed
by joint position is only meaningful if both sides agree on joint order, and nothing in the bundle
makes that ordering checkable, so an array would invite a consumer to read the wrong joint. `torque`
therefore carries `static_poses[].compiled_nm`/`published_nm` as scalars (the peak over joints, stated
as such), with per-joint values, if present, keyed by joint name. Lane B proposed this from the
consumer side; the joint-index argument is the reason it is adopted.

**Decision: the cross-repo fixture is exported from the archive `verify.json` names, and its digest
travels beside it.** A test fixture written by hand tests what the reader wanted, not what the
package says. `scripts/export_summary_fixture.py` unpacks the shipped zip with its digest, runs the
same `build_summary` the CLI runs, and writes the JSON unmodified, plus a `sha256sum`-format sidecar
naming the archive. A consumer whose zip has been replaced is detectable rather than silently stale.
The fixture is not reshaped for a test: if a test needs a different shape, the reader is wrong.

**Decision: the page accepts exactly one message, from its own origin, naming one of six sections.**
The voice shell has to be able to say "show me the torque" and have the page answer. The narrow
contract is `{type: "robocad.section", section}` posted to the frame, valid only when `event.origin`
equals the page's own origin, and only for `overview|checks|comparison|torque|revision|twin`.
Anything else is ignored without a reply, because an error message is also a map of what to try
next. From `file://` (opaque origin) the listener accepts nothing; the page stays usable standalone
and `#torque` in the URL still scrolls, which is what a README link does.

**Decision: `synthetic_count` stays scoped to the provenance block and a second count names the
calibration block.** A security review read one zero and called it fail-open: the summary said "0 of
31" while 18 calibration figures beside it come from simulated logs. The zero is true and the
reading was fair, so `synthetic_figures` now reports `{provenance, calibration,
calibration_is_synthetic}` and the printed line says both. `synthetic_count` is kept unchanged
because a consumer already reads it; the schema stays `/1` because nothing was removed or
reinterpreted, only added beside it.

**Decision: build123d is pinned below 0.13, and the STEP importer names the import that failed.**
A clean venv resolved `build123d 0.13.0`, whose OCP no longer exposes `TDF_LabelSequence`; the
importer caught the `ImportError` and told the user to install the runtime dependencies, which they
had. Two changes: `build123d>=0.9.0,<0.13` in `requirements.txt` and `pyproject.toml` so a fresh
install lands on a kernel the importer supports, and the error message now carries the failing
import, because "moved between releases" and "never installed" look identical from the outside.

**Decision: `calibration.current_channel.params` lists Coulomb friction before viscous damping.**
The current channel resolves Coulomb (0.1466 recovered against 0.15 true); the viscous estimate
beside it is attenuated (0.0436 against 0.08) and reads like a failure when it leads. The order is
the only change: both parameters stay, both carry `true`, `recovered`, `lo`, `hi`, and the block
still says `synthetic: true`. Lane B proposed this from the consumer side and drops her
preference-scan workaround now that the producer orders it.

**Decision: nothing on this branch goes to LFS.** The largest file the branch touches is the demo
zip at 3.76 MB, and the 23 files it adds together are 0.3 MB. The 5 MB line is where a repository
starts paying for binaries it cannot review; nothing here is close, so the zip stays in git, the
tag stays checkable with `git show`, and no history was rewritten to move it.

**Decision: a package records a digest per file, and unpack checks it.** A zip digest answers "is
this the archive a caller verified?", not "does this archive hold the files the build produced?".
Twice in two rounds a file has been right in the tree and stale in the package, and both times the
only detector was a person diffing copies. `teardown_export/package_demo.py` now writes
`FILES.sha256` after its final write, taking the sidecar's name from `robocad.twin_cli` rather than
repeating it, and `twin unpack` recomputes each line and refuses on a mismatch, a recorded-but-missing
file, or a file no line records. The check is optional for a zip that has no sidecar, because a
consumer's package is theirs; when it is present it is binding.

**Decision: a figure on the page must exist in the summary, and a checker enforces it.** The page
and the voice are meant to read one generator, `build_summary`, but only the voice was held to it.
The torque panel printed "tens of mm" where the summary carried 70.69 mm, because it read `torque.js`,
baked against an older `torque.json`. Prose in place of a number is the mild version of the defect;
the real cost is two sources of truth about one measurement. The panels now read `summary.js` for
every figure, and `scripts/check_page_numbers.py` renders the page and fails on any numeric token in
the torque, comparison, checks or twin panels that does not trace to the summary JSON, allowing only
the precision the page prints and the unit scales it legitimately applies.

**Decision: the synthetic preview block lives inside `calibration`, not beside it, and ships.** Two
consequences settled together. The summary reserves the `synthetic` kind for the calibration block, so
a preview block outside it either broke that rule or taught a reader there are two; it is simulated
data with planted parameters, so it belongs inside. And the archive has to carry
`synthetic_preview.json`: the page prints 270 → 224 mrad, and a summary built from a zip without that
file had no preview at all, so the page and the voice would describe the same demo differently. The
packager copies it for the same reason it copies `torque.json`.

**Decision: the page payload is decimated at a 3,000-triangle budget, not 2,500.** Measured, not
chosen by feel: 2,500 produced 128,073 triangles because the reducer overshoots below the budget and
leaves roughly 500 per mesh; 3,000 produced 533,262 of the bundle's 620,093 (86.0%) with a largest
mesh of 3,370; 5,000 produced no reduction at all at 14.8 MB. The budget and ratio travel in
`trajectory.js` and the packaged README, so a recipient can re-derive both.

**Decision: `demo-bundle-v1.3` was recreated once, before publication.** The tag was first placed on
the code commit, before the zip it names existed in the tree, which would have made
`git show demo-bundle-v1.3:docs/demo/so101_demo.zip` fail. Nothing was pushed or handed out. The tag
was deleted and recreated at the final commit. The rule against re-tagging protects artifacts someone
may already hold; an unpublished tag that cannot resolve its own package protects nothing.

**Decision: `twin revise` refuses a diff whose solid bound moved.** Wall thickness and infill cannot
change the solid mass: the solid is the CAD volume at a stated density. A diff between two compiles
that disagree about it is therefore not a revision of one assumption, and the printed mass it reports
is that disagreement plus the revision. Measured while building this: a compile of the same STEP file
without the frozen bundle's servo mass produced a solid of 1.0413 kg against 1.3320 kg and a printed
mass of 0.6485 kg against 0.9017 kg — a 28% "reduction" at *higher* infill, which is the shape of the
defect. `revise` now exits 3 with that reason and still writes `diff.md` carrying it, and
`--servo-mass-kg`/`--servo-source` exist so the caller can hold the rest of the compile fixed.

**Decision: the print model is bounded by the CLI, not by `PrintModel`.** `PrintModel` accepts any
infill from 0 to 1 and any positive wall, which is right for a model and wrong for an instruction a
person speaks. `twin compile --infill` and `twin revise --infill` accept 0.1 to 1.0, and
`--wall-mm` 0.8 to 3.0; outside that, exit code 2 before the compiler starts. Zero infill is a
number, not a part, and a mass computed from it would be reported with the same confidence as one
from a printable assumption.

**Decision: "Try it yourself" is written outside the packaged README.** `README.md` is copied into
`so101_demo.zip`, so editing it after the v1.3 tag would mean the tagged package can no longer be
re-derived from the tree it names. The commands live in `docs/demo/TRY_IT_YOURSELF.md`, which is not
in the packager's file list, and the packaged README is untouched.

**Decision: a mass-only change is `changed` in a revision diff.** `diff_links` measured change in
quantity and volume, so the first real print-model revision printed `0 changed` beside a 6% mass rise
and `unchanged` beside `+11.35 g` on all seven rows. Geometry and mass are two different axes and a
revision can move one without the other; the status column now means "anything in this row moved".
Re-rendering the same two bundles costs nothing and the table now reads `7 changed`, volumes `+0.00%`,
masses positive.

**Decision: `twin revise` gets no baked-in servo mass; the fix is provenance in the bundle.** The
frozen compile used a datasheet figure for one servo (Feetech STS3215, 55 +/- 1 g). A CLI default
would stamp that actuator on every bundle the tool is ever run against, and the mass it produced would
read exactly as confidently as a measured one. The flag pair stays explicit and the solid-bound guard
refuses the alternative. The improvement is `actuator_mass_kg` and its source recorded in
`bundle.json` at compile time, so `revise` can read them from `--before` instead of asking, and a
revision cannot be run without the assumption the frozen bundle actually made. Not done now: adding a
field changes what the next package's bundle records, and v1.3 is frozen and re-derivable.

## E5: merge commits, tags at the merged heads, and the correction that lands after the tag

**Decision.** Both demo branches land through PRs with real merge commits — RoboCAD `feat/v1.1` →
`master` (`1ac923c`), Hi-EV `feat/robocad-shell` → `main` (`c76fd47`) — and `demo-v1.0` is an
annotated tag at each merged head.

**Why merge commits and not squash.** A squash would collapse 29 commits of evidence (E4's revise
path, E2's four clean-machine defects and their fixes) into one opaque commit. The tag is supposed to
be certifiable: each fix commit named in FINAL_STATUS must still exist in the merged history for the
claim to be checkable.

**Why the tag goes on the merge commit and not on a later docs commit.** The rule is to tag the merged
heads, so that is what is tagged. The cost is visible and recorded: the FINAL_STATUS blob inside
`demo-v1.0` still contains the line "`demo-v1.0` does not exist yet", because that line was written
before the tag existed. Re-tagging is forbidden this sprint, so the correction is a post-tag commit
and the tag keeps the older sentence. Anyone reading the tag reads the older sentence; anyone reading
`master` reads the correction.

**Why the merged head was cloned instead of trusting the working checkout.** A merge can be clean in
git and broken in practice. The gate ran `start_demo.ps1` from fresh clones of `origin/master` and
`origin/main` with a fresh venv, so what was proven is exactly what a person would get from the
remote.

## B5: one signal-to-noise definition, and which of the two numbers is the number

**Decision.** The ratio quoted anywhere is friction torque at a stated reference speed divided by the
actuator torque of one encoder count, computed at `REFERENCE_SPEED_RAD_S = 1.9` rad/s. 0.10 for the
SO-101 at `kp` 998 and a 12-bit encoder; 0.04 is retired.

**Why the document's definition wins and not the generator's.** The generator's version was not a
different estimate of the same thing, it was an estimate of a different thing: it divided by the peak
speed of whichever log it happened to be describing. That made the same robot's physics print a
different number depending on which log was in hand, which is not a property anyone can act on. A
reference speed is a choice; a log's peak speed is an accident. The note now names the speed in the
sentence it prints, so a reader can perform the division themselves and disagree with the exponent
rather than with the prose.

**Why the frozen artifacts were not rebaked to match.** A rebake produces a new package digest, and
the current digest has been verified and recorded in FINAL_STATUS and in the package's `FILES.sha256`.
Trading a verified digest for a cosmetic consistency fix, after the freeze, is the wrong trade. The
cost is stated rather than hidden: the four JSON artifacts still carry the 0.04 sentence, and
FINAL_STATUS lists all four by path so the next bake closes it.

## U1: the page is a cockpit, and what that costs

**Decision.** `docs/demo/page/index.html` is a single-screen cockpit at 1280x720 through 1920x1080:
no page scroll, no scroll inside a card, everything a spoken sentence names visible at once. Content
that does not fit lives in a drawer, opened by the card's "i" or by the section message in presenter
mode.

**Why not keep the scrolling page and fix its rail.** The page's job during a demo is to be an answer
to a sentence. A scroll is not an answer: at 1280x720 the fourth panel was off-screen, so "show me the
checks" scrolled to something the audience had not seen yet. A layout that guarantees every section is
on screen makes the section message a flash instead of a navigation, and the flash is testable.

**Why every number goes through one adapter.** Seven cards each reaching into five payloads is how a
page ends up with two different values for the same quantity, which is exactly the defect B5 found in
prose. One `DATA` object, built once from the globals, is the only place a figure enters the page; the
page-text checker walks the same numbers back to the summary.

**Why `HULLS` and `OFFICIAL GHOST` are not switches.** The packaged payload carries visual meshes only
(`SO101_MESHES`, 259 `_vis` entries) and no published-model geometry. A toggle that turns nothing on
is worse than a missing toggle: it promises a comparison the page cannot make. `SELF-COLLISION` and
`CoM` were shipped instead, and the omission is explained in the display card's own drawer entry
rather than left for someone to notice.

**Why the fps gate launches a GPU browser.** The 7 fps reading is headless Chromium's SwiftShader
fallback on this machine, not the page: the same payload renders at 61 fps headless and 145 fps headed
through D3D11. A gate that fails on the harness teaches people to ignore the gate. The test pins the
GPU path and prints the renderer name on failure, and both numbers are recorded.

## The release package is tagged demo-bundle-v1.5, not v1.4

**Decision.** The final visual stretch package is published as `demo-bundle-v1.5`. The existing
annotated tag `demo-bundle-v1.4` (commit `f7ebbac`, zip sha256 `d27f4d2d…`) is left exactly where it
is, and the release follows the same procedure as every earlier package: bake the zip with its tag
name written into `manifest.js` while the tag is still pending, commit the zip, create the tag once on
that commit, then prove the tag's blob equals the zip in `verify.json` and that the zip's own
`manifest.js` records the same name.

**Why not re-create v1.4 on the release commit.** `v1.4` is already referenced by `verify.json`, by
the package header in the HUD gate, and by other lanes' digests. Whether or not `git ls-remote --tags
origin` lists it (today it does not: origin carries `v1`, `v1.1`, `v1.2`, `v1.3` only), a tag that a
document of record already names is a published name here. Renumbering the release costs one word and
removes the question permanently, which is a cheaper trade than an exception to a rule that exists to
keep digests honest.

**What that means for the release brief.** The brief asks for `demo-bundle-v1.4`. It gets `v1.5`,
because `v1.4` already names a package whose zip does not ship `meshes/`, so its `--live` phrase fails
on a missing OBJ. FINAL_STATUS names `v1.5` and its commit; nothing else in the brief changes.

**Considered and rejected.** Deleting the local `v1.4` and creating it once on the release commit: it
would have satisfied the letter of the brief, but it makes a tag that documents and other lanes
already carry mean something different from what they recorded, and the only argument for it was a
version number.

## The release package is demo-bundle-v1.6; v1.5 stays where it is

**Decision.** The published package of record is `demo-bundle-v1.6` at commit `d5615d3`, zip sha256
`49d75172…`. `demo-bundle-v1.5` (commit `2422af4`, zip `19701ec2…`) is left untouched, even though it
was created minutes earlier in this same sprint and never pushed or announced.

**Why v1.5 could not simply be moved.** After the v1.5 tag was created, the packaged page failed its
own visual gate: at 1440, 1024 and 870 px the PACKAGE tile clipped its tag to "demo-bundle-v1."
because the tag and its status pill shared one 150 px value line. Fixing that changes the page, which
changes the zip, which changes the sha256 that v1.5's `verify.json` proves. A tag whose recorded zip
is not the zip we ship is precisely what the "no re-tagging" rule exists to prevent, and the rule does
not have an unpushed exception: the exception is the thing that gets widened until a digest no longer
means anything.

**What the cost actually was.** One tag name and one paragraph of explanation. A reader comparing the
tag list sees v1.5 and v1.6 next to each other; this section is why, and the honest reading is that
the visual gate ran after the tag instead of before it. That ordering is the process defect, not the
version number: the tile test now exists, and it should have been red in the tree before the first
bake, which is cheap and would have produced one tag.

**Considered and rejected.** Deleting v1.5 and recreating it on `d5615d3`: the only argument is that
the number is tidier, and the price is teaching every later digest-reading script that tags here can
move. Rejected for the same reason `v1.3` was only ever recreated once, before it was referenced by
anything.

## demo-bundle-v1.7 supersedes v1.6, and the churn is the lesson

**Decision.** The package of record is `demo-bundle-v1.7` at commit `656d244`, zip sha256
`f14291bf…`. `demo-bundle-v1.6` (`d5615d3`, zip `49d75172…`) and `demo-bundle-v1.5` (`2422af4`, zip
`19701ec2…`) are left where they are.

**What went wrong.** Two tags were cut in one hour for the same reason both times: the visual gate ran
after the tag instead of before it. v1.5 shipped a page that clipped its own tag text; v1.6 shipped a
page that answered "change infill to 30 percent" in chat while the card behind it still showed the
other bake, because the page had no channel for that sentence.

**The process fix, stated so the next release can follow it.** The bake is the last step, not a
checkpoint:

1. every page assertion runs against the tree page (`tests/test_page_*.py -m ""`), which is cheap and
   needs no bake;
2. only when those are green is the package baked, once;
3. the packaged-page assertions run against the baked copy, because build output is what a recipient
   gets;
4. only then is the tag created, and the tag is created on the commit that already holds that zip.

A tag made before step 3 can be wrong in a way no test will tell you about until after it exists, and
the only honest repair costs a version number. That is what happened here, twice.

**Considered and rejected.** Squashing the three tags into one by deleting v1.5 and v1.6: the rule
against moving a published tag is the reason `verify.json` can be trusted at all, and a reader who
sees three tags can read this section, while a reader who sees one has no way to know anything was
ever wrong.


