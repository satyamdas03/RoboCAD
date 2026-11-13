# RoboCAD Twin demo, 3 minute walkthrough

What this folder contains today, stated plainly, because the honest version is more useful than a
polished one.

## Open this first

`docs/demo/page/index.html`, opened directly from disk in a browser. No server, no network. It is a
single page plus three classic scripts, chosen because a page served from `file://` cannot use
`fetch` or ES modules.

What the page shows: the SO-101 model in 3D, orbiting, with per-link mass bars, per-joint angle and
actuator torque read from a baked MuJoCo trajectory, and isolate, exploded and CoM views. The
provenance line in the header states which model is loaded and says whether it is synthetic.

**Right now the provenance line reads `so101_new_calib.xml`, the official SO-101 MuJoCo model at the
pinned commit, not our compiled bundle.** The page switches when Lane A tags `demo-bundle-v1`. Until
then, every number on the page comes from the official model and the page says so on screen.

## The 3 minute script

1. **0:00** Open the page. Point at the provenance line: this is the official SO-101 model, and the
   page tells you that rather than letting you assume it is ours.
2. **0:30** Press Play. Six joints sweep, the gripper opens and closes. Every value in the right hand
   panel is read from the baked trajectory, not typed in. Point at a torque value and say: this is
   what the model says the actuator needs at this instant.
3. **1:00** Click a link in the Links panel. It isolates. Press Exploded to pull the chain apart along
   the joint axes. Press CoM to show the centre of mass markers.
4. **1:40** Open `docs/demo/twin/synthetic_preview.json`. Read the disclaimer at the top, and read
   the `not_identifiable` list. This is the Twin half: synthetic logs with planted friction, damping,
   armature and latency, and an attempt to recover them.
5. **2:30** Read the numbers honestly. The trajectory error improves from 270 to 224 milliradians
   after the fit, but **the parameter recovery did not work**: 0 of 19 planted parameters were
   recovered within tolerance, so every one is marked `identifiable: false`. The method and its
   failure are both in the file.
6. **2:50** Close on the limits below, out loud, not as a footnote.

## What is real, what is synthetic

| Artefact | Status |
|---|---|
| SO-101 CAD and official URDF/MJCF | Real, third party, Apache-2.0, pinned at commit `a758567` |
| The 3D page and its baked trajectory | Real MuJoCo simulation of that model, deterministic |
| Page numbers | Read from the baked MuJoCo model, not hand written |
| Synthetic twin logs | **SYNTHETIC.** Generated from the model with planted perturbations |
| Recovered parameters in `synthetic_preview.json` | **SYNTHETIC and not yet recovered.** Marked `identifiable: false` |
| Compiled-from-CAD bundle | Built by Lane A; its checks are shown on the page with the honest red |
| Film | **Not recorded yet** |

Nothing in this folder is a real robot measurement. No hardware was touched.

## Known limits

- Joint axes and origins, masses and inertias in the compiled comparison are not in this build yet;
  the compiler side is being finished in Lane A.
- Mass honesty: printed parts at solid PLA are an upper bound, not a mass. Nothing printed from the
  compiler is fit to quote until an infill assumption is written into `materials.yaml`.
- The synthetic identification does not yet recover planted parameters. This is a real negative
  result, kept and labelled rather than tuned until it looked good.
- The page runs at 54 to 58 fps headless on this machine at 83k triangles; no claim is made about
  other hardware.

## Reproducing it

```
python teardown_export/bake.py <model.xml> docs/demo/page --seconds 6 --hz 100 --triangles 3000
python teardown_export/check_page.py docs/demo/page/index.html --shot shot.png
python -c "import mujoco,sys; sys.path.insert(0,'.'); from ai_cad.twin.synthetic import run_preview, write_preview; write_preview(run_preview(mujoco, '<model.xml>'), 'docs/demo/twin/synthetic_preview.json')"
```

The official model and its 19 MB of STL assets are deliberately outside the repository; download
them at the pinned commit before running the commands above.
