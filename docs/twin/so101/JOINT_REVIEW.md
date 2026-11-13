# M2 joint skeleton: review record

The review this file records is the one `docs/DECISIONS.md` decision 2 requires: the session that did
not write a document checks it against written criteria and records PASS or FAIL. It exists so the
skeleton is not taken on trust, and so the answer to "who checked this" is a name and a command rather
than an assurance.

## What is being reviewed

Two documents, because M2 produced two:

| document | what it holds | link identity |
|---|---|---|
| `robot.joints.proposed.yaml` | inference output: 26 link groups, **1** geometry-confirmed joint, 91 unresolved pairs | one row per link group |
| `bundle/robot.joints.yaml` | the compiled skeleton the bundle simulates: 7 bodies, **6** revolute joints | one row per merged body |

`robot.joints.yaml` in this directory is the adopted copy of the proposal, with the header above the
body naming this record. The body is the proposal's text unchanged.

## The four criteria and the command

```
python scripts/check_joints_yaml.py \
    --proposal docs/twin/so101/robot.joints.proposed.yaml \
    --skeleton docs/twin/so101/bundle/robot.joints.yaml \
    --official so101_new_calib.urdf
```

Output, verbatim, run 2026-11-14 against the files at `demo-bundle-v1` (`f202c12`):

```
PASS  every instance assigned exactly once
      259 instance(s) assigned across 26 link(s), expected 259; duplicates: none
PASS  six revolute joints on the servo shaft axis
      6 joint(s), 6 revolute, non-unit axes: none. Each axis direction is the servo output-shaft
      direction from the CAD (`ai_cad/compiler/kinematics.py`, `axis_dir=axis.direction`), which is
      what makes the 1.0 deg criterion one object rather than two measurements; the axis point sits
      at most 57.83 mm from the servo shaft line.
PASS  limits sourced and stated
      6 of 6 joint(s) carry a limit and a stated source; missing: none; distinct sources: 1.
PASS  tree matches the official topology
      chain order joint_1 -> joint_2 -> joint_3 -> joint_4 -> joint_5 -> joint_6; roots: 1
      (expected 1); body-to-body mismatches: none.

4/4 criteria pass
```

Each criterion, and the one thing a reader should know before believing the PASS:

1. **Every instance assigned exactly once.** 259 instance ids, 26 link groups, no id in two groups, no
   id missing. This is exact; there is no tolerance to argue about.
2. **Six revolute joints on the servo shaft axis.** The PASS is a statement about how the number is
   produced, not about two measurements agreeing: `ai_cad/compiler/kinematics.py` sets each joint's
   `axis_dir` to the direction of the `ServoAxis` it found in the CAD, so axis and shaft are the same
   object. What this criterion does *not* say is that the axis point lies on the shaft line — the
   worst joint sits 57.83 mm from it, because the recorded point is the joint origin, which is where
   the two bodies meet rather than where the shaft surface is. Read the number as "the direction is
   the shaft's; the point is the joint's".
3. **Limits sourced and stated.** All six carry a lower and upper bound and a source string naming
   `so101_new_calib.urdf`, its sha256 and its pinned revision. The limits are adopted from the
   published model and the report says so; the STEP file carries no travel limits of its own.
4. **Tree matches the official topology.** Compared joint name to child link, not by document order,
   because the official file lists the chain tip first and pairing in order maps the gripper to
   joint_1. One root, no mismatches.

## Who checked

- **Author self-check:** the build session, by running the command above. This is what the output in
  this file is.
- **Independent cross-review:** requested from the monitor session on 2026-11-14 with the command and
  this file named. Its verdict is recorded below when it arrives. Until it does, this file claims a
  self-check and not a review, and the tracker says the same.

### Cross-review verdict

Pending. No verdict has been received and none is invented here.

## What this review does not cover

The proposal's 91 unresolved pairs are listed, not resolved: on a servo-mediated arm the six links
share no coaxial bore/shaft interface, so geometry cannot confirm those joints and the compiled
skeleton's six joints come from the servo/horn topology the compiler reconstructs, which is what
criterion 2 and 4 check. A reader who wants the unresolved pairs has them in the proposal with the
reason each is missing.

The jaw frame is a separate known-unknown, recorded in `docs/DECISIONS.md` and in the comparison: the
jaw origin is 5.74 mm from the official one at rest and no gripper offset fixes it.
