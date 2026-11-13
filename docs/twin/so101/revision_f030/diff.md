# Revision diff: infill assumption f = 0.20 to f = 0.30

Before: `docs\twin\so101\bundle` (1.20 mm wall over 20% infill)
After: `docs\twin\so101\revision_f030\bundle` (1.20 mm wall over 30% infill)

Same pipeline, same STEP file, one input changed: the print model's infill fraction. The diff is keyed only on the link names in `robot.joints.yaml`.

## Sanity

- zero links added
- zero links removed
- every link with printed parts is heavier
- links with no printed parts are unchanged
- servos unchanged: actuator and joint blocks identical

All 5 hold. 0 added, 0 removed, every printed link heavier, bought-in only links unchanged, servos unchanged.

## Totals

| | before | after | change |
|---|---|---|---|
| printed mass (kg) | 0.9017 | 0.9555 | +0.0538 kg (+6.0%) |
| solid bound (kg) | 1.3320 | 1.3320 | unchanged, the solid is not a print assumption |

## Link by link

| link | printed parts | mass before | mass after | change | CoM moved (mm) | inertia diag change |
|---|---|---|---|---|---|---|
| `base_so101` | 149 | 0.2116 | 0.2229 | +0.0113 kg (+5.4%) | 0.33 | +6.4 / +7.6 / +6.8% |
| `rotation_pitch_so101` | 14 | 0.1391 | 0.1473 | +0.0082 kg (+5.9%) | 0.81 | +11.2 / +10.6 / +7.0% |
| `upper_arm_so101` | 14 | 0.0642 | 0.0746 | +0.0104 kg (+16.2%) | 0.13 | +15.7 / +15.9 / +15.7% |
| `under_arm_so101` | 22 | 0.1512 | 0.1617 | +0.0105 kg (+7.0%) | 1.01 | +6.4 / +7.9 / +7.0% |
| `wrist_roll_pitch_so100` | 45 | 0.2001 | 0.2058 | +0.0057 kg (+2.8%) | 0.12 | +2.3 / +3.1 / +2.4% |
| `wrist_roll_follower_so101` | 8 | 0.1201 | 0.1266 | +0.0064 kg (+5.3%) | 0.13 | +9.9 / +8.5 / +9.6% |
| `moving_jaw_so101` | 1 | 0.0154 | 0.0167 | +0.0013 kg (+8.3%) | 0.00 | +8.3 / +8.3 / +8.3% |

Mass, centre of mass and inertia are reported together because the infill assumption moves all three: inertia scales with the same factor as mass, and the centre of mass moves only where the added material is not symmetric about the old one.

The solid bound is printed beside the estimate in both bundles and does not move, which is the point of keeping it: it is the number that cannot be wrong in the direction that matters.

## What the extra mass costs at the joint

The same effort check runs inside both bundles, so the revision's cost can be read rather than argued:

| | demand | joint | share of its 2.942 N*m limit |
|---|---|---|---|
| f = 0.20 | 0.652 N*m | `joint_2` | 22% |
| f = 0.30 | 0.687 N*m | `joint_2` | 23% |

Both are measured with contacts disabled at a sample of poses, which is what makes them comparable to each other. A heavier print is a heavier arm, and the joint that carries the most of it is the same joint in both compiles.
