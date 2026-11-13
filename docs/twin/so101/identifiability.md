# Identifiability: what this data can and cannot tell us

SYNTHETIC method validation. Nothing here is a hardware measurement. Every number comes from plants
in a MuJoCo model of the SO-101 and attempts to recover them from simulated logs.

This file exists to answer one question honestly: **what would a partner have to log before friction
can be identified from their robot?** The blocked rung is the answer, not a failure.

## The rungs, and where they stopped

Each rung adds exactly one difficulty. Tolerance is declared before the run and not adjusted after.

| Rung | What it adds | Truth | Recovered | Error | Verdict |
|---|---|---|---|---|---|
| 0 | One joint, viscous damping only, noise free, 1 kHz | 0.080 | 0.0805 | 0.57% | **recovered** |
| 1 | Plus Coulomb friction | 0.080 / 0.150 | 0.0813 / 0.1487 | 1.6% / 0.86% | **recovered** |
| 2 | Plus a 3-sample command latency | 3 samples | 3 samples | exact | **recovered** |
| 3 | 62 Hz log rate, sensor noise, 4096-count quantisation | 0.080 / 0.150 | 0.494 / -0.197 | 517% / 231% | **blocked** |
| 4 | A second joint, noise free, 1 kHz | 0.080 / 0.150 | 0.0808 / 0.1488 | 1.2% / 0.8% | **recovered** |

Four of five rungs recover. The fifth does not, and the reason is arithmetic rather than tuning.

## Why rung 3 fails, in one paragraph

The published SO-101 servo has a position stiffness of about **998 N m per rad**. A 4096-count
encoder quantises position to **1.53 mrad**. One count of position error is therefore worth about
**1.53 N m** of commanded actuator torque. The friction signal being identified is roughly
**0.15 N m** (0.08 damping at about 1.9 rad/s). That is a **signal to noise ratio of 0.10**. No
estimator recovers a parameter buried ten times under noise; the data does not contain it.

The first attempt at this failed differently and the cause was mine: zeroing the other joints'
damping removed what keeps a very stiff servo stable, the simulation diverged, and the divergence was
fitted as friction. That is why the harness is built in rungs.

## What data would identify friction

Computed from the same arithmetic, at 62 Hz unless stated. SNR must reach 3 before a fit is worth
attempting; the column is the whole argument.

| Scenario | SNR | Crosses 3? |
|---|---|---|
| Position only, 12-bit encoder, 62 Hz (today's status quo) | 0.10 | no |
| Position only, 12-bit, averaged over 16 samples at 1 kHz | 0.39 | no |
| Position only, 16-bit encoder, 62 Hz | 1.57 | no |
| Position only, 16-bit, averaged over 16 samples at 1 kHz | 6.27 | **yes** |
| Position only, 20-bit encoder, 62 Hz | 25.08 | **yes** |
| **Torque or current logged, 1% of rated noise** | **4.48** | **yes** |
| Torque or current logged, 1%, averaged over 4 | 8.96 | **yes** |

Read plainly:

- **Sample rate alone does not fix it.** Raising 62 Hz to 1 kHz with a 12-bit encoder and averaging
  moves SNR from 0.10 to 0.39. Still not identifiable.
- **Encoder resolution mostly fixes it.** A 16-bit encoder plus 1 kHz averaging crosses, and a 20-bit
  encoder crosses at the published rate without any averaging.
- **A torque or current channel fixes it immediately**, at 1% noise, and that is the cheapest ask of
  the three. The SO-101's Feetech servos already report load and current; the published NAD dataset
  records `load1` to `load6` at 62 Hz.

## The ask, for a hardware partner

**One bench protocol, three runs plus one held-out, with the servo load or current channel logged at
62 Hz alongside position.** That single channel moves the identification from impossible to
comfortable and does not require new encoders or a faster bus.

If current or torque is not available, the second option is a 20-bit encoder or better on the joints
being identified, which is an invasive change and only worth it if the partner already plans it.

What is **never** identifiable from position data, at any rate or resolution, and is reported as such
rather than guessed: link mass and inertia at these speeds, gear efficiency, and the motor torque
constant without a separate bench characterisation.

## Reproducing

```
python -c "import mujoco,sys; sys.path.insert(0,'.'); from ai_cad.twin.identification import run, write; \
write(run(mujoco, '<so101_new_calib.xml>'), 'docs/demo/twin/identification.json')"
```

Scenario arithmetic: `docs/demo/twin/identifiability_scenarios.json`.
