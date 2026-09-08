# Optional Solver Installation Guide

RoboCAD uses open-source, GPL-compatible engineering solvers for deep multi-physics verification. These solvers are **optional**: when they are not installed, RoboCAD automatically falls back to lightweight built-in estimates and surrogate models.

## Quick start

Run the convenience bootstrap and then the health checker:

```bash
python scripts/setup_solvers.py
python -m robocad.health
```

Use `--dry-run` to preview commands without installing, and `--check` to see what is already installed:

```bash
python scripts/setup_solvers.py --dry-run
python scripts/setup_solvers.py --check
```

## Solvers

### CalculiX (structural FEA)

Adapter uses `ccx` from CalculiX CrunchiX.

- **Ubuntu/Debian:** `sudo apt install calculix-ccx`
- **Windows:** Download from <https://www.calculix.de> and add `ccx` to `PATH`.
- **macOS:** Build from source or use a precompiled package manager formula.

### ElmerFEM (multiphysics / thermal)

Adapter uses `ElmerSolver`.

- **Ubuntu:** `sudo snap install elmerfem-csc` or see <https://www.elmerfem.org/blog/binaries/>.
- **Windows:** Precompiled binaries are available at the link above.
- **Arch:** `sudo pacman -S elmerfem`

### OpenFOAM (CFD)

Adapter uses `blockMesh` / `simpleFoam` / `icoFoam`.

- **Ubuntu:** Follow <https://openfoam.org/download/>.
- **macOS:** `brew install openfoam`
- **Windows:** Install inside WSL2 or use the official Docker image. Windows native builds exist but are less stable.

### Gmsh (mesh generation helper)

Used indirectly by some export paths.

- `pip install gmsh` installs the Python SDK, but the standalone binary is usually still required for `.geo` meshing.
- Binaries: <https://gmsh.info/#Download>

## Licensing

RoboCAD **does not bundle or link against these solvers**. It invokes them as external command-line tools through `subprocess`. Their respective licenses apply to the installed binaries:

- CalculiX: GPL v2 or later
- ElmerFEM: LGPL v2.1 or later
- OpenFOAM: GPL v3
- Gmsh: GPL v2 (for the GUI) / free for command-line use

Because they are invoked as separate processes, integrating them does not change the license of RoboCAD itself.

## Troubleshooting

- `python -m robocad.health` prints an `install_hint` for every missing solver.
- Set the solver mode in API calls to `"auto"` to use real solvers when available and fall back otherwise.
- Set it to `"surrogate"` if you never want to require binaries.
