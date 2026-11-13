# Sprint log, deadline Sat 14 Nov 2026 22:00 Sydney

Satyam is unavailable until the deadline. Decisions get made, logged in `docs/DECISIONS.md` with a
one-line reason, and work continues. This log is the shared state between the two sessions; chat is
for decisions only.

## Lanes claimed

- **Lane A, compile path** (M2 YAML, M3 properties and collision, M4 bundle, checks, both diffs):
  build session, `robocad-61`.
- **Lane B, show path** (M6 page, film, synthetic twin, demo package, verifier): monitor session.

Lane B builds on the **official SO-101 MJCF first** and switches to `demo-bundle-v1` the moment
Lane A tags it. No lane waits on the other.

## Entries

Append one every 60 to 90 minutes: done, evidence, blocked, next. Tag evidence verified-ran,
verified-read or claimed. Never claim a lane's output without opening it.

### 2026-11-13 08:00Z, monitor session, Lane B start

- Claimed Lane B.
- Killed the heavy/slow/mujoco baseline run per the sprint instruction. It was at 25 percent with one
  xfail and two xpass, no failures. `BASELINE.md` records the stop and the reason.
- `docs/DECISIONS.md` gains the sprint decisions: publish `docs/twin/so101/` with a NOTICE, M2
  cross-review by the lane that did not write the YAML, CoACD capped at 30 minutes then convex hulls,
  heavy tier stopped for the sprint, and the living page built on three.js directly because no
  Teardown kit exists in this repo.
- Next: fetch the official SO-101 MJCF at the pinned commit, bake a trajectory, and stand up the
  page skeleton so B1 does not wait for the compiler.

### 2026-11-13 20:00Z, monitor session, Lane B

Done, all `verified-ran`:

- B1 page: offline from `file://`, zero network requests, 54 to 58 fps headless, 83k triangles,
  600 frames. Page geometry agrees with MuJoCo to 0.001 mm on three geoms, which is the check that
  separates a correct page from a pretty wrong one.
- B3 synthetic twin preview: generator plants friction, damping, armature and 16 ms latency, logs at
  62 Hz with noise and 4096 count quantisation. **Identification failed: 0 of 19 parameters
  recovered**, every one flagged `identifiable: false`. Trajectory error improves 270 to 224 mrad,
  which is a fit, not a recovery. Kept and labelled, not tuned.
- Page carries a SYNTHETIC watermarked twin panel with that honest count.
- B2 film: `docs/demo/film/so101_demo.mp4`, 1280x800, 24.0 s, 720 frames at 30 fps, 2.9 MB, recorded
  from the page itself so it shows the provenance line and the SYNTHETIC panel.
- `docs/demo/README.md` (3 minute script, real versus synthetic table, known limits) and
  `docs/demo/FINAL_STATUS.md` (every claim tagged).

Blocked: the compiled bundle. The page still shows the official SO-101 model and says so on screen.
No `demo-bundle-v1` tag exists yet, so nothing is bound to a bundle whose layout is not final.

Next: bind the page to `report.json` when Lane A tags, print the infill assumption beside every
printed link, and re-record the film against the compiled numbers.

### 2026-11-13 23:30Z, monitor session, Lane B

Done since the last entry, all `verified-ran`:

- Identification rebuilt as five rungs. Rungs 0, 1, 2 and 4 recover (0.57, 1.6/0.86, latency exact,
  0.12/0.56 percent). Rung 3, 62 Hz with noise and 4096 count quantisation, is blocked and quantified:
  1.53 mrad quantisation times a 998 N m/rad servo is about 1.53 N m of torque noise against a
  0.15 N m friction signal. The page shows the rung table with the blocked rung and its reason.
- Torque comparison harness. Three artefacts had to be removed before it meant anything: contact
  forces from the bundle's own overlapping hulls (989 N m on a 0.6 N m joint), servo saturation at
  the 3.35 N m forcerange, and body-frame axes compared across models. The trajectory is now
  analytic and contacts are disabled on both sides.
- Page gains a required-torque panel and a kinematics-vs-official row.
- Open disagreement with Lane A, unresolved: they measure joint axes agreeing within 2.14 degrees
  after one fitted datum rotation and anchors 27.7 to 110.3 mm apart. I reproduce 2 degrees on
  joints 2, 3 and 4 but 115, 65 and 175 degrees on joints 1, 5 and 6, with anchors 15.9 to 509.8 mm
  apart. Both cannot be right on the same MJCF. Asked which file and sha they measured.

Next: resolve the kinematics disagreement, re-record the film once the page settles, live viewer.

### 2026-11-14 10:40 Sydney, monitor session, Lane B final

Done, `verified-ran`:

- Page bound to `demo-bundle-v1` and rendering the bundle's own 259 visual meshes, decimated to
  128k of its 620k triangles (stated in the provenance line, because "renders the bundle's meshes"
  without that would overstate it). 54 to 56 fps, zero network requests, zero console errors.
- Comparison panel: solid upper bound 1.332 kg, print model 0.902 kg, published 0.632 kg, +42.7
  percent, with the conventions note and the 1.69 mm frame-free link-length agreement underneath.
- Torque panel reads its limit from the bundle's actuators, 2.94 N m, unsaturated: peak 1.26 N m
  official against 0.63 N m compiled.
- Revision panel wired and waiting only for `diff.json`; it stays hidden rather than showing the old
  broken diff.
- M2 cross-review: PASS, 4 of 4, run by this lane against the committed files, with the official
  URDF's sha256 verified against the pinned digest before the check ran. Recorded in JOINT_REVIEW.md.
- Package `docs/demo/so101_demo.zip`, sha256 `9afc087707d971f93bdfa4862939cbc775663d525fc0b459fffd8f68250a0362`, built and tested by extracting into a fresh
  temporary directory and opening that copy from `file://` with the network off: seven checks, seven
  link rows, comparison and torque panels populated, five identification rungs, zero page errors,
  zero external requests, no missing relative links.
- Packaging hardened after a review finding: it now refuses symlinks and any path resolving outside
  the repository, because an archive someone emails is a publishing surface.

Two package defects caught by that test and fixed, both worth recording because neither was visible
in the repo copy: rewriting the page header removed the provenance element the script reads, and the
page asked for a `diff.js` that the package did not contain.

Open: `diff.json` from Lane A's 0.30 infill run, the film re-record, and the final zip rebuild.
