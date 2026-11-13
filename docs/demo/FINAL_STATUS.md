# Final status, demo sprint

Owner of this file: monitor session (Lane B). Updated 2026-11-14. Every claim carries a tag:
`verified-ran`, `verified-read`, `claimed`. Deadline: Sat 14 Nov 2026, 22:00 Sydney.

## Open this first, in this order

1. `docs/demo/page/index.html` — open it directly from disk. No server, no network. Living page.
2. `docs/demo/film/so101_demo.mp4` — 24 s, recorded from that same page.
3. `docs/demo/twin/identification.json` then the page's "Twin method" panel — the identification
   rungs and exactly which one is blocked.
4. `docs/demo/README.md` — the 3 minute walkthrough and the real-versus-synthetic table.
5. Lane A's `report.html` and comparison, at whatever path Lane A names.

## What the page shows today

| Element | Source | State |
|---|---|---|
| 3D view | published SO-101 visual meshes | `verified-ran`, offline, 51 to 58 fps |
| Link masses, total 1.041 kg | compiled bundle `report.json` | `verified-ran` (report read, page bound) |
| Seven checks, worst `fail` | compiled bundle `report.json` | `verified-ran` |
| Required torque per joint | inverse dynamics, both models | `verified-ran` |
| Kinematics vs official | sense-searched datum fit | `verified-ran` |
| Twin method rungs | `identification.json` | `verified-ran` |
| Provenance line | states every split above on screen | `verified-ran` |

## Verified numbers

- Page loads from `file://` with the browser context offline: **zero non-file requests**. `verified-ran`
- Page geometry matches MuJoCo to **0.000 to 0.001 mm** on three mesh geoms. `verified-ran`
- Render 51 to 58 fps headless at 83k triangles, 600 frames, page HTML under 30 KB. `verified-ran`
- Compiled bundle: 7 bodies, 6 hinge joints, 433 collision hulls, 1.0413 kg, checks
  `meshes_load` pass, `inertia_valid` pass, `pose_equivalence` pass at 0.000 m over 100
  configurations, `mujoco_load` pass, `self_collision` **fail**, `limits_and_effort` warn,
  `free_base_stand` skipped. `verified-read` from `report.json`
- Joint axes agree with the published model within **2.14 degrees** (rms 1.05) after a
  sense-searched datum fit over all 64 sense combinations. `verified-ran`
- Joint **origins** do not agree: perpendicular offsets **94.2, 110.3, 54.0, 54.7, 27.7, 54.5 mm**.
  The repeating ~54 mm is unattributed and is the open question in the comparison. `verified-ran`
- Self-collision: hulls overlap **7.9 mm** at rest. The B-rep solids touch and share **0.52 mm³**
  across 47 of 47 shape pairs, which is contact-scale, not a statement that the parts fit together,
  against a 32.27 cm³ wrist and 20.69 cm³ jaw. Hull overlap is real for the simulator; the solids
  do not interfere. `verified-read` from Lane A, corrected after their unit bug
- Identification rungs 0, 1, 2 and 4 recover (0.57, 1.6/0.86, latency exact, 0.12/0.56 percent).
  Rung 3 is blocked. `verified-ran`
- Default test tier at `c7a6544`: 520 of 808 collected, measured in an isolated worktree.
  `verified-ran`. Not re-run at the final commit; the sprint stopped that work by instruction.

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

1. **Printed mass is an upper bound at 100 percent fill.** The compile layer counts printed plastic
   as solid PLA at the material library density, `materials.py` `"pla": 1240.0` kg/m3, and the report
   field is `printed_mass_upper_bound_kg`. There is **no wall thickness and no infill fraction**
   anywhere in the compile layer; a page line claiming "1.2 mm wall, 0.20 infill" would describe a
   model that is not in the bundle, so the page does not claim it. `verified-read` from Lane A.
2. **Servo mass, 55 g plus or minus 1 g**, sourced to the Feetech STS3215 product specification
   document (feetech.cn); the code carries the document name, not a URL. It enters the
   comparison only, as the figure that reconciles our mass against the published mass. It does **not**
   enter the bundle's mass properties, which is why `actuator_mass_kg` is null; a reader who assumes
   55 g is already inside our body masses would overstate every body. `verified-read` from Lane A.
3. **Publishing `docs/twin/so101/`.** Satyam authorised this in the sprint directive, verbatim:
   "Publish docs/twin/so101/: YES. Add docs/twin/so101/NOTICE.md crediting the SO-101 project, its
   Apache-2.0 licence, the pinned commit, and a list of what we changed." What is still true: the
   directory is **uncommitted**, `NOTICE.md` is not written, and no `demo-bundle-v1` tag exists,
   because Lane A will not commit derived CAD on a relayed instruction. Nothing in this folder
   describes it as published.
4. **M2 YAML review**: cross-reviewed by the lane that did not write it, criteria recorded in
   `DECISIONS.md`. M2 stays `[~]` while the YAML is uncommitted for the licence question.

## What is deliberately not shipped

- **Compiled collision-hull visuals on the page.** The bundle ships 433 convex hulls and no visual
  meshes; rendered, they look like a pile of blocks. The bake exists at `docs/demo/page_compiled/`
  and switching is one file copy once the bundle carries visual meshes. The page instead renders
  published meshes and states that split on screen.
- **Film re-record against compiled visuals**, for the same reason. The shipped film is honest: it
  is the page as it stands.
- **Official-model toggle**, cut by the sprint's own cut order.
- **Heavy test tier**, stopped by instruction; one frozen Labs test exceeds 900 s.

## Next three steps after the demo

1. Attribute the ~54 mm perpendicular joint-origin offset. The hypothesis on the table is that the
   axis point is taken on a mating cylindrical face rather than at the bore centre, which would make
   the offset look like a radius. Lane A is testing it against the six bore radii.
2. Carry visual meshes in the bundle, then switch the page and re-record the film against compiled
   geometry.
3. Widen the identification to a real torque or current channel so a partner's bench log can be
   identified at 62 Hz, which is the only way the Twin's central claim becomes checkable outside
   this machine.
