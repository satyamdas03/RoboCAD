"""Export build123d shapes to common manufacturing formats."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from build123d import export_step, export_stl


def export_model(
    shape,
    output_dir: Path,
    name: str = "model",
) -> dict[str, Optional[Path]]:
    """Export a build123d shape to STEP and STL.

    Returns a dict mapping format to Path or None on failure.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    step_path = output_dir / f"{name}.step"
    stl_path = output_dir / f"{name}.stl"

    try:
        export_step(shape, str(step_path))
    except Exception as exc:
        print(f"STEP export failed: {exc}")
        step_path = None

    try:
        export_stl(shape, str(stl_path))
    except Exception as exc:
        print(f"STL export failed: {exc}")
        stl_path = None

    return {"step": step_path, "stl": stl_path}
