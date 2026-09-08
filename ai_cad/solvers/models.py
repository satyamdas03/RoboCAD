"""Shared data models for the RoboCAD solver adapters.

Lightweight containers for meshes, boundary conditions, and solver results.  The
mesh representation is intentionally minimal (nodes + hexahedral elements) so
that adapters can write input decks for CalculiX and ElmerFEM without touching
the geometry-prep or meshing subsystems.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import numpy as np


class BoundaryConditionType(str, Enum):
    """Kinds of boundary condition adapters must understand."""

    FIXED = "fixed"
    FORCE = "force"
    PRESSURE = "pressure"
    TEMPERATURE = "temperature"
    HEAT_FLUX = "heat_flux"
    CONVECTION = "convection"


@dataclass
class BoundaryCondition:
    """A single boundary condition applied to a named region or node list."""

    bc_type: BoundaryConditionType | str
    region: str | list[int]
    value: float = 0.0
    direction: Optional[tuple[float, float, float]] = None
    label: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.bc_type, str):
            self.bc_type = BoundaryConditionType(self.bc_type)


@dataclass
class Mesh:
    """A tiny finite-element mesh used by solver adapters.

    Nodes and elements are 1-based in the files we write, but internally the
    arrays are stored 0-based for NumPy convenience.  ``node_sets`` are named
    groups of node IDs (1-based) used for boundary conditions.
    """

    nodes: np.ndarray
    elements: np.ndarray
    node_sets: dict[str, list[int]] = field(default_factory=dict)
    element_sets: dict[str, list[int]] = field(default_factory=dict)
    divisions: Optional[tuple[int, int, int]] = None

    def __post_init__(self) -> None:
        self.nodes = np.asarray(self.nodes, dtype=float)
        self.elements = np.asarray(self.elements, dtype=int)
        if self.elements.size > 0 and self.elements.min() == 0:
            raise ValueError("Mesh.elements must be 1-based (CalculiX/Elmer require ids >= 1).")

    @property
    def node_count(self) -> int:
        return int(self.nodes.shape[0])

    @property
    def element_count(self) -> int:
        return int(self.elements.shape[0])

    @staticmethod
    def box(
        extents: tuple[float, float, float] = (1.0, 1.0, 1.0),
        divisions: tuple[int, int, int] = (4, 4, 4),
        origin: tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> "Mesh":
        """Create a structured hexahedral box mesh.

        Args:
            extents: (dx, dy, dz) of the box.
            divisions: number of elements along (x, y, z).
            origin: minimum corner coordinate.

        Returns:
            Mesh with node sets for faces ``-x``, ``+x``, ``-y``, ``+y``,
            ``-z``, ``+z`` and ``divisions`` metadata.
        """
        dx, dy, dz = extents
        nx, ny, nz = divisions
        nx_nodes, ny_nodes, nz_nodes = nx + 1, ny + 1, nz + 1

        coords = np.zeros((nx_nodes * ny_nodes * nz_nodes, 3), dtype=float)
        for k in range(nz_nodes):
            for j in range(ny_nodes):
                for i in range(nx_nodes):
                    idx = i + j * nx_nodes + k * nx_nodes * ny_nodes
                    coords[idx] = [
                        origin[0] + dx * i / nx,
                        origin[1] + dy * j / ny,
                        origin[2] + dz * k / nz,
                    ]

        elements = []
        for k in range(nz):
            for j in range(ny):
                for i in range(nx):
                    n0 = i + j * nx_nodes + k * nx_nodes * ny_nodes
                    n1 = n0 + 1
                    n2 = n1 + nx_nodes
                    n3 = n0 + nx_nodes
                    n4 = n0 + nx_nodes * ny_nodes
                    n5 = n4 + 1
                    n6 = n5 + nx_nodes
                    n7 = n4 + nx_nodes
                    # 1-based ids, CalculiX/Elmer convention.
                    elements.append([n0 + 1, n1 + 1, n2 + 1, n3 + 1, n4 + 1, n5 + 1, n6 + 1, n7 + 1])

        elements = np.asarray(elements, dtype=int)

        tol = 1e-9
        node_sets: dict[str, list[int]] = {}
        for name, axis, sign in [
            ("-x", 0, -1),
            ("+x", 0, +1),
            ("-y", 1, -1),
            ("+y", 1, +1),
            ("-z", 2, -1),
            ("+z", 2, +1),
        ]:
            coord = origin[axis] if sign == -1 else origin[axis] + extents[axis]
            mask = np.abs(coords[:, axis] - coord) < tol
            node_sets[name] = (np.nonzero(mask)[0] + 1).tolist()

        return Mesh(nodes=coords, elements=elements, node_sets=node_sets, divisions=divisions)


@dataclass
class SolverResult:
    """Result returned by every solver adapter."""

    success: bool
    solver: str
    analysis_type: str
    input_files: list[Path]
    result_files: dict[str, Path | None]
    metrics: dict[str, float]
    errors: list[str]
    details: dict[str, Any]
    raw_output: dict[str, Any] | None = None

    def model_dump(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "solver": self.solver,
            "analysis_type": self.analysis_type,
            "input_files": [p.as_posix() for p in self.input_files],
            "result_files": {k: (v.as_posix() if v else None) for k, v in self.result_files.items()},
            "metrics": self.metrics,
            "errors": self.errors,
            "details": self.details,
            "raw_output": self.raw_output,
        }


class SurfaceLabel(str, Enum):
    """Semantic role for a surface face."""

    INLET = "inlet"
    OUTLET = "outlet"
    WALL = "wall"
    LOAD = "load"
    FIXTURE = "fixture"


@dataclass
class GeometryPrepResult:
    """Result of loading and labelling a surface mesh."""

    success: bool
    mesh: Any = None
    labels: dict[int, SurfaceLabel] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def model_dump(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "mesh": None,
            "labels": {k: v.value for k, v in self.labels.items()},
            "errors": self.errors,
            "details": self.details,
        }
