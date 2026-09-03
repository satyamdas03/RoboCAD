"""Capability registry for the RoboCAD GEDA Bridge.

Exposes the features, scene templates, part families, and API contract version
that downstream consumers (e.g., `LearningRobotics`) can rely on.
"""
from __future__ import annotations

from ai_cad.geda_bridge.scene_templates import TEMPLATE_REGISTRY
from ai_cad.geda_bridge.world_builder import WORLD_TEMPLATE_REGISTRY


BUNDLE_SCHEMA_VERSION = "2.0.0"
API_VERSION = "0.5.0"

SUPPORTED_EXPORT_FORMATS = ["stl", "step", "urdf", "mjcf", "bundle.zip", "world.mjcf", "world.isaac.json"]
SUPPORTED_SIMULATORS = ["mujoco", "isaac_sim"]
SUPPORTED_PART_FAMILIES = [
    "cube",
    "cylinder",
    "wedge",
    "l_bracket",
    "gripper_jaw",
    "bracket",
    "peg",
    "plate",
    "limb_segment",
    "end_effector",
    "mount",
    "hub",
    "torso_plate",
    "hip_hub",
    "shoulder_hub",
    "foot",
]


def get_capabilities() -> dict[str, object]:
    """Return the current RoboCAD GEDA Bridge capability registry."""
    return {
        "api_version": API_VERSION,
        "bundle_schema_version": BUNDLE_SCHEMA_VERSION,
        "supported_export_formats": SUPPORTED_EXPORT_FORMATS,
        "supported_simulators": SUPPORTED_SIMULATORS,
        "supported_scene_templates": sorted(TEMPLATE_REGISTRY),
        "supported_world_templates": sorted(WORLD_TEMPLATE_REGISTRY),
        "supported_part_families": SUPPORTED_PART_FAMILIES,
        "endpoints": {
            "health": "GET /health",
            "generate": "POST /generate",
            "simulate": "POST /designs/{id}/simulate",
            "bundle": "GET /designs/{id}/bundle",
            "scene": "POST /designs/{id}/scene",
            "world": "POST /designs/{id}/world",
            "world_randomize": "POST /designs/{id}/world/randomize",
            "world_replay": "POST /designs/{id}/world/replay",
            "brain_train": "POST /designs/{id}/train-brain",
            "brain_report": "GET /designs/{id}/brain",
            "brain_replay_attention": "POST /designs/{id}/brain-replay-attention",
            "capabilities": "GET /capabilities",
            "handshake": "POST /designs/{id}/handshake",
        },
        "contract_doc": "docs/BUNDLE_CONTRACT.md",
    }
