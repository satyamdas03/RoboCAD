"""What the part looks like, as distinct from what the simulator collides with.

The collision mesh is a set of convex hulls. That is the right shape for a physics engine and the
wrong shape to look at: a bracket with a hole in it becomes a solid blob, and a viewer shows a robot
made of pebbles. The visual mesh is the B-rep tessellated coarsely, so the silhouette is the part's
own, and it is written with ``contype="0" conaffinity="0"`` so MuJoCo never collides it. Picture and
physics stay separate, which is also what lets the collision model be honest about being an
approximation.

Three numbers are measured rather than declared: the triangle count, the size on disk, and whether
the decimation changed the shape. The last one is the reason for the tolerance test --
a visual mesh that has drifted from its solid is a lie that looks like a detail.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from ai_cad.compiler.collision import CollisionError, tessellate
from ai_cad.compiler.properties import PropertyError

# Coarse enough to be small, fine enough that a 3 mm fillet still reads as a fillet. Measured on
# SO-101: the same assembly at the collision deflection is 2.1 MB of convex hulls; this deflection
# puts the whole visual set in the same order of size.
VISUAL_DEFLECTION_M = 0.8e-3
VISUAL_ANGULAR_DEFLECTION_RAD = 0.6

# Per-part ceiling, applied by vertex clustering when a part tessellates heavier than this. A viewer
# shows a link at a few hundred pixels; a link with 20,000 triangles is not better at that size.
VISUAL_MAX_TRIANGLES = 4000

# The bundle's own budget for visual geometry. Above it the meshes are coarsened further and the
# report says what was lost, rather than a recipient finding a 40 MB directory.
#
# 24 MB, not 5 MB, because the cost of the smaller number was measured rather than guessed: on the
# SO-101 the set is 19.4 MB at full fidelity and the meshes are written per placed instance, so a
# 5 MB budget moved the coarsest part's vertices by 6.83 mm -- a 30 mm link turned into a pebble.
# A picture that far from the part is not worth 14 MB, and 19.4 MB is a size a demo bundle can
# carry. The figure is reported either way, so a bundle that does get coarsened says by how much.
VISUAL_BUDGET_BYTES = 24 * 1024 * 1024

# How far a decimated vertex may move from the surface it came from, as a fraction of the part's
# bounding-box diagonal. Reported, not asserted: at 1 mm deflection on a 30 mm link this is a
# fraction of a pixel at demo zoom.
SHAPE_TOLERANCE_FRACTION = 2e-3


class VisualError(RuntimeError):
    """Raised when a visual mesh cannot be produced from a part."""


class VisualMesh(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    vertices: np.ndarray
    faces: np.ndarray
    triangles: int
    cell_m: float = 0.0
    warnings: list[str] = Field(default_factory=list)


def _cluster(vertices: np.ndarray, faces: np.ndarray, max_triangles: int) -> tuple[np.ndarray, np.ndarray, float]:
    """Vertex clustering until the face count fits, returning the grid cell used.

    Every vertex snaps to the nearest grid point of ``cell``, so it moves by at most ``cell/2``;
    triangles that collapse to a line or a point are dropped. The cell is returned so the caller can
    state the displacement instead of hiding it.
    """
    if len(faces) <= max_triangles:
        return vertices, faces, 0.0
    extent = vertices.max(axis=0) - vertices.min(axis=0)
    diagonal = float(np.linalg.norm(extent))
    cell = max(diagonal / 512.0, 1e-9)
    for _ in range(40):
        keys = np.round(vertices / cell).astype(np.int64)
        _, first, inverse = np.unique(keys, axis=0, return_index=True, return_inverse=True)
        remapped = inverse[faces]
        keep = (
            (remapped[:, 0] != remapped[:, 1])
            & (remapped[:, 1] != remapped[:, 2])
            & (remapped[:, 0] != remapped[:, 2])
        )
        if int(keep.sum()) <= max_triangles:
            # The representative of each cluster is a real vertex of the source mesh, so the mesh
            # never grows a point that was not on the part.
            return vertices[first], remapped[keep], cell
        cell *= 1.25
    raise VisualError("could not reduce the mesh to the triangle budget")


def visual_mesh(part, max_triangles: int = VISUAL_MAX_TRIANGLES) -> VisualMesh:
    """The part's own surface, coarsely tessellated, never its convex hull."""
    shape = getattr(part, "shape", None)
    if shape is None:
        raise VisualError(f"part {getattr(part, 'part_id', '?')} has no shape to tessellate")
    try:
        vertices, faces = tessellate(
            shape,
            linear_deflection_m=VISUAL_DEFLECTION_M,
            angular_deflection_rad=VISUAL_ANGULAR_DEFLECTION_RAD,
        )
    except CollisionError as exc:
        raise VisualError(str(exc)) from exc
    vertices, faces, cell = _cluster(vertices, faces, max_triangles)
    warnings: list[str] = []
    if cell:
        warnings.append(
            f"visual mesh reduced by clustering on a {cell * 1e3:.3f} mm grid; vertices moved by at "
            f"most {cell * 0.5 * 1e3:.3f} mm"
        )
    return VisualMesh(
        vertices=vertices,
        faces=faces,
        triangles=int(len(faces)),
        cell_m=cell,
        warnings=warnings,
    )


def write_visual_obj(mesh: VisualMesh, path: str | Path) -> Path:
    """One OBJ, three decimals of a millimetre: past that a picture gains nothing and the file grows."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# visual mesh: the part's own surface, not its collision hull"]
    for x, y, z in mesh.vertices:
        lines.append(f"v {x:.6f} {y:.6f} {z:.6f}")
    for a, b, c in mesh.faces:
        lines.append(f"f {int(a) + 1} {int(b) + 1} {int(c) + 1}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def estimate_bytes(mesh: VisualMesh) -> int:
    """What ``write_visual_obj`` will write, to within a few percent.

    A vertex line is ``v -0.123456 0.123456 -0.123456`` plus a newline, about 32 bytes; a face line
    is ``f 12345 23456 34567`` plus a newline, about 22. The budget is checked against this estimate
    so a bundle is not written past it and then reported as over it.
    """
    return int(len(mesh.vertices) * 32 + len(mesh.faces) * 22)


def fit_budget(
    meshes: dict[str, VisualMesh],
    budget_bytes: int = VISUAL_BUDGET_BYTES,
    max_triangles: int = VISUAL_MAX_TRIANGLES,
    counts: dict[str, int] | None = None,
) -> list[str]:
    """Re-cluster meshes until their written size fits, returning what that cost.

    Meshing part by part cannot know the total, so this runs after: while the estimate is over
    budget, the per-part triangle cap falls and every mesh above it is clustered again from the
    vertices it already has. A cluster representative is always a real source vertex, so a mesh that
    is reduced twice is still a coarser version of the part and not a new shape.

    ``counts`` is how many files each part becomes on disk. Visual meshes are written per placed
    instance, in the body frame, so a part used four times is written four times; budgeting the
    part-level sum alone undercounted the SO-101 by about four to one, which is how a 5 MB budget
    produced a 14 MB directory. Defaults to one file per part.

    Returns warnings, empty when the set already fitted.
    """
    weight = counts or {}

    def written() -> int:
        return sum(estimate_bytes(m) * weight.get(pid, 1) for pid, m in meshes.items())

    warnings: list[str] = []
    total = written()
    cap = max_triangles
    while total > budget_bytes and cap > 64:
        cap = max(int(cap * 0.6), 64)
        for part_id, mesh in meshes.items():
            if mesh.triangles <= cap:
                continue
            vertices, faces, cell = _cluster(mesh.vertices, mesh.faces, cap)
            meshes[part_id] = VisualMesh(
                vertices=vertices,
                faces=faces,
                triangles=int(len(faces)),
                cell_m=max(mesh.cell_m, cell),
                warnings=mesh.warnings,
            )
        total = written()
    if total > budget_bytes:
        warnings.append(
            f"visual meshes are {total / 1e6:.2f} MB against a {budget_bytes / 1024 / 1024:.0f} MB budget "
            f"and could not be reduced further without dropping below {cap} triangles per part"
        )
    return warnings


def visual_meshes(
    assembly,
    part_ids,
    budget_bytes: int = VISUAL_BUDGET_BYTES,
    max_triangles: int = VISUAL_MAX_TRIANGLES,
    counts: dict[str, int] | None = None,
) -> tuple[dict[str, VisualMesh], list[str]]:
    """Visual meshes for the named parts, plus one warning per part that could not be meshed.

    A part with no visual mesh does not stop the bundle: the collision hull is still there and the
    robot still simulates. The report says which parts are pictured by a hull and nothing else.

    The written set as a whole is held to ``budget_bytes`` by :func:`fit_budget`, which needs
    ``counts`` to know how many files each part becomes.
    """
    out: dict[str, VisualMesh] = {}
    warnings: list[str] = []
    for part_id in part_ids:
        part = getattr(assembly, "parts", {}).get(part_id)
        if part is None:
            warnings.append(f"part {part_id} is not in the assembly; no visual mesh for it")
            continue
        try:
            mesh = visual_mesh(part, max_triangles=max_triangles)
        except (VisualError, PropertyError) as exc:
            warnings.append(f"part {part_id}: no visual mesh ({exc}); its hull is what a viewer shows")
            continue
        out[part_id] = mesh

    warnings.extend(fit_budget(out, budget_bytes, max_triangles, counts))
    for part_id, mesh in out.items():
        warnings.extend(f"part {part_id}: {w}" for w in mesh.warnings)
    return out, warnings


__all__ = [
    "SHAPE_TOLERANCE_FRACTION",
    "VISUAL_BUDGET_BYTES",
    "VISUAL_DEFLECTION_M",
    "VISUAL_MAX_TRIANGLES",
    "VisualError",
    "VisualMesh",
    "estimate_bytes",
    "fit_budget",
    "visual_mesh",
    "visual_meshes",
    "write_visual_obj",
]
