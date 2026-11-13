# Conventions: how the compiled bundle's joint origins relate to the official model

Comparing joint origins without these offsets gives misleading errors of several cm.

The compiled SO-101 and the published `so101_new_calib.urdf` describe the same robot but do not share a
zero pose or a base frame. Read raw, the two chains disagree by a median of **168 mm**, and that number
is a property of the comparison, not of the robot. With the conventions below applied, the five
upstream joint origins agree to **2.50 mm median, 5.95 mm p90, 11.25 mm maximum**.

## 1. Per-joint zero offsets

The published model's zero is a rotated pose of the compiled model's zero on five of the six joints.
The offsets are constant, applied to the compiled model, positive sign, and named by the official joint
they belong to:

| joint | official name | offset (degrees) |
|---|---|---|
| `joint_1` | `shoulder_pan` | −88.17 |
| `joint_2` | `shoulder_lift` | +90.29 |
| `joint_3` | `elbow_flex` | −90.31 |
| `joint_4` | `wrist_flex` | −0.15 |
| `joint_5` | `wrist_roll` | 0.00 |
| `joint_6` | `gripper` | fixed at zero; its origin is excluded from the residual |

A ±90° offset is not a small correction. Applied to a parent joint it rotates every downstream axis
with it, which is why a comparison that omits these offsets reports individual axes disagreeing by
115°, 65° and 175° on joints 1, 5 and 6 while the robot is in fact the same one.

## 2. Base-frame translation, no rotation

A pure translation of **(38.74, 6.64, −2.86) mm**, magnitude 39.40 mm, applied to the compiled model in
world coordinates. **No rotation.**

This was tested rather than assumed: an earlier ICP registration proposed a 10.303° base rotation, and
pinning the frame to it gives a 13.61 mm fit residual, while pinning it to identity gives 2.50 mm.
Identity is the better model of the frame. The ICP rotation is a registration bias — it fitted convex
hulls of a mostly planar base, which cannot constrain rotation about the plane normal.

## 3. What was measured, and how

| item | value |
|---|---|
| residual | Euclidean distance at each of the five joint origins, stacked over poses |
| poses | `numpy.random.default_rng(0)`, 100 samples, uniform −1.7 to 1.7 rad on all six joints |
| result | median 2.50 mm, p90 5.95 mm, max 11.25 mm |
| offsets fitted | see the table above; fitted, not copied from a datasheet |
| seeds | from the published vector and from zero both converge to the same vector at 2.50 mm |

Source: `docs/demo/twin/p0a_confirmation.json`, independently reproduced by the monitor session from
its own script on 2026-11-14. Where `docs/DECISIONS.md` prints the offsets as +90.28 and 6.63, the JSON
above is authoritative; the difference is a second-decimal transcription slip, not a second result.

## Why this is not a fit artifact

Three measurements use no registration at all, and all three agree:

- **Link lengths.** Consecutive joint-origin spacing is constant in joint angle and invariant under any
  rigid transform. Official against compiled, mm: 64.78 / 66.01, 116.00 / 116.06, 135.00 / 134.22,
  63.72 / 62.04, 36.18 / 36.73. Worst disagreement **1.69 mm**. Spread within each model: 0.000 µm.
- **Joint sense.** A frame-free triple product agrees on all six joints: the compiled joint turns the
  way the published joint turns.
- **Axis angles.** The angle between consecutive joint axes agrees to 0.00, 0.50, 0.71, 0.00, 0.00
  degrees.

A 2.50 mm residual sits inside those errors: the link error alone is 1.7 mm, and 0.7° of axis error
over a 0.35 m reach is about 4 mm.

## The jaw frame is a separate known-unknown

The compiled jaw origin is placed 5.74 mm from the published jaw link origin at rest, and **no gripper
zero offset reduces it** — the best scan still leaves 40.21 mm across poses. The jaw-to-wrist spacing
itself matches, 36.73 mm against 36.18 mm, so the arm is right and the jaw's own frame definition is
the outlier. Acceptance therefore uses frame-free invariants plus an explicit jaw number, not a
tip residual.

## What these conventions do not establish

The comparison is of joint origins. It says nothing about collision geometry, mass, inertia or contact
behaviour — that is where the `self_collision` fail and the oversized hulls live, and those are
reported separately in `bundle/report.json`. It is also one robot from one CAD source; generalisation
to another third-party model is untested.

## Consequence for any document or page that compares the two models

The sentence "the compiled robot moves wrongly by roughly seven centimetres" is not supportable and is
withdrawn. The supportable statement is that the compiled model reproduces the published kinematics
within its own link-length and axis-direction error once its zero pose and base translation are
applied — and that the bundle did not, before this file, state either convention.
