"""Safely execute generated build123d code and capture the resulting shape."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Optional


def _cleanup_stale_artifacts(output_dir: Path, max_age_seconds: float = 86400.0) -> None:
    """Remove execution artifacts older than ``max_age_seconds`` to bound disk growth."""
    if not output_dir.exists():
        return
    cutoff = time.time() - max_age_seconds
    for path in output_dir.iterdir():
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            pass


def execute_code(
    code: str,
    timeout: int = 60,
    output_dir: Optional[Path] = None,
) -> dict:
    """Run generated Python code in a subprocess and return the `result` object.

    The generated code must define a top-level variable named `result` that is a
    build123d Shape. The executor serializes it to STEP/STL files and loads basic
    metadata.

    Returns a dict with keys:
        - success: bool
        - result_type: str or None
        - error: str or None
        - traceback: str or None
        - script_path: Path or None
        - step_path: Path or None
        - stl_path: Path or None
        - bounds: tuple or None
        - volume: float or None
    """
    if output_dir is None:
        output_dir = Path("output") / "executions"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Bound disk growth from long-running servers / repeated regenerations.
    _cleanup_stale_artifacts(output_dir)

    run_id = uuid.uuid4().hex[:8]
    script_path = output_dir / f"generated_{run_id}.py"
    step_path = output_dir / f"result_{run_id}.step"
    stl_path = output_dir / f"result_{run_id}.stl"
    metadata_path = output_dir / f"metadata_{run_id}.json"
    error_path = output_dir / f"error_{run_id}.txt"

    # Wrap user code so we can export and inspect the result.
    # We use JSON for metadata to avoid stdout parsing pitfalls.
    wrapper = f"""
{code}

import json
import sys
import traceback

_metadata_path = r"{metadata_path.as_posix()}"
_step_path = r"{step_path.as_posix()}"
_stl_path = r"{stl_path.as_posix()}"

try:
    if "result" not in dir():
        raise NameError("Generated code did not define a top-level variable named 'result'.")

    shape = result

    from build123d import export_step, export_stl
    export_step(shape, _step_path)
    export_stl(shape, _stl_path)

    bounds = shape.bounding_box().size if hasattr(shape, "bounding_box") else None
    volume = shape.volume if hasattr(shape, "volume") else None
    shape_type = type(shape).__name__

    metadata = {{
        "success": True,
        "type": shape_type,
        "bounds": list(bounds) if bounds is not None else None,
        "volume": volume,
    }}
    with open(_metadata_path, "w", encoding="utf-8") as _f:
        json.dump(metadata, _f)
    print("__ROBOCAD_SUCCESS__")
except Exception as _exc:
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
        error_path.write_text(f"Execution timed out after {timeout}s.", encoding="utf-8")
        return _failure(
            f"Execution timed out after {timeout}s.",
            script_path=script_path,
        )

    if proc.returncode != 0:
        error_path.write_text(proc.stderr, encoding="utf-8")
        return _failure(
            "Generated code failed to execute.",
            traceback=proc.stderr,
            script_path=script_path,
        )

    metadata = _load_metadata(metadata_path)

    result = {
        "success": metadata.get("success", False),
        "result_type": metadata.get("type"),
        "error": None,
        "traceback": None,
        "script_path": script_path,
        "step_path": step_path if step_path.exists() else None,
        "stl_path": stl_path if stl_path.exists() else None,
        "bounds": _parse_bounds(metadata.get("bounds")),
        "volume": metadata.get("volume"),
    }

    # Clean up the temporary generated script and empty error file on success.
    # STL/STEP are retained briefly so callers can copy them; stale-artifact
    # cleanup removes old files after the configured retention window.
    if result["success"] and os.environ.get("ROBOCAD_KEEP_EXECUTION_ARTIFACTS") != "1":
        for path in (script_path, error_path):
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                pass

    return result


def _failure(
    error: str,
    traceback: str = "",
    script_path: Optional[Path] = None,
) -> dict:
    return {
        "success": False,
        "result_type": None,
        "error": error,
        "traceback": traceback,
        "script_path": script_path,
        "step_path": None,
        "stl_path": None,
        "bounds": None,
        "volume": None,
    }


def _load_metadata(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _parse_bounds(bounds: Any) -> tuple[float, ...] | None:
    if bounds is None:
        return None
    try:
        return tuple(float(x) for x in bounds)
    except (ValueError, TypeError):
        return None
