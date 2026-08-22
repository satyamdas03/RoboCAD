"""Unified RoboCAD backend API: prompt → parametric CAD result."""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

from ai_cad.executor import execute_code
from ai_cad.generator import DEFAULT_MODEL, generate_model, self_correct
from ai_cad.models import (
    CADParameter,
    ExportPaths,
    GenerationResult,
    ValidationReport,
)
from ai_cad.parameters import extract_parameters
from ai_cad.validator import validate_model


class RoboCADBackend:
    """High-level backend that orchestrates code generation, execution,
    validation, and parameter extraction into a single structured result.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        default_output_dir: Optional[Path] = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model or os.environ.get("ROBOCAD_MODEL") or DEFAULT_MODEL
        self.default_output_dir = default_output_dir or Path("output") / "generated"

    def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_retries: int = 2,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        output_dir: Optional[Path] = None,
        timeout: int = 60,
    ) -> GenerationResult:
        """Generate a validated parametric CAD model from a natural-language prompt.

        Retries on both execution/runtime failures and geometry validation failures
        by feeding the error/traceback back to the LLM, up to ``max_retries`` times.
        """
        start = time.time()
        model = model or self.model or DEFAULT_MODEL
        output_dir = output_dir or self.default_output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        if not self.api_key:
            return GenerationResult(
                prompt=prompt,
                success=False,
                model=model,
                max_retries=max_retries,
                error="ANTHROPIC_API_KEY not set.",
            )

        attempts_used = 0
        code: Optional[str] = None
        error: Optional[str] = None
        traceback_str: Optional[str] = None
        exec_result: dict = {}
        validation: ValidationReport | None = None
        parameters: list[CADParameter] = []

        gen = generate_model(
            prompt,
            model=model,
            api_key=self.api_key,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        attempts_used += 1

        while True:
            if not gen["success"]:
                error = gen.get("error") or "Code generation failed."
                break

            code = gen.get("code")
            if code is None:
                error = "Generation succeeded but no code was extracted."
                break

            exec_result = execute_code(code, timeout=timeout, output_dir=output_dir)

            if not exec_result["success"]:
                traceback_str = exec_result.get("traceback") or exec_result.get("error", "")
                if attempts_used - 1 < max_retries:
                    gen = self_correct(
                        prompt,
                        code,
                        traceback_str,
                        model=model,
                        max_retries=1,
                        api_key=self.api_key,
                    )
                    attempts_used += 1
                    continue
                error = exec_result.get("error", "Generated code failed to execute.")
                break

            validation = self._build_validation_report(exec_result.get("stl_path"))
            if validation is not None and validation.valid:
                break

            # Retry on validation failure if we have budget left.
            validation_error = ""
            if validation is not None and validation.errors:
                validation_error = "Validation failed:\n" + "\n".join(validation.errors)
                if validation.warnings:
                    validation_error += "\nWarnings:\n" + "\n".join(validation.warnings)
            traceback_str = validation_error or "Geometry validation failed."
            if attempts_used - 1 < max_retries:
                gen = self_correct(
                    prompt,
                    code,
                    traceback_str,
                    model=model,
                    max_retries=1,
                    api_key=self.api_key,
                )
                attempts_used += 1
                continue

            if validation is not None and validation.errors:
                error = validation.errors[0]
            else:
                error = "Geometry validation failed after all retries."
            break

        # Extract parameters from the final code if available.
        if code is not None and exec_result.get("success"):
            parameters = extract_parameters(code)

        success = bool(
            exec_result.get("success")
            and (validation is not None and validation.valid)
        )

        exports = ExportPaths(
            step=exec_result.get("step_path"),
            stl=exec_result.get("stl_path"),
            script=exec_result.get("script_path"),
        )

        return GenerationResult(
            prompt=prompt,
            success=success,
            code=code,
            parameters=parameters,
            exports=exports,
            validation=validation,
            attempts_used=attempts_used,
            max_retries=max_retries,
            model=model,
            error=error,
            traceback=traceback_str,
            latency_seconds=round(time.time() - start, 3),
        )

    @staticmethod
    def _build_validation_report(stl_path: Optional[Path]) -> ValidationReport | None:
        if stl_path is None:
            return ValidationReport(
                valid=False,
                errors=["No STL file was produced."],
            )
        raw = validate_model(stl_path)
        return ValidationReport(
            valid=raw.get("valid", False),
            manifold=raw.get("manifold", False),
            watertight=raw.get("watertight", False),
            bounds_mm=raw.get("bounds_mm"),
            volume_mm3=raw.get("volume_mm3"),
            surface_area_mm2=raw.get("surface_area_mm2"),
            warnings=raw.get("warnings", []),
            errors=raw.get("errors", []),
        )


def generate(
    prompt: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    max_retries: int = 2,
    **kwargs,
) -> GenerationResult:
    """Convenience function that creates a backend and generates a result."""
    backend = RoboCADBackend(api_key=api_key, model=model)
    return backend.generate(prompt, max_retries=max_retries, **kwargs)
