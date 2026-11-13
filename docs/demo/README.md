# SO-101 demo: open this first

`so101_demo.zip` is the whole demo. Unzip it anywhere and open `index.html` in a browser. No server,
no network, no install. Every number on the page is read from the compiled bundle's `report.json`,
and the provenance line at the top says which bundle and which checks are shown.

## 3 minute script

1. **0:00, compiled from its own CAD.** Open `index.html`. Read the provenance line aloud: this is
   the SO-101 compiled from the STEP file exported from the SO-ARM100 repository at commit
   `a758567`, not a hand-written model. The 3D geometry is the bundle's own visual meshes,
   decimated to 128k of its 620k triangles so a browser can hold it.
2. **0:30, the seven checks.** Point at the Checks panel. Five pass. `self_collision` **fails**: two
   convex hulls overlap 7.9 mm at rest. The B-rep solids touch and share 0.52 mm3, which is
   contact-scale, so MuJoCo will act on a contact the CAD does not have. The report carries 265
   warnings, including 26 parts whose hulls are more than 3x their own volume. None of this is
   hidden, and none of it is a passing light.
3. **1:00, same robot as the official model.** Comparison panel: joint axes agree within **1.05°**
   rms, worst 2.14°. Joint origins look wrong by up to 110 mm **until the zero-pose conventions are
   applied**, and then they agree at **2.50 mm median / 11.25 mm worst**. Frame-free link lengths
   agree to **1.69 mm**, which no registration can fake. See `CONVENTIONS.md`.
4. **1:30, masses with their assumptions.** Solid upper bound **1.332 kg**, print model **0.902 kg**,
   published **0.632 kg**. The print model assumes 1.2 mm walls and 0.20 infill, so printed mass is a
   range, not a measurement. Servos use 55 g datasheet mass through their CAD envelope.
5. **2:00, what that does to the motors.** Torque panel: required torque for the same trajectory on
   both models, with the bundle's own 2.94 N m actuator limit drawn as a dashed line. Peak 1.26 N m
   official against 0.63 N m compiled, so neither saturates on this motion.
6. **2:30, the revision.** `diff.md`: the same pipeline recompiled at 0.30 infill, diffed per link on
   the same link names.
7. **2:45, calibration and what we need.** Twin panel: four of five identification rungs recover
   their planted values. The fifth cannot, and the page says why: a 4096-count encoder is 1.53 mrad,
   the servo is 998 N m per rad, so position quantisation is 1.53 N m of torque noise against a
   0.15 N m friction signal. **A motor-current channel takes that SNR from 0.10 to 4.48.** That is
   the ask: three excitation runs and one held-out, with the servo load channel logged.

## Real versus synthetic

| Artefact | Status |
|---|---|
| SO-101 CAD, URDF, MJCF | Real, third party, Apache-2.0, pinned at `a758567` |
| Compiled bundle, checks, comparison, torque | Real output of the compiler on that CAD |
| Page, film | Rendered from the compiled bundle and its report |
| Synthetic twin preview and rungs | **SYNTHETIC.** Planted parameters in simulation; no hardware |
| Live viewer | Local MuJoCo viewer against the same bundle |

Nothing here is a hardware measurement. No robot was commanded.

## Known limits

- Joint origins require the zero-pose conventions to compare at all; a naive comparison reports
  errors of several centimetres that do not exist.
- Printed masses are a model built on two stated assumptions, not measurements.
- `self_collision` fails for a simulator-geometry reason, and the check is not softened.
- The identification result is a method validation on synthetic data, and it stops at the rung where
  the data runs out of information.
