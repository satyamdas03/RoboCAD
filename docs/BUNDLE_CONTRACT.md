# RoboCAD GEDA Bridge — Bundle Ingestion Contract

**Version:** 2.0.0  
**Date:** 2026-08-27  
**Status:** Phase 15A reference contract  
**Audience:** `LearningRobotics`, external simulators, and any consumer of RoboCAD simulation bundles.

---

## 1. Overview

A RoboCAD **simulation bundle** is a self-contained directory (and matching `.zip`) that describes one or more rigid bodies produced by the RoboCAD GEDA Bridge. It contains:

- A JSON manifest describing the asset.
- Watertight STL meshes in SI units (meters).
- Inertial data per body.
- Optional URDF and MJCF files for direct simulator loading.
- Optional verification report.

Any simulator or downstream pipeline that implements this contract can load a RoboCAD bundle without RoboCAD-specific code.

---

## 2. Bundle directory layout

```
{bundle_dir}/
├── manifest.json          # Required. Top-level BundleManifest.
├── inertial.json          # Required. Same data, focused on physics properties.
├── meshes/
│   ├── {name}.stl         # Required. One STL per BundlePart.
│   └── ...
├── model.mjcf             # Optional. MuJoCo native world/robot file.
├── model.urdf             # Optional. URDF fallback.
└── verification.json      # Optional. BundleVerification report.
```

All length units are **meters** and mass units are **kilograms**.

---

## 3. `manifest.json` schema

```json
{
  "schema_version": "2.0.0",
  "design_id": "uuid-or-design-name",
  "name": "model",
  "created_at": "2026-08-27T00:00:00Z",
  "generator": "RoboCAD GEDA Bridge",
  "length_unit": "m",
  "mass_unit": "kg",
  "urdf_file": "model.urdf",
  "mjcf_file": "model.mjcf",
  "parts": [
    {
      "part_id": "wedge",
      "instance_id": null,
      "name": "wedge",
      "material": "PLA",
      "density_kg_m3": 1250.0,
      "mesh_file": "meshes/wedge.stl",
      "inertial": {
        "mass_kg": 0.012,
        "center_of_mass_m": [0.0, 0.0, 0.005],
        "inertia_tensor_kg_m2": [1e-6, 1e-6, 1e-6, 0.0, 0.0, 0.0],
        "principal_moments_kg_m2": [1e-6, 1e-6, 1e-6],
        "principal_axes": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        "density_kg_m3": 1250.0,
        "material": "PLA"
      },
      "transform_m": [
        [1, 0, 0, 0],
        [0, 1, 0, 0],
        [0, 0, 1, 0],
        [0, 0, 0, 1]
      ]
    }
  ]
}
```

### Field definitions

| Field | Type | Required | Description |
|---|---|---|---|
| `schema_version` | string | ✅ | Must be `"2.0.0"` for this contract. |
| `design_id` | string | optional | RoboCAD design identifier. |
| `name` | string | ✅ | Human-readable asset name. |
| `created_at` | string (ISO 8601) | ✅ | Generation timestamp. |
| `generator` | string | optional | Source generator (e.g., `"RoboCAD GEDA Bridge"`). |
| `length_unit` | string | ✅ | Always `"m"`. |
| `mass_unit` | string | ✅ | Always `"kg"`. |
| `urdf_file` | string | optional | Relative path to URDF. |
| `mjcf_file` | string | optional | Relative path to MJCF. |
| `parts` | list[BundlePart] | ✅ | Rigid bodies in the asset. |

### `BundlePart` fields

| Field | Type | Required | Description |
|---|---|---|---|
| `part_id` | string | ✅ | Unique part identifier within the bundle. |
| `instance_id` | string \| null | optional | Assembly instance identifier. |
| `name` | string | ✅ | Safe name for simulator links/bodies. |
| `material` | string | ✅ | Material name. |
| `density_kg_m3` | float | ✅ | Volumetric density. |
| `mesh_file` | string | ✅ | Relative path to `.stl`. |
| `inertial` | InertialData | ✅ | Mass properties. |
| `transform_m` | 4x4 matrix \| null | optional | Body pose in asset frame (mm origin, m scale in output). |

### `InertialData` fields

| Field | Type | Required | Description |
|---|---|---|---|
| `mass_kg` | float | ✅ | Body mass. |
| `center_of_mass_m` | [x, y, z] | ✅ | CoM in body frame, meters. |
| `inertia_tensor_kg_m2` | [Ixx, Iyy, Izz, Ixy, Ixz, Iyz] | ✅ | Inertia about CoM. |
| `principal_moments_kg_m2` | [Ix, Iy, Iz] \| null | optional | Principal moments. |
| `principal_axes` | [[x,y,z], ...] \| null | optional | Principal axes rows. |
| `density_kg_m3` | float | ✅ | Density used for mass computation. |
| `material` | string | ✅ | Material name. |

---

## 4. Loader contract

A compliant loader MUST:

1. Read `manifest.json` and validate `schema_version` is understood.
2. Resolve mesh paths relative to the bundle directory.
3. Verify every listed `.stl` exists and is non-empty.
4. Load the asset into the target simulator with the provided inertial frames.
5. Return a `BundleLoadResult` containing the simulator handle, body count, and any warnings.

A compliant loader SHOULD:

1. Use the bundled `model.mjcf` when running in MuJoCo.
2. Use the bundled `model.urdf` when running in URDF-based simulators.
3. Fall back to constructing the world from `manifest.json` + meshes if no simulator-native file is present.
4. Run a short physics stability check before returning.

---

## 5. Capability registry

RoboCAD exposes its supported features via `GET /capabilities`. The response is a JSON object:

```json
{
  "api_version": "0.3.0",
  "bundle_schema_version": "2.0.0",
  "supported_export_formats": ["stl", "step", "urdf", "mjcf", "bundle.zip"],
  "supported_simulators": ["mujoco"],
  "supported_scene_templates": ["gripper_cube_grasp", "bracket_hook_hang", "wedge_push_block", "peg_insertion"],
  "supported_part_families": ["cube", "cylinder", "wedge", "l_bracket", "gripper_jaw"],
  "endpoints": {
    "generate": "POST /generate",
    "simulate": "POST /designs/{id}/simulate",
    "scene": "POST /designs/{id}/scene",
    "capabilities": "GET /capabilities"
  }
}
```

---

## 6. Stability handshake test

The reference end-to-end test:

1. RoboCAD generates/export a wedge bundle.
2. Composes a `wedge_push_block` scene.
3. Loads the scene into MuJoCo.
4. Runs a 10 s rollout at `dt=0.002` (5000 steps).
5. Asserts no NaN/inf positions, velocities, or contacts; reports max penetration and energy drift.

If the test passes, the bundle → scene → simulator handoff is verified.

---

## 7. Changelog

- **2.0.0** (2026-08-27): Phase 15A reference contract. Adds `design_id`, `instance_id`, and capability registry.
