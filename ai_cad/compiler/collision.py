"""Collision geometry: convex hulls a physics engine can actually use.

A visual mesh is not a collision mesh. MuJoCo wants convex shapes, and a 40,000-triangle link B-rep
turned into a mesh geom is both slow and wrong (it is not convex, so contacts are wrong). CoACD
decomposes the tessellated part into a small set of convex hulls, which is what a simulator needs.

Two things are measured on every part, not assumed:
- how much of the part's volume the hulls cover, because a decomposition that misses a hollow is a
  collision model that lets another body pass through;
- whether the tessellation closed, because an open mesh decomposes into garbage that still loads.

Units are metres throughout: MuJoCo is metres, and a mesh exported in millimetres would put a 3 cm
link 30 km from the robot.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from pydantic import BaseModel, Field

from ai_cad.compiler.properties import PropertyError

# Tessellation. A 0.2 mm chord is finer than any feature that matters for contact on a desktop robot,
# and coarse enough that a 259-instance assembly tessellates in seconds.
LINEAR_DEFLECTION_M = 0.2e-3
ANGULAR_DEFLECTION_RAD = 0.5

# CoACD settings. The seed is pinned because a decomposition that changes between runs turns a
# version diff into noise, and the cap keeps a pathological part from producing a hundred geoms.
COACD_THRESHOLD = 0.05
COACD_MAX_HULLS = 16
COACD_SEED = 0
COACD_MAX_HULL_VERTICES = 64

# A decomposition outside this band is reported. CoACD overestimates concave geometry by design, so
# the upper bound is generous; the lower one catches hulls that lost a feature entirely.
MIN_FILL_RATIO = 0.3
MAX_FILL_RATIO = 3.0

# When a part is already nearly convex, one hull is both the faster and the more honest answer: CoACD
# would spend minutes rediscovering a shape it cannot improve on. Measured: the SO-101 PCB (19,440
# triangles) took 543 s at CoACD defaults and covers 1.03x its own volume with a single hull.
CONVEX_TOLERANCE = 1.25

# Above this triangle count a non-convex part is covered by its convex hull and the reason is
# recorded, rather than run through a decomposition whose cost is unbounded. CoACD has no timeout of
# its own -- it is a blocking C call -- and the demo sprint caps collision work at 30 minutes total.
COACD_TRIANGLE_LIMIT = 6000

# A convex hull of a finely tessellated curved part is as detailed as the tessellation itself. Capped
# so a hull stays a collision shape instead of a second copy of the CAD: measured on SO-101, one
# unreduced hull was 15.8 MB, which MuJoCo will load and then grind against.
MAX_HULL_VERTICES = 96

WELD_TOLERANCE_M = 1e-9


class CollisionError(RuntimeError):
    """Raised when a part cannot be given collision geometry at all."""


class Hull(BaseModel):
    """One convex hull, in metres, in the part frame."""

    vertices: list[tuple[float, float, float]]
    faces: list[tuple[int, int, int]]
    volume_m3: float = Field(ge=0.0, allow_inf_nan=False)
    # True when the hull was snapped to a grid to fit MAX_HULL_VERTICES. The snap moves each vertex by
    # at most half a cell, so the shape differs from the true hull by at most that much; the grid size
    # travels with the shape so the report can state the bound instead of shrugging.
    reduced: bool = False
    snap_m: float = 0.0


class CollisionMesh(BaseModel):
    """The collision representation of one part, with the numbers that justify it."""

    part_id: str
    hulls: list[Hull] = Field(default_factory=list)
    triangle_count: int = 0
    closed: bool = False
    method: str = "coacd"  # "coacd" | "convex_hull"
    part_volume_m3: float = 0.0
    fill_ratio: float = 0.0
    warnings: list[str] = Field(default_factory=list)

    @property
    def hull_count(self) -> int:
        return len(self.hulls)


# ------------------------------------------------------------------------------------------------
# tessellation
# ------------------------------------------------------------------------------------------------
def tessellate(shape) -> tuple[np.ndarray, np.ndarray]:
    """Triangulate a B-rep into a welded vertex/face array, in metres.

    OCP gives every face its own copy of the shared vertices, so the raw result is a soup of
    disconnected triangles. Welding by coordinate is what makes the mesh closed, and a closed mesh is
    what makes the decomposition meaningful.
    """
    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    try:
        BRepMesh_IncrementalMesh(shape, LINEAR_DEFLECTION_M, False, ANGULAR_DEFLECTION_RAD, True)
    except Exception as exc:  # pragma: no cover - kernel failure on a broken shape
        raise CollisionError(f"tessellation failed: {exc}") from exc

    raw: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        location = face.Location()
        triangulation = BRep_Tool.Triangulation_s(face, location)
        if triangulation is not None:
            base = len(raw)
            # ``Triangulation_s`` hands back the face's location and node coordinates expressed in
            # the face's own frame. Applying the location is not optional: a part placed with a
            # transform tessellates into a shape sitting somewhere else, or, worse, into a mesh whose
            # triangles no longer meet, which is how a fused L-shape came out 4166 mm3 instead of
            # 5500.
            transform = location.Transformation()
            located = not location.IsIdentity()
            for index in range(1, triangulation.NbNodes() + 1):
                point = triangulation.Node(index)
                if located:
                    point = point.Transformed(transform)
                raw.append((point.X() * 1e-3, point.Y() * 1e-3, point.Z() * 1e-3))
            # The kernel winds every triangle to the face's own surface, so a REVERSED face comes out
            # wound the wrong way round relative to the solid. Without this flip a cube tessellates to
            # a mesh whose edges do not pair up and whose half the faces point inward, and a
            # decomposition of that is a cover of nothing in particular.
            flip = face.Orientation() == TopAbs_REVERSED
            for index in range(1, triangulation.NbTriangles() + 1):
                a, b, c = triangulation.Triangle(index).Get()
                a, b, c = base + a - 1, base + b - 1, base + c - 1
                faces.append((a, c, b) if flip else (a, b, c))
        explorer.Next()

    if not faces:
        raise CollisionError("part tessellated to zero triangles")
    vertices = np.asarray(raw, dtype=float)
    if not np.all(np.isfinite(vertices)):
        raise CollisionError("tessellation produced a non-finite vertex")
    vertices, faces_array = _weld(vertices, np.asarray(faces, dtype=np.int64))
    return vertices, faces_array


def _weld(vertices: np.ndarray, faces: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Merge vertices that coincide, and drop triangles that collapse doing so."""
    keys = np.round(vertices / WELD_TOLERANCE_M).astype(np.int64)
    _, first_index, inverse = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    welded = vertices[first_index]
    remapped = inverse[faces.reshape(-1)].reshape(faces.shape)
    keep = (
        (remapped[:, 0] != remapped[:, 1])
        & (remapped[:, 1] != remapped[:, 2])
        & (remapped[:, 0] != remapped[:, 2])
    )
    return welded, remapped[keep]


def _closed(vertices: np.ndarray, faces: np.ndarray) -> bool:
    """Every edge of a closed triangle mesh is traversed once in each direction.

    Encoded as vertex-index pairs rather than a broadcast comparison: an earlier version compared
    every edge against every other one, which is quadratic in memory and takes a 40,000-triangle part
    from milliseconds to unusable.
    """
    count = int(len(vertices))
    if count > 3_000_000_000:  # pragma: no cover - int64 key would overflow
        raise CollisionError("mesh has too many vertices to check closure cheaply")
    directed = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]).astype(np.int64)
    keys = directed[:, 0] * count + directed[:, 1]
    reversed_keys = directed[:, 1] * count + directed[:, 0]
    unique_keys = np.unique(keys)
    if unique_keys.size != keys.size:
        return False  # the same directed edge appears twice: not a manifold
    return bool(np.array_equal(np.unique(reversed_keys), unique_keys))


def _triangle_volume(vertices: np.ndarray, faces: np.ndarray) -> float:
    """Signed volume of a closed triangle mesh."""
    a = vertices[faces[:, 0]]
    b = vertices[faces[:, 1]]
    c = vertices[faces[:, 2]]
    return float(np.abs(np.einsum("ij,ij->i", a, np.cross(b, c)).sum()) / 6.0)


# ------------------------------------------------------------------------------------------------
# convex decomposition
# ------------------------------------------------------------------------------------------------
def decompose(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    threshold: float = COACD_THRESHOLD,
    max_hulls: int = COACD_MAX_HULLS,
    seed: int = COACD_SEED,
) -> list[Hull]:
    """Split a triangle mesh into convex hulls with CoACD, deterministically."""
    import coacd

    if max_hulls < 1:
        raise CollisionError("max_hulls must be at least 1")
    parts = coacd.run_coacd(
        coacd.Mesh(vertices.astype(np.float32), faces.astype(np.int32)),
        threshold=threshold,
        max_convex_hull=max_hulls,
        max_ch_vertex=COACD_MAX_HULL_VERTICES,
        seed=seed,
    )
    hulls: list[Hull] = []
    for hull_vertices, hull_faces in parts:
        v = np.asarray(hull_vertices, dtype=float)
        f = np.asarray(hull_faces, dtype=np.int64)
        hulls.append(
            Hull(
                vertices=[tuple(float(c) for c in row) for row in v],
                faces=[tuple(int(i) for i in row) for row in f],
                volume_m3=abs(_triangle_volume(v, f)),
            )
        )
    return hulls


def _quantise(vertices, cell: float):
    """Vertices snapped to a grid of ``cell`` metres, deduplicated.

    Snapping moves a point by at most half a cell, so the hull of the snapped set differs from the
    true hull by at most that much in each direction. That bound is what lets the caller report a
    number instead of a shrug.
    """
    import numpy as np

    snapped = np.round(np.asarray(vertices, dtype=float) / cell) * cell
    return np.unique(snapped, axis=0)


def convex_hull(vertices, max_vertices: int | None = None) -> Hull:
    """The convex hull of a point cloud, as a triangle mesh.

    A densely tessellated curved part has almost all of its vertices on its own hull, so the hull is
    as big as the tessellation: measured on SO-101, one part's hull came to 15.8 MB and over half a
    million vertices. MuJoCo loads that happily and then spends the rest of the run in narrowphase
    against it.

    Above ``MAX_HULL_VERTICES`` the point cloud is snapped to a grid and re-hulled, with the grid
    coarsened until the hull fits. Quadric decimation was tried first and is not used: asked for 192
    faces on a 1,006,104-face hull, it returned 31,840.
    """
    import numpy as np
    import trimesh

    cap = MAX_HULL_VERTICES if max_vertices is None else max_vertices
    points = np.asarray(vertices, dtype=float)
    mesh = trimesh.convex.convex_hull(points)
    cell_used = 0.0
    if len(mesh.vertices) > cap:
        extent = points.max(axis=0) - points.min(axis=0)
        diagonal = float(np.linalg.norm(extent))
        cell = max(diagonal / 64.0, 1e-6)
        for _ in range(12):
            candidate = trimesh.convex.convex_hull(_quantise(points, cell))
            if len(candidate.vertices) <= cap or cell > diagonal:
                mesh = candidate
                cell_used = cell
                break
            cell *= 1.7
    v = np.asarray(mesh.vertices, dtype=float)
    f = np.asarray(mesh.faces, dtype=np.int64)
    return Hull(
        vertices=[tuple(float(c) for c in row) for row in v],
        faces=[tuple(int(i) for i in row) for row in f],
        volume_m3=abs(_triangle_volume(v, f)),
        reduced=cell_used > 0.0,
        snap_m=cell_used,
    )


def collision_mesh(part, **kwargs) -> CollisionMesh:
    """Collision geometry for one imported part, with its quality numbers and the method used.

    ``part`` is an :class:`~ai_cad.importers.models.ImportedPart`. A part that cannot be decomposed
    raises: a link with no collision geometry silently passes through the world in simulation, which
    is a failure that looks like a physics bug from the outside.
    """
    shape = getattr(part, "shape", None)
    if shape is None:
        raise CollisionError(f"part {part.part_id} has no shape to tessellate")
    if not getattr(part, "is_solid", False):
        raise CollisionError(
            f"part {part.part_id} is not a closed solid; a collision mesh of a face or an open shell "
            "is a surface another body can pass through"
        )
    vertices, faces = tessellate(shape)

    part_volume = abs(float(part.signature.volume_m3))
    closed = _closed(vertices, faces)
    warnings: list[str] = []

    hull = convex_hull(vertices)
    if part_volume > 0.0 and hull.volume_m3 <= part_volume * CONVEX_TOLERANCE:
        # The part is convex enough that splitting it would add geoms and cost contact time for
        # nothing. This is also what keeps a dense PCB out of a decomposition that has no timeout.
        hulls = [hull]
        method = "convex_hull"
    elif len(faces) > kwargs.get("triangle_limit", COACD_TRIANGLE_LIMIT):
        hulls = [hull]
        method = "convex_hull"
        warnings.append(
            f"{part.part_id}: {len(faces)} triangles exceeds the {COACD_TRIANGLE_LIMIT} collision-"
            "decomposition limit, so the convex hull is used; concave features smaller than the hull "
            "are not collided"
        )
    else:
        hulls = decompose(vertices, faces, **kwargs)
        method = "coacd"
        if not hulls:
            raise CollisionError(f"part {part.part_id} decomposed into zero hulls")

    hull_volume = sum(h.volume_m3 for h in hulls)
    fill = hull_volume / part_volume if part_volume > 0.0 else 0.0
    if any(h.reduced for h in hulls):
        snap = max(h.snap_m for h in hulls)
        warnings.append(
            f"{part.part_id}: the tessellation puts {len(vertices)} points on the hull, so it was "
            f"snapped to a {snap * 1e3:.2f} mm grid to stay under {MAX_HULL_VERTICES} vertices; every "
            f"hull vertex is within {snap * 0.5 * 1e3:.2f} mm of the true surface"
        )
    if not closed:
        warnings.append(
            f"{part.part_id}: the tessellation is not a closed surface, so the decomposition is a "
            "convex cover of an open mesh"
        )
    if method == "coacd" and len(hulls) >= kwargs.get("max_hulls", COACD_MAX_HULLS):
        warnings.append(
            f"{part.part_id}: decomposition hit the {len(hulls)} hull cap; a more concave part "
            "would be approximated more coarsely"
        )
    if part_volume > 0.0 and not (MIN_FILL_RATIO <= fill <= MAX_FILL_RATIO):
        warnings.append(
            f"{part.part_id}: hulls cover {fill:.2f}x the part's volume "
            f"({MIN_FILL_RATIO} to {MAX_FILL_RATIO} is expected); check the tessellation"
        )
    return CollisionMesh(
        part_id=part.part_id,
        hulls=hulls,
        triangle_count=int(len(faces)),
        closed=closed,
        method=method,
        part_volume_m3=part_volume,
        fill_ratio=fill,
        warnings=warnings,
    )


# ------------------------------------------------------------------------------------------------
# MuJoCo assets
# ------------------------------------------------------------------------------------------------
def write_obj(hull: Hull, path: str | Path) -> Path:
    """Write one hull as an OBJ file, in the units the file already carries (metres)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"v {x:.9g} {y:.9g} {z:.9g}" for x, y, z in hull.vertices]
    lines.extend(f"f {a + 1} {b + 1} {c + 1}" for a, b, c in hull.faces)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def write_assets(mesh: CollisionMesh, directory: str | Path) -> list[str]:
    """Write every hull of one part, returning the file names in geom order."""
    base = Path(directory)
    names: list[str] = []
    for index, hull in enumerate(mesh.hulls):
        name = f"{mesh.part_id}_h{index}.obj"
        write_obj(hull, base / name)
        names.append(name)
    return names


def mjcf_fragment(mesh: CollisionMesh, asset_names: list[str], body_name: str) -> tuple[str, str]:
    """Return ``(<asset> lines, <geom> lines)`` for one collision body.

    Mesh geoms are written with ``contype``/``conaffinity`` at their defaults and no mass override:
    MuJoCo derives mass from the mesh volume and a density, and overriding it here would disagree
    with the mass this compiler measured from the B-rep.
    """
    if len(asset_names) != len(mesh.hulls):
        raise CollisionError(
            f"{mesh.part_id}: {len(asset_names)} assets for {len(mesh.hulls)} hulls"
        )
    assets = "\n".join(f'      <mesh name="{Path(n).stem}" file="{n}"/>' for n in asset_names)
    geoms = "\n".join(
        f'      <geom name="{body_name}_h{i}" type="mesh" mesh="{Path(n).stem}"/>'
        for i, n in enumerate(asset_names)
    )
    return assets, geoms


def mjcf_body(mesh: CollisionMesh, directory: str | Path, body_name: str | None = None) -> str:
    """A complete ``<body>`` block with its ``<asset>`` entries, ready to drop into an MJCF file."""
    name = body_name or mesh.part_id
    assets, geoms = mjcf_fragment(mesh, write_assets(mesh, directory), name)
    return (
        "  <asset>\n"
        f"{assets}\n"
        "  </asset>\n"
        "  <worldbody>\n"
        f'    <body name="{name}" pos="0 0 0">\n'
        "      <freejoint/>\n"
        f"{geoms}\n"
        "    </body>\n"
        "  </worldbody>"
    )


def load_in_mujoco(mjcf_body: str, directory: str | Path):
    """Load an MJCF fragment in MuJoCo, returning the model and every warning it emitted.

    The warning callback is how this module proves "zero warnings" instead of claiming it: MuJoCo
    reports an unusable mesh through that channel, and a test that ignores it proves nothing.
    """
    import mujoco

    warnings: list[str] = []

    def _collect(text) -> None:  # pragma: no cover - only fires on a bad model
        warnings.append(str(text))

    previous = mujoco.get_mju_user_warning()
    mujoco.set_mju_user_warning(_collect)
    try:
        xml = f'<mujoco model="collision-check">\n{mjcf_body}\n</mujoco>'
        model = mujoco.MjModel.from_xml_string(xml, assets=_asset_dict(directory))
    finally:
        mujoco.set_mju_user_warning(previous)
    return model, warnings


def _asset_dict(directory: str | Path) -> dict[str, bytes]:
    base = Path(directory)
    return {p.name: p.read_bytes() for p in base.glob("*.obj")}


__all__ = [
    "COACD_MAX_HULLS",
    "COACD_SEED",
    "COACD_THRESHOLD",
    "CollisionError",
    "CollisionMesh",
    "Hull",
    "collision_mesh",
    "convex_hull",
    "decompose",
    "load_in_mujoco",
    "mjcf_body",
    "mjcf_fragment",
    "tessellate",
    "write_assets",
    "write_obj",
]
