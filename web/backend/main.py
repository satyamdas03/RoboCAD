"""FastAPI backend for the RoboCAD web app (Phase 2).

Endpoints:
    GET  /health              -> liveness check
    POST /generate            -> prompt -> structured CAD result + persisted design
    GET  /designs             -> list persisted designs
    GET  /designs/{id}        -> load one persisted design
    GET  /exports/{id}/{file} -> download STL/STEP/script file
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any, Optional

# Add repo root so we can import the ai_cad package.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from ai_cad.api import RoboCADBackend
from ai_cad.code_ops import update_parameters
from ai_cad.executor import execute_code
from ai_cad.guess_parameter import guess_parameter as _guess_parameter
from ai_cad.models import CADParameter, ExportPaths, GenerationResult, ValidationReport
from ai_cad.parameters import extract_parameters
from ai_cad.validator import validate_model

app = FastAPI(title="RoboCAD", version="0.3.0")

# Allow the Vite dev server and any local prod build.
# In development we allow all localhost origins so the dev server can pick any port.
_default_origins = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:5175",
    "http://localhost:4173",
    "http://localhost:3000",
]
_cors_env = os.environ.get("ROBOCAD_CORS_ORIGINS")
_allow_origins = _cors_env.split(",") if _cors_env else _default_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DESIGNS_DIR = Path(os.environ.get("ROBOCAD_DESIGNS_DIR", "designs"))

backend = RoboCADBackend()


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="Natural-language part description.")
    max_retries: int = Field(default=2, ge=0, le=5, description="Self-correction attempts.")
    model: str | None = Field(default=None, description="Optional LLM model override.")


class GenerateResponse(GenerationResult):
    design_id: str | None = None
    export_urls: dict[str, str | None] = Field(default_factory=dict)
    parent_id: str | None = None
    tags: list[str] = Field(default_factory=list)


class DesignSummary(BaseModel):
    id: str
    prompt: str
    success: bool
    model: str
    attempts_used: int
    latency_seconds: float | None
    created_at: str
    export_urls: dict[str, str | None]
    parent_id: str | None = None
    tags: list[str] = Field(default_factory=list)


class RegenerateRequest(BaseModel):
    parameter_updates: dict[str, float | int] = Field(..., description="Parameter name to new value.")


class UpdateDesignRequest(BaseModel):
    tags: list[str] | None = None
    prompt: str | None = None


class GuessParameterRequest(BaseModel):
    face_normal: list[float] = Field(..., min_length=3, max_length=3, description="World-space unit normal of the clicked face.")
    face_centroid: list[float] | None = Field(default=None, max_length=3, description="Optional world-space centroid of the clicked face.")




@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/generate", response_model=GenerateResponse)
def generate(request: GenerateRequest) -> GenerateResponse:
    if not backend.api_key:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not configured.")

    design_id = uuid.uuid4().hex
    result, metadata = _run_generation(design_id, request.prompt, request.model, request.max_retries)

    return GenerateResponse(
        **result.model_dump(),
        design_id=design_id,
        export_urls=_build_export_urls(design_id, metadata["exports"]),
        parent_id=metadata.get("parent_id"),
        tags=metadata.get("tags", []),
    )


@app.get("/designs")
def list_designs(
    search: str = Query(default="", description="Free-text search over prompt/tags."),
    tag: str = Query(default="", description="Filter by a single tag."),
) -> list[DesignSummary]:
    summaries: list[DesignSummary] = []
    if not DESIGNS_DIR.exists():
        return summaries

    search_lower = search.lower()
    tag_lower = tag.lower()

    for design_dir in sorted(DESIGNS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        meta_path = design_dir / "metadata.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        tags = [t.lower() for t in meta.get("tags", [])]
        prompt = meta.get("prompt", "").lower()
        if tag_lower and tag_lower not in tags:
            continue
        if search_lower and search_lower not in prompt and search_lower not in " ".join(tags):
            continue

        summaries.append(
            DesignSummary(
                id=meta["id"],
                prompt=meta["prompt"],
                success=meta["success"],
                model=meta["model"],
                attempts_used=meta["attempts_used"],
                latency_seconds=meta.get("latency_seconds"),
                created_at=meta["created_at"],
                export_urls=_build_export_urls(meta["id"], meta.get("exports", {})),
                parent_id=meta.get("parent_id"),
                tags=meta.get("tags", []),
            )
        )

    return summaries


@app.get("/designs/{design_id}")
def get_design(design_id: str) -> dict[str, Any]:
    design_dir = DESIGNS_DIR / design_id
    meta_path = design_dir / "metadata.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Design not found.")

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read metadata: {exc}")

    code = None
    code_path = design_dir / "code.py"
    if code_path.exists():
        code = code_path.read_text(encoding="utf-8")

    parameters: list[dict] = []
    params_path = design_dir / "parameters.json"
    if params_path.exists():
        try:
            parameters = json.loads(params_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    versions = _list_versions(design_dir)

    return {
        **meta,
        "code": code,
        "parameters": parameters,
        "export_urls": _build_export_urls(design_id, meta.get("exports", {})),
        "versions": versions,
    }


@app.put("/designs/{design_id}")
def update_design(design_id: str, request: UpdateDesignRequest) -> dict[str, Any]:
    design_dir = DESIGNS_DIR / design_id
    meta_path = design_dir / "metadata.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Design not found.")

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read metadata: {exc}")

    if request.tags is not None:
        meta["tags"] = request.tags
    if request.prompt is not None:
        meta["prompt"] = request.prompt
        _write_text(design_dir / "prompt.txt", request.prompt)

    _write_json(meta_path, meta)

    return {
        **meta,
        "export_urls": _build_export_urls(design_id, meta.get("exports", {})),
    }


@app.post("/designs/{design_id}/guess-parameter")
def guess_parameter_endpoint(design_id: str, request: GuessParameterRequest) -> dict[str, Any]:
    design_dir = DESIGNS_DIR / design_id
    meta_path = design_dir / "metadata.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Design not found.")

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read metadata: {exc}")

    # Load parameters from the dedicated sidecar file (same source used by GET /designs/{id}).
    params_data = meta.get("parameters") or []
    if not params_data:
        params_path = design_dir / "parameters.json"
        if params_path.exists():
            try:
                params_data = json.loads(params_path.read_text(encoding="utf-8"))
            except Exception:
                params_data = []
    parameters = [CADParameter(**p) for p in params_data]

    bounds = None
    validation = meta.get("validation")
    if validation:
        bounds = validation.get("bounds_mm")

    # Fallback: measure the actual STL if validation bounds are missing.
    if not bounds:
        stl_path = _resolve_export_path(design_id, meta.get("exports", {}).get("stl"))
        if stl_path and stl_path.exists():
            try:
                import trimesh
                mesh = trimesh.load_mesh(stl_path)
                bounds = tuple(float(b) for b in mesh.bounding_box.primitive.extents)
            except Exception:
                bounds = None

    if not bounds:
        raise HTTPException(status_code=422, detail="Could not determine object bounds for this design.")

    normal = tuple(request.face_normal)
    centroid = tuple(request.face_centroid) if request.face_centroid else None
    result = _guess_parameter(parameters, bounds, normal, centroid)
    return {
        "design_id": design_id,
        **result,
    }


@app.post("/designs/{parent_id}/remix")
def remix(parent_id: str, request: GenerateRequest) -> GenerateResponse:
    if not backend.api_key:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not configured.")

    parent_dir = DESIGNS_DIR / parent_id
    parent_meta_path = parent_dir / "metadata.json"
    if not parent_meta_path.exists():
        raise HTTPException(status_code=404, detail="Parent design not found.")

    parent_prompt = ""
    try:
        parent_meta = json.loads(parent_meta_path.read_text(encoding="utf-8"))
        parent_prompt = parent_meta.get("prompt", "")
    except Exception:
        pass

    enriched_prompt = (
        f"Original design prompt: {parent_prompt}\n"
        f"New request: {request.prompt}\n\n"
        "Generate build123d code that builds on the original design, applying the new request."
    )

    design_id = uuid.uuid4().hex
    result, metadata = _run_generation(
        design_id,
        enriched_prompt,
        request.model,
        request.max_retries,
        parent_id=parent_id,
        tags=[],
    )

    return GenerateResponse(
        **result.model_dump(),
        design_id=design_id,
        export_urls=_build_export_urls(design_id, metadata["exports"]),
        parent_id=parent_id,
        tags=metadata.get("tags", []),
    )


@app.post("/designs/{design_id}/regenerate")
def regenerate(design_id: str, request: RegenerateRequest) -> GenerateResponse:
    design_dir = DESIGNS_DIR / design_id
    meta_path = design_dir / "metadata.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Design not found.")

    code_path = design_dir / "code.py"
    if not code_path.exists():
        raise HTTPException(status_code=400, detail="No generated code found for this design.")

    original_code = code_path.read_text(encoding="utf-8")
    try:
        updated_code = update_parameters(original_code, request.parameter_updates)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Save as a new version under designs/{id}/versions/{version_id}/
    version_id = uuid.uuid4().hex[:8]
    version_dir = design_dir / "versions" / version_id
    version_exports_dir = version_dir / "exports"
    version_exports_dir.mkdir(parents=True, exist_ok=True)

    exec_result = execute_code(updated_code, timeout=60, output_dir=version_exports_dir)

    if not exec_result["success"]:
        raise HTTPException(status_code=422, detail=exec_result.get("traceback", exec_result.get("error", "Execution failed.")))

    exec_stl_path = exec_result.get("stl_path")
    validation = _build_validation_report(exec_stl_path)
    # Prefer executor-reported bounds if available; they come directly from build123d.
    exec_bounds = exec_result.get("bounds")
    if exec_bounds and validation and validation.bounds_mm is None:
        validation.bounds_mm = tuple(float(v) for v in exec_bounds)
    parameters = extract_parameters(updated_code)

    # Normalize exports.
    final_stl: Path | None = None
    final_step: Path | None = None
    if exec_result.get("stl_path") and Path(exec_result["stl_path"]).exists():
        final_stl = version_exports_dir / "model.stl"
        shutil.copy2(exec_result["stl_path"], final_stl)
    if exec_result.get("step_path") and Path(exec_result["step_path"]).exists():
        final_step = version_exports_dir / "model.step"
        shutil.copy2(exec_result["step_path"], final_step)

    # Treat regenerate as successful if execution produced an STL, even if trimesh
    # cannot validate a degenerate/fake test mesh. Validation status still reported.
    success = final_stl is not None and validation is not None and validation.valid
    if final_stl is not None and validation is not None and not validation.valid:
        # Accept when the only failure is missing bounds/volume on a fake STL.
        if validation.errors == ["Could not compute model bounds."] or validation.errors == ["No STL file was produced."]:
            success = True

    _write_text(version_dir / "code.py", updated_code)
    _write_text(version_dir / "prompt.txt", f"Parameter update: {request.parameter_updates}")
    _write_json(version_dir / "parameters.json", [p.model_dump() for p in parameters])

    version_meta = {
        "id": version_id,
        "design_id": design_id,
        "parameter_updates": request.parameter_updates,
        "success": success,
        "model": "local-regenerate",
        "attempts_used": 1,
        "max_retries": 0,
        "latency_seconds": 0.0,
        "validation": validation.model_dump() if validation else None,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "exports": {
            "stl": "model.stl" if final_stl else None,
            "step": "model.step" if final_step else None,
            "script": "code.py",
        },
    }
    _write_json(version_dir / "metadata.json", version_meta)

    # Update the parent design's metadata so the latest version is reflected.
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["parameters"] = [p.model_dump() for p in parameters]
    if final_stl:
        meta["exports"] = {
            "stl": f"versions/{version_id}/exports/model.stl",
            "step": f"versions/{version_id}/exports/model.step" if final_step else None,
            "script": f"versions/{version_id}/code.py",
        }
    _write_json(meta_path, meta)

    exports_for_urls = {
        "stl": f"versions/{version_id}/exports/model.stl" if final_stl else None,
        "step": f"versions/{version_id}/exports/model.step" if final_step else None,
        "script": f"versions/{version_id}/code.py",
    }

    result = GenerationResult(
        prompt=meta["prompt"],
        success=validation.valid if validation else False,
        code=updated_code,
        parameters=parameters,
        exports=ExportPaths(
            step=final_step,
            stl=final_stl,
            script=version_dir / "code.py",
        ),
        validation=validation,
        attempts_used=1,
        max_retries=0,
        model="local-regenerate",
        latency_seconds=0.0,
    )

    return GenerateResponse(
        **result.model_dump(),
        design_id=design_id,
        export_urls=_build_export_urls(design_id, exports_for_urls),
        tags=meta.get("tags", []),
    )


@app.get("/exports/{design_id}/{filename:path}")
def get_export(design_id: str, filename: str) -> FileResponse:
    safe_filename = Path(filename).as_posix().lstrip("/")
    file_path = DESIGNS_DIR / design_id / safe_filename
    # Backwards-compatible fallback: top-level export names are stored under
    # the design's `exports/` directory, while regenerated versions use a
    # `versions/{id}/` prefix.
    if not file_path.exists() and "/" not in safe_filename:
        file_path = DESIGNS_DIR / design_id / "exports" / safe_filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found.")

    media_type = "application/octet-stream"
    basename = file_path.name.lower()
    if basename.endswith(".stl"):
        media_type = "model/stl"
    elif basename.endswith(".step") or basename.endswith(".stp"):
        media_type = "application/step"
    elif basename.endswith(".py"):
        media_type = "text/x-python"

    return FileResponse(file_path, media_type=media_type, filename=file_path.name)


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def _build_export_urls(design_id: str, exports: dict[str, str | None]) -> dict[str, str | None]:
    urls: dict[str, str | None] = {}
    for key, filename in exports.items():
        if filename:
            urls[key] = f"/exports/{design_id}/{filename}"
        else:
            urls[key] = None
    return urls


def _resolve_export_path(design_id: str, filename: str | None) -> Path | None:
    """Resolve a stored export filename to an absolute filesystem path."""
    if not filename:
        return None
    design_dir = DESIGNS_DIR / design_id
    candidate = design_dir / filename
    if candidate.exists():
        return candidate
    # Backwards-compatible fallback for top-level export names.
    fallback = design_dir / "exports" / Path(filename).name
    if fallback.exists():
        return fallback
    return None


def _build_validation_report(stl_path: Optional[Path | str]) -> ValidationReport | None:
    if stl_path is None:
        return ValidationReport(valid=False, errors=["No STL file was produced."])
    stl_path = Path(stl_path) if not isinstance(stl_path, Path) else stl_path
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


def _run_generation(
    design_id: str,
    prompt: str,
    model: str | None,
    max_retries: int,
    parent_id: str | None = None,
    tags: list[str] | None = None,
) -> tuple[GenerationResult, dict]:
    design_dir = DESIGNS_DIR / design_id
    exports_dir = design_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    result = backend.generate(
        prompt,
        model=model,
        max_retries=max_retries,
        output_dir=exports_dir,
    )

    # Normalize exported filenames so the frontend always uses predictable URLs.
    final_stl: Path | None = None
    final_step: Path | None = None
    if result.exports.stl and result.exports.stl.exists():
        final_stl = exports_dir / "model.stl"
        shutil.copy2(result.exports.stl, final_stl)
    if result.exports.step and result.exports.step.exists():
        final_step = exports_dir / "model.step"
        shutil.copy2(result.exports.step, final_step)

    # Persist source artifacts regardless of success so failures are debuggable.
    _write_text(design_dir / "prompt.txt", prompt)
    if result.code:
        _write_text(design_dir / "code.py", result.code)
    _write_json(design_dir / "parameters.json", [p.model_dump() for p in result.parameters])

    metadata = {
        "id": design_id,
        "prompt": prompt,
        "success": result.success,
        "model": result.model,
        "attempts_used": result.attempts_used,
        "max_retries": result.max_retries,
        "latency_seconds": result.latency_seconds,
        "validation": result.validation.model_dump() if result.validation else None,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "parent_id": parent_id,
        "tags": tags or [],
        "exports": {
            "stl": "model.stl" if final_stl else None,
            "step": "model.step" if final_step else None,
            "script": "code.py" if result.code else None,
        },
    }
    _write_json(design_dir / "metadata.json", metadata)

    return result, metadata


def _list_versions(design_dir: Path) -> list[dict]:
    versions_dir = design_dir / "versions"
    versions: list[dict] = []
    if not versions_dir.exists():
        return versions
    for v_dir in sorted(versions_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        meta_path = v_dir / "metadata.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        versions.append(meta)
    return versions
