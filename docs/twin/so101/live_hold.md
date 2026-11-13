# Live hold: what the controller does with this bundle

A5 of the final sprint. The command is the one in the order:

```
python -m robocad.demo so101 --bundle docs/twin/so101/bundle --live --mode hold
```

Run headless (`--mode hold` without `--live`) so the numbers are reproducible here and in CI; the
viewer draws the run and does not drive it, and `_hold` uses one simulation loop for both paths. The
`--live` window itself was **not exercised**: this session has no display it can confirm, so the
viewer path is code that runs the same loop with `mj_step` and a `sync()`, and the claim here is about
the numbers, not about the window opening. Output, 2026-11-14, on the frozen bundle (`demo-bundle-v1`,
`f202c12`):

```
hold: commanded an extended pose for 2 s (2000 steps, headless)
steady-state joint error 573.26 mrad (peak 828.63 mrad)
per joint, mean error over the last 200 steps:
  joint_1                    573.26 mrad
  joint_2                     19.60 mrad
  joint_3                    508.69 mrad
  joint_4                      9.45 mrad
  joint_5                     12.43 mrad
  joint_6                    294.80 mrad
actuator saturation: 7533 step-instances at or above 99.9% of forcerange
```

**This is a fail, and the demo keeps replay mode.**

## Why it fails, in the model's own numbers

| joint | rest | commanded | final | error | holding force | limit |
|---|---|---|---|---|---|---|
| `joint_1` | 0.000 | 0.576 | 0.003 | 573 mrad | 2.942 N·m | 2.942 N·m |
| `joint_2` | 0.000 | 0.524 | 0.507 | 16 mrad | 1.456 N·m | 2.942 N·m |
| `joint_3` | 0.000 | 0.507 | −0.011 | 518 mrad | 2.942 N·m | 2.942 N·m |
| `joint_4` | 0.000 | 0.497 | 0.520 | 23 mrad | 2.942 N·m | 2.942 N·m |
| `joint_5` | 0.000 | 0.838 | 0.869 | 31 mrad | 2.942 N·m | 2.942 N·m |
| `joint_6` | 0.000 | 0.288 | −0.027 | 315 mrad | 2.942 N·m | 2.942 N·m |

Every joint is at or at the edge of its 2.942 N·m forcerange. That is the whole explanation: the
position gain in this bundle is the assumption `kp` = 20, and a 0.5 rad step at `kp` = 20 asks for
10 N·m — three times what the servo's stall torque allows. The command therefore saturates, and the
joint moves until the error is small enough that `kp * error` fits inside 2.942 N·m, which is about
0.15 rad. Joints 2, 4 and 5 reach their commanded pose because gravity loads them toward it; joints 1,
3 and 6 are loaded against it and stop near rest, pinned at the limit.

`kp` = 20 and `kv` = 1 are assumptions and the bundle says so: the real servo closes its own loop and
publishes no stiffness for a simulator to use. Holding a 0.5 rad step is a torque question, not a
stiffness question, and at 2.942 N·m this arm cannot do it against gravity with any reasonable gain —
which is a statement about this *pose*, not about the servos being undersized, because the effort
check that matters (`limits_and_effort`) holds the reference pose and both travel ends and needs at
most 0.652 N·m there.

Contacts make it worse, not better: this bundle's collision hulls overlap by 7.9 mm at rest, the same
overlap that makes `self_collision` fail, and with contacts enabled three joints are held near rest
with 61 contacts active in the scene. Disabled, the arm sags differently — joints 5 and 6 then carry
the error — so the hull overlap changes *which* joints fail, not whether the hold works.

## What ships instead

Replay mode, which is what the film is recorded from: the bundle's recorded motion, not a controller
being asked to hold a pose it cannot reach. If a hold is wanted for the demo later, the honest fix is a
torque-based controller with the gains identified from data — that is Phase 2 calibration, not
something to fake here.
