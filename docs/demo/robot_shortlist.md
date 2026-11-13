# Robot shortlist for the demo slice

Week 1 search, per the course correction of 2026-11-13. Goal: 3 to 5 outside robots with
published CAD and a clear licence, ranked by whether open motion or torque logs exist as well.
Satyam picks one. Nothing downstream starts until he does.

Method: every claim below was checked against the primary source, not a search summary. A claim
carrying `[verified: api]` was read from the GitHub contents API or the licence API for that repo.
A claim carrying `[verified: fetch]` was read from the page itself. `[claimed]` means it appeared in
search results only and I have not confirmed it.

## Decision

Satyam picked **SO-101** on 2026-11-13. Pinned source revision, so the import is reproducible and
the licence is tied to a specific commit:

- Repository: https://github.com/TheRobotStudio/SO-ARM100
- Commit: `a758567c3978dfeefe282ede0500085a48fe8f78`, committed 2026-10-06, message "docs: list
  Seeed Studio and WowRobo first in kits section (#188)" `[verified: api]`
- Licence at that repository: Apache-2.0, confirmed through the GitHub licence API `[verified: api]`
- Assembly to import: `STEP/SO101/SO101 Assembly.step`, 20,496,014 bytes, blob
  `541ad0e11398` `[verified: api]`
- Outside description to check against: `Simulation/SO101/so101_new_calib.urdf` and
  `Simulation/SO101/so101_new_calib.xml` at the same commit `[verified: api]`
- Logs, for the later real-data half only: NAD dataset, MIT, real SO-101 hardware `[verified: fetch]`

Apache-2.0 requires keeping the copyright and licence notices with any redistributed derived model,
and stating what we changed. That applies to the page, the film and the report.


Ranking rule: a robot needs a STEP file someone can hand us, a licence that lets us publish a
derived model, and ideally logs that make a synthetic-versus-real claim testable later.

## Ranking

| Rank | Robot | STEP CAD | Licence | Open motion or torque logs | Partner relevance |
|---|---|---|---|---|---|
| 1 | SO-101 arm (The Robot Studio + Hugging Face) | Yes, in repo, 20.5 MB assembly plus 12 part files | Apache-2.0 | Yes: NAD dataset has real SO-101 load registers at about 62 Hz | High: cheap, many labs and startups own one |
| 2 | ODRI Bolt biped | Yes, one 26.5 MB STEP in repo | BSD-3-Clause | Yes, but for Solo12 (same actuator family, different robot) | Medium: research labs and dynamic-legged people |
| 3 | OpenArm 1.0 / 2.0 (Enactic) | Yes, via Google Drive, not in git | CERN-OHL-S-2.0, strongly reciprocal | Unverified: an `openarm_dataset` repo exists, contents not checked | Medium to high: 7-DOF, humanoid-adjacent |
| 4 | Berkeley Humanoid Lite | Only by hand export from Onshape | CC BY-SA 4.0 for assets, MIT for code | None found | Medium: 3D-printed humanoid, academic |
| 5 | Unitree Go2 | Not published as STEP | BSD-3-Clause on description and MJCF only | None public from Unitree | High, but it fails the CAD criterion |

Detail, strongest first.

### 1. SO-101 (recommended)

- CAD: `STEP/SO101/` holds 13 entries including `SO101 Assembly.step` at 20,496,014 bytes and
  twelve part files (base, motor holders, upper arm, under arm, rotation pitch, mounting plates,
  leader and follower specific subfolders). `[verified: api]`
  https://github.com/TheRobotStudio/SO-ARM100
- Licence: Apache-2.0, confirmed through the repository licence API. `[verified: api]`
- Ground truth for our own checks: `Simulation/SO101/` ships `so101_new_calib.urdf`,
  `so101_old_calib.urdf`, `so101_new_calib.xml` (MJCF), `scene.xml` and `joints_properties.xml`.
  `[verified: api]` This matters more than it looks: the M4 pose check and the M3 inertia numbers
  can be compared against somebody else's published description instead of only against our own
  output.
- Logs: the Neural Actuation Dataset records real SO-101 hardware, 100 trajectories, about 66k
  frames at roughly 62 Hz, with `load1` to `load6` signed counts (the paper's current feature) and
  `current1` to `current6` raw counts, MIT licence. `[verified: fetch]`
  https://huggingface.co/datasets/frankzydou/NAD
- Honest gap: no torque column for SO-101. Load register is a current proxy, so the Twin preview
  would have to say so, or use the Franka part of the same dataset, which does carry measured and
  commanded joint torques but has no public STEP CAD.
- Scale: 6 joints, 267 parts in the assembly. Big enough to prove part deduplication and instance
  transforms, small enough to debug in a day.

### 2. ODRI Bolt

- CAD: `mechanics/biped_6dof_v1/cad_files/STEP/biped_6dof_v1.STEP`, 26,548,352 bytes. `[verified: api]`
  https://github.com/open-dynamic-robot-initiative/open_robot_actuator_hardware
- Licence: BSD-3-Clause, Max Planck Gesellschaft and New York University. `[verified: fetch]`
- Logs: `paLeziart/solo12-recordings`, BSD-2-Clause, two trotting experiments at 500 Hz with
  `q_mes`, `v_mes`, `torquesFromCurrentMeasurment` (spelling as published), IMU and contact status.
  `[verified: fetch]` https://github.com/paLeziart/solo12-recordings
- Honest gap: those recordings are Solo12, a quadruped, not Bolt, a biped. Same actuator family and
  same software stack, different machine. Presenting them as Bolt data would be exactly the kind of
  overclaim this project has to stop making.
- Why it is second and not first: no URDF or MJCF in the hardware repo to compare our compile
  against, so M4 would be validating our output against itself.

### 3. OpenArm

- CAD: STEP assemblies for OpenArm 2.0, Cell and KER live on Google Drive, GitHub Releases carry
  only tarball mirrors. `[verified: fetch]` https://github.com/enactic/openarm_hardware
- Licence: CERN-OHL-S-2.0, strongly reciprocal, Copyright 2025 Enactic. `[verified: fetch]`
- Consequence, and the reason this needs your decision rather than mine: a strongly reciprocal
  hardware licence means a derived model published by us likely has to be released under the same
  terms. That is fine for a demo if the terms are honoured and stated, but it is a licence decision,
  and the rules say you decide those.
- Logs: the main repo lists `openarm_dataset` as a companion. Contents not checked, so treat log
  availability as unknown. `[claimed]`

### 4. Berkeley Humanoid Lite

- CAD: source of truth is public Onshape documents; the assets repo ships URDF, MJCF, USD and STL,
  not STEP. `[verified: fetch]` https://github.com/HybridRobotics/berkeley-humanoid-lite-assets
- Licence: CC BY-SA 4.0 for assets and CAD, MIT for code. `[verified: fetch]`
- Fits the "Onshape as a hand-exported STEP" decision, but it adds a manual export step and a
  share-alike obligation on anything derived.
- Logs: none found. `[claimed]` absent rather than confirmed absent.

### 5. Unitree Go2, listed to close the question

- URDF lives in `unitreerobotics/unitree_ros`, MJCF in `unitreerobotics/unitree_mujoco` and in the
  MuJoCo Menagerie, all BSD-3-Clause. `[verified: fetch]`
- No official STEP. It fails the "compiled from its own CAD" test, which is the whole demo claim, so
  it is not a candidate unless you relax that requirement.

## What I recommend

SO-101. Three reasons, in order of weight. It has STEP in the repository so nothing depends on a
manual export. It ships somebody else's URDF and MJCF, so our checks get an outside reference to
disagree with, which is the fastest way to find out whether our compiler is honest. And it is a
robot the engineers we are about to talk to can afford and may already own, which makes "here is
your robot, compiled" a real conversation instead of a hypothetical.

Second choice if you want legs and real torque logs now: ODRI Bolt, accepting that the only public
logs are Solo12 and would be labelled as such.

## What is not verified, stated plainly

- OpenArm STEP contents, because they are on Google Drive and I did not download from it.
- Whether `openarm_dataset` actually contains torque or current channels.
- Whether Berkeley Humanoid Lite Onshape documents are publicly exportable without an account.
- Whether any SO-101 dataset has enough excitation to identify friction and armature, rather than
  only enough to fit a mass. The synthetic preview does not need it; a real claim later does.

## Decision needed from Satyam

One robot, by name. If it is OpenArm, the share-alike licence question comes with it and needs an
explicit yes before anything derived is published.
