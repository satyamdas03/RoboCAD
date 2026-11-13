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
