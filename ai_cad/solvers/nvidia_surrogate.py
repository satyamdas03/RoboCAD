"""Minimal NVIDIA NIM surrogate for deep multi-physics estimates.

This module predicts drag, stress, and thermal behavior for common shapes by
first trying a lightweight NVIDIA NIM chat call, then falling back to simple
shape-based heuristics when no API key is configured or the call fails.
"""
from __future__ import annotations

import json
import math
import os
import re
from typing import Any

import trimesh

from ai_cad.materials import Material, get_material
from ai_cad.nvidia_client import NvidiaClient, NvidiaError


class NvidiaSurrogate:
    """Shape-aware surrogate that uses NVIDIA NIM when available."""

    def __init__(self, client: NvidiaClient | None = None) -> None:
        self.client = client or NvidiaClient()
        self.has_key = self.client.available()

    def predict(
        self,
        mesh: trimesh.Trimesh,
        quantity: str,
        params: dict[str, Any],
        material: Material | None = None,
    ) -> dict[str, Any]:
        """Return a prediction dict for one of drag/stress/thermal.

        Args:
            mesh: trimesh surface mesh of the design.
            quantity: one of "drag", "stress", "thermal".
            params: case-specific overrides (velocity_m_s, load_magnitude_n, etc.).
            material: material properties; defaults to PLA.

        Returns:
            Dict with solver name, metrics, and any warnings.
        """
        material = material or get_material("PLA")
        if self.has_key:
            try:
                return self._call_nim(mesh, quantity, params, material)
            except NvidiaError as exc:
                # Fall through to deterministic lookup on any NIM failure.
                return self._fallback(
                    mesh, quantity, params, material, warning=f"NIM call failed: {exc}"
                )
        return self._fallback(mesh, quantity, params, material)

    def _call_nim(
        self,
        mesh: trimesh.Trimesh,
        quantity: str,
        params: dict[str, Any],
        material: Material,
    ) -> dict[str, Any]:
        prompt = self._build_prompt(mesh, quantity, params, material)
        model = os.environ.get(
            "ROBOCAD_SURROGATE_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b"
        )
        response = self.client.chat(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            temperature=0.2,
            max_tokens=512,
        )
        parsed = self._parse_response(response, quantity)
        parsed["solver"] = "nvidia_nim_surrogate"
        return parsed

    def _build_prompt(
        self,
        mesh: trimesh.Trimesh,
        quantity: str,
        params: dict[str, Any],
        material: Material,
    ) -> str:
        bounds = mesh.bounds
        extents = bounds[1] - bounds[0]
        volume_mm3 = float(mesh.volume) if mesh.volume else 0.0
        area_mm2 = float(mesh.area) if mesh.area else 0.0
        base = (
            "You are a fast engineering surrogate. Return ONLY a compact JSON object "
            "with numeric estimates and a short list of redesign suggestions. "
            "Do not include markdown fences or explanation."
        )
        shape = (
            f"Mesh extents (mm): {extents.tolist()}, volume (mm^3): {volume_mm3:.2f}, "
            f"surface area (mm^2): {area_mm2:.2f}. Material: {material.name}."
        )
        if quantity == "drag":
            detail = (
                f"Air velocity {params.get('velocity_m_s', 10.0)} m/s. "
                f"Estimate drag_coefficient and drag_force_n."
            )
        elif quantity == "stress":
            detail = (
                f"Applied load {params.get('load_magnitude_n', 100.0)} N. "
                f"Estimate max_stress_mpa and safety_factor."
            )
        elif quantity == "thermal":
            detail = (
                f"Heat flux {params.get('heat_flux_w', 10.0)} W. "
                f"Estimate thermal_resistance_c_per_w and max_temperature_c."
            )
        else:
            detail = f"Estimate quantity '{quantity}' with reasonable engineering values."
        schema = {
            "drag": '{"drag_coefficient": float, "drag_force_n": float, "warnings": [str]}',
            "stress": '{"max_stress_mpa": float, "safety_factor": float, "warnings": [str]}',
            "thermal": '{"thermal_resistance_c_per_w": float, "max_temperature_c": float, "warnings": [str]}',
        }.get(quantity, '{"value": float, "warnings": [str]}')
        return f"{base}\n{shape}\n{detail}\nSchema: {schema}"

    def _parse_response(self, response: str, quantity: str) -> dict[str, Any]:
        """Extract JSON from an LLM response."""
        text = response or ""
        # Try to locate a JSON object.
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            text = match.group(0)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = {}
        if quantity == "drag":
            return {
                "drag_coefficient": float(data.get("drag_coefficient", 1.0)),
                "drag_force_n": float(data.get("drag_force_n", 0.0)),
                "warnings": data.get("warnings", []) if isinstance(data.get("warnings"), list) else [],
            }
        if quantity == "stress":
            return {
                "max_stress_mpa": float(data.get("max_stress_mpa", 0.0)),
                "safety_factor": float(data.get("safety_factor", 1.0)),
                "warnings": data.get("warnings", []) if isinstance(data.get("warnings"), list) else [],
            }
        if quantity == "thermal":
            return {
                "thermal_resistance_c_per_w": float(
                    data.get("thermal_resistance_c_per_w", 0.0)
                ),
                "max_temperature_c": float(data.get("max_temperature_c", 25.0)),
                "warnings": data.get("warnings", []) if isinstance(data.get("warnings"), list) else [],
            }
        return {"value": float(data.get("value", 0.0)), "warnings": []}

    def _fallback(
        self,
        mesh: trimesh.Trimesh,
        quantity: str,
        params: dict[str, Any],
        material: Material,
        warning: str | None = None,
    ) -> dict[str, Any]:
        """Deterministic shape-based estimates used when NVIDIA is unavailable."""
        result: dict[str, Any] = {"solver": "shape_lookup_surrogate"}
        warnings: list[str] = []
        if warning:
            warnings.append(warning)

        extents = mesh.extents
        volume_mm3 = float(mesh.volume) if mesh.volume else 0.0
        area_mm2 = float(mesh.area) if mesh.area else 0.0

        if quantity == "drag":
            velocity = float(params.get("velocity_m_s", 10.0))
            rho = 1.225  # kg/m^3 air density
            # Approximate frontal area from smallest bounding-box face.
            frontal_m2 = float(min(extents[0] * extents[1], extents[0] * extents[2], extents[1] * extents[2])) * 1e-6
            cd = 1.05  # blunt body default
            drag_force = 0.5 * rho * velocity**2 * frontal_m2 * cd
            result["drag_coefficient"] = round(cd, 4)
            result["drag_force_n"] = round(drag_force, 6)
            result["frontal_area_m2"] = round(frontal_m2, 8)

        elif quantity == "stress":
            load = float(params.get("load_magnitude_n", 100.0))
            fixed_face = params.get("fixed_face", "-x")
            axis_map = {"+x": 0, "-x": 0, "+y": 1, "-y": 1, "+z": 2, "-z": 2}
            axis = axis_map.get(fixed_face, 0)
            length = float(extents[axis])
            area_axes = [i for i in range(3) if i != axis]
            b, h = float(extents[area_axes[0]]), float(extents[area_axes[1]])
            I = b * h**3 / 12.0 if b * h > 0 else 1e-6
            max_stress = (load * length * (h / 2.0)) / I if I > 0 else 0.0
            max_displacement = (load * length**3) / (3.0 * material.youngs_modulus_mpa * I) if I > 0 else 0.0
            safety_factor = material.yield_strength_mpa / max_stress if max_stress > 0 else None
            result["max_stress_mpa"] = round(max_stress, 4)
            result["max_displacement_mm"] = round(max_displacement, 6)
            result["safety_factor"] = round(safety_factor, 2) if safety_factor is not None else 0.0

        elif quantity == "thermal":
            heat_flux = float(params.get("heat_flux_w", 10.0))
            ambient = float(params.get("ambient_temp_c", 25.0))
            h_conv = float(params.get("convection_coefficient_w_per_m2_k", 50.0))
            area_m2 = area_mm2 * 1e-6
            if area_m2 > 0:
                r_th = 1.0 / (h_conv * area_m2)
                max_temp = ambient + heat_flux * r_th
            else:
                r_th = float("inf")
                max_temp = ambient
            result["thermal_resistance_c_per_w"] = round(r_th, 4)
            result["max_temperature_c"] = round(max_temp, 2)
            result["surface_area_mm2"] = round(area_mm2 * 1e6, 4)
            result["volume_mm3"] = round(volume_mm3, 4)

        else:
            result["value"] = 0.0
            warnings.append(f"Unknown quantity '{quantity}'; returning placeholder.")

        result["warnings"] = warnings
        return result
