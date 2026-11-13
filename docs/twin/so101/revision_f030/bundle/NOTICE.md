# NOTICE: derived work from the SO-101

This directory contains a RoboCAD compile output derived from the SO-101 open-source robot arm.

## Upstream work

- Project: SO-101, by The Robot Studio in collaboration with Hugging Face
- Repository: https://github.com/TheRobotStudio/SO-ARM100
- File used as input: `STEP/SO101/SO101 Assembly.step`
- Pinned revision: commit `a758567c3978dfeefe282ede0500085a48fe8f78` (2026-10-06)
- File size at that revision: 20,496,014 bytes, blob `541ad0e11398e6701d006c40a032ffd67bac5369`
- Licence: Apache License 2.0

A copy of the upstream licence is at the repository root in `LICENSE`. The upstream copyright and
licence notices are retained. This notice is provided under section 4 of that licence.

## What RoboCAD changed

RoboCAD did not modify the upstream CAD. It read the assembly and produced a simulation model:

- Grouped the 83 imported parts and 259 placed instances into 7 links by geometry.
- Inferred joint axes and origins from the CAD geometry, rather than copying the published
  description. Joint limits are adopted from the published model where stated, and the report
  records that provenance.
- Computed mass, centre of mass and inertia from the B-rep at the density in the material library.
  Printed parts carry two numbers: a shell-and-infill estimate at a 1.20 mm wall over 20 percent
  infill, which totals 0.902 kg for the robot, and the solid bound beside it, which totals 1.332 kg.
  The solid figure is the one that cannot be wrong in the direction that matters, and the report
  never presents the estimate as a measurement.
- Gave each of the six joints a MuJoCo position actuator with a force limit of 2.942 N*m, the stall
  torque the ST3215 12 V datasheet states. The torque is not taken from the Feetech
  product-specification PDF, which documents the 7.4 V variant; the report names the sources for
  both figures separately, because they do not come from the same document. The gains, `kp` = 20
  and `kv` = 1, are assumptions and the report says so: the servo closes its own loop and publishes
  no stiffness for a simulator to use.
- Generated approximate convex collision hulls, 433 in total, and 259 visual meshes.
- Wrote an MJCF and a URDF description, plus the check report in this directory.

## Known state at the time of writing

The check report in this directory is the authority for this artifact. At this revision it records
`self_collision` as **fail**: two convex hulls overlap by 7.9 mm at rest, so MuJoCo will act on a
contact the CAD does not have. Beside that, the same report carries the B-rep measurement: the CAD
solids of the two bodies touch and share 0.52 mm^3 over 47 of 47 shape pairs, which is contact
scale rather than interference between two parts occupying the same space.

`limits_and_effort` is **pass**, and what makes it a measurement rather than a string comparison is
the second half: each joint's demanded torque is read from inverse dynamics at the reference pose
and at both ends of its travel, and compared against the actuator's stated limit. The largest demand
is 0.652 N*m on `joint_2`, 22 percent of its 2.942 N*m stall torque, so the servos are not
undersized for holding position. Two caveats travel with that number and are printed with it: the
measurement disables contacts, because the hull overlap above would otherwise put the solver's
push-apart forces into the torque; and it samples poses rather than searching them.

Five checks pass, one fails, one is skipped as not applicable to a bolted base.

The 259 visual meshes total 19.38 MB and 620,093 triangles. They are the B-rep tessellated coarsely,
not the collision hulls, so a viewer draws the part's own surface rather than a convex cover. They
are written with `contype` and `conaffinity` zero, which is why adding a picture did not change the
contact set, the body masses, or any check: `tests/test_visual_meshes.py` asserts exactly that. One
file is written per placed instance, in the body frame, so a part used several times is written
several times. The coarsest part's vertices moved by 1.20 mm, which the report states rather than
hides.

An earlier copy of this notice described a report that did not contain that B-rep measurement,
because the directory then held a bundle compiled before a units defect in the measuring code was
fixed. This directory has since been regenerated from the fixed code; the numbers above are read
from the `report.json` sitting beside this notice.

This bundle carries no revision diff. There is no earlier compile of this robot to diff against, and
the one comparison on hand -- the part-family proposal against the compiled bodies -- is not a
revision: the proposal names 26 part families, the bundle names 7 merged bodies, and seven of those
names are the same word on both sides while covering different sets of parts. Diffed by name that
pair reports nineteen links removed that never moved, so `ai_cad/compiler/revision.py` refuses it and
says so instead of writing the table. `tests/test_revision.py::TestComparability` covers the
refusal.

This directory is published because Satyam Das authorised it directly on 2026-11-13. The reasoning
and the pinned revision are recorded in `docs/DECISIONS.md` and in `docs/THIRD_PARTY.md`.
