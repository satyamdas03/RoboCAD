"""Safely execute generated build123d code and capture the resulting shape."""
from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Any, Optional


def execute_code(
    code: str,
    timeout: int = 60,
    output_dir: Optional[Path] = None,
) -> dict:
    """Run generated Python code in a subprocess and return the `result` object.

    The generated code must define a top-level variable named `result` that is a
    build123d Shape. The executor serializes it to a STEP file and loads basic
    metadata.

    Returns a dict with keys:
        - success: bool
        - result_type: str or None
        - error: str or None
        - traceback: str or None
        - step_path: Path or None
        - stl_path: Path or None
        - bounds: tuple or None
        - volume: float or None
    """
    import subprocess
    import sys

    if output_dir is None:
        output_dir = Path("output") / "executions"
    output_dir.mkdir(parents=True, exist_ok=True)

    run_id = uuid.uuid4().hex[:8]
    script_path = output_dir / f"generated_{run_id}.py"
    step_path = output_dir / f"result_{run_id}.step"
    stl_path = output_dir / f"result_{run_id}.stl"
    error_path = output_dir / f"error_{run_id}.txt"

    # Wrap user code so we can export and inspect the result.
    wrapper = f"""
{code}

import traceback
import sys

try:
    # Ensure result exists
    if "result" not in dir():
        raise NameError("Generated code did not define a top-level variable named 'result'.")

    shape = result

    # Export STEP
    from build123d import export_step
    export_step(shape, r"{step_path.as_posix()}")

    # Export STL
    from build123d import export_stl
    export_stl(shape, r"{stl_path.as_posix()}")

    # Compute basic metadata
    bounds = shape.bounding_box().size if hasattr(shape, "bounding_box") else None
    volume = shape.volume if hasattr(shape, "volume") else None
    shape_type = type(shape).__name__

    print("__ROBOCAD_SUCCESS__")
    print(f"type={{shape_type}}")
    print(f"bounds={{' '.join(str(x) for x in bounds)}}" if bounds else "bounds=None")
    print(f"volume={{volume}}" if volume is not None else "volume=None")
except Exception as exc:
    traceback.print_exc()
    sys.exit(1)
"""

    script_path.write_text(wrapper, encoding="utf-8")

    try:
        proc = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "result_type": None,
            "error": f"Execution timed out after {timeout}s.",
            "traceback": "",
            "step_path": None,
            "stl_path": None,
            "bounds": None,
            "volume": None,
        }

    if proc.returncode != 0:
        error_path.write_text(proc.stderr, encoding="utf-8")
        return {
            "success": False,
            "result_type": None,
            "error": "Generated code failed to execute.",
            "traceback": proc.stderr,
            "step_path": None,
            "stl_path": None,
            "bounds": None,
            "volume": None,
        }

    # Parse metadata from stdout.
    metadata = _parse_metadata(proc.stdout)

    return {
        "success": True,
        "result_type": metadata.get("type"),
        "error": None,
        "traceback": None,
        "step_path": step_path if step_path.exists() else None,
        "stl_path": stl_path if stl_path.exists() else None,
        "bounds": metadata.get("bounds"),
        "volume": metadata.get("volume"),
    }


def _parse_metadata(stdout: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    success = "__ROBOCAD_SUCCESS__" in stdout
    metadata["success"] = success
    for line in stdout.splitlines():
        if line.startswith("type="):
            metadata["type"] = line.split("=", 1)[1].strip()
        elif line.startswith("bounds="):
            value = line.split("=", 1)[1].strip()
            if value != "None":
                try:
                    metadata["bounds"] = tuple(float(x) for x in value.split())
                except ValueError:
                    metadata["bounds"] = None
            else:
                metadata["bounds"] = None
        elif line.startswith("volume="):
            value = line.split("=", 1)[1].strip()
            if value != "None":
                try:
                    metadata["volume"] = float(value)
                except ValueError:
                    metadata["volume"] = None
            else:
                metadata["volume"] = None
    return metadata
