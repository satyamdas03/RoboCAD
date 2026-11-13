# Final status, demo sprint

Written by the monitor session (Lane B). Updated as the sprint runs. Every claim carries a tag:
`verified-ran`, `verified-read`, `claimed`.

Deadline: Sat 14 Nov 2026, 22:00 Sydney.

## What a viewer can open right now

| Artefact | Path | State |
|---|---|---|
| Living page | `docs/demo/page/index.html` | Works offline from `file://`, `verified-ran` |
| Page integrity check | `teardown_export/check_page.py` | `verified-ran`, zero network requests |
| Baked trajectory | `docs/demo/page/trajectory.js` | 600 frames at 100 Hz from the official SO-101 model, `verified-ran` |
| Synthetic twin preview | `docs/demo/twin/synthetic_preview.json` | Produced, **labelled SYNTHETIC**, identification failed honestly, `verified-ran` |
| Walkthrough | `docs/demo/README.md` | Written, `verified-read` |
| Compiled bundle + report | `docs/twin/so101/bundle/` | **Not present yet**, Lane A in progress |
| Film | none | **Not recorded yet** |

## Verified numbers, Lane B

- Page loads from `file://` with the browser context offline: zero non-file requests. `verified-ran`
  Command: `python teardown_export/check_page.py docs/demo/page/index.html --shot shot.png`
- Render rate 54 to 58 fps headless at 83,122 triangles and 600 frames. `verified-ran`
- Page geometry matches MuJoCo exactly: world position of the first vertex of three mesh geoms agrees
  with `geom_xpos`/`geom_xmat` to 0.000 to 0.001 mm. This is the check that stops a pretty page from
  showing a wrong model. `verified-ran`
- Payload sizes: page HTML under 30 KB, three.js bundle 662 KB (MIT, credited), meshes 1.9 MB,
  trajectory 353 KB, all excluded from the 1 MB page rule as mesh and vendor payloads. `verified-ran`

## The synthetic twin, stated as it is

Generator: MuJoCo SO-101, planted per joint Coulomb friction, viscous damping, armature and a 16 ms
control latency, logged at 62 Hz with sensor noise and 4096 count encoder quantisation. `verified-ran`

Identification: least squares on the torque residual after removing rigid body torque, with a logged
acceleration channel and armature as a regressor. `verified-ran`

Result: **0 of 19 parameters recovered within tolerance.** Trajectory RMSE improves from 270 to 224
milliradians on a held out run, which is a fit, not a recovery. Every parameter is marked
`identifiable: false` in the output file. Control latency is reported as below the 16 ms sample
period and flagged, not guessed.

What is not identifiable, and is written into the artefact: link mass and inertia (never solved for),
rotor armature (weakly observable at 62 Hz), gear efficiency and motor torque constant (needs a bench
calibration).

This is a negative result, kept and labelled. It should be the first item in any partner conversation
about the Twin, because a partner will ask exactly this question.

## Decisions Satyam must confirm

1. The M2 `robot.joints.yaml` review: done by the lane that did not write it, criteria recorded in
   `docs/DECISIONS.md`.
2. The infill assumption for printed parts: not yet written into `materials.yaml`, so no compiled
   mass is fit to quote.
3. Publishing `docs/twin/so101/` as a derived work under Apache-2.0 with a NOTICE.

## Next three steps after the demo

1. Fix the identification, using a proper linear-in-parameters regressor with consistent states, and
   re-run the synthetic benchmark until recovery is demonstrated. Nothing about the Twin is credible
   until this passes.
2. Write the infill assumption and measured servo masses into `materials.yaml`, then produce the
   compiled-vs-official comparison. That comparison is the headline and it does not exist yet.
3. Record the film from the same baked timeline once the page is bound to the compiled bundle.
