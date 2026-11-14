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

### 2026-11-14 11:00 Sydney, build session, Lane A close

A1 to A6 done, `verified-ran` unless tagged otherwise.

- **A1 clean run at the tag.** `git worktree add ../robocad-final demo-bundle-v1`, then `python -m
  pytest -q`: **745 passed, 300 deselected, 3 warnings, exit 0, 391.13 s**, collected 1045. No
  caveat is attached, because the tree was the tag and not the tag plus edits. In `BASELINE.md`.
- **A2 M2 review closed.** `docs/twin/so101/robot.joints.yaml` and `docs/twin/so101/JOINT_REVIEW.md`
  committed, tracker row `[x]`. The review ran against four written criteria and re-hashed the
  official URDF against the digest the checker pins, before the check.
- **A3 revision diff.** Same pipeline, `f = 0.30`, output `docs/twin/so101/revision_f030/`, keyed only
  on the link names `robot.joints.yaml` declares. Printed mass **0.9016588355893798 ->
  0.9554530302470398 kg (+6.0%)**, solid bound 1.3320123928 kg unchanged, effort **0.652 -> 0.687
  N m on `joint_2` (22% -> 23% of the 2.942 N m stall)**. Sanity all hold: **0 added, 0 removed**,
  all 7 printed links heavier (+2.8% to +16.2%), and the actuator and joint blocks byte-identical,
  which is what "servos unchanged" means when the bundle states its hardware there. The `f = 0.30`
  bundle is committed beside the diff (2.5 MB, hulls only) so the diff re-derives without this
  machine, and it loads and replays 500 steps. Seven tests in
  `tests/test_revision_f030_artifact.py` guard the artifact's arithmetic.
- **A4 conventions.** `docs/twin/so101/CONVENTIONS.md` opens with the mandated sentence about joint
  origins without offsets being misleading by centimetres, and carries the five offsets
  (-88.17, +90.29, -90.31, -0.15, 0.00 deg), the base translation (38.74, 6.64, -2.86) mm and the
  2.50 mm median residual.
- **A5 live viewer.** `--mode replay` ships and replays the bundle. `--mode hold` **fails and the
  failure ships**: 573.26 mrad steady error with all six joints at the 2.942 N m force limit, because
  `kp` = 20 asks 10 N m for a 0.5 rad step and the servo has 2.942. Per-joint numbers in
  `docs/twin/so101/live_hold.md`.
- **A6 package verification.** `scripts/verify_demo_zip.py` names three numbers before computing
  them, extracts the zip to a fresh directory and re-derives each from the zip's own baked JSON.
  Final package sha256 `fff730639bc40ca7e4f7efc924a092fed0bebae4f01ec659291da1ea8920c26f`,
  3,892,730 bytes, 20 files, built from `430c77e` per the packager: **four passes, exit 0,
  VERIFIED**, in `docs/demo/verify.json` with the built-from commit recorded as a claim rather than a
  verified fact.

Two defects the verifier caught rather than a reader:

1. The 10:52 package rendered `docs\twin\so101\bundle` in the revision panel. The page was fine; my
   `diff.json` wrote `str(path)`. Fixed at `cdb1662` with `as_posix()`, page rebaked, repacked. A
   repo-side test could not have caught this, because the repo copy is built on the machine whose
   convention the path uses.
2. The rendered panel had to be checked, not merely the payload. A non-null `window.SO101_REVISION`
   with an empty panel would have passed the old check while showing nothing.

Post-tag test tier: **745 passed, 300 deselected, 3 warnings, 432.76 s, exit 0** at `0ef337c`, which
did not yet collect the seven new artifact tests (`7 passed` separately). Collected **752 of 1052, 300
deselected** at `70ce42c`, measured with `--collect-only -q -p no:cacheprovider`. The single run over
all 752 is recorded at the freeze commit in `BASELINE.md`.

Next: the freeze commit, and the three post-demo steps in `FINAL_STATUS.md`.

### 2026-11-14 final, monitor session, Lane B closed

Verified artifact, not a claim: `docs/demo/so101_demo.zip`, sha256
`5977d7f4e50d87edc5d904fad39401a3e383d14403c0f91e38b4d749e5050b69`, 3,892,620 bytes, 20 files,
built at commit `64efbd5`.

Independent verification by the other lane, recorded in `docs/demo/verify.json` (commit `4af81f5`):

    [PASS] 1  printed mass  sum(bodies) 0.901658836 kg, totals 0.901658836 kg
    [PASS] 2  revision       0.901658836 -> 0.955453030 kg over 7 link(s)
    [PASS] 3  check rows     {'pass': 5, 'fail': 1, 'skipped': 1}
    [PASS] 4  page opens    7 check rows rendered, 7 link rows, revision panel 470 chars over 7 row(s),
                             0 page error(s), 0 non-file request(s), 0 missing relative link(s)

Four passes, exit 0. The fourth check is the one that matters: the zip was unzipped somewhere else
and opened from file:// with the network off, which is the only test that resembles what a recipient
does.

Open, and deliberately not closed today: the repo page and the packaged page are two bakes of the
same content, and only the packaged one is verified. If the repo copy drifts, nothing catches it.

### 2026-11-14 freeze, Lane B final

Shipped artifact, verified twice over, the second time after two repacks:

    docs/demo/so101_demo.zip
    sha256 fff730639bc40ca7e4f7efc924a092fed0bebae4f01ec659291da1ea8920c26f
    3,892,730 bytes, 20 files, built from commit 430c77e

Verification, written to `docs/demo/verify.json` rather than to a message:

    [PASS] 1  printed mass  sum(bodies) 0.901658836 kg, totals 0.901658836 kg
    [PASS] 2  revision       0.901658836 -> 0.955453030 kg over 7 link(s)
    [PASS] 3  check rows     {'pass': 5, 'fail': 1, 'skipped': 1}
    [PASS] 4  page opens    7 check rows, 7 link rows, revision panel 470 chars over 7 rows,
                             0 page error(s), 0 non-file request(s), 0 missing relative link(s)

Two repacks after the first verification, both for defects the verifier found and neither about
numbers: a shipped document named its paths in Windows separators, and the revision document carried
no synthetic label while every other surface did. Both were worth their cost, and both are the class
of defect a repo-side test cannot see.

`verify.json` records the build commit under the key `built_from_claimed`, which is the honest name:
a zip is not a git object and re-running the packager would not reproduce its bytes, so the verifier
records what the packager asserted and labels it as an assertion.

### 2026-11-14 11:30 Sydney, build session, Lane A freeze

Frozen. Nothing in `docs/twin/so101/bundle/` was touched after the tag `demo-bundle-v1` at `f202c12`;
the revision compile, the diff and every document live beside it.

The deliverable:

    docs/demo/so101_demo.zip
    sha256 fff730639bc40ca7e4f7efc924a092fed0bebae4f01ec659291da1ea8920c26f
    3,892,730 bytes, 20 files, built from commit 430c77e

Final default tier, every test the selection collects:

    python -m pytest -q
    752 passed, 300 deselected, 3 warnings in 367.27s (0:06:07), exit 0

collected 752 of 1052 at the tree `4af81f5`. In `docs/BASELINE.md` under "The freeze commit", with the
uncommitted-during-the-run edits named so the row is not cleaner than the truth.

Four things this lane changed after the tag, all recorded because each was a claim that had stopped
being true: the bundle was said to carry no visual meshes when it carries 259 beside the 433 hulls; a
mass-consistency line quoted a 1.04134 kg total and "exactly 1240.0 kg/m3" for every body, both of
which were true before the print model existed; two `sha256` values were quoted for `model.mjcf` and
`model.urdf` that no longer matched anything and, being working-tree hashes, could never have matched
on a checkout with different line endings; and the security section described three findings as open
when all three were fixed in source. The status file now says what the artifacts say.

Next: the three post-demo steps in `FINAL_STATUS.md`. Nothing else in this lane waits on the sprint.

### 2026-11-14 12:05 Sydney, v1.1 session, Lane A

`feat/v1.1` is cut from the freeze and carries four commits so far: P0 (`699da53`, torque
contradiction) and P1 (`e1312b1`, current channel) from Lane B, R2 (`d24a0d0`, conventions inside the
bundle) and R3 (`3b0a1e8`, the package states how much of the bundle it renders) from this lane.

**R2, conventions inside the bundle.** `manifest.json` and a comment block in `model.mjcf` now carry
the five zero-pose offsets, the gripper offset, the base translation and the residual, rendered from
one `Conventions` object so the two copies cannot drift. The test that matters is a mutation: it edits
the bundle's own manifest and requires the second read to return the edited value, so a reader taking
the numbers from its own constants passes every round-trip test and fails that one.

    python -m pytest tests/test_conventions.py tests/test_revision_f030_artifact.py -q
    31 passed in 36.19s                                       [verified-ran]

**R3, mesh resolution.** The bundle keeps the full-resolution visuals; the packager decimates for the
page, computes the ratio from the packaged payload and the bundle's own `report.json` rather than
quoting it, records the bake's triangle budget (now written into `trajectory.js`), and states that no
decimated mesh is ever written back. Seven tests, including one that fails if `bake.py` stops
recording the budget.

    python -m pytest tests/test_mesh_resolution.py -q
    7 passed in 1.76s                                         [verified-ran]

**R1.4, the live hold retest, and why it still fails.** The corrected pose mapping lands every joint
inside its own range (no clamp fired, and the ranges are wide enough that no legal target needed one),
so the previous explanation — a target outside the range held by a limit constraint — is disproved,
not confirmed. The retest was run headless because that is where the numbers are, and it fails:

    python -m robocad demo so101 --bundle docs/twin/so101/bundle --mode hold
    steady-state joint error 573.23 mrad (peak 828.63 mrad)
    actuator saturation: 113698 step-instances at or above 99.9% of forcerange
    what the steady error is made of (contacts active at the end: 64):
      joint_1  asks 11.46  gravity 0.000  contacts 3.29  limit 2.94
      joint_3  asks 10.24  gravity 0.254  contacts 2.71  limit 2.94
      joint_6  asks  6.40  gravity 0.004  contacts 2.59  limit 2.94
                                                              [verified-ran]

Neither of the two candidates the order named is the cause. Gravity at the commanded pose is at most
0.254 N*m against a 2.942 N*m limit, so the servo is not short of torque for the load; and the demand
`kp * error` is 11.46 N*m, which the servo cannot supply, so it saturates. What consumes the budget is
the collision solver: 64 contacts are active at the last step and `qfrc_constraint` reaches 3.29 N*m on
joint_1, more than the actuator has. That is the bundle's own `self_collision` check showing through —
it reports **fail**, deepest overlap −7.939e−03 m, and the hold is that number with a controller on
top. No gain or torque change fixes it. **The demo path stays replay only,** and hold stays available
as a diagnostic that prints its own reason.

Two wrong versions of the diagnostic were shipped to a terminal before this one and are recorded in
the code: `mj_inverse` with a default `ctrl` reported the forcerange (2.942 N*m) on every joint, and
`mj_forward` before `mj_inverse` recomputed `qacc` and made the answer exactly zero. The measurement
now reads `qfrc_bias` at rest, which is the gravity term by definition and is untouched by contact or
limit constraint forces. Six tests pin all three: the load does not equal the limit, does not scale
with it, does not pick up a limit force outside the range, and goes to zero when gravity is switched
off.                                                    [verified-ran, 6 passed in 0.83s]

### 2026-11-14 13:10 Sydney, v1.1 session, Lane A, H0 and H5

**H0, the JSON CLI Hi-EV calls.** `robocad/twin_cli.py`, wired into `python -m robocad twin`:
`summary --bundle DIR [--json]`, `page --bundle DIR --out DIR`, `compile --step FILE --joints FILE
--out DIR [--json-progress]`. No Hi-EV import; a subprocess and JSON, so a changed field is a schema
failure rather than an import that happens to still resolve.

    python -m robocad twin summary --bundle docs/twin/so101/bundle
    so101: .../docs/twin/so101/bundle
      bodies 7  joints 6  parts 83  instances 259
      mass 0.901658836 kg modelled, 1.332012393 kg solid bound [derived]
      worst check fail
      conventions: measured, P0-a registration ...
      synthetic figures: 9 of 31                        [verified-ran]

The summary's content is its `provenance` block: every key of `totals` carries `{kind, synthetic,
basis}`, and `synthetic` is derived from `kind` (`derived` and `synthetic` are true) so the flag cannot
disagree with the label in a hand-written entry. Anything no rule anticipated defaults to `derived`
with the basis "no provenance rule for this figure: treat it as a model output, not a measurement" —
fail-closed, because the alternative is an unlabelled model output in a panel a reader takes as
measurement. On this bundle that is 9 of 31 figures, the two masses chief among them.

`compile --json-progress` emits one JSON object per line over a fixed stage set
(`import|joints|properties|collision|bundle|checks|done`, last line `done` at 100, no other name
accepted), and a failure ends with `{"stage":"error",...}` and exit 2 through the same sink, so a GUI
waiting on the stream cannot hang on a dead pipe. Exit 3 means "built, and its own checks are red".
`--joints` adopts the limits of a reviewed `robot.joints.yaml` with that file's own provenance
sentence, and refuses a file that states two sources.

    python -m robocad twin page --bundle docs/twin/so101/bundle --out <tmp> --json
    rebuilt_from_this_bundle: meshes.js, report.js, trajectory.js
    copied_from_page_assets: diff.js, identification.js, index.html, three.min.js, torque.js, twin.js
    referenced_but_absent: []   complete: true        [verified-ran, 3.7 s]

`twin page` names what it rebuilt from this bundle and what it copied, because the torque payload needs
the published model as well as the compiled one and a page that silently carried last week's torque
number beside this week's bundle would be the worst of both. It also checks every local `src` the page
links and refuses to call the result complete while one is missing. Default triangle budget is 500 to
match the shipped page (3.1 MB) rather than bake's 2500 (10.9 MB for the same robot).

Tests: `tests/test_twin_cli.py`, 17 tests, all passing (15 default + 2 `-m mujoco`). [verified-ran]

**H5, the blade, delivered as a tested handoff.** Lane B sent the exact `BridgeEvent` union and the
route prefix `/robocad/page/`, so the blade is written against both and against a fixture rather than
discovered on live events. `docs/twin/hiev_blade/`: `panel.ts` (all the rules), `Blade.tsx` (iframe,
postMessage, presenter mode), `fixture.mjs` (`phase -> panel -> delta -> done`, then Esc),
`panel.test.mjs`, `INTEGRATION.md` (six hunks for the Hi-EV tree).

    cd docs/twin/hiev_blade && node --test
    tests 10   pass 10   fail 0                       [verified-ran]

Pinned there: the six sections and no others; a `src` outside `/robocad/page/` is refused, including
`..`, backslashes, schemes and control characters; Esc closes the blade **and** hushes the voice in one
action; frame messages need the frame's own window, the expected origin and the right shape; the frame
is `sandbox="allow-scripts"` with no `allow-same-origin`; the CSP fragment is exactly
`frame-src http://127.0.0.1:7345`. `panel.ts` is imported by the tests through node's type stripping,
so the tests exercise the file that ships rather than a JS copy that can drift.
