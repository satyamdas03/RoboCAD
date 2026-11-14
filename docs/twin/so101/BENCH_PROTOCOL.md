# Bench protocol: 15 minutes, one robot, one file

This is what a partner runs to give us data we can actually identify a model from. It needs no
programming, only the robot's own control software and a way to log.

The measurement below is why this exists. From position-only logs at 62 Hz, friction is **not
identifiable**: a 4096-count encoder is 1.53 mrad, the servo is about 998 N m per rad, so one count
of position error is 1.53 N m of torque noise against a 0.15 N m friction signal, a signal to noise
ratio of **0.10**. Add the motor current channel and Coulomb friction comes back within tolerance on
both joints tested, because the quantity being fitted stops being a difference of two large numbers.
That single channel is the whole ask.

## What to log

Per sample, per joint, at **62 Hz or faster**:

| Channel | Why | Required |
|---|---|---|
| Joint position | the state | yes |
| Joint velocity, if the controller provides it | avoids differencing quantised position | preferred |
| **Motor current, or load register** | the torque proxy, and the thing that makes this work | **yes** |
| Bus voltage | current to torque depends on it | yes |
| Motor temperature | warm magnets lose torque; lets us bound it | yes |
| Commanded position or torque | what was asked for, for latency | yes |

File format: **CSV, one row per sample**, first row a header, one column per channel named
`<joint>_<channel>`, plus `timestamp_s`. The SO-101's Feetech servos report load and current directly,
so this is a matter of dumping the registers you already read for control.

## The routine, 15 minutes

1. **Mount the robot clear of the bench.** No payload. Nothing within 20 cm of the arm. A human
   supervises and keeps a hand on the emergency stop for the whole run.
2. **Tag the hardware.** Write `revision.yaml` next to the log: robot id, CAD revision or date, servo
   model, firmware version, what is bolted on, date, and your name. One file, six lines.
3. **Warm up, 2 minutes.** Move every joint slowly through its full range 10 times. This is for
   temperature and lubrication, not for data.
4. **Run the excitation, 6 minutes.** For each joint in turn, move only that joint, with the others
   held at mid-range, following a multi-sine: three to five sine waves summed, 0.2 to 1.0 Hz, using
   60 percent of the joint's range. Six seconds per joint, two repetitions. If your controller has a
   scripting interface, this is a short loop; if not, the same motion done by hand at varying speed
   still helps, just worse.
5. **Run one held-out motion, 3 minutes.** Different frequencies from the excitation, same joint
   order. This is the only honest way to test a calibration, so it is not optional.
6. **Repeat steps 4 and 5 once, so there are at least three excitation runs and one held-out run.**
   Uncertainty intervals need more than one run; a single run supports neither a bootstrap nor a
   held-out split.
7. **Export and name.** `<robot>_<revision>_<excite|heldout>_<n>.csv`, zip them with `revision.yaml`.

## What we return

Send us the zip and we return a calibrated model with **an interval on every parameter**, a list of
what the data could not identify, and a simulator file that reproduces the held-out run to a stated
error. Parameters we cannot identify are reported as ranges or as unidentifiable, never as point
estimates.

## Limits and honesty

- Joint and torque limits are the robot's own; do not disable them for this.
- If a joint cannot move 60 percent of its range safely, use what it can and say so.
- Nothing here commands a robot without a human present. The run is supervised start to finish.
- This protocol has been validated on **synthetic** logs only. It has not been run on hardware, and
  the tolerances quoted in `identifiability.md` come from simulation.
