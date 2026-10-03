"""Demo: morphology search + MuJoCo walking with frame capture.

Produces a small report directory with rendered frames and a JSON metrics file.
The walking evaluation uses the same ``physics_score_candidate`` path that the
morphology scorer uses internally, so the captured behavior is identical to the
one that contributes to the composite score.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

# Ensure repo root is on path so `ai_cad` imports resolve regardless of cwd.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    import mujoco
except Exception as exc:
    raise SystemExit(f"MuJoCo is required for this demo: {exc}") from exc

from ai_cad.gait_adaptation import extract_morphology_features
from ai_cad.morphology import default_space, search_morphologies
from ai_cad.morphology_physics import physics_score_candidate
from ai_cad.robot_templates import humanoid_template, quadruped_template


OUT_DIR = Path(__file__).resolve().parent.parent / "demo_output" / "morphology_walk"
LOG_FILE = OUT_DIR / "progress.log"
N_STEPS = 100
CAPTURE_INTERVAL = 20
WIDTH, HEIGHT = 640, 360


def _log(msg: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{msg}\n"
    LOG_FILE.write_text(LOG_FILE.read_text(encoding="utf-8") + line, encoding="utf-8")
    print(msg, flush=True)


def _test_walk(tree, label: str, n_steps: int = N_STEPS) -> dict[str, Any]:
    """Score a candidate with the real physics path and capture frames."""
    tmp_path = Path(tempfile.mkdtemp(prefix=f"robocad_demo_{label}_"))
    frames: list[Any] = []
    frame_times: list[float] = []
    renderer: Any | None = None

    def _capture(step: int, model, data) -> None:
        nonlocal renderer
        if renderer is None:
            # MuJoCo Renderer signature is (model, height, width).
            renderer = mujoco.Renderer(model, HEIGHT, WIDTH)
        if step % CAPTURE_INTERVAL != 0:
            return
        # Do NOT call mj_forward here: mj_step has already left `data` in a
        # consistent state, and calling mj_forward would overwrite the solver
        # warm-start (qacc_warmstart) and destabilize the walking rollout.
        renderer.update_scene(data)
        frames.append(renderer.render().copy())
        frame_times.append(float(data.time))

    try:
        result = physics_score_candidate(
            tree,
            n_steps=n_steps,
            tmp_dir=tmp_path,
            cleanup=False,
            step_callback=_capture,
        )
    finally:
        # The compiled model keeps mesh data in memory, so the temp directory can
        # be removed once scoring is complete. Ignore any Windows file-handle
        # races and leave the directory behind if deletion fails.
        shutil.rmtree(tmp_path, ignore_errors=True)

    # Extract morphology features from the default pose for the report.
    from ai_cad.gait import _detect_template

    with tempfile.TemporaryDirectory() as tmp:
        from ai_cad.geda_bridge.exporter import export_bundle_from_tree
        from ai_cad.morphology_physics import _scale_masses_and_add_freejoint

        bundle_dir = Path(tmp) / label
        bundle_dir.mkdir()
        bundle = export_bundle_from_tree(tree, bundle_dir, name=label)
        _scale_masses_and_add_freejoint(bundle.mjcf, tree)
        model = mujoco.MjModel.from_xml_path(str(bundle.mjcf))
        data = mujoco.MjData(model)
        mujoco.mj_forward(model, data)
        template = _detect_template(model)
        features = extract_morphology_features(model, data, tree)

    return {
        "walk": result.get("walk", {}),
        "frames": frames,
        "frame_times": frame_times,
        "physics_score": result.get("physics_score"),
        "standing_ok": result.get("standing_ok"),
        "sway_ok": result.get("sway_ok"),
        "step_ok": result.get("step_ok"),
        "features": {
            "template": features.template,
            "com_height_m": features.com_height_m,
            "total_leg_length_m": features.total_leg_length_m,
            "robot_mass_kg": features.robot_mass_kg,
            "foot_length_m": features.foot_length_m,
            "foot_width_m": features.foot_width_m,
        },
    }


def _find_walking_candidate(template_name: str, n_max: int = 3):
    _log(f"\nSearching {template_name} morphology grid (n_max={n_max})...")
    space = default_space(template_name)
    space.n_max = n_max
    # Fast heuristic search first; we then run the expensive physics scorer only
    # on the top candidates to keep the demo interactive.
    candidates = search_morphologies(
        space,
        payload_kg=2.0,
        robot_mass_kg=20.0,
        use_physics=False,
        use_structural=True,
        use_collision=False,
    )
    candidates = sorted(candidates, key=lambda c: -c.composite_score)
    _log(f"  {len(candidates)} candidates; top composite = {candidates[0].composite_score:.3f}")

    # Test the top 2 candidates with the same physics scorer used by the search.
    for i, cand in enumerate(candidates[:2], 1):
        _log(f"  Testing candidate {i}/{len(candidates[:2])} (composite={cand.composite_score:.3f})...")
        result = _test_walk(cand.tree, f"{template_name}_cand{i}", n_steps=N_STEPS)
        walk = result["walk"]
        _log(
            f"  walk_ok={walk.get('walk_ok')}  "
            f"forward={walk.get('forward_distance_m', 0):.3f}m  "
            f"drop={walk.get('torso_z_drop_m', 1):.3f}m  "
            f"tilt={walk.get('max_pitch_roll_deg', 90):.1f}deg  "
            f"physics={result.get('physics_score')}"
        )
        if walk.get("walk_ok"):
            return result, cand, i

    return None, None, 0


def _test_default_template(template_name: str):
    _log(f"\nTesting default {template_name} template...")
    tree = humanoid_template() if template_name == "humanoid" else quadruped_template()
    result = _test_walk(tree, f"{template_name}_default", n_steps=N_STEPS)
    walk = result["walk"]
    _log(
        f"  walk_ok={walk.get('walk_ok')}  "
        f"forward={walk.get('forward_distance_m', 0):.3f}m  "
        f"drop={walk.get('torso_z_drop_m', 1):.3f}m  "
        f"tilt={walk.get('max_pitch_roll_deg', 90):.1f}deg  "
        f"physics={result.get('physics_score')}"
    )
    return result


def _save_frames(frames: list, times: list[float], out: Path, prefix: str):
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for idx, (frame, t) in enumerate(zip(frames, times)):
        path = out / f"{prefix}_frame_{idx:02d}_t{t:.2f}s.png"
        from PIL import Image

        Image.fromarray(frame).save(path)
        paths.append(str(path.relative_to(OUT_DIR)))
    return paths


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE.write_text("", encoding="utf-8")
    report: dict[str, Any] = {
        "title": "RoboCAD Morphology Search → MuJoCo Walking Demo",
        "date": "2026-10-03",
        "templates": {},
    }

    for template_name in ("humanoid", "quadruped"):
        result, cand, cand_index = _find_walking_candidate(template_name, n_max=4)
        source = f"searched candidate {cand_index}"
        if result is None:
            result = _test_default_template(template_name)
            source = "default template (fallback)"
            cand_index = 0

        walk = result["walk"]
        frame_paths = _save_frames(
            result["frames"],
            result["frame_times"],
            OUT_DIR / template_name,
            f"{template_name}_cand{cand_index}",
        )

        report["templates"][template_name] = {
            "source": source,
            "candidate_index": cand_index,
            "composite_score": cand.composite_score if cand else None,
            "physics_score": result.get("physics_score"),
            "metrics": {
                "walk_ok": bool(walk.get("walk_ok")),
                "forward_distance_m": float(walk.get("forward_distance_m", 0.0)),
                "torso_z_drop_m": float(walk.get("torso_z_drop_m", 1.0)),
                "max_pitch_roll_deg": float(walk.get("max_pitch_roll_deg", 90.0)),
                "n_steps": result.get("n_steps", 600),
                "sim_time_s": float(walk.get("sim_time_s", 0.0)),
            },
            "features": result["features"],
            "frames": frame_paths,
        }

    report_path = OUT_DIR / "report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    _log(f"\nDemo report saved to: {report_path}")
    _log(json.dumps(report["templates"], indent=2))


if __name__ == "__main__":
    main()
