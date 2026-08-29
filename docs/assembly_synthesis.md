# Mechanical assembly synthesis (Phase 19)

Phase 19 turns RoboCAD's fixed part assemblies into articulated mechanisms:

- **Interface library** on every part family — `pin`, `bore`, `slot`, `flange`, `mount` — each with a `mate_hint` (`fixed`, `revolute`, `prismatic`, `concentric`, `coincident`).
- **Mate inference** matches interfaces between instances and emits both geometric `Mate` objects and `KinematicJoint` definitions.
- **Kinematic solver** relaxes LCS-based mates iteratively and flags overconstrained assemblies.
- **Assembly collision** checks pairwise clearance/interference between placed instances.
- **MJCF/URDF export** writes real joints, actuators, and sensors for MuJoCo/ROS.
- **Browser replay** previews range-of-motion from the backend pose graph.

## Endpoints

- `POST /designs/{id}/synthesize-assembly` — re-run mate inference and joint synthesis on an existing design.
- `GET /designs/{id}/assembly-poses?samples_per_joint=8` — sampled poses through each joint's range.
- `POST /designs/{id}/assembly-collision` — pairwise collision/clearance report.

## Front-end panels

- `AssemblyPanel` — instance and mate list.
- `AssemblyReplayPanel` — lightweight range-of-motion table and player.
- `AssemblyCollisionPanel` — worst clearance and per-pair status.

## Implementation files

- `ai_cad/part_families.py` — `Interface` list and mate hints.
- `ai_cad/mate_inference.py` — rule-first mate/joint inference.
- `ai_cad/assembly.py` — `solve_assembly`, revolute/prismatic mate relaxation.
- `ai_cad/assembly_collision.py` — pairwise trimesh clearance/intersection.
- `ai_cad/geda_bridge/exporter.py` — hierarchy-aware MJCF/URDF with joints/actuators/sensors.
- `web/backend/main.py` — new assembly endpoints.
- `web/frontend/src/components/AssemblyReplayPanel.jsx` / `AssemblyCollisionPanel.jsx`.
