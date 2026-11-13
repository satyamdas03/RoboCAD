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

The check report in this directory is the authority. At this revision it reports
`self_collision` as **fail**: two convex hulls overlap by 7.9 mm at rest while the B-rep solids
touch and share 0.52 mm^3, which is contact scale. That means MuJoCo will act on a contact the CAD
does not have. The other checks pass or are skipped as recorded in `report.json`.

This directory is published because Satyam Das authorised it directly on 2026-11-13. The reasoning
and the pinned revision are recorded in `docs/DECISIONS.md` and in `docs/THIRD_PARTY.md`.
