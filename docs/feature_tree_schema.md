# RoboCAD Feature-Tree JSON Schema v1.0.0

**Status:** Phase 8 specification. This document defines the structured representation that RoboCAD will use to replace the monolithic `code.py` artifact in Phases 9–14.

**Design goal:** A human-readable, versioned, partially-regenerable parametric feature history that can be transpiled to `build123d` today and to Onshape FeatureScript in the future.

---

## 1. Philosophy

- **Feature tree is the source of truth.** The prompt and a structured JSON tree are saved; the generated `code.py` and STL become derived artifacts (still kept as fallbacks during transition).
- **Every feature is a node.** Each extrude, cut, fillet, hole, pattern, and sketch is an independent node with a unique ID, parameters, and explicit dependencies.
- **Parameters are global and typed.** Numeric values live in a root parameter table and are referenced by name. Changing one parameter regenerates only downstream features.
- **Constraints live in sketches.** 2D geometric constraints (distance, concentric, parallel, etc.) are stored next to the sketch entities they control.
- **Assemblies are first-class.** An assembly is a list of part instances plus mates that define how those instances relate to each other.

---

## 2. Top-level document

```json
{
  "schema_version": "1.0.0",
  "design_id": "uuid",
  "prompt": "A 120 mm × 80 mm × 3 mm base plate with four M3 mounting holes...",
  "created_at": "2026-08-25T12:34:56Z",
  "model": "qwen3-coder:latest",
  "units": "mm",
  "parameters": [ ... ],
  "coordinate_systems": [ ... ],
  "parts": [ ... ],
  "assemblies": [ ... ]
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `schema_version` | string | yes | Semantic version of this schema. Current: `1.0.0`. |
| `design_id` | string | yes | Stable UUID for the design. |
| `prompt` | string | yes | Original natural-language prompt. |
| `created_at` | string (ISO 8601) | yes | Timestamp when the tree was first generated. |
| `model` | string | no | LLM model used to generate the tree. |
| `units` | string | yes | Document units. Allowed: `mm`, `cm`, `m`, `in`. Default `mm`. |
| `parameters` | array | yes | Global parameter table. |
| `coordinate_systems` | array | no | Named local coordinate systems used by parts and mates. |
| `parts` | array | yes | One or more parts. Single-part designs contain one part. |
| `assemblies` | array | no | Zero or more assembly definitions. |

---

## 3. Parameters

A parameter is a named, typed, editable value. It may be a simple literal or a computed expression referencing other parameters.

```json
{
  "name": "plate_length",
  "value": 120.0,
  "unit": "mm",
  "description": "Overall plate length",
  "expression": null,
  "min": 1.0,
  "max": 10000.0
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Identifier. Must be unique, start with a letter or `_`, and contain only `[A-Za-z0-9_]`. |
| `value` | number \| string | yes | Current numeric value or expression string. |
| `unit` | string | no | Unit string. Default `mm`. |
| `description` | string | no | Human-readable meaning. |
| `expression` | string \| null | no | Formula such as `"plate_length / 2"`. If present, `value` should be the evaluated result. |
| `min` / `max` | number \| null | no | Optional soft bounds for UI sliders. |

**Rules:**
- Parameter names are case-sensitive.
- If `expression` is non-null, the solver evaluates it before regenerating features.
- All numeric dimensions in features reference parameters by name (string). Numeric literals are allowed only inside `value` fields.

---

## 4. Coordinate systems

A coordinate system defines an origin and orientation in 3D space. Used by planes, assembly instances, and mates.

```json
{
  "id": "origin",
  "name": "Global origin",
  "origin": [0, 0, 0],
  "x_axis": [1, 0, 0],
  "y_axis": [0, 1, 0],
  "z_axis": [0, 0, 1]
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | yes | Unique ID. |
| `name` | string | no | Display name. |
| `origin` | [x, y, z] | yes | Origin point in document units. |
| `x_axis` / `y_axis` / `z_axis` | [x, y, z] | yes | Orthonormal basis vectors. |

---

## 5. Sketches

Sketches are 2D profiles drawn on a plane. They are consumed by features such as `extrude`, `cut`, and `revolve`.

### 5.1 Sketch object

```json
{
  "id": "base_profile",
  "name": "Base plate profile",
  "plane": {
    "type": "base",
    "name": "XY"
  },
  "entities": [ ... ],
  "constraints": [ ... ],
  "dimensions": [ ... ]
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | yes | Unique sketch ID. |
| `name` | string | no | Display name. |
| `plane` | object | yes | Sketch plane definition (see 5.2). |
| `entities` | array | yes | 2D entities (see 5.3). |
| `constraints` | array | yes | Geometric constraints (see 5.4). |
| `dimensions` | array | yes | Driving dimensions tied to parameters (see 5.5). |

### 5.2 Plane reference

```json
{"type": "base", "name": "XY"}
{"type": "base", "name": "YZ"}
{"type": "base", "name": "ZX"}
{"type": "face", "feature_id": "base_solid", "face_name": "top"}
{"type": "offset", "from_csys_id": "origin", "offset_z": "thickness"}
```

| Type | Fields | Description |
|---|---|---|
| `base` | `name` | One of `XY`, `YZ`, `ZX`. |
| `face` | `feature_id`, `face_name` | Sketch on a face of an existing feature. `face_name` is a semantic hint such as `top`, `bottom`, `front`, `back`, `left`, `right`. |
| `offset` | `from_csys_id`, `offset_z` | Plane offset from a coordinate system along its Z axis. |

### 5.3 Entities

Supported entity types: `rectangle`, `circle`, `line`, `arc`, `polygon`.

```json
{
  "type": "rectangle",
  "id": "rect1",
  "center": [0, 0],
  "width": "plate_length",
  "height": "plate_width",
  "angle": 0
}
```

```json
{
  "type": "circle",
  "id": "hole1",
  "center": ["hole_spacing_x/2", "hole_spacing_y/2"],
  "radius": "hole_diameter/2"
}
```

```json
{
  "type": "line",
  "id": "line1",
  "start": [0, 0],
  "end": ["plate_length", 0]
}
```

```json
{
  "type": "arc",
  "id": "arc1",
  "center": [0, 0],
  "radius": "corner_radius",
  "start_angle": 0,
  "end_angle": 90
}
```

**Common fields:**

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique within the sketch. |
| `type` | string | Entity type. |
| `center` / `start` / `end` | [number \| string, number \| string] | 2D coordinates on the sketch plane. |
| `width` / `height` / `radius` / `diameter` / `angle` | number \| string | Size parameters. |
| `construction` | boolean | If true, entity is construction geometry only. |

### 5.4 Constraints

Constraints are geometric relationships between entities. The Phase 10 solver will resolve sketch coordinates from these constraints and dimensions.

```json
{
  "type": "distance",
  "entities": ["line1"],
  "value": "plate_length"
}
```

```json
{
  "type": "concentric",
  "entities": ["hole1", "hole2"]
}
```

Supported constraint types:

| Type | Entities | Description |
|---|---|---|
| `coincident` | 2 (point + point, or point + line/arc) | Two points or a point and curve coincide. |
| `horizontal` | 1 line | Line is horizontal in sketch space. |
| `vertical` | 1 line | Line is vertical in sketch space. |
| `parallel` | 2 lines | Lines are parallel. |
| `perpendicular` | 2 lines | Lines are perpendicular. |
| `equal` | 2+ entities | Lines equal length or circles equal radius. |
| `distance` | 1–2 entities | Distance between points, point-line, or parallel lines equals parameter. |
| `diameter` | 1 circle | Circle diameter equals parameter. |
| `radius` | 1 circle / arc | Radius equals parameter. |
| `angle` | 2 lines | Angle between lines equals parameter. |
| `concentric` | 2+ circles/arcs | Share center. |
| `tangent` | 2 entities | Line/circle or circle/circle tangent. |
| `symmetric` | 3 entities | Two entities symmetric about a centerline. |
| `fix` | 1 point | Fully constrain a point. |

### 5.5 Dimensions

Dimensions explicitly link geometric values to named parameters. They are the primary way the UI exposes sketch values for editing.

```json
{
  "name": "plate_length",
  "type": "distance",
  "entities": ["line1"],
  "value": 120.0
}
```

| Field | Type | Description |
|---|---|---|
| `name` | string | Parameter name this dimension drives. |
| `type` | string | Dimension type (`distance`, `diameter`, `radius`, `angle`). |
| `entities` | string[] | Entity IDs the dimension applies to. |
| `value` | number \| string | Current value or expression. |

---

## 6. Features

A feature is a single modeling operation applied to a part. Features form a directed acyclic graph through `depends_on` and by referencing sketches and other features.

### 6.1 Common feature fields

```json
{
  "id": "base_solid",
  "type": "extrude",
  "name": "Base extrusion",
  "enabled": true,
  "depends_on": [],
  "sketch_id": "base_profile",
  "parameters": { ... }
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | yes | Unique feature ID within the part. |
| `type` | string | yes | Feature type (see 6.2). |
| `name` | string | no | Display name. |
| `enabled` | boolean | no | If false, feature is suppressed. Default `true`. |
| `depends_on` | string[] | no | IDs of features that must be evaluated before this one. |
| `sketch_id` | string | no | Sketch consumed by the feature, if any. |
| `parameters` | object | yes | Type-specific parameters. |

### 6.2 Feature types

#### `extrude`

Extrude a sketch into a solid.

```json
{
  "type": "extrude",
  "parameters": {
    "amount": "thickness",
    "direction": "positive",
    "mode": "add",
    "taper_angle": 0
  }
}
```

| Parameter | Type | Description |
|---|---|---|
| `amount` | number \| string | Extrusion distance. |
| `direction` | string | `positive`, `negative`, `both`, `normal`, `normal_reverse`. |
| `mode` | string | `add`, `subtract`, `intersect`. |
| `taper_angle` | number \| string | Optional draft angle in degrees. |

#### `revolve`

Revolve a sketch around an axis.

```json
{
  "type": "revolve",
  "parameters": {
    "axis": {"type": "sketch_line", "entity_id": "centerline"},
    "angle": 360
  }
}
```

#### `fillet`

Apply a rounded edge.

```json
{
  "type": "fillet",
  "parameters": {
    "radius": "corner_radius",
    "edges": [{"type": "all"}]
  }
}
```

Edge selectors:
- `{"type": "all"}` — all convex edges.
- `{"type": "feature_edges", "feature_id": "base_solid"}` — all edges of a feature.
- `{"type": "last_feature"}` — edges created by the most recent feature.

#### `chamfer`

Same selectors as fillet, with `distance` or `distance1`/`distance2` parameters.

#### `shell`

Hollow out a solid.

```json
{
  "type": "shell",
  "parameters": {
    "thickness": "wall_thickness",
    "faces_to_remove": ["top"]
  }
}
```

#### `mirror`

Mirror one or more features across a plane.

```json
{
  "type": "mirror",
  "parameters": {
    "feature_ids": ["leg1"],
    "plane": {"type": "base", "name": "YZ"}
  }
}
```

#### `linear_pattern`

Repeat child features in a rectangular grid.

```json
{
  "type": "linear_pattern",
  "parameters": {
    "feature_ids": ["hole_feature"],
    "direction_x": [1, 0, 0],
    "direction_y": [0, 1, 0],
    "spacing_x": "hole_spacing_x",
    "spacing_y": "hole_spacing_y",
    "count_x": 2,
    "count_y": 2
  }
}
```

#### `circular_pattern`

Repeat child features around an axis.

```json
{
  "type": "circular_pattern",
  "parameters": {
    "feature_ids": ["bolt_hole"],
    "axis": {"type": "csys_axis", "csys_id": "origin", "axis": "z"},
    "count": 4,
    "total_angle": 360
  }
}
```

---

## 7. Parts

A part is a named sequence of features plus local sketches.

```json
{
  "id": "base_plate",
  "name": "Base Plate",
  "color": "#d8dce5",
  "material": "PLA",
  "sketches": [ ... ],
  "features": [ ... ],
  "default_csys_id": "origin"
}
```

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique part ID. |
| `name` | string | Display name. |
| `color` | string | Optional display color (hex). |
| `material` | string | Optional material hint for mass/FEA. |
| `sketches` | array | Sketches owned by this part. |
| `features` | array | Ordered feature list. |
| `default_csys_id` | string | Coordinate system the part is built in. |

**Feature ordering rule:** A feature may only reference sketches and features that appear earlier in the list or in its `depends_on` array. Cycles are invalid.

---

## 8. Assemblies

An assembly places part instances relative to each other using mates.

### 8.1 Assembly object

```json
{
  "id": "chassis_assembly",
  "name": "Differential-drive chassis",
  "instances": [ ... ],
  "mates": [ ... ]
}
```

### 8.2 Instances

```json
{
  "id": "motor_mount_left",
  "part_id": "motor_mount",
  "name": "Left motor mount",
  "transform": {
    "origin": [-50, 20, 0],
    "x_axis": [1, 0, 0],
    "y_axis": [0, 1, 0],
    "z_axis": [0, 0, 1]
  },
  "parameters": {}
}
```

Instances may override part parameters locally (e.g., a mirrored copy). Parameter overrides are stored in `parameters` as name → value mappings.

### 8.3 Mates

Mates define geometric relationships between instances. RoboCAD uses an LCS (local coordinate system) / expression style similar to Assembly4, not a full physics solver.

```json
{
  "id": "wheelbase_mate",
  "name": "100 mm wheelbase",
  "type": "distance",
  "entities": [
    {"instance_id": "motor_mount_left", "csys_id": "mount_face"},
    {"instance_id": "motor_mount_right", "csys_id": "mount_face"}
  ],
  "parameters": {
    "distance": "wheelbase"
  }
}
```

Supported mate types:

| Type | Description |
|---|---|
| `coincident` | Two planes/faces coincide. |
| `concentric` | Two cylinders/axes align. |
| `distance` | Two planes/faces separated by a parameter. |
| `angle` | Two planes/axes at a parameter angle. |
| `parallel` | Two planes/axes parallel. |
| `perpendicular` | Two planes/axes perpendicular. |
| `fixed` | Instance locked at its transform. |

Each mate `entity` references:
- `instance_id` — assembly instance.
- `csys_id` — a coordinate system defined on the part or instance.
- Optional `feature_id` / `entity_id` for face/edge references.

---

## 9. Example: base plate feature tree

```json
{
  "schema_version": "1.0.0",
  "design_id": "abc123",
  "prompt": "A 120 mm × 80 mm × 3 mm rectangular plate with four M3 mounting holes on a 100 mm × 60 mm grid.",
  "created_at": "2026-08-25T12:34:56Z",
  "model": "qwen3-coder:latest",
  "units": "mm",
  "parameters": [
    {"name": "plate_length", "value": 120.0, "unit": "mm", "description": "Overall plate length"},
    {"name": "plate_width", "value": 80.0, "unit": "mm", "description": "Overall plate width"},
    {"name": "thickness", "value": 3.0, "unit": "mm", "description": "Plate thickness"},
    {"name": "hole_diameter", "value": 3.2, "unit": "mm", "description": "Mounting hole diameter"},
    {"name": "hole_spacing_x", "value": 100.0, "unit": "mm", "description": "Hole spacing along X"},
    {"name": "hole_spacing_y", "value": 60.0, "unit": "mm", "description": "Hole spacing along Y"}
  ],
  "coordinate_systems": [
    {"id": "origin", "name": "Global origin", "origin": [0, 0, 0], "x_axis": [1, 0, 0], "y_axis": [0, 1, 0], "z_axis": [0, 0, 1]}
  ],
  "parts": [
    {
      "id": "base_plate",
      "name": "Base Plate",
      "default_csys_id": "origin",
      "sketches": [
        {
          "id": "base_profile",
          "name": "Base profile",
          "plane": {"type": "base", "name": "XY"},
          "entities": [
            {"type": "rectangle", "id": "rect1", "center": [0, 0], "width": "plate_length", "height": "plate_width", "angle": 0}
          ],
          "constraints": [
            {"type": "horizontal", "entities": ["rect1.bottom"]},
            {"type": "vertical", "entities": ["rect1.left"]}
          ],
          "dimensions": [
            {"name": "plate_length", "type": "distance", "entities": ["rect1"], "value": 120.0},
            {"name": "plate_width", "type": "distance", "entities": ["rect1"], "value": 80.0}
          ]
        },
        {
          "id": "hole_profile",
          "name": "Mounting hole profile",
          "plane": {"type": "face", "feature_id": "base_solid", "face_name": "top"},
          "entities": [
            {"type": "circle", "id": "hole1", "center": ["hole_spacing_x/2", "hole_spacing_y/2"], "radius": "hole_diameter/2"},
            {"type": "circle", "id": "hole2", "center": ["-hole_spacing_x/2", "hole_spacing_y/2"], "radius": "hole_diameter/2"},
            {"type": "circle", "id": "hole3", "center": ["hole_spacing_x/2", "-hole_spacing_y/2"], "radius": "hole_diameter/2"},
            {"type": "circle", "id": "hole4", "center": ["-hole_spacing_x/2", "-hole_spacing_y/2"], "radius": "hole_diameter/2"}
          ],
          "constraints": [
            {"type": "equal", "entities": ["hole1", "hole2", "hole3", "hole4"]},
            {"type": "symmetric", "entities": ["hole1", "hole3", "rect1.center"]},
            {"type": "symmetric", "entities": ["hole2", "hole4", "rect1.center"]}
          ],
          "dimensions": [
            {"name": "hole_diameter", "type": "diameter", "entities": ["hole1"], "value": 3.2},
            {"name": "hole_spacing_x", "type": "distance", "entities": ["hole1.center", "hole2.center"], "value": 100.0},
            {"name": "hole_spacing_y", "type": "distance", "entities": ["hole1.center", "hole3.center"], "value": 60.0}
          ]
        }
      ],
      "features": [
        {
          "id": "base_solid",
          "type": "extrude",
          "name": "Base plate body",
          "enabled": true,
          "sketch_id": "base_profile",
          "parameters": {
            "amount": "thickness",
            "direction": "positive",
            "mode": "add"
          }
        },
        {
          "id": "mounting_holes",
          "type": "extrude",
          "name": "Mounting holes",
          "enabled": true,
          "depends_on": ["base_solid"],
          "sketch_id": "hole_profile",
          "parameters": {
            "amount": "thickness + 0.2",
            "direction": "negative",
            "mode": "subtract"
          }
        }
      ]
    }
  ],
  "assemblies": []
}
```

---

## 10. Versioning and partial regeneration

- The feature tree is saved as `feature_tree.json` next to `code.py` in the design directory.
- Each feature node records a `generated_at` timestamp and optional `hash` of its parameters.
- When a parameter changes, the system computes the affected feature subgraph (the changed feature plus all dependents) and re-evaluates only those nodes.
- Suppressed features (`enabled: false`) are skipped during transpilation but preserved in the tree so users can re-enable them.

---

## 11. Mapping to build123d (Phase 9)

| Feature-tree concept | build123d equivalent |
|---|---|
| Part | `BuildPart()` context |
| Base-plane sketch | `BuildSketch(Plane.XY)` |
| Face sketch | `BuildSketch(selected_face)` |
| Rectangle | `Rectangle(width, height)` |
| Circle | `Circle(radius)` |
| Extrude add | `extrude(amount)` in `BuildPart` |
| Extrude subtract | `extrude(amount=-depth, mode=Mode.SUBTRACT)` |
| linear_pattern | `GridLocations(spacing_x, spacing_y, count_x, count_y)` |
| circular_pattern | `PolarLocations(radius, count, start_angle)` |
| Fillet | `fillet(edges, radius)` |
| Shell | `shell(faces, thickness)` |

A `transpiler.py` will walk the tree in dependency order and emit a single build123d script. Raw `code.py` remains a fallback for designs that cannot yet be represented by the schema.

---

## 12. Migration strategy

1. **Phase 8 (now):** schema approved; benchmark shows how often current LLM output can be restructured into the schema.
2. **Phase 9:** Add `ai_cad/feature_tree.py`, `ai_cad/transpiler.py`, `ai_cad/feature_store.py`. New designs get both `feature_tree.json` and `code.py`.
3. **Phase 10:** Add 2D constraint solver; dimensions drive parameter values.
4. **Phase 11:** Add assembly support; multi-part STEP export.
5. **Phase 12+:** Verification rules consume the feature tree directly.

---

## 13. Schema evolution rules

- `schema_version` is mandatory and must be semver.
- New schema versions must be backward-compatible for at least one full phase or provide a migration script.
- Unknown feature types or fields must be ignored by the transpiler, not cause failure.
