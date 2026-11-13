# SO-101: compiled twin against the published model

Generated 2026-11-13T15:54:40+00:00 from `so101.step`.

- Bodies: 7  Joints: 6  Parts: 83  Instances: 259
- Collision hulls: 433
- Joint limits: from SO-ARM100 so101_new_calib.urdf, sha256 3a65d2d35e68a8d2f0c2cc176d19b884506543c93ba72980145b80abe276022c, at revision a758567c3978dfeefe282ede0500085a48fe8f78, joint <limit> elements. Not derived from the CAD: the STEP file carries no travel limits.

## Checks

| check | status | what it measured |
|---|---|---|
| `meshes_load` | pass | 692 of 692 meshes loaded as mesh geoms from 433 collision hull(s) and 259 visual mesh(es), 0 warning(s). |
| `inertia_valid` | pass | Every body's tensor is positive definite and satisfies the triangle inequality. |
| `pose_equivalence` | pass | URDF and MJCF agree to 0.000e+00 m over 100 random configurations and 0.000e+00 m at rest, against a 1e-06 m tolerance. |
| `mujoco_load` | pass | Loaded with zero warnings; 1000 passive steps at 0.0020 s stayed finite. |
| `self_collision` | fail | 1 non-adjacent pair(s) overlap, deepest -7.939e-03 m. The CAD solids of wrist_roll_pitch_so100 and moving_jaw_so101 intersect and share 0.52 mm3 of material, so part of that overlap is real and part of it may be the hull; this measurement does not split the two. The status stays fail either way: MuJoCo collides the hulls, so the simulator will act on the overlap whatever the B-rep says. MuJoCo collides the convex hulls, and this overlap is an overlap of those hulls, so a rollout on this model will see the solver push them apart. The effort check therefore measures with contact forces disabled, which is why its torque is the load the gearing must hold rather than this overlap's contact forces; a torque read from inverse dynamics with contacts enabled would be neither. |
| `limits_and_effort` | pass | 6 joint(s) carry a travel limit and 6 actuator(s) state a force limit, from SO-ARM100 so101_new_calib.urdf, sha256 3a65d2d35e68a8d2f0c2cc176d19b884506543c93ba72980145b80abe276022c, at revision a758567c3978dfeefe282ede0500085a48fe8f78, joint <limit> elements. Not derived from the CAD: the STEP file carries no travel limits. The largest demand at the sampled poses is 0.652 N*m on joint_2, 22% of its 2.942 N*m limit, measured with contacts disabled and at a sample of poses rather than a search over all of them. |
| `free_base_stand` | skipped | the base body carries no free joint, so there is no balance to test; this check applies to legged robots only |

## Notes

- Axes and origins come from the servos' output shafts and drive-horn placements in the CAD.
- Topology order comes from the CAD assembly names, not from geometry.
- Joint limits come from SO-ARM100 so101_new_calib.urdf, sha256 3a65d2d35e68a8d2f0c2cc176d19b884506543c93ba72980145b80abe276022c, at revision a758567c3978dfeefe282ede0500085a48fe8f78, joint <limit> elements. Not derived from the CAD: the STEP file carries no travel limits.
- Every mass rests on an assumed density unless a part was weighed; the per-body flag says which, and the report never presents an assumed mass as a measurement.
- The printed/actuator/fastener split comes from the CAD part names. On this file 13 parts carry generic names (SOLID, Component1..7) and cannot be placed by name, so they are counted as unclassified and their volume is reported separately rather than folded into either side of the split.
- Each actuator carries a datasheet mass of 0.0550 kg: Feetech STS3215 product specification (STS3215-PRODUCT_SPECIFICATION.pdf, feetech.cn): weight 55 +/- 1 g, both the 7.4 V and the 12 V variant. It is applied as the density that reproduces that mass through the part's own CAD envelope, so the mass is the datasheet's and the centre of mass and inertia remain the envelope's. It is not a weigh-in, and it is one figure applied to every actuator rather than one per unit.
- Each of the 6 joints carries a position actuator with a force limit of 2.94199 N*m stall, from Feetech ST3215 12 V variant: stall torque 30 kg*cm (2.942 N*m), rated load 10 kg*cm (0.981 N*m), as published at docs.waveshare.com/ST3215_Servo and in the RobotShop and TorqueMicro listings for that variant. The torque is NOT taken from the Feetech product-specification PDF cited for the 55 g mass, which documents the 7.4 V variant (19.5 kg*cm stall, 5 kg*cm rated); continuous rating 0.980665 N*m. The limit is the figure the datasheet states for this servo; the torque each joint is actually asked for is measured by inverse dynamics and reported under limits_and_effort. kp = 20 N*m/rad and kv = 1 N*m*s/rad are ASSUMPTIONS, not datasheet values: the servo closes its own control loop and publishes no stiffness for a simulator to use. Every torque figure below was measured against these gains.
- The collision model is 151 convex hulls over 83 parts. 13 part(s) are covered by hulls that inflate them beyond 3x their own solid volume and 4 did not tessellate to a closed surface, so on those parts the hulls are an envelope rather than a shape. self_collision is FAIL on 1 non-adjacent pair(s). That is a statement about the hulls, which are what MuJoCo collides; the same check measures the B-rep of the same bodies, and where the solids only touch, the overlap is the convex approximation rather than an interference in the CAD. The status stays fail either way: the simulator acts on the hulls.
- 259 visual mesh(es), 620,093 triangles, 19.38 MB, written with contype and conaffinity zero so the simulator never collides them. They are the B-rep tessellated coarsely rather than the collision hulls, so what a viewer draws is the part's own surface. One file is written per placed instance, in the body frame, so a part used several times is written several times. Where a part was coarsened, its vertices moved by up to 1.20 mm on the coarsest one -- a visible bevel at demo zoom, stated rather than hidden; the per-part warnings give each part's own figure and say which grid it was reduced on. That is inside the 24 MB budget set for visual geometry; the per-part warnings give the grid cell any part was clustered on to get there.
- Masses in this report are a shell-and-infill estimate at 1.20 mm wall over 20% infill; the solid bound is reported beside it and is never replaced. The centre of mass is held at the solid's centre and the inertia tensor is scaled by the same factor as the mass, which is an approximation stated here rather than hidden in the arithmetic.

## Mass: RoboCAD against SO-ARM100 so101_new_calib.urdf

| body (ours) | body (theirs) | ours kg | printed only (ub) kg | print estimate kg | theirs kg | delta g | delta % | fill vs whole mass | printed fill |
|---|---|---|---|---|---|---|---|---|---|
| `base_so101` | base_link | 0.2116 | 0.2452* | 0.2116 | 0.1470 | +64.6 | +43.9% | 0.58 | 0.38 |
| `rotation_pitch_so101` | shoulder_link | 0.1391 | 0.1316* | 0.1391 | 0.1000 | +39.1 | +39.1% | 0.64 | 0.34 |
| `upper_arm_so101` | upper_arm_link | 0.0642 | 0.0000* | 0.0642 | 0.1030 | -38.8 | -37.7% | 0.70 | — |
| `under_arm_so101` | lower_arm_link | 0.1512 | 0.0462* | 0.1512 | 0.1040 | +47.2 | +45.3% | 0.56 | 1.06 |
| `wrist_roll_pitch_so100` | wrist_link | 0.2001 | 0.0918* | 0.2001 | 0.0790 | +121.1 | +153.3% | 0.53 | 0.26 |
| `wrist_roll_follower_so101` | gripper_link | 0.1201 | 0.0462* | 0.1201 | 0.0870 | +33.1 | +38.1% | 0.71 | 0.69 |
| `moving_jaw_so101` | moving_jaw_so101_v1_link | 0.0154 | 0.0257 | 0.0154 | 0.0120 | +3.4 | +28.5% | 0.47 | 0.47 |
| **total** | | **0.9017** | **0.5867** | **0.9017** | **0.6320** | **+269.7** | **+42.7%** | | |

## Joint-to-joint spacing (no frame needed)

| joint | to joint | ours (mm) | theirs (mm) | delta (mm) | delta % |
|---|---|---|---|---|---|
| `joint_1` | `joint_2` | 66.01 | 64.78 | +1.23 | +1.90% |
| `joint_2` | `joint_3` | 116.06 | 116.00 | +0.06 | +0.05% |
| `joint_3` | `joint_4` | 134.22 | 135.00 | -0.78 | -0.58% |
| `joint_4` | `joint_5` | 62.04 | 63.72 | -1.69 | -2.65% |
| `joint_5` | `joint_6` | 36.73 | 36.18 | +0.55 | +1.52% |

## Frame alignment

| | value |
|---|---|
| method | rotation fitted to the joint axis directions (with a search over axis senses), translation from the anchor centroid |
| joints used | 6 |
| rotation (axis x angle, deg) | -0.275 -0.521 +89.799 |
| translation (m) | +0.1259 -0.0043 +0.0536 |
| axis senses used | +1 +1 +1 +1 -1 -1 |
| rotations that fitted equally | 4 |
| axis residual, RMS (deg) | 1.05 |
| axis residual, worst (deg) | 2.14 |
| anchor residual, RMS (mm) | 77.541 |
| anchor residual, worst (mm) | 110.343 |

## Joint axes

| joint (ours) | joint (theirs) | ours axis (CAD world) | ours in their frame | theirs axis (world, rest) | angle after carry | anchor delta (mm) | along axis (mm) | perpendicular (mm) |
|---|---|---|---|---|---|---|---|---|
| `joint_1` | shoulder_pan | +0.000 +0.009 -1.000 | +0.000 +0.003 -1.000 | -0.000 +0.000 -1.000 | 0.16° | 108.96 | -54.80 | 94.18 |
| `joint_2` | shoulder_lift | +1.000 +0.009 +0.000 | -0.005 +1.000 +0.003 | -0.000 +1.000 +0.000 | 0.34° | 110.34 | -1.24 | 110.34 |
| `joint_3` | elbow_flex | +1.000 +0.009 +0.009 | -0.005 +1.000 +0.011 | -0.000 +1.000 +0.000 | 0.72° | 53.96 | +0.59 | 53.96 |
| `joint_4` | wrist_flex | +1.000 -0.000 +0.017 | +0.003 +1.000 +0.020 | -0.000 +1.000 +0.000 | 1.17° | 54.78 | +2.19 | 54.73 |
| `joint_5` | wrist_roll | +0.000 -1.000 -0.009 | +1.000 -0.003 +0.000 | -1.000 -0.000 -0.000 | 0.20° | 56.09 | +48.77 | 27.70 |
| `joint_6` | gripper | +1.000 -0.000 +0.009 | +0.003 +1.000 +0.011 | +0.000 -0.999 -0.049 | 2.14° | 54.49 | +0.42 | 54.48 |

## Notes

- Ours is measured from the CAD B-rep at a stated density. Theirs is the value published in the official model. Neither is adjusted to match the other.
- The body correspondence is a judgement from the two naming schemes and is printed beside the numbers so it can be disputed.
- Some of our bodies rest on an ASSUMED material density; their mass is therefore an estimate, not a measurement, and the report says which.
- The official model accounts for 0.6320 kg. Our joints imply 6 actuators, and at Feetech STS3215 product specification (STS3215-PRODUCT_SPECIFICATION.pdf, feetech.cn): weight 55 +/- 1 g, both the 7.4 V and the 12 V variant they weigh 330 g, which is 52% of their total. That leaves 302 g for every printed link and fastener. Our printed parts alone are 587 g at 100% solid, so the arithmetic is consistent with their masses being whole-body masses that include the servos, at a fill fraction well under solid. That is a reading of the numbers, not a statement of their method.
- The printed-only column counts parts whose CAD names classify them as links. Parts with generic names (SOLID, Component1..7) are left out of it rather than guessed into it, so it is a lower bound on printed plastic, not a total; a body marked with an asterisk carries such parts, and a printed-only figure of 0 for that body means only that no part on it could be identified as printed.
- The fill column is derived, not assumed: the official mass divided by the mass our geometry would have as 100% solid PLA (1240 kg/m3). Read against a body's whole published mass it can exceed a real fill fraction, because a servo is not plastic.
- The printed-fill column removes one actuator per joint from their body mass and divides what is left by our printed-only upper bound. It assumes their link masses include the servo that link carries, which is the common convention and is stated here rather than silently applied.
- The print estimate is a model, not a measurement: each body's parts as a shell over infill at the wall thickness and infill fraction stated in the bundle, except the bought-in ones. Those bodies weigh 1.3320 kg at 100% solid and 0.9017 kg under the model. 6 bought-in part(s) keep their datasheet mass and are not reduced, so the change is smaller than the infill fraction alone would suggest. The model's centre-of-mass and inertia treatment is stated in the bundle's warnings. The infill fraction is a choice, not a finding: read the interval across infill fractions, not this single number.
- The joint-to-joint spacings are printed before the frame alignment because no change of frame can alter them: a rotation and a translation move both ends of a segment by the same amount, so their agreement is not a consequence of the fit. The largest difference is 1.7 mm between joint_4 and joint_5. A difference in the pose the two files were stored in would show up here too, so agreement means the links are the same length and both files are in much the same configuration.
- Our world datum and theirs are different choices of origin and axes, so one rigid transform is fitted over the 6 joints both files place and ours is carried into their frame before any angle is computed. The rotation is fitted to the axis directions and the translation to the anchor centroid. It is a change of frame, not a correction of the robot: the axis angles and anchor distances below are the residual after it.
- The rotation is fitted to the axis directions rather than to the anchor positions. An anchor is a poor constraint on a rotation: a revolute joint's origin is free to sit anywhere along its own axis, and a difference in the pose the two files were stored in moves every anchor at once. Fitting the rotation to anchors spends both of those on the rotation and reports the robot as worse than it is.
- 4 sense combinations fitted the axis directions within 0.25 degrees of each other, so the directions alone did not decide the datum. The anchors chose between them, and the rotation printed above is the one they chose. A reader who disagrees with that tie-break should know the axis agreement would look the same under the others.
- 2 of 6 of our axes had to be reversed to agree with theirs. A revolute axis has no natural sense, so a reversed axis is a convention both files are free to choose differently; the per-joint signs are in the frame alignment table so the choice is visible rather than assumed.
- The anchor distance is split along their joint's own axis and perpendicular to it. Only the perpendicular part is a statement about where the joint is: an along-axis difference is the freedom every revolute joint has to put its origin anywhere on its axis line. A perpendicular difference is real, and it can come from the pose each file was stored in as well as from the geometry, so this comparison reports it without attributing it.
