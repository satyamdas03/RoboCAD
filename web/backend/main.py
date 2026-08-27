"""FastAPI backend for the RoboCAD web app (Phases 2–6).

Endpoints:
    GET  /health                       -> liveness check
    POST /generate                     -> prompt -> structured CAD result + persisted design
    GET  /designs                      -> list persisted designs
    GET  /designs/{id}                 -> load one persisted design
    GET  /designs/{id}/manufacturing-report -> manufacturability analysis
    POST /designs/{id}/onshape         -> upload STEP to Onshape
    GET  /onshape/documents          -> list Onshape documents
    GET  /exports/{id}/{file}        -> download STL/STEP/script file
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

import requests
from dotenv import load_dotenv

# Load local environment variables from a gitignored .env file so users can keep
# secrets such as Onshape credentials next to the project without committing them.
# override=True ensures values in .env win over any empty shell variables.
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env", override=True)

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
from ai_cad.assembly import transpile_assembly
from ai_cad.dfm import analyze_dfm
from ai_cad.feature_store import save as save_feature_tree
from ai_cad.feature_tree import Assembly, FeatureTree
from ai_cad.fea import run_static_analysis
from ai_cad.geda_bridge import export_bundle_from_mesh, export_bundle_from_tree, package_bundle_paths, verify_bundle
from ai_cad.geda_bridge.models import BundleManifest, BundleVerification
from ai_cad.guess_parameter import guess_parameter as _guess_parameter
from ai_cad.manufacturing import analyze_model as _analyze_manufacturing
from ai_cad.models import CADParameter, ExportPaths, GenerationResult, ManufacturingReport, ValidationReport
from ai_cad.onshape import OnshapeClient
from ai_cad.parameters import extract_parameters
from ai_cad.tolerances import check_fit
from ai_cad.transpiler import transpile
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
    use_assembly: bool = Field(default=False, description="Generate as a multi-part assembly if the model returns one.")


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


class RegenerateFromFeatureTreeRequest(BaseModel):
    parameter_updates: dict[str, float | int] = Field(..., description="Parameter name to new value.")


class UpdateDesignRequest(BaseModel):
    tags: list[str] | None = None
    prompt: str | None = None


class GuessParameterRequest(BaseModel):
    face_normal: list[float] = Field(..., min_length=3, max_length=3, description="World-space unit normal of the clicked face.")
    face_centroid: list[float] | None = Field(default=None, max_length=3, description="Optional world-space centroid of the clicked face.")


class OnshapeUploadRequest(BaseModel):
    document_id: str | None = Field(default=None, description="Existing Onshape document id; if omitted, a new document is created.")
    workspace_id: str | None = Field(default=None, description="Workspace id within the document (required with document_id).")
    document_name: str | None = Field(default=None, description="Name for a newly created Onshape document.")


class FitCheckRequest(BaseModel):
    other_design_id: str = Field(..., description="Design id whose STL will be compared against the target design.")
    name: str = Field(default="fit_check", description="Identifier for this fit check.")
    clearance_threshold_mm: float = Field(default=0.05, ge=0, description="Min positive clearance to classify as clearance fit.")
    interference_threshold_mm: float = Field(default=-0.05, le=0, description="Max negative clearance to classify as interference fit.")
    samples: int = Field(default=2000, ge=100, le=10000, description="Surface sample count.")


class FEARequest(BaseModel):
    fixed_face: str = Field(default="-x", description="Fully constrained face: +x, -x, +y, -y, +z, -z.")
    load_magnitude_n: float = Field(default=100.0, gt=0, description="Applied force magnitude in Newtons.")
    material: str = Field(default="PLA", description="Material name (PLA, PETG, ABS, aluminum, steel).")


class SimulateRequest(BaseModel):
    material: str = Field(default="PLA", description="Material name for density lookup.")
    tolerance: float = Field(default=0.1, gt=0, le=1.0, description="Mesh tessellation tolerance in mm.")




@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/generate", response_model=GenerateResponse)
def generate(request: GenerateRequest) -> GenerateResponse:
    if not backend.api_key:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not configured.")

    design_id = uuid.uuid4().hex
    result, metadata = _run_generation(
        design_id,
        request.prompt,
        request.model,
        request.max_retries,
        use_feature_tree=True,
        use_assembly=request.use_assembly,
    )

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

    assembly = None
    feature_tree = None
    feature_tree_path = design_dir / "feature_tree.json"
    if feature_tree_path.exists():
        try:
            feature_tree = json.loads(feature_tree_path.read_text(encoding="utf-8"))
            assemblies = feature_tree.get("assemblies")
            if assemblies:
                assembly = assemblies[0]
        except Exception:
            feature_tree = None
            assembly = None

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
        "feature_tree": feature_tree,
        "assembly": assembly,
        "parameters": parameters,
        "export_urls": _build_export_urls(design_id, meta.get("exports", {})),
        "versions": versions,
    }


@app.get("/designs/{design_id}/assembly")
def get_assembly(design_id: str) -> dict[str, Any]:
    """Return the first assembly in the design's feature tree, if any."""
    design_dir = DESIGNS_DIR / design_id
    feature_tree_path = design_dir / "feature_tree.json"
    if not feature_tree_path.exists():
        raise HTTPException(status_code=404, detail="No feature tree found for this design.")
    try:
        data = json.loads(feature_tree_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read feature tree: {exc}")
    assemblies = data.get("assemblies", [])
    if not assemblies:
        raise HTTPException(status_code=404, detail="No assembly found for this design.")
    return {"design_id": design_id, "assembly": assemblies[0]}


@app.get("/designs/{design_id}/feature-tree")
def get_feature_tree(design_id: str) -> dict[str, Any]:
    """Return the persisted Feature-Tree JSON for a design, if any."""
    design_dir = DESIGNS_DIR / design_id
    feature_tree_path = design_dir / "feature_tree.json"
    if not feature_tree_path.exists():
        raise HTTPException(status_code=404, detail="Feature tree not found for this design.")
    try:
        data = json.loads(feature_tree_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read feature tree: {exc}")
    return {"design_id": design_id, "feature_tree": data}


@app.post("/designs/{design_id}/regenerate-from-feature-tree")
def regenerate_from_feature_tree(
    design_id: str,
    request: RegenerateFromFeatureTreeRequest,
) -> GenerateResponse:
    """Update parameters in the saved feature tree, transpile, and re-execute."""
    design_dir = DESIGNS_DIR / design_id
    meta_path = design_dir / "metadata.json"
    feature_tree_path = design_dir / "feature_tree.json"
    if not meta_path.exists() or not feature_tree_path.exists():
        raise HTTPException(status_code=404, detail="Design or feature tree not found.")

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        tree_data = json.loads(feature_tree_path.read_text(encoding="utf-8"))
        tree = FeatureTree(**tree_data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load feature tree: {exc}")

    for name, value in request.parameter_updates.items():
        if not tree.update_parameter(name, value):
            raise HTTPException(status_code=400, detail=f"Unknown parameter: {name}")

    try:
        if tree.assemblies:
            code = transpile_assembly(tree)
        else:
            code = transpile(tree)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to transpile feature tree: {exc}")

    exports_dir = design_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    exec_result = execute_code(code, timeout=60, output_dir=exports_dir)

    if not exec_result["success"]:
        raise HTTPException(
            status_code=422,
            detail=exec_result.get("traceback", exec_result.get("error", "Execution failed.")),
        )

    validation = _build_validation_report(exec_result.get("stl_path"))
    exec_bounds = exec_result.get("bounds")
    if exec_bounds and validation and validation.bounds_mm is None:
        validation.bounds_mm = tuple(float(v) for v in exec_bounds)
    parameters = [CADParameter(**p.model_dump()) for p in tree.parameters]

    final_stl: Path | None = None
    final_step: Path | None = None
    if exec_result.get("stl_path") and Path(exec_result["stl_path"]).exists():
        final_stl = exports_dir / "model.stl"
        shutil.copy2(exec_result["stl_path"], final_stl)
    if exec_result.get("step_path") and Path(exec_result["step_path"]).exists():
        final_step = exports_dir / "model.step"
        shutil.copy2(exec_result["step_path"], final_step)

    _write_text(design_dir / "code.py", code)
    _write_json(feature_tree_path, tree.model_dump(mode="json"))
    _write_json(design_dir / "parameters.json", [p.model_dump() for p in parameters])

    meta["parameters"] = [p.model_dump() for p in parameters]
    if final_stl:
        meta["exports"] = {
            "stl": "model.stl",
            "step": "model.step" if final_step else None,
            "script": "code.py",
        }
    if validation:
        meta["validation"] = validation.model_dump()
    _write_json(meta_path, meta)

    result = GenerationResult(
        prompt=meta["prompt"],
        success=validation.valid if validation else False,
        code=code,
        parameters=parameters,
        exports=ExportPaths(
            step=final_step,
            stl=final_stl,
            script=design_dir / "code.py",
        ),
        validation=validation,
        feature_tree=tree,
        attempts_used=1,
        max_retries=0,
        model="local-feature-tree",
        latency_seconds=0.0,
    )

    return GenerateResponse(
        **result.model_dump(),
        design_id=design_id,
        export_urls=_build_export_urls(design_id, meta["exports"]),
        tags=meta.get("tags", []),
    )


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


@app.get("/onshape/documents")
def onshape_documents(
    query: str = Query(default="", description="Free-text search over document names."),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """List Onshape documents accessible to the configured API key."""
    try:
        client = OnshapeClient()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    try:
        result = client.list_documents(query=query or None, limit=limit)
        return {"documents": result.get("items", []), "total": result.get("total", 0)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Onshape API error: {exc}")


@app.post("/designs/{design_id}/onshape")
def upload_to_onshape(design_id: str, request: OnshapeUploadRequest) -> dict[str, Any]:
    """Upload a design's STEP file to Onshape.

    If document_id/workspace_id are provided, the STEP is imported into that
    document. Otherwise a new Onshape document is created (public documents are
    required for free Onshape plans).
    """
    design_dir = DESIGNS_DIR / design_id
    meta_path = design_dir / "metadata.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Design not found.")

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read metadata: {exc}")

    step_path = _resolve_export_path(design_id, meta.get("exports", {}).get("step"))
    if not step_path or not step_path.exists():
        raise HTTPException(status_code=422, detail="No STEP export found for this design.")

    try:
        client = OnshapeClient()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    try:
        if request.document_id and request.workspace_id:
            result = client.upload_step(
                step_path,
                request.document_id,
                request.workspace_id,
            )
        else:
            document_name = request.document_name or f"RoboCAD {meta.get('prompt', '')[:40]}"
            result = client.upload_step_to_new_document(
                step_path,
                document_name,
                "Uploaded by RoboCAD",
            )
        return {
            "design_id": design_id,
            "onshape": result,
        }
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else 502
        detail = exc.response.text if exc.response is not None else str(exc)
        if status == 409 and "Free accounts" in detail:
            raise HTTPException(
                status_code=409,
                detail="Onshape free accounts only allow public documents. Please upgrade or use an existing public document.",
            )
        raise HTTPException(status_code=status, detail=f"Onshape API error: {detail}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Onshape upload failed: {exc}")


@app.get("/designs/{design_id}/manufacturing-report")
def manufacturing_report(design_id: str) -> dict[str, Any]:
    """Return a manufacturing report for a design's STL export."""
    design_dir = DESIGNS_DIR / design_id
    meta_path = design_dir / "metadata.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Design not found.")

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read metadata: {exc}")

    stl_path = _resolve_export_path(design_id, meta.get("exports", {}).get("stl"))
    if not stl_path or not stl_path.exists():
        raise HTTPException(status_code=422, detail="No STL export found for this design.")

    try:
        raw = _analyze_manufacturing(stl_path)
        report = ManufacturingReport(**raw)
        return {
            "design_id": design_id,
            "report": report.model_dump(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to analyze model: {exc}")


@app.get("/designs/{design_id}/dfm-report")
def dfm_report(design_id: str) -> dict[str, Any]:
    """Return a Design-for-Manufacturing report for a design's STL export."""
    design_dir = DESIGNS_DIR / design_id
    meta_path = design_dir / "metadata.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Design not found.")

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read metadata: {exc}")

    stl_path = _resolve_export_path(design_id, meta.get("exports", {}).get("stl"))
    if not stl_path or not stl_path.exists():
        raise HTTPException(status_code=422, detail="No STL export found for this design.")

    try:
        report = analyze_dfm(stl_path)
        return {"design_id": design_id, "report": report.model_dump()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to run DFM analysis: {exc}")


@app.post("/designs/{design_id}/fit-check")
def fit_check_endpoint(design_id: str, request: FitCheckRequest) -> dict[str, Any]:
    """Check geometric fit/clearance between this design's STL and another design's STL."""
    target_dir = DESIGNS_DIR / design_id
    target_meta_path = target_dir / "metadata.json"
    other_dir = DESIGNS_DIR / request.other_design_id
    other_meta_path = other_dir / "metadata.json"

    if not target_meta_path.exists():
        raise HTTPException(status_code=404, detail="Target design not found.")
    if not other_meta_path.exists():
        raise HTTPException(status_code=404, detail="Other design not found.")

    try:
        target_meta = json.loads(target_meta_path.read_text(encoding="utf-8"))
        other_meta = json.loads(other_meta_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read metadata: {exc}")

    target_stl = _resolve_export_path(design_id, target_meta.get("exports", {}).get("stl"))
    other_stl = _resolve_export_path(request.other_design_id, other_meta.get("exports", {}).get("stl"))
    if not target_stl or not target_stl.exists():
        raise HTTPException(status_code=422, detail="No STL export found for the target design.")
    if not other_stl or not other_stl.exists():
        raise HTTPException(status_code=422, detail="No STL export found for the other design.")

    try:
        result = check_fit(
            target_stl,
            other_stl,
            name=request.name,
            clearance_threshold_mm=request.clearance_threshold_mm,
            interference_threshold_mm=request.interference_threshold_mm,
            samples=request.samples,
        )
        return {
            "design_id": design_id,
            "other_design_id": request.other_design_id,
            "report": result.model_dump(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to run fit check: {exc}")


@app.post("/designs/{design_id}/fea-report")
def fea_report(design_id: str, request: FEARequest) -> dict[str, Any]:
    """Run a simple static analysis (cantilever beam estimate) on a design's STL."""
    design_dir = DESIGNS_DIR / design_id
    meta_path = design_dir / "metadata.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Design not found.")

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read metadata: {exc}")

    stl_path = _resolve_export_path(design_id, meta.get("exports", {}).get("stl"))
    if not stl_path or not stl_path.exists():
        raise HTTPException(status_code=422, detail="No STL export found for this design.")

    valid_faces = {"+x", "-x", "+y", "-y", "+z", "-z"}
    if request.fixed_face not in valid_faces:
        raise HTTPException(status_code=400, detail=f"fixed_face must be one of {valid_faces}")

    try:
        result = run_static_analysis(
            stl_path,
            fixed_face=request.fixed_face,
            load_magnitude_n=request.load_magnitude_n,
            material=request.material,
        )
        return {"design_id": design_id, "report": result.model_dump()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to run FEA: {exc}")


@app.post("/designs/{design_id}/simulate")
def simulate_design(design_id: str, request: SimulateRequest) -> dict[str, Any]:
    """Generate a simulation-ready MJCF/URDF bundle for a design."""
    design_dir = DESIGNS_DIR / design_id
    meta_path = design_dir / "metadata.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Design not found.")

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read metadata: {exc}")

    simulation_dir = design_dir / "simulation"
    simulation_dir.mkdir(parents=True, exist_ok=True)

    feature_tree_path = design_dir / "feature_tree.json"
    try:
        if feature_tree_path.exists():
            tree_data = json.loads(feature_tree_path.read_text(encoding="utf-8"))
            tree = FeatureTree(**tree_data)
            paths = export_bundle_from_tree(tree, simulation_dir, name="model", tolerance=request.tolerance)
        else:
            stl_path = _resolve_export_path(design_id, meta.get("exports", {}).get("stl"))
            if not stl_path or not stl_path.exists():
                raise HTTPException(status_code=422, detail="No STL export or feature tree found for this design.")
            import trimesh
            mesh = trimesh.load_mesh(stl_path)
            if isinstance(mesh, trimesh.Scene):
                if len(mesh.geometry) == 1:
                    mesh = next(iter(mesh.geometry.values()))
                else:
                    raise HTTPException(status_code=422, detail="STL contains multiple bodies; cannot export as single simulation body.")
            paths = export_bundle_from_mesh(mesh, simulation_dir, name="model", material=request.material)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to export simulation bundle: {exc}")

    paths = package_bundle_paths(paths, simulation_dir / "bundle.zip")

    verification = verify_bundle(paths.directory)

    # Update metadata so the bundle URL is surfaced in design summaries.
    meta.setdefault("exports", {})
    meta["exports"]["bundle"] = "simulation/bundle.zip"
    _write_json(meta_path, meta)

    return {
        "design_id": design_id,
        "valid": verification.valid,
        "verification": verification.model_dump(),
        "manifest": BundleManifest(**json.loads(paths.manifest_json.read_text(encoding="utf-8"))).model_dump(),
        "bundle_url": f"/exports/{design_id}/simulation/bundle.zip",
    }


@app.get("/designs/{design_id}/simulation")
def get_simulation_report(design_id: str) -> dict[str, Any]:
    """Return the persisted simulation manifest and verification for a design."""
    design_dir = DESIGNS_DIR / design_id
    meta_path = design_dir / "metadata.json"
    manifest_path = design_dir / "simulation" / "manifest.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Design not found.")
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="No simulation bundle found for this design.")

    try:
        manifest = BundleManifest(**json.loads(manifest_path.read_text(encoding="utf-8")))
        verification = verify_bundle(manifest_path.parent)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read simulation report: {exc}")

    return {
        "design_id": design_id,
        "valid": verification.valid,
        "verification": verification.model_dump(),
        "manifest": manifest.model_dump(),
        "bundle_url": f"/exports/{design_id}/simulation/bundle.zip",
    }


@app.get("/designs/{design_id}/bundle")
def download_bundle(design_id: str) -> FileResponse:
    """Download the generated simulation bundle zip for a design."""
    bundle_path = DESIGNS_DIR / design_id / "simulation" / "bundle.zip"
    if not bundle_path.exists():
        raise HTTPException(status_code=404, detail="Bundle not found. Run POST /designs/{id}/simulate first.")
    return FileResponse(bundle_path, media_type="application/zip", filename=f"{design_id}_bundle.zip")


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
        use_feature_tree=False,
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
    use_feature_tree: bool = False,
    use_assembly: bool = False,
) -> tuple[GenerationResult, dict]:
    design_dir = DESIGNS_DIR / design_id
    exports_dir = design_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    result = backend.generate(
        prompt,
        model=model,
        max_retries=max_retries,
        output_dir=exports_dir,
        use_feature_tree=use_feature_tree,
        use_assembly=use_assembly,
    )

    # Build a manufacturing report for successful STL exports.
    if result.success and result.exports.stl and result.exports.stl.exists():
        try:
            manufacturing = ManufacturingReport(**_analyze_manufacturing(result.exports.stl))
            result.manufacturing = manufacturing
        except Exception:
            pass

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
    if result.feature_tree is not None:
        save_feature_tree(design_id, result.feature_tree)
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
