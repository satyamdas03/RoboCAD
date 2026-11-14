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

### 2026-11-14, v1.1 session, Lane A, H7 cross-check and the R5 wording

Timestamps in this file's earlier headers were written against a clock that ran ahead of the machine;
this entry and later ones use the machine's own time (local 12:14 AUSEDT, 01:14 UTC). Flagging it
rather than back-dating, because an entry whose time is invented is not evidence.

**H7, Lane A checks Lane B's spoken numbers.** She sent eleven H6 narration figures. Each was checked
by loading the artifact it cites and rounding to the precision she speaks, not by reading the page.
Ten match. Two do not. `verified-ran`, table in `docs/demo/H7_cross_check.md`:

- `revision_f030/diff.json` `totals.mass_after_kg` = **0.9554530302470398**. At three decimals that is
  **0.955**, and her line says 0.956. The before figure (0.902) is right.
- `docs/demo/twin/identification.json` has two current-channel rungs and **both carry
  `reached: true`**, so "1 of 2 rungs recovered" contradicts the field the rest of the panel uses.
  The number is reachable another way — the 25% tolerance on *damping*, where `elbow_flex` reads
  24.86% and `shoulder_lift` 45.53% — but that is a different sentence and must be spoken as one.
- Minor, reported not fixed: her torque line says "at matched static poses" while
  `static_gravity[0]` is the rest pose only.

Everything else survived, including the figures that carry the most weight: 7 bodies / 6 joints,
5 pass / 1 fail / 1 skipped, 7.9 mm hull overlap, P0-a's 2.50 median and 11.25 worst, 0.902 vs 0.632
published with a 1.332 solid bound, 0.767 vs 0.538 static gravity, and the jaw's 70.7 mm.

**Her origin caveat, answered in code.** `Blade.tsx` now warns on an origin mismatch
(`refused a frame message from <origin>; expected <origin>`), and `INTEGRATION.md` states that the
origin is a setting rather than a constant, with the build-time-read option named for the case where
the shell ships more than one port configuration. `panel.ts` is unchanged and its 10 tests still pass
(`verified-ran`, `node --test panel.test.mjs` from that directory: 10 pass, 0 fail).

**Ownership call, logged in `docs/DECISIONS.md`.** The v1.1 tag, the zip rebuild and the fresh-folder
verification stay with Lane B, because she is still editing `docs/demo/page/index.html` and
`torque.js`; a zip built mid-edit is worse than one built last. I own the `FINAL_STATUS.md` wording and
will state the package's status as hers, with her evidence, plus the three-number check she runs.

### 2026-11-14 12:55 AUSEDT (01:55 UTC), v1.1 session, Lane A, the suite, and the package read from inside

**Default tier, green.** `python -m pytest -q -p no:cacheprovider` →
**798 passed, 308 deselected, 3 warnings in 957.27 s, exit 0**, `verified-ran`. Three warnings, all the
long-standing `InsecureKeyLengthWarning`s from the LiveKit token tests. 46 more tests than the freeze
run, which is the four v1.1 files. The tree moved under the run: Lane B's `teardown_export` changes
landed after it started, so the tests covering exactly those files were re-run on the moved tree —
**17 passed** for `-k "package or bake or mesh_resolution or torque"` and **8 passed** for the
MuJoCo-marked tests in `test_demo_static_load.py` and `test_twin_cli.py`. Stated that way in
`FINAL_STATUS.md` rather than claiming the sixteen-minute run covered code that landed after it began.

**The v1.1 package, read from inside rather than around.** Two defects, both now fixed by Lane B and
both re-verified here at sha256 `46b848e9…`, 25 files:

- `manifest.json` named five files the package did not carry (`robot.joints.yaml`, `model.mjcf`,
  `model.urdf`, `bundle.json`, `meshes/`). Fixed: the three real artifacts now ship, `meshes/` is
  declared absent under `not_in_package` with a reason, and the package test now **fails the build** on
  a manifest entry that does not resolve in the extracted copy. `verified-ran`.
- The spoken "jaw frame differs by 70.7 mm" was nowhere in the package while its torque payload said
  "tens of mm". Fixed: `torque.js` now carries `pose_gate_worst_mm` 70.69 with the five samples. Her
  first version of that gate read 97.37 mm because it omitted the base translation; both harnesses
  agree at 70.69 after the fix. `verified-ran`.
- `scripts/verify_demo_zip.py` passed 4 of 4 on the **defective** build too, which is the point worth
  keeping: the manifest is not a page link, so a link checker cannot see it. The fix that lasts is
  hers (a check), not mine (a read). `verify.json` regenerated against `46b848e9…`; the tracked zip at
  `2f2920c` hashes to the same digest, so the verified artifact is the committed one.

**Blade, two more fixes, both with the same shape as the manifest one — a guard that disagreed with
the thing it guards against.** `safeSrc` accepted `%2e%2e`, `.%2e` and `%2E%2E`, none of which
contains the literal `..` the check looked for and all of which a browser decodes into one; the guard
is now a flat refusal of `%`, with seven encoded variants pinned (`a7ee645`). And `Blade.tsx` imported
`'../../robocad/panel'` from `web/src/ui/`, one level too high; Lane B corrected it on integration and
the file and `INTEGRATION.md` now agree (`aa5566b`). Blade tests 10 of 10 after both.

**Not done, and said so.** The heavy/slow tier was not run in full. Only the MuJoCo-marked tests in
the two files v1.1 changed were run, because the rest of the heavy tier's cost is unrelated to this
change and the freeze already records that tier as stopped by instruction.

### 2026-11-14 13:08 AUSEDT (02:08 UTC), v1.2 fix-up, Lane A, F1 and F2 reproduced before touching anything

Order: the pasted v1.2 fix-up, F1–F7. Standing rule for this sprint is reproduce-then-fix with the
reproduction pasted here. Both P0 items were run against the shipped zip first.

**F1 reproduction.** Extracted `docs/demo/so101_demo.zip` to a fresh temp directory and hashed the
artifacts the review named, `verified-ran`:

```
zip             : 46b848e90ff12d5189e009f38a2fb25d4950646d26166a9c9132ac622a067d4b 3919227
zip report.json : 34caf7e857e94f1ee50d30d616efb0e23c1af543b4509fa4c50d5be1c90130d9
tree report.json: 34caf7e857e94f1ee50d30d616efb0e23c1af543b4509fa4c50d5be1c90130d9
zip index.html  : 613fc09fc8fbf1588e8f4923fb06e0a4f31050d199639210e63c4e0db2b27621
page index.html : edd42ab68fd2908b54adc783011cd9fe2c56fa8ca930fbf234f50038ac25b79d
zip torque.js   : 8e90eb1d24a7ae7d70d35f7ff2250bac24d501471bb035fb668f59c67a3b4e35
page torque.js  : 8e90eb1d24a7ae7d70d35f7ff2250bac24d501471bb035fb668f59c67a3b4e35
zip  report.html stamp: Generated 2026-11-14T00:52:14+00:00 from
tree report.html stamp: Generated 2026-11-14T00:52:14+00:00 from
```

Two findings, one against the order and one for it:

- **The report.json divergence the order cites is not reproducible.** The zip's `report.json` and
  `docs/twin/so101/bundle/report.json` are byte-identical at `34caf7e8…`. The order says the tree's is
  `1d0699cc…`, which was true before the bundle was regenerated at `2f2920c`; it is not true of HEAD.
  Stated plainly rather than "reproduced" because a review whose evidence has expired is still right
  about the defect only if the defect is still there, and this half of it is not.
- **The page divergence is real and is the whole of what remains.** A unified diff of the two
  `index.html` files is four lines: 730 → 731, one `<div>` added at line 49. That div is the
  packaged-demo nav block `teardown_export/package_demo.py` injects into the zip copy. So the blade
  serving `docs/demo/page/index.html` shows a page the zip does not contain, and the fix is to stop
  serving a second copy at all.

**F2 reproduction.** `python -m robocad twin summary --bundle docs/twin/so101/bundle --json` today
carries `schema_version, name, bundle, totals, checks, worst_status, conventions, provenance,
synthetic_count, warnings, notes` and nothing else. Grepping those numbers in the summary:
0.632 **absent**, 2.14 **absent**, 2.50 appears only as the manifest's `residual_mm.median` inside
`conventions` and has no section of its own, 0.767 **absent**, 0.538 **absent**, 70.69 **absent**,
0.955 **absent**, 0.147 **absent**. Only the totals the report already had (1.332 solid, 0.902
printed) come through. The numbers exist in the bundle under other keys and other files
(`comparison.json` alignment, `diff.json`, the torque and identification payloads), which is exactly
the review's point: the summary is a subset, and the voice reads the subset.

Lane B independently reproduced both and reports 4 of 7 sections falling to "not in the report" and
the revision section inventing 0.20/0.30. She has asked for the real schema to be sent as it prints,
not as specified, once F2 lands, and has proposed torque `static_poses` carry one scalar per pose
(peak over joints) rather than arrays. Both accepted: readers go against the artifact, and the torque
scalar-plus-`per_joint` split is what the page already does.

**F2 shipped (`cfbb0d8`).** The same command now prints, after the check lines:

```
  checks 5 pass  1 fail  1 skipped
  masses: solid 1.332 [modelled], print 0.9017 [modelled], published 0.632 [stated]
  torque at rest: 0.7668 compiled vs 0.5377 published N m, limit 2.941995
  revision infill 0.2 -> 0.3: mass 0.9017 -> 0.9555 kg, 7 links changed
  synthetic figures: 0 of 31
```

`--json` carries `check_counts`, `masses` (with `wall_mm 1.2`, `infill 0.2`,
`density_kg_m3 1240`, `servo_g 55`), `residuals` (`axis_rms_deg 1.054`, `axis_worst_deg 2.1408`,
`origin_median_mm 2.5`, `origin_p90_mm 5.95`, `origin_max_mm 11.25`, `link_length_mm 1.69`),
`torque` (rest/quarter/half as one scalar per pose, `limit_stall_nm 2.941995`,
`rated_nm 0.980665`, `dynamic_comparable false`, `pose_gate_mm 70.69`, and a `dynamic_reason` that
names 70.69 mm), `revision` (`0.20 -> 0.30`, `0.9017 -> 0.9555 kg`, 7 links, no added or removed),
and `calibration` (`position_only.snr 0.1 / status insufficient`, four current-channel parameters
each with `lo`/`hi`, `synthetic true`). Every number is copied out of the bundle's own files; the
four payloads the summary needed but the bundle lacked (`torque.json`, `diff.json`,
`identification.json`, `identifiability_scenarios.json`) were added to it rather than recomputed in
the reader. `synthetic_count` is 0 of 31 provenance entries, and every leaf outside `calibration`
has a non-`synthetic` kind — the test asserts both by walking the document.
`python -m pytest -q tests/test_twin_cli.py` → `32 passed, 2 deselected in 13.08s`.

**F3 + F5 shipped, and the three review findings that came with them.**

*F3 — one fixture, exported, not written.* `python scripts/export_summary_fixture.py` unpacks
`docs/demo/so101_demo.zip` with the digest `docs/demo/verify.json` records and writes
`docs/demo/robocad_summary.v1.json` (53 505 bytes) verbatim, plus
`docs/demo/robocad_summary.v1.sha256` in `sha256sum` format. Run against the **v1.1** zip it reported
`sections: check_counts, masses, residuals, revision` / `missing: torque, calibration`, which is the
proof the exporter reads the package rather than the tree: those two payloads are simply not in the
old archive. Run against the rebuilt zip all six sections are present.

*F5 — the page answers one message.* `docs/demo/page/sections.js` maps
`overview→#hud, checks→#checks-grp, comparison→#cmp-grp, torque→#torque-grp, revision→#rev-grp,
twin→#twin-grp`, scrolls the panel into view and flashes it for 1 500 ms. It accepts
`{type:"robocad.section", section}` only when `event.origin === location.origin` and the page is
served over http(s); `#section` in the URL works on load and on `hashchange`. Node test:
`node --test docs/demo/page/sections.test.mjs` → `8 passed`, covering right origin, five wrong
origins, unknown section, wrong type, `file://` refusal, the 1.5 s flash, a hidden empty panel
refusing the jump, and wired message/hash delivery. Real browser, packaged zip served over
`http://127.0.0.1:<port>`: `scroll_before 0 → scroll_after 2699`, flash present at 900 ms and gone
after 2 s, `wrong_origin_accepted: null`, `page_errors: []`.

*Review findings, all three addressed.* (1) Member cap counted only non-directory entries; it now
counts `infolist()`, regression test writes 4 directory entries + 1 file against a cap of 3.
(2) `synthetic_count` read as fail-open; `synthetic_figures {provenance, calibration,
calibration_is_synthetic}` now reports 0 provenance and 18 calibration figures, and the printed line
says both. (3) Arithmetic on untrusted bundle JSON could traceback; `_number()` returns `None` for a
non-number so the figure is omitted, `_print_summary` formats through it, and `main()` turns any
`build_summary` failure into the same exit-2 JSON error line. Two regression tests: a `"heavy"`
mass and a `"not a number"` spacing still produce a summary, and a `{"checks": "not a list"}`
report exits 2 with a JSON error line.
`python -m pytest -q tests/test_twin_cli.py` → `38 passed, 2 deselected in 43.10s`.

*Rebuild.* `python teardown_export/package_demo.py` → `PACKAGE OK`; zip is now **29 entries**,
sha256 `fa16ff010b4d295854b14cb47461a9a0e76f805afc66a82fe3c02d32fc8eb889`.
`python scripts/verify_demo_zip.py docs/demo/so101_demo.zip --out docs/demo/verify.json` → four
PASS rows, `VERIFIED`.

### 2026-11-14, hardening pass before the tag [verified: ran]

*Two holes the tests did not cover, found by probing rather than by a failing test.*

Terminal injection, `totals` block. The sanitiser covered the names, checks and provenance lines but
not the line that prints the report's own totals, so a mass field carrying `\r` started a fresh
terminal line. Reproduced before fixing: a synthetic `report.json` with `total_mass_kg:
"heavy\r\nforged line"` printed `mass heavy` then `forged line kg modelled` on the next line.
Fixed by routing every value in that line (bodies/joints/parts/instances, both masses, the kind)
through a new `_text()` helper -- `_safe` of the written value, `None` for a missing one -- and the
same for `worst_status`, `check_counts`, the masses' kind and the torque pose. Regression test
`test_a_control_character_in_a_bundle_string_does_not_reach_the_terminal` now fails on the old code
and passes on this one. `python -m pytest -q tests/test_twin_cli.py` -> `42 passed, 1 deselected in
11.21s`. `node --test docs/demo/page/sections.test.mjs` -> `10 pass, 0 fail` (the two tests added
with the null-origin and non-parent-source refusals are in the earlier block's count of 8; this is
the current number).

*Lane B's ordering request, adopted.* `calibration.current_channel.params` led with the attenuated
viscous estimate (0.0436 recovered against 0.08 true) and followed with Coulomb, the parameter the
current channel actually resolves (0.1466 against 0.15). Reordered so Coulomb leads, with the reason
in a comment beside the loop. Fixture regenerated from the untouched package:
`coulomb_friction 0.15 -> 0.1466`, `viscous_damping 0.08 -> 0.0436` for the first joint. Lane B can
drop her preference scan.

*F7 (2): the four commands with no Anthropic SDK installed.* `python -m robocad twin unpack` on
`docs/demo/so101_demo.zip` -> `sha256 fa16ff01... (verified)`, 29 files. `twin summary` on the
extracted bundle -> the seven check rows, masses, torque, revision and calibration lines, all
correct, no traceback. `twin page` -> exit 2 with the intended sentence: the package ships
`meshes.js` and not the source meshes, so a page cannot be baked from it; that message is the fix,
not a defect. `twin compile` needed two environment facts to run at all: `pydantic` is a real
dependency of the compile path, and build123d resolved to 0.13.0, whose OCP build no longer carries
`TDF_LabelSequence`, so the STEP importer died claiming the dependencies were missing. Pinned
`build123d>=0.9.0,<0.13` in `requirements.txt` and `pyproject.toml`, and the importer now names the
failing import in its message. With 0.11.1 in a venv that has no `anthropic` module at all:
`twin compile --step ...` reached `import 10% 1 parts, 1 instances` and then refused a single-part
STEP for the right reason (its kinematics chain names bodies the assembly does not contain). The
claim is the one the order asked for: none of the four commands needs the Anthropic SDK, and none
of them tracebacks on a machine that has never had it.

*F7 (4): what this branch puts into git.* Largest file touched between the merge-base and HEAD is
`docs/demo/so101_demo.zip` at **3.76 MB**, then `docs/twin/so101/bundle/model.mjcf` at 0.12 MB. All
23 newly added files together are 0.3 MB. Nothing exceeds 5 MB, so nothing moves to LFS and nothing
leaves git. Measured with `git show HEAD:<path> | wc -c` over `git diff --name-status base..HEAD`,
not from the working tree.

### 2026-11-14, the zip was stale, and now a digest says so [verified: ran]

Before tagging, the packaged page was compared against the tree it is built from:

    so101_demo/sections.js zip 67a239f3842b tree f68f8bc7eb31 DIFFERS
    zip has "null": True   tree has "null": True
    zip has event.source: False   tree has event.source: True

The rebuild earlier in this sprint happened before the two security guards went into
`docs/demo/page/sections.js`, so the package carried the pre-fix listener. Lane B found the sharper
form of the check: both copies contain the string `"null"`, so grepping for the null-origin refusal
would have declared the package fixed. The token that discriminates is `event.source`.

Rebuilt: `python teardown_export/package_demo.py` -> `PACKAGE OK`, playwright on the unpacked copy
reports `page_errors: []`, `external_requests: []`, `missing_relative_links: []`,
`manifest_dead_entries: []`, panels `checks 7, links 7, cmp 840, torque 634, ident 7`. Zip is now
**30 entries**, sha256 `b2f835c019fc114d0753f6e8dda33e3118c2b90eab122ffbeb339174d0744774`. The packaged
`sections.js` now hashes to the tree's `f68f8bc7eb31`, and `event.source` is present in it.

*The class of defect, not just the instance.* This is the second round where a file existed in the
tree and differed in the package, so the packager now records a digest per file. It writes
`FILES.sha256` after its last write, and `twin unpack` recomputes every line, refusing on a mismatch
or on a file no line records. On the rebuilt package:

    sha256 b2f835c019fc114d0753f6e8dda33e3118c2b90eab122ffbeb339174d0744774 (verified)
    30 files into <fresh dir>
    29 files match the FILES.sha256 the package ships

Three tests cover it: matching digests report `checked: 1`; a file whose bytes differ from its
recorded digest raises `does not match the digest recorded`; a file with no line raises `no digest
records it`. `python -m pytest -q tests/test_twin_cli.py` -> `45 passed, 1 deselected in 8.28s`.

`python scripts/verify_demo_zip.py docs/demo/so101_demo.zip --out docs/demo/verify.json` -> four PASS
rows, `VERIFIED`, and `verify.json` now names sha256 `b2f835c0…`. Fixture re-exported from that
archive: `sections: check_counts, masses, residuals, torque, revision, calibration`,
`synthetic figures: 0`.

*One legibility fix in the page.* The impeccable hook flagged `.synth`, the badge that labels a
synthetic figure, at 10px. That is content-bearing functional text, so it moved to 11px
(`letter-spacing: .08em -> .06em` to keep the badge the same width). No id or class changed, so the
blade's element pointers and the section map are unaffected. Nothing else on the page is under 11px.

*Suite.* Full default tier on the tree before these last three changes: **829 passed, 307 deselected,
3 warnings in 1015.77s**.

### 2026-11-14, F7 (4) cross-checked against Lane B's measurement [verified: ran]

Both lanes measured the same thing and the two figures only looked different because of units.
Mine: `git diff --name-status $(git merge-base master HEAD) HEAD`, then `git show HEAD:<path> | wc -c`
per file -> **23 files added, 0.3 MB together, largest added 0.12 MiB (`torque.json`), largest file
touched 3.76 MiB (the demo zip)**, nothing over 5 MB. Lane B: same 23 files, largest 0.13 MB, and
against the `demo-bundle-v1` tag the diff is 514 files with the 3.94 MB package. 3,943,593 bytes is
3.94 MB decimal and 3.76 MiB; neither of us is wrong and the decision (no LFS, no history rewrite)
holds under both readings.

The order's figure of "1,266 files and 1.07M lines" is not reproducible from either base here. It is
not mine: it came in with the review that opened this sprint, and I have no command that produces it.
Recorded as unreproduced rather than adopted, per the rule that an unverified number does not become
a premise. Anyone planning a merge should use the measured pair above.

## S3 — repeated sentence in the self_collision explanation [verified: ran]

Reproduced first, on the shipped artifact (`docs/twin/so101/bundle/report.json`, the file the v1.2 zip
carries as sha256 `34caf7e8…`):

```
self_collision fail 131 words
1 non-adjacent pair(s) overlap, deepest -7.939e-03 m. The CAD solids of wrist_roll_pitch_so100 and
moving_jaw_so101 intersect and share 0.52 mm3 of material, so part of that overlap is real and part of
it may be the hull; this measurement does not split the two. The status stays fail either way: MuJoCo
collides the hulls, so the simulator will act on the overlap whatever the B-rep says. MuJoCo collides
the convex hulls, and this overlap is an overlap of those hulls, so a rollout on this model will see
the solver push them apart. The effort check therefore measures with contact forces disabled, which is
why its torque is the load the gearing must hold rather than this overlap's contact forces; a torque
read from inverse dynamics with contacts enabled would be neither.
```

The hull fact is stated twice: "MuJoCo collides the hulls" and "MuJoCo collides the convex hulls".
That is exactly what the outside review heard. The reviewer's "neither.." with two dots is not in the
artifact; it is their speech layer joining a full stop to a leading dot. No literal `".."` exists in
this text.

Fix: `ai_cad/compiler/compile.py`, `_brep_note`. One sentence carries the fact and the status:

```
MuJoCo collides the convex hulls, and this overlap is an overlap of those hulls, so a rollout on this
model will see the solver push them apart; the status stays fail whatever the B-rep says.
```

Test: `TestExplanationReadsAloud` in `tests/test_twin_bundle.py` — no repeated sentence
(case/punctuation-insensitive), no repeated ten-word run, and `"mujoco collides"` appears once in the
note while `"status stays fail"` survives.

```
$ python -m pytest -q -p no:cacheprovider tests/test_twin_bundle.py -k "ExplanationReadsAloud or BrepNote"
6 passed, 24 deselected in 0.84s
```

**v1.2 unchanged.** No rebake, no re-tag, `demo-bundle-v1.2` stays the artifact of record. The fix
ships in the next bundle; logged in FINAL_STATUS under "Fixed in source, ships in the next bundle".

## S5 — v1.3: the page and the voice read one summary [verified: ran]

The page printed figures its own summary did not hold. The clearest one: the torque panel said the jaw
frame "differs by tens of mm" while the summary carried **70.69 mm**, because the panel read
`torque.js`, baked against an older `torque.json` than the one `build_summary` read. A recipient could
not reach the number the panel was hedging.

Fixed at the root rather than in the sentence: the page's torque, comparison, checks and twin panels
now read `summary.js` for every figure, and a checker enforces it.

```
$ python scripts/check_page_numbers.py
80 numeric tokens across torque-grp, cmp, checks, twin-grp all trace to the summary

$ python -m pytest tests/test_page_text_matches_summary.py -q -m heavy
2 passed in 10.18s
```

`scripts/check_page_numbers.py` renders the page from `file://`, takes the numeric tokens in those
four panels, and requires each to match a number in the summary JSON at the precision printed
(rounding allowed, metre↔millimetre and fraction↔percent allowed, hex digests ignored). "tens of mm"
fails it; so would any number typed into the HTML.

Other figures that moved onto the summary's account:

- stall 2.94 N·m and rated 0.98 N·m are now two rows; the old single row called the stall figure
  "rated", a threefold overstatement of headroom (`[verified: ran]`, `screens/torque.png`).
- the rung rows travel in `calibration.rungs`, so the blocked rung's reason (1.53 mrad, 998 N·m/rad,
  4096 counts) has one source; rung 5 prints once with both joints (`[verified: ran]`, `screens/twin.png`).
- the "what would identify friction" sentence prints again: a `$` anchor in `/torque or current
  logged, 1 percent$/i` matched nothing in the summary's scenario names and had silently sent the
  panel to its no-table fallback.
- `synthetic_preview.json` is now **in the package**: the page printed 270 → 224 mrad while a summary
  built from the archive had no preview block at all (`[verified: ran]`, fixture `calibration.twin_preview`).
- the header names the tag it was cut from, read from `manifest.js`, which the packager writes with
  `--tag` after checking the tag exists (`[verified: ran]`, `packaged demo-bundle-v1.3` in the page).

Page payload, rebuilt and measured rather than guessed:

```
budget 2500 -> 128,073 tris (pathological: the reducer overshoots and leaves ~500 per mesh)
budget 3000 -> 533,262 tris of 620,093 = 86.0%, largest mesh 3,370
budget 5000 -> 100% (14.8 MB, no reduction)
```

Chosen: 3,000. Recorded in the packaged README's "Mesh resolution" section and in `docs/demo/README.md`.

Package and tag:

```
$ python -m robocad twin unpack --zip docs/demo/so101_demo.zip --out <fresh dir>
32 files match the FILES.sha256 the package ships
$ python scripts/verify_demo_zip.py docs/demo/so101_demo.zip --built-from demo-bundle-v1.3 --out docs/demo/verify.json
[PASS] 1..4  VERIFIED
zip sha256 f86c28f703f84ccfcb3269233ad7a0ef88e2843172387728f5af7c01b6b569f3, 8,135,673 bytes
```

Hi-EV contract test on the refreshed fixture: `python -m pytest tests/test_robocad_tool.py -q` → **8
passed**.

**Tag correction, before publication:** `demo-bundle-v1.3` was first created on the code commit,
before the zip it names was in the tree, so `git show demo-bundle-v1.3:docs/demo/so101_demo.zip` would
have failed. Nothing had been pushed or handed out. The tag was deleted and recreated at the final
commit; no published artifact was moved.

**Not done:** `film.mp4` is still v1.2's; `docs/twin/so101/comparison.md` in the tree is still the
pre-S3 render and is not in the package. Both are in FINAL_STATUS under "Not done, stated plainly".

## E4 — "change infill to 30 percent" reaches a modelled mass [verified: ran]

The order: a spoken "change the infill to 30 percent" has to drive a real recompile and come back
with a mass the voice can say, bounded so the number always has a process behind it, and refuse
anything else. That is three pieces, and they are one path.

**1. The print model is a CLI input, and it is bounded there.** `twin compile` gained `--infill`,
`--wall-mm`, `--servo-mass-kg`, `--servo-source`. The bounds live in the CLI, not in `PrintModel`:
infill 0.1–1.0, wall 0.8–3.0 mm. Outside, exit 2 and the compiler never starts.

```
$ python -m robocad twin compile --step s.step --out out --infill 0.05
error: infill 0.05 is outside 0.1-1: below 0.1 is not a printable part and above 1.0 is solid, so the
mass would be a number with no process behind it
$ echo $?
2

$ python -m robocad twin compile --step s.step --out out --wall-mm 0.4
error: wall 0.4 mm is outside 0.8-3 mm: a wall thinner than 0.8 mm does not survive a print, and one
thicker than the part has no infilled interior to model
$ echo $?
2
```

**2. The assumption is announced before the compiler runs**, as a tooling phase at 0%, ahead of the
compiler's own first stage at 10%. The emitter refuses unknown stages, so `tooling:print_model` is in
`KNOWN_STAGES` on its own merit (`STAGES` still describes compiler stages only):

```
{"stage": "tooling:print_model", "pct": 0, "msg": "print model: 1.20 mm wall, 0.30 infill"}
{"stage": "import", "pct": 10, "msg": "83 parts, 259 instances"}
```

**3. `twin revise` compiles against the new print model and diffs it against the frozen bundle.**
New verb, in the help so a subprocess caller can find it:

```
$ python -m robocad twin --help
usage: robocad twin [-h] {summary,page,compile,revise,unpack} ...
```

The real run, on the SO-101 STEP at the pinned commit, 25m58s:

```
$ python -m robocad twin revise \
    --step "STEP/SO101/SO101 Assembly.step" --before docs/twin/so101/bundle \
    --out <tmp> --joints docs/twin/so101/bundle/robot.joints.yaml \
    --infill 0.30 --servo-mass-kg 0.055 \
    --servo-source "Feetech STS3215 product specification: weight 55 +/- 1 g" --json-progress
{"stage": "tooling:print_model", "pct": 0, "msg": "print model: 1.20 mm wall, 0.30 infill"}
...
{"stage": "properties", "pct": 45, "msg": "7 bodies, 0.955 kg modelled"}
{"stage": "checks", "pct": 97, "msg": "7 checks, worst fail"}
recompiled at 1.20 mm wall, 0.30 infill
links        7  (0 added, 0 removed, 7 changed)
printed mass 0.9017 kg -> 0.9555 kg (+6.0%)
solid bound  1.3320 kg -> 1.3320 kg (the solid is not a print assumption)
diff written <tmp>/diff.md
$ echo $?
0
```

0.9017 → 0.9555 kg, +6.0%, and the solid bound does not move: the same two numbers the frozen
`docs/twin/so101/revision_f030/diff.json` carries.

**A second defect, found by reading the table.** The compile above printed `0 changed` next to a 6%
mass rise, and `diff.md` said `unchanged` beside `+11.35 g` on every row: the status counted only
quantity and volume, so a print-model revision — which moves mass and no vertex — read as nothing
happened. `diff_links` now counts a mass change too. Re-rendered from the same two bundles, no
recompile and no new measurement:

```
links        7  (0 added, 0 removed, 7 changed)
| `base_so101` | changed | 150 | 150 | +0 | 204.732 | 204.732 | +0.00% | +11.35 |
```

`tests/test_revision.py` carries `test_a_mass_only_change_is_not_reported_as_unchanged`, 23 passed.

**A defect this exposed, and the guard that closes it.** The first real revise run came back
0.9017 → 0.6485 kg at *higher* infill, with the solid bound moving 1.3320 → 1.0413 kg. Cause: the
frozen bundle was compiled with six actuators and the revise run named none, so the servo CAD
envelopes were counted as printed PLA. The mass change was real, and it was not the revision.

Two fixes, because either alone is insufficient:
- `--servo-mass-kg` / `--servo-source` let the caller state the datasheet mass the frozen bundle used.
- a **solid-bound guard**: wall thickness and infill cannot change the solid, so if the two bundles
  disagree about `total_solid_mass_kg` the diff is refused — exit 3, and `diff.md` still written,
  carrying the reason, because a refused diff is evidence.

```
**Not comparable.** the solid bound moved 0.6485 kg -> 1.0413 kg, and wall thickness and infill
cannot change it: the two compiles differ by something other than the print model. ...
```

Tests, all green:

```
$ python -m pytest tests/test_twin_print_model.py -q
14 passed
$ python -m pytest tests/test_twin_cli.py tests/test_twin_print_model.py tests/test_twin_bundle.py \
    tests/test_demo_so101_twin.py -q
80 passed, 11 deselected
```

The tests drive the CLI with a stand-in compiler: the real compile needs the third-party STEP and 26
minutes of convex decomposition, and none of that is what the rules are about.

Documentation: `docs/demo/TRY_IT_YOURSELF.md`, deliberately **outside** the packaged README, which
ships inside `so101_demo.zip` — editing it after the tag would break re-derivation of the v1.3
package. Nothing here talks to hardware; the wall and infill figures are stated assumptions, not
measurements of a printed part.

**Not done:** `revise` does not re-run the effort check or the torque comparison against the new
bundle's masses; it reports printed mass and the link diff. The frozen `revision_f030` carries that
effort pair (0.652 → 0.687 N·m) and it came from the scripted path, not from the CLI.

**A third refusal, so the tool cannot be run without its assumption.** A caller who omits
`--servo-mass-kg` previously got 26 minutes of compile and then a refused diff. The frozen bundle
says how many bought-in parts it models, so the check belongs before the compile: if the bundle
models any and the mass is not stated, `revise` exits 2 in milliseconds and names both flags; a mass
with a blank `--servo-source` is refused the same way, because a number without its datasheet is the
claim this project does not make. No default is baked in — 55 g is one actuator's datasheet figure,
and a default would stamp it on every bundle the tool is run against (`docs/DECISIONS.md`).

```
$ python -m robocad twin revise --step s.step --before docs/twin/so101/bundle --out out --infill 0.30
error: the frozen bundle models 6 bought-in part(s) with no printed mass, and this compile was not
told their mass: pass --servo-mass-kg with --servo-source, or the servo envelopes are counted as
printed plastic and the solid bound moves for a reason that is not the print model
$ echo $?
2
# real 0m1.082s, against 25m58s for the compile it did not start
```

`tests/test_twin_print_model.py` grew to 16: the refusal, the blank-source refusal, and a test that
both flags reach the compiler together. With `tests/test_revision.py`:
**39 passed**.

**What a presenter experiences, measured.** Two refusals a demo will actually hit, both timed on this
machine against the real frozen bundle:

| command | what it says | wall clock | exit |
|---|---|---|---|
| `revise … --infill 1.5` | `infill 1.5 is outside 0.1-1: …` | 1.095 s | 2 |
| `revise … --infill 0.30` with no servo flags | `the frozen bundle models 6 bought-in part(s) …` | 1.082 s | 2 |
| `revise … --infill 0.30` with both flags | `printed mass 0.9017 kg -> 0.9555 kg (+6.0%)` | 25m58s | 0 |

Before the provenance check existed, the middle row cost the third row's 25m58s and then refused the
diff. The timings are wall clock on this laptop, not a benchmark; the compile time is dominated by
convex decomposition and will move on other hardware.

Full default tier on the final tree, after every edit above:

```
$ python -m pytest -q
852 passed, 309 deselected, 3 warnings in 663.26s (0:11:03)
```

309 are the heavy/slow/mujoco tests, deselected by the default tier's own marker configuration; they
are not skipped-with-reasons and this line does not claim they ran.

## E2 — a clean machine, and the four things it found [verified: ran]

Fresh directory, `git clone --branch feat/v1.1 --depth 1` from origin, fresh `python -m venv`, then
`pip install -e ".[dev]"`. Nothing ran in the working checkout, and every command below was typed
into that clone.

What worked on `.[dev]` alone, with `anthropic`, `mujoco`, `fastapi` and `openai` all **absent**:

```
$ python -m robocad twin summary --bundle docs/twin/so101/bundle --json
{"schema_version": "robocad.twin.summary/1", ...}   exit 0
$ python -m robocad twin unpack --zip docs/demo/so101_demo.zip --out unpacked \
    --verify-sha f86c28f703f84ccfcb3269233ad7a0ef88e2843172387728f5af7c01b6b569f3
  sha256 f86c28f7… (verified)
  33 files into …/unpacked
  32 files match the FILES.sha256 the package ships   exit 0
$ python -m robocad twin compile --step missing.step --out out --infill 1.5
error: infill 1.5 is outside 0.1-1: …                  exit 2
$ python -m robocad twin --help
usage: robocad twin [-h] {summary,page,compile,revise,unpack} ...
```

What did not work, and why each one matters:

1. **`twin page` died in a helper module.** `teardown_export/bake.py` raised
   `ModuleNotFoundError: No module named 'mujoco'` and the caller saw a traceback from a file they
   had never opened. MuJoCo is the `sim` extra on purpose, so `build_page` now checks and refuses:
   `error: building the page needs MuJoCo: … Install it with `pip install -e ".[sim]"`, or use the
   packaged so101_demo.zip, which is already baked` — exit 2. With `[sim]` installed the same command
   builds the page in **5.27 s**.
2. **PyYAML was in no dependency list.** `ai_cad/compiler/revision.py` imports it at module scope and
   `revise` imported that module *after* compiling, so the failure mode was 26 minutes of work
   followed by `ModuleNotFoundError: No module named 'yaml'`. Declared, and the import moved ahead of
   the compile so it fails in a second.
3. **`defusedxml` was in no dependency list.** `ai_cad/compiler/compare.py` imports it at module
   scope; anything that reached the comparison failed on import.
4. **The suite does not run on `.[dev]`.** 22 test modules import `anthropic`, 4 import `livekit`, and
   the packaging test imports `setuptools`, which a 3.12+ venv does not ship. The last one is fixed
   (`setuptools>=69` in `[dev]`); the first two are deliberate extras, and adding `importorskip` to 26
   test files to get green is exactly what this sprint's rules forbid. The requirement is stated
   instead: **the suite needs `pip install -e ".[dev,web,sim,ai,voice]"`, the CLI does not.**

The packaging tests earned their keep here: they refused a dependency with no licence row, so
`docs/THIRD_PARTY.md` gained `pyyaml 6.0.3 MIT` and `defusedxml 0.7.1 Python-2.0`.

Commits, each on `feat/v1.1`: `0b63ab0` (MuJoCo sentence), `043b06f` (pyyaml), `9f15a15`
(defusedxml), `4f56da0` (notice rows and setuptools).
