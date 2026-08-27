"""Runtime validation of GEDA Bridge bundles by loading them in MuJoCo."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:  # pragma: no cover - exercised only where mujoco is installed.
    import mujoco
except Exception:  # noqa: BLE001
    mujoco = None


def validate_bundle_with_mujoco(bundle_dir: Path) -> dict[str, Any]:
    """Load a bundle's MJCF and URDF into MuJoCo and run a short simulation.

    The MJCF/URDF filenames are read from ``manifest.json`` (``mjcf_file`` /
    ``urdf_file``). If the manifest omits them, the function falls back to the
    first ``*.mjcf`` / ``*.urdf`` file in the bundle directory.

    Returns a dict with:

    - ``mujoco_available`` (bool)
    - ``mjcf_loadable`` (bool)
    - ``urdf_loadable`` (bool)
    - ``mjcf_nbody`` (int)
    - ``urdf_nbody`` (int)
    - ``sim_steps_ok`` (bool)
    - ``errors`` (list[str])
    - ``warnings`` (list[str])
    """
    bundle_dir = Path(bundle_dir)
    result: dict[str, Any] = {
        "mujoco_available": mujoco is not None,
        "mjcf_loadable": False,
        "urdf_loadable": False,
        "mjcf_nbody": 0,
        "urdf_nbody": 0,
        "sim_steps_ok": False,
        "errors": [],
        "warnings": [],
    }

    if mujoco is None:
        result["warnings"].append(
            "mujoco is not installed; skipping runtime load validation."
        )
        return result

    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.exists():
        result["errors"].append("manifest.json not found in bundle.")
        return result

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"Failed to parse manifest.json: {exc}")
        return result

    name = manifest.get("name", "model")

    def _resolve_path(field_name: str, extension: str) -> Path:
        file_name = manifest.get(field_name)
        if file_name:
            return bundle_dir / file_name
        candidates = sorted(bundle_dir.glob(f"*{extension}"))
        if candidates:
            chosen = candidates[0]
            result["warnings"].append(
                f"manifest missing {field_name}; falling back to {chosen.name}."
            )
            return chosen
        assumed = bundle_dir / f"{name}{extension}"
        result["warnings"].append(
            f"manifest missing {field_name}; assumed {assumed.name}."
        )
        return assumed

    mjcf_path = _resolve_path("mjcf_file", ".mjcf")
    urdf_path = _resolve_path("urdf_file", ".urdf")

    sim_attempted = False
    sim_ok: list[bool] = []

    for label, path in (("mjcf", mjcf_path), ("urdf", urdf_path)):
        load_key = f"{label}_loadable"
        nbody_key = f"{label}_nbody"

        if not path.exists():
            result["errors"].append(f"{label.upper()} file not found: {path.name}")
            sim_ok.append(False)
            continue

        try:
            model = mujoco.MjModel.from_xml_path(str(path))
            result[load_key] = True
            result[nbody_key] = int(getattr(model, "nbody", 0))
        except Exception as exc:  # noqa: BLE001
            result["errors"].append(
                f"Failed to load {label.upper()} {path.name}: {exc}"
            )
            sim_ok.append(False)
            continue

        try:
            data = mujoco.MjData(model)
            for _ in range(20):
                mujoco.mj_step(model, data)
            sim_attempted = True
            sim_ok.append(True)
        except Exception as exc:  # noqa: BLE001
            result["errors"].append(
                f"Simulation failed for {label.upper()} {path.name}: {exc}"
            )
            sim_ok.append(False)

    result["sim_steps_ok"] = all(sim_ok) if sim_attempted else False
    return result
