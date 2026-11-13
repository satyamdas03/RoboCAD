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
- Computed mass, centre of mass and inertia from the B-rep at the density in the material library,
  which for printed parts means solid PLA at 1240 kg/m^3 and therefore an upper bound at 100 percent
  fill. There is no wall thickness or infill fraction in this model.
- Generated approximate convex collision hulls, one per part, 433 in total.
- Wrote an MJCF and a URDF description, plus the check report in this directory.

## Known state at the time of writing

The check report in this directory is the authority for this artifact. At this revision it records
`self_collision` as **fail**: two convex hulls overlap by 7.9 mm at rest, so MuJoCo will act on a
contact the CAD does not have. Beside that, the same report carries the B-rep measurement: the CAD
solids of the two bodies touch and share 0.52 mm^3 over 47 of 47 shape pairs, which is contact
scale rather than interference between two parts occupying the same space.

It also records `limits_and_effort` as **warn**, and the reason is the model, not the limits: the
six joints carry travel limits adopted from the published URDF, with that file's sha256 in the
provenance, but this bundle contains no `<actuator>` element at all, so nothing in it states what
torque or force any joint may be given. A check named `limits_and_effort` cannot pass on travel
limits alone, and this one does not. Four checks pass, one fails, one warns, one is skipped as not
applicable to a bolted base.

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
