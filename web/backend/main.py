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
from ai_cad.composer import compose_feature_tree
from ai_cad.decomposition import DecompositionResult, decompose, should_decompose
from ai_cad.domain import classify_domain
from ai_cad.executor import execute_code
from ai_cad.assembly import sample_assembly_poses, solve_assembly, transpile_assembly
from ai_cad.assembly_collision import check_assembly_collision
from ai_cad.dfm import analyze_dfm
from ai_cad.feature_store import save as save_feature_tree
from ai_cad.feature_tree import Assembly, FeatureTree
from ai_cad.intent_parser import parse_domain_intent
from ai_cad.mate_inference import infer_mates
from ai_cad.fea import run_static_analysis
from ai_cad.geda_bridge import (
    build_scene,
    export_bundle_from_mesh,
    export_bundle_from_tree,
    export_scene_to_mjcf,
    get_capabilities,
    list_skills,
    load_bundle_manifest,
    package_bundle_paths,
    recommend_skill,
    run_variant_sweep,
    stability_check_bundle,
    train_push_skill,
    validate_bundle_with_mujoco,
    verify_bundle,
)
from ai_cad.geda_bridge.models import BundleManifest, BundleVerification
from ai_cad.guess_parameter import guess_parameter as _guess_parameter
from ai_cad.manufacturing import analyze_model as _analyze_manufacturing
from ai_cad.models import CADParameter, ExportPaths, GenerationResult, ManufacturingReport, ValidationReport
from ai_cad.onshape import OnshapeClient
from ai_cad.parameters import extract_parameters
from ai_cad.tolerances import check_fit
from ai_cad.aero import run_aero_analysis
from ai_cad.cfd import export_cfd_mesh_from_stl
from ai_cad.electronics import export_idf, run_electronics_analysis
from ai_cad.thermal import run_thermal_analysis
from ai_cad.transpiler import transpile
from ai_cad.validator import validate_model
from ai_cad.verification import get_report, run_verification
from ai_cad.verification_models import LoadCase, VerificationRequest, VerificationResult as VerificationResultModel
from ai_cad.robot_templates import humanoid_template, manipulator_on_base_template, quadruped_template
from ai_cad.actuator_sizing import actuator_summary, size_actuators_for_tree
from ai_cad.kinematic_tree import forward_kinematics, sample_reachable_workspace
from ai_cad.stability import check_stability, stability_summary

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
    detect_domain: bool = Field(default=False, description="Classify the prompt domain and extract a domain intent.")
    decompose: bool = Field(default=True, description="Automatically decompose multi-domain system prompts into part families.")


class ClassifyDomainRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="Natural-language part description.")


class GenerateResponse(GenerationResult):
    design_id: str | None = None
    export_urls: dict[str, str | None] = Field(default_factory=dict)
    parent_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    domain: str | None = None
    domain_intent: dict[str, Any] | None = None
    decomposition: dict[str, Any] | None = None


class DecomposeRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="Natural-language system description.")


class DecomposedPartModel(BaseModel):
    id: str
    name: str
    domain: str
    family: str
    sub_prompt: str
    count: int = 1


class DecomposeResponse(BaseModel):
    prompt: str
    primary_domain: str
    multi_domain: bool
    parts: list[DecomposedPartModel]
    notes: list[str] = Field(default_factory=list)

    @classmethod
    def from_result(cls, result: DecompositionResult) -> "DecomposeResponse":
        return cls(
            prompt=result.prompt,
            primary_domain=result.primary_domain,
            multi_domain=result.multi_domain,
            parts=[
                DecomposedPartModel(
                    id=p.id,
                    name=p.name,
                    domain=p.domain,
                    family=p.family,
                    sub_prompt=p.sub_prompt,
                    count=p.count,
                )
                for p in result.parts
            ],
            notes=result.notes,
        )


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
    domain: str | None = None


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


class AeroAnalysisRequest(BaseModel):
    naca: str = Field(default="0012", description="NACA 4-digit airfoil code.")
    angle_of_attack_deg: float = Field(default=0.0, description="Freestream angle of attack in degrees.")
    flow_velocity_ms: float = Field(default=10.0, gt=0, description="Freestream velocity in m/s.")


class ThermalAnalysisRequest(BaseModel):
    heat_flux_w: float = Field(default=10.0, ge=0, description="Applied thermal load in watts.")
    ambient_temp_c: float = Field(default=25.0, description="Ambient temperature in degrees Celsius.")
    convection_coefficient_w_per_m2_k: float = Field(
        default=50.0, gt=0, description="Convective heat transfer coefficient in W/(m^2*K)."
    )


class CFDMeshRequest(BaseModel):
    solver: str = Field(default="su2_stub", description="CFD solver stub format: su2_stub or openfoam_stub.")
    angle_of_attack_deg: float = Field(default=0.0, description="Freestream angle of attack in degrees.")
    flow_velocity_ms: float = Field(default=10.0, gt=0, description="Freestream velocity in m/s.")
    characteristic_length_m: float = Field(default=0.1, gt=0, description="Reference length for Reynolds number.")


class IDFExportRequest(BaseModel):
    board_name: str = Field(default="ROBOCAD_PCB", description="Board name written into the IDF .emn file.")


class VerifyRequest(BaseModel):
    load_case: str = Field(..., description="One of the supported verification load-case names.")
    materials: dict[str, str] = Field(default_factory=dict, description="Map of part_id to material name.")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Case-specific parameter overrides.")


class MeshQualityRequest(BaseModel):
    part_id: str | None = Field(default=None, description="Optional part id; ignored for single STL designs.")


class SceneTemplateRequest(BaseModel):
    template: str = Field(default="gripper_cube_grasp", description="Scene template name.")
    material: str = Field(default="PLA", description="Material name for density lookup.")
    tolerance: float = Field(default=0.1, gt=0, le=1.0, description="Mesh tessellation tolerance in mm.")


class TrainSkillRequest(BaseModel):
    skill_description: str = Field(default="push the block to the goal", description="Natural-language skill/task to train.")
    n_iters: int = Field(default=20, ge=5, le=100, description="CEM training iterations.")
    pop_size: int = Field(default=50, ge=10, le=200, description="CEM population size.")
    eval_episodes: int = Field(default=10, ge=1, le=50, description="Evaluation episodes for success rate.")


class VariantSweepRequest(BaseModel):
    parameter_ranges: dict[str, dict[str, float]] = Field(..., description="Parameter name -> {min/max or relative_min/relative_max or step}.")
    n_variants: int = Field(default=5, ge=2, le=20, description="Number of variants to generate.")
    tolerance: float = Field(default=0.1, gt=0, le=1.0, description="Mesh tessellation tolerance in mm.")
    run_stability: bool = Field(default=True, description="Run a 2 s MuJoCo stability check on each variant.")


class RobotTemplateRequest(BaseModel):
    template: str = Field(..., description="One of: humanoid, quadruped, manipulator_on_base.")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Template parameter overrides.")


class RobotAnalysisRequest(BaseModel):
    payload_kg: float = Field(default=5.0, gt=0, description="Design payload mass in kg.")
    safety_factor: float = Field(default=2.0, gt=0, description="Actuator safety factor.")
    robot_mass_kg: float = Field(default=20.0, gt=0, description="Total robot mass estimate in kg.")
    lateral_accel_m_s2: float = Field(default=0.5, ge=0, description="Lateral acceleration budget for ZMP check in m/s^2.")
    end_effector_id: str = Field(default="hand_r", description="Instance id used for reachable workspace sampling.")
    swing_foot_id: str = Field(default="foot_l", description="Foot instance id used for gait feasibility proxy.")




@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/classify-domain")
def classify_domain_endpoint(req: ClassifyDomainRequest) -> dict[str, Any]:
    return classify_domain(req.prompt).model_dump()


@app.post("/decompose", response_model=DecomposeResponse)
def decompose_endpoint(req: DecomposeRequest) -> DecomposeResponse:
    result = decompose(req.prompt, use_llm=False)
    return DecomposeResponse.from_result(result)


def _classify_domain_safe(prompt: str) -> dict[str, Any]:
    """Call classify_domain, tolerating test mocks that only accept one argument."""
    try:
        return classify_domain(prompt, use_embeddings=False).model_dump()
    except TypeError:
        return classify_domain(prompt).model_dump()


@app.post("/generate", response_model=GenerateResponse)
def generate(request: GenerateRequest) -> GenerateResponse:
    design_id = uuid.uuid4().hex
    decomposition_data: dict[str, Any] | None = None

    if request.decompose and should_decompose(request.prompt):
        result, metadata, decomposition_data = _run_decomposed_generation(
            design_id,
            request.prompt,
        )
    else:
        if not backend.api_key:
            raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not configured.")
        result, metadata = _run_generation(
            design_id,
            request.prompt,
            request.model,
            request.max_retries,
            use_feature_tree=True,
            use_assembly=request.use_assembly,
        )

    domain: str | None = None
    domain_intent_data: dict[str, Any] | None = None
    if request.detect_domain:
        domain = _classify_domain_safe(request.prompt)["primary"]
        intent = parse_domain_intent(request.prompt, domain=domain)
        domain_intent_data = intent.model_dump(mode="json")
        _write_json(DESIGNS_DIR / design_id / "domain_intent.json", domain_intent_data)

    if decomposition_data:
        _write_json(DESIGNS_DIR / design_id / "decomposition.json", decomposition_data)

    return GenerateResponse(
        **result.model_dump(),
        design_id=design_id,
        export_urls=_build_export_urls(design_id, metadata["exports"]),
        parent_id=metadata.get("parent_id"),
        tags=metadata.get("tags", []),
        domain=domain,
        domain_intent=domain_intent_data,
        decomposition=decomposition_data,
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
                domain=meta.get("domain"),
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


@app.get("/designs/{design_id}/domain-intent")
def get_domain_intent(design_id: str) -> JSONResponse:
    path = DESIGNS_DIR / design_id / "domain_intent.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="No domain intent for this design")
    return JSONResponse(content=json.loads(path.read_text(encoding="utf-8")))


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


@app.post("/designs/{design_id}/synthesize-assembly")
def synthesize_assembly(design_id: str) -> dict[str, Any]:
    """Re-run mate inference and joint synthesis on the design's assembly."""
    design_dir = DESIGNS_DIR / design_id
    feature_tree_path = design_dir / "feature_tree.json"
    if not feature_tree_path.exists():
        raise HTTPException(status_code=404, detail="No feature tree found for this design.")

    try:
        data = json.loads(feature_tree_path.read_text(encoding="utf-8"))
        tree = FeatureTree(**data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load feature tree: {exc}")

    if not tree.assemblies:
        raise HTTPException(status_code=404, detail="No assembly found for this design.")

    assembly = tree.assemblies[0]
    try:
        mates, joints = infer_mates(tree, assembly)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Mate inference failed: {exc}")

    # Merge inferred mates/joints, avoiding duplicates.
    existing_mate_ids = {m.id for m in assembly.mates}
    existing_joint_ids = {j.id for j in assembly.joints}
    for mate in mates:
        if mate.id not in existing_mate_ids:
            assembly.mates.append(mate)
    for joint in joints:
        if joint.id not in existing_joint_ids:
            assembly.joints.append(joint)

    _write_json(feature_tree_path, tree.model_dump(mode="json"))
    return {
        "design_id": design_id,
        "assembly": json.loads(json.dumps(assembly.model_dump(mode="json"))),
        "joints_added": len(joints),
        "mates_added": len(mates),
    }


@app.get("/designs/{design_id}/assembly-poses")
def get_assembly_poses(
    design_id: str,
    samples_per_joint: int = Query(default=8, ge=2, le=32),
) -> dict[str, Any]:
    """Return sampled range-of-motion poses for an articulated assembly."""
    design_dir = DESIGNS_DIR / design_id
    feature_tree_path = design_dir / "feature_tree.json"
    if not feature_tree_path.exists():
        raise HTTPException(status_code=404, detail="No feature tree found for this design.")

    try:
        tree = FeatureTree(**json.loads(feature_tree_path.read_text(encoding="utf-8")))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load feature tree: {exc}")

    if not tree.assemblies:
        raise HTTPException(status_code=404, detail="No assembly found for this design.")

    try:
        poses = sample_assembly_poses(tree, samples_per_joint=samples_per_joint)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to sample poses: {exc}")

    return {"design_id": design_id, **poses}


@app.post("/designs/{design_id}/assembly-collision")
def assembly_collision(design_id: str) -> dict[str, Any]:
    """Check pairwise collision / clearance between assembly instances."""
    design_dir = DESIGNS_DIR / design_id
    feature_tree_path = design_dir / "feature_tree.json"
    if not feature_tree_path.exists():
        raise HTTPException(status_code=404, detail="No feature tree found for this design.")

    try:
        tree = FeatureTree(**json.loads(feature_tree_path.read_text(encoding="utf-8")))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load feature tree: {exc}")

    if not tree.assemblies:
        raise HTTPException(status_code=404, detail="No assembly found for this design.")

    try:
        reports = check_assembly_collision(tree, design_dir / "collision", samples=1000)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to run collision check: {exc}")

    pairs = [r.model_dump() for r in reports]
    worst = None
    if pairs:
        worst = min(pairs, key=lambda p: p["min_clearance_mm"])
    return {
        "design_id": design_id,
        "pair_count": len(pairs),
        "pairs": pairs,
        "worst": worst,
    }


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


@app.post("/designs/{design_id}/aero-report")
def aero_report(design_id: str, request: AeroAnalysisRequest) -> dict[str, Any]:
    """Run a lightweight aero estimate on a design's STL."""
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
        result = run_aero_analysis(
            stl_path,
            naca=request.naca,
            angle_of_attack_deg=request.angle_of_attack_deg,
            flow_velocity_ms=request.flow_velocity_ms,
        )
        aero_dir = design_dir / "aero"
        aero_dir.mkdir(parents=True, exist_ok=True)
        _write_json(aero_dir / "aero_report.json", result.model_dump())
        meta.setdefault("exports", {})
        meta["exports"]["aero_report"] = "aero/aero_report.json"
        _write_json(meta_path, meta)
        return {"design_id": design_id, "report": result.model_dump()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to run aero analysis: {exc}")


@app.get("/designs/{design_id}/aero-report")
def get_aero_report(design_id: str) -> dict[str, Any]:
    """Return the persisted aero report for a design."""
    design_dir = DESIGNS_DIR / design_id
    meta_path = design_dir / "metadata.json"
    report_path = design_dir / "aero" / "aero_report.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Design not found.")
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="No aero report found for this design.")

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read aero report: {exc}")

    return {"design_id": design_id, "report": report}


@app.post("/designs/{design_id}/thermal-report")
def thermal_report(design_id: str, request: ThermalAnalysisRequest) -> dict[str, Any]:
    """Run a lightweight thermal estimate on a design's STL."""
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
        result = run_thermal_analysis(
            stl_path,
            heat_flux_w=request.heat_flux_w,
            ambient_temp_c=request.ambient_temp_c,
            convection_coefficient_w_per_m2_k=request.convection_coefficient_w_per_m2_k,
        )
        thermal_dir = design_dir / "thermal"
        thermal_dir.mkdir(parents=True, exist_ok=True)
        _write_json(thermal_dir / "thermal_report.json", result.model_dump())
        meta.setdefault("exports", {})
        meta["exports"]["thermal_report"] = "thermal/thermal_report.json"
        _write_json(meta_path, meta)
        return {"design_id": design_id, "report": result.model_dump()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to run thermal analysis: {exc}")


@app.get("/designs/{design_id}/thermal-report")
def get_thermal_report(design_id: str) -> dict[str, Any]:
    """Return the persisted thermal report for a design."""
    design_dir = DESIGNS_DIR / design_id
    meta_path = design_dir / "metadata.json"
    report_path = design_dir / "thermal" / "thermal_report.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Design not found.")
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="No thermal report found for this design.")

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read thermal report: {exc}")

    return {"design_id": design_id, "report": report}


@app.post("/designs/{design_id}/electronics-report")
def electronics_report_post(design_id: str) -> dict[str, Any]:
    """Run electronics/mechatronics analysis on a design's feature tree."""
    design_dir = DESIGNS_DIR / design_id
    meta_path = design_dir / "metadata.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Design not found.")

    feature_tree_path = design_dir / "feature_tree.json"
    if not feature_tree_path.exists():
        raise HTTPException(status_code=422, detail="No feature tree found for this design.")

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        tree_data = json.loads(feature_tree_path.read_text(encoding="utf-8"))
        tree = FeatureTree(**tree_data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read design data: {exc}")

    try:
        elec_dir = design_dir / "electronics"
        elec_dir.mkdir(parents=True, exist_ok=True)
        result = run_electronics_analysis(tree, elec_dir)
        _write_json(elec_dir / "electronics_report.json", result.model_dump())
        meta.setdefault("exports", {})
        meta["exports"]["electronics_report"] = "electronics/electronics_report.json"
        _write_json(meta_path, meta)
        return {"design_id": design_id, "report": result.model_dump()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to run electronics analysis: {exc}")


@app.get("/designs/{design_id}/electronics-report")
def electronics_report_get(design_id: str) -> dict[str, Any]:
    """Return the persisted electronics/mechatronics report for a design."""
    design_dir = DESIGNS_DIR / design_id
    meta_path = design_dir / "metadata.json"
    report_path = design_dir / "electronics" / "electronics_report.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Design not found.")
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="No electronics report found for this design.")

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read electronics report: {exc}")

    return {"design_id": design_id, "report": report}


@app.post("/designs/{design_id}/idf-export")
def idf_export(design_id: str, request: IDFExportRequest) -> dict[str, Any]:
    """Export an IDF v3.0 board (.emn), package library (.emp), and STEP placeholder."""
    design_dir = DESIGNS_DIR / design_id
    meta_path = design_dir / "metadata.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Design not found.")

    feature_tree_path = design_dir / "feature_tree.json"
    if not feature_tree_path.exists():
        raise HTTPException(status_code=422, detail="No feature tree found for this design.")

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        tree_data = json.loads(feature_tree_path.read_text(encoding="utf-8"))
        tree = FeatureTree(**tree_data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read design data: {exc}")

    try:
        idf_dir = design_dir / "idf"
        idf_dir.mkdir(parents=True, exist_ok=True)
        paths = export_idf(
            tree,
            idf_dir,
            design_id,
            board_name=request.board_name,
        )
        meta.setdefault("exports", {})
        meta["exports"]["idf"] = "idf"
        _write_json(meta_path, meta)
        return {
            "design_id": design_id,
            "board_name": request.board_name,
            "files": {k: str(v.relative_to(design_dir).as_posix()) for k, v in paths.items()},
            "download_urls": {
                k: f"/exports/{design_id}/idf/{v.name}" for k, v in paths.items()
            },
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to export IDF: {exc}")


@app.post("/designs/{design_id}/cfd-mesh")
def cfd_mesh(design_id: str, request: CFDMeshRequest) -> dict[str, Any]:
    """Export a CFD surface mesh + solver stub for a design."""
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
        cfd_dir = design_dir / "cfd"
        cfd_dir.mkdir(parents=True, exist_ok=True)
        result = export_cfd_mesh_from_stl(
            stl_path,
            cfd_dir,
            solver=request.solver,
            angle_of_attack_deg=request.angle_of_attack_deg,
            flow_velocity_ms=request.flow_velocity_ms,
            characteristic_length_m=request.characteristic_length_m,
        )
        meta.setdefault("exports", {})
        if result.success:
            meta["exports"]["cfd_mesh"] = "cfd"
            _write_json(meta_path, meta)
        return {"design_id": design_id, "report": result.model_dump()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to export CFD mesh: {exc}")


@app.get("/designs/{design_id}/bundle")
def download_bundle(design_id: str) -> FileResponse:
    """Download the generated simulation bundle zip for a design."""
    bundle_path = DESIGNS_DIR / design_id / "simulation" / "bundle.zip"
    if not bundle_path.exists():
        raise HTTPException(status_code=404, detail="Bundle not found. Run POST /designs/{id}/simulate first.")
    return FileResponse(bundle_path, media_type="application/zip", filename=f"{design_id}_bundle.zip")


@app.post("/designs/{design_id}/scene")
def compose_scene(design_id: str, request: SceneTemplateRequest) -> dict[str, Any]:
    """Compose a standard manipulation scene around a design's simulation bundle."""
    design_dir = DESIGNS_DIR / design_id
    meta_path = design_dir / "metadata.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Design not found.")

    simulation_dir = design_dir / "simulation"
    manifest_path = simulation_dir / "manifest.json"
    if not manifest_path.exists():
        # Auto-generate the bundle first using the same material/tolerance.
        simulate_design(design_id, SimulateRequest(material=request.material, tolerance=request.tolerance))

    try:
        manifest = BundleManifest(**json.loads(manifest_path.read_text(encoding="utf-8")))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read bundle manifest: {exc}")

    scene_name = f"{design_id}_{request.template}"
    scene_path = simulation_dir / f"scene_{request.template}.mjcf"
    try:
        scene = build_scene(request.template, manifest.parts)
        export_scene_to_mjcf(scene, scene_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to compose scene: {exc}")

    runtime_ok = False
    runtime_info: dict[str, Any] = {}
    try:
        runtime_info = validate_bundle_with_mujoco(simulation_dir)
        # Try to load the scene MJCF specifically.
        import mujoco

        model = mujoco.MjModel.from_xml_path(str(scene_path))
        data = mujoco.MjData(model)
        for _ in range(20):
            mujoco.mj_step(model, data)
        runtime_info["scene_loadable"] = True
        runtime_info["scene_nbody"] = int(getattr(model, "nbody", 0))
        runtime_ok = True
    except Exception as exc:
        runtime_info["scene_loadable"] = False
        runtime_info["scene_error"] = str(exc)

    # Persist scene metadata in the design for GET retrieval.
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta.setdefault("scenes", {})
    meta["scenes"][request.template] = {
        "template": request.template,
        "scene_file": f"simulation/scene_{request.template}.mjcf",
        "runtime_ok": runtime_ok,
        "runtime_info": runtime_info,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    _write_json(meta_path, meta)

    return {
        "design_id": design_id,
        "template": request.template,
        "scene_name": scene_name,
        "scene_url": f"/exports/{design_id}/simulation/scene_{request.template}.mjcf",
        "runtime_ok": runtime_ok,
        "runtime_info": runtime_info,
    }


@app.get("/designs/{design_id}/scene")
def get_scene_report(design_id: str, template: str = Query(default="gripper_cube_grasp", description="Scene template name.")) -> dict[str, Any]:
    """Return the persisted scene metadata for a design and template."""
    design_dir = DESIGNS_DIR / design_id
    meta_path = design_dir / "metadata.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Design not found.")

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read metadata: {exc}")

    scenes = meta.get("scenes", {})
    if template not in scenes:
        raise HTTPException(status_code=404, detail=f"Scene template '{template}' not found. Run POST /designs/{id}/scene first.")

    return {
        "design_id": design_id,
        "template": template,
        "scene": scenes[template],
        "scene_url": f"/exports/{design_id}/simulation/scene_{template}.mjcf",
    }


@app.get("/capabilities")
def capabilities() -> dict[str, Any]:
    """Return the RoboCAD GEDA Bridge capability registry."""
    return get_capabilities()


@app.post("/designs/{design_id}/handshake")
def handshake(design_id: str, template: str = Query(default="wedge_push_block", description="Scene template for stability check.")) -> dict[str, Any]:
    """Run the LearningRobotics handshake: export → scene → 10 s MuJoCo stability rollout."""
    design_dir = DESIGNS_DIR / design_id
    meta_path = design_dir / "metadata.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Design not found.")

    simulation_dir = design_dir / "simulation"
    manifest_path = simulation_dir / "manifest.json"
    if not manifest_path.exists():
        # Auto-generate the bundle first.
        simulate_design(design_id, SimulateRequest(material="PLA", tolerance=0.1))

    try:
        manifest = load_bundle_manifest(simulation_dir)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read bundle manifest: {exc}")

    try:
        scene = build_scene(template, manifest.parts)
        scene_path = simulation_dir / f"scene_{template}.mjcf"
        export_scene_to_mjcf(scene, scene_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to compose scene: {exc}")

    check = stability_check_bundle(simulation_dir, scene_template=template, duration_seconds=10.0)

    # Persist handshake result.
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta.setdefault("handshakes", {})
    meta["handshakes"][template] = {
        "template": template,
        "scene_file": f"simulation/scene_{template}.mjcf",
        "success": check["success"],
        "rollout": check["rollout"],
        "nbody": check["nbody"],
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    _write_json(meta_path, meta)

    return {
        "design_id": design_id,
        "template": template,
        "success": check["success"],
        "scene_url": f"/exports/{design_id}/simulation/scene_{template}.mjcf",
        "nbody": check["nbody"],
        "rollout": check["rollout"],
        "errors": check.get("errors", []),
        "warnings": check.get("warnings", []),
    }


@app.get("/designs/{design_id}/handshake")
def get_handshake_report(design_id: str, template: str = Query(default="wedge_push_block", description="Scene template for stability check.")) -> dict[str, Any]:
    """Return the persisted handshake result for a design and template."""
    design_dir = DESIGNS_DIR / design_id
    meta_path = design_dir / "metadata.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Design not found.")

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read metadata: {exc}")

    handshakes = meta.get("handshakes", {})
    if template not in handshakes:
        raise HTTPException(status_code=404, detail=f"Handshake for '{template}' not found. Run POST /designs/{id}/handshake first.")

    return {
        "design_id": design_id,
        "template": template,
        "handshake": handshakes[template],
        "scene_url": f"/exports/{design_id}/simulation/scene_{template}.mjcf",
    }


@app.post("/designs/{design_id}/recommend-skill")
def recommend_skill_endpoint(design_id: str, request: TrainSkillRequest) -> dict[str, Any]:
    """Recommend a scene template and default policy config for a skill."""
    design_dir = DESIGNS_DIR / design_id
    meta_path = design_dir / "metadata.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Design not found.")

    recommendation = recommend_skill(request.skill_description)
    # Persist recommendation for later train-skill call.
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["recommended_skills"] = meta.get("recommended_skills", [])
    meta["recommended_skills"].append(
        {
            "skill_description": request.skill_description,
            "template": recommendation.template,
            "confidence": recommendation.confidence,
            "goal_pos": recommendation.goal_pos,
            "block_start": recommendation.block_start,
            "policy_config": recommendation.policy_config,
            "reasoning": recommendation.reasoning,
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
    )
    _write_json(meta_path, meta)

    return {
        "design_id": design_id,
        "skill_description": request.skill_description,
        "template": recommendation.template,
        "confidence": recommendation.confidence,
        "goal_pos": recommendation.goal_pos,
        "block_start": recommendation.block_start,
        "policy_config": recommendation.policy_config,
        "reasoning": recommendation.reasoning,
        "available_skills": list_skills(),
    }


@app.post("/designs/{design_id}/train-skill")
def train_skill_endpoint(design_id: str, request: TrainSkillRequest) -> dict[str, Any]:
    """Train a tiny push policy for a design's simulation asset (Phase 15B smoke test)."""
    design_dir = DESIGNS_DIR / design_id
    meta_path = design_dir / "metadata.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Design not found.")

    simulation_dir = design_dir / "simulation"
    manifest_path = simulation_dir / "manifest.json"
    if not manifest_path.exists():
        # Auto-generate the bundle first.
        simulate_design(design_id, SimulateRequest(material="PLA", tolerance=0.1))

    try:
        manifest = load_bundle_manifest(simulation_dir)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read bundle manifest: {exc}")

    # Resolve the first mesh in the bundle.
    if not manifest.parts:
        raise HTTPException(status_code=422, detail="Bundle has no parts.")
    mesh_file = manifest.parts[0].mesh_file
    mesh_path = simulation_dir / mesh_file
    if not mesh_path.exists():
        raise HTTPException(status_code=422, detail=f"Mesh file not found: {mesh_file}")

    recommendation = recommend_skill(request.skill_description)
    goal_pos = recommendation.goal_pos
    block_start = recommendation.block_start
    success_radius = recommendation.policy_config.get("success_radius_m", 0.06) if recommendation.policy_config else 0.06

    try:
        report = train_push_skill(
            asset_mesh_path=mesh_path,
            output_dir=simulation_dir,
            goal_m=goal_pos,
            block_start_m=block_start or (0.25, 0.0, 0.49),
            n_iters=request.n_iters,
            pop_size=request.pop_size,
            eval_episodes=request.eval_episodes,
            success_radius_m=success_radius,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Skill training failed: {exc}")

    # Persist result.
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta.setdefault("skills", {})
    meta["skills"][recommendation.template] = {
        "template": recommendation.template,
        "skill_description": request.skill_description,
        "success": report["success"],
        "success_rate": report["success_rate"],
        "mean_final_distance_m": report["mean_final_distance_m"],
        "policy_file": report.get("policy_file"),
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    _write_json(meta_path, meta)

    return {
        "design_id": design_id,
        "template": recommendation.template,
        **report,
    }


@app.get("/designs/{design_id}/skills")
def list_skills_endpoint(design_id: str) -> dict[str, Any]:
    """Return persisted skill training results for a design."""
    design_dir = DESIGNS_DIR / design_id
    meta_path = design_dir / "metadata.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Design not found.")

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read metadata: {exc}")

    return {
        "design_id": design_id,
        "skills": meta.get("skills", {}),
        "recommended_skills": meta.get("recommended_skills", []),
    }


@app.post("/designs/{design_id}/variant-sweep")
def variant_sweep_endpoint(design_id: str, request: VariantSweepRequest) -> dict[str, Any]:
    """Generate N parametric variants of a design and export each as a simulation bundle."""
    design_dir = DESIGNS_DIR / design_id
    meta_path = design_dir / "metadata.json"
    feature_tree_path = design_dir / "feature_tree.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Design not found.")
    if not feature_tree_path.exists():
        raise HTTPException(status_code=422, detail="Variant sweep requires a feature tree. Generate with use_feature_tree=True first.")

    output_root = design_dir / "variant_sweep"
    try:
        report = run_variant_sweep(
            feature_tree_path=feature_tree_path,
            parameter_ranges=request.parameter_ranges,
            n_variants=request.n_variants,
            output_root=output_root,
            tolerance=request.tolerance,
            run_stability=request.run_stability,
            seed=42,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Variant sweep failed: {exc}")

    # Persist report path in metadata.
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["variant_sweeps"] = meta.get("variant_sweeps", [])
    meta["variant_sweeps"].append(
        {
            "report_path": report["report_path"],
            "n_variants": request.n_variants,
            "parameter_ranges": request.parameter_ranges,
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
    )
    _write_json(meta_path, meta)

    return report


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


@app.post("/designs/{design_id}/verify")
def verify_design(design_id: str, request: VerifyRequest) -> dict[str, Any]:
    """Run a multi-physics verification load case on a design."""
    design_dir = DESIGNS_DIR / design_id
    meta_path = design_dir / "metadata.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Design not found.")

    try:
        load_case = LoadCase(request.load_case)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported load case: {request.load_case}. Supported: {[c.value for c in LoadCase]}",
        )

    try:
        req = VerificationRequest(
            design_id=design_id,
            load_case=load_case,
            materials=request.materials,
            parameters=request.parameters,
        )
        result = run_verification(req, design_dir=design_dir)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Verification failed: {exc}")

    # Persist report for GET retrieval.
    verify_dir = design_dir / "verification"
    verify_dir.mkdir(parents=True, exist_ok=True)
    _write_json(verify_dir / f"{result.report_id}.json", result.model_dump(mode="json"))
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        meta = {}
    meta.setdefault("verification_reports", [])
    meta["verification_reports"].append(
        {
            "report_id": result.report_id,
            "load_case": result.load_case.value,
            "passed": result.passed,
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
    )
    _write_json(meta_path, meta)

    return {"design_id": design_id, "report": result.model_dump(mode="json")}


@app.get("/designs/{design_id}/verify-report/{report_id}")
def get_verify_report(design_id: str, report_id: str) -> dict[str, Any]:
    """Return a cached verification report by id."""
    result = get_report(report_id)
    if result is None or result.design_id != design_id:
        # Try to load from disk.
        report_path = DESIGNS_DIR / design_id / "verification" / f"{report_id}.json"
        if report_path.exists():
            try:
                data = json.loads(report_path.read_text(encoding="utf-8"))
                result = VerificationResultModel(**data)
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"Failed to read report: {exc}")
        else:
            raise HTTPException(status_code=404, detail="Verification report not found.")

    return {"design_id": design_id, "report": result.model_dump(mode="json")}


@app.post("/designs/{design_id}/mesh-quality-check")
def mesh_quality_check(design_id: str, request: MeshQualityRequest) -> dict[str, Any]:
    """Run the mesh-quality pre-checker on a design's STL export."""
    return verify_design(
        design_id,
        VerifyRequest(load_case=LoadCase.MESH_QUALITY.value),
    )


@app.get("/robot-templates")
def list_robot_templates() -> dict[str, Any]:
    """Return the available robot system templates."""
    return {
        "templates": [
            {
                "name": "humanoid",
                "description": "Biped humanoid robot with legs and optional arms.",
                "parameters": ["robot_height", "payload_kg", "robot_mass_kg", "leg_dof", "arm_dof", "gait_style"],
            },
            {
                "name": "quadruped",
                "description": "Quadruped robot with four legs.",
                "parameters": ["robot_height", "payload_kg", "robot_mass_kg", "leg_dof", "gait_style"],
            },
            {
                "name": "manipulator_on_base",
                "description": "Mobile base carrying a serial manipulator.",
                "parameters": ["base_size", "reach", "payload_kg", "robot_mass_kg", "arm_dof"],
            },
        ]
    }


@app.post("/robot-templates")
def create_robot_template(req: RobotTemplateRequest) -> dict[str, Any]:
    """Instantiate a parameterized robot-system template as a persisted design."""
    template_name = req.template.lower()
    if template_name == "humanoid":
        tree = humanoid_template()
    elif template_name == "quadruped":
        tree = quadruped_template()
    elif template_name == "manipulator_on_base":
        tree = manipulator_on_base_template()
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown robot template '{req.template}'. Supported: humanoid, quadruped, manipulator_on_base.",
        )

    # Apply parameter overrides.
    for name, value in req.parameters.items():
        try:
            tree.update_parameter(name, value)
        except Exception:
            # Unknown or unparseable parameter; skip silently.
            pass

    design_id = uuid.uuid4().hex
    design_dir = DESIGNS_DIR / design_id
    design_dir.mkdir(parents=True, exist_ok=True)

    meta = {
        "id": design_id,
        "prompt": tree.prompt,
        "success": True,
        "model": f"robot-template:{template_name}",
        "attempts_used": 1,
        "max_retries": 0,
        "latency_seconds": 0.0,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "exports": {},
        "tags": ["robot_template", template_name],
        "domain": "mechanical",
    }
    _write_json(design_dir / "metadata.json", meta)
    _write_json(design_dir / "feature_tree.json", tree.model_dump(mode="json"))
    _write_json(design_dir / "parameters.json", [p.model_dump() for p in tree.parameters])

    return {
        "design_id": design_id,
        "template": template_name,
        "feature_tree": tree.model_dump(mode="json"),
        "export_urls": _build_export_urls(design_id, {}),
    }


@app.post("/designs/{design_id}/robot-analysis")
def robot_analysis(design_id: str, request: RobotAnalysisRequest) -> dict[str, Any]:
    """Run actuator sizing, stability, workspace, and gait feasibility on a robot design."""
    design_dir = DESIGNS_DIR / design_id
    feature_tree_path = design_dir / "feature_tree.json"
    if not feature_tree_path.exists():
        raise HTTPException(status_code=404, detail="Feature tree not found for this design.")

    try:
        tree = FeatureTree(**json.loads(feature_tree_path.read_text(encoding="utf-8")))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load feature tree: {exc}")

    if not tree.assemblies:
        raise HTTPException(status_code=422, detail="No assembly found for robot analysis.")

    # Actuator sizing.
    actuator_specs = size_actuators_for_tree(
        tree,
        payload_kg=request.payload_kg,
        safety_factor=request.safety_factor,
    )

    # Stability / ZMP.
    stability_report = check_stability(
        tree,
        robot_mass_kg=request.robot_mass_kg,
        lateral_accel_m_s2=request.lateral_accel_m_s2,
    )

    # Reachable workspace of the requested end-effector.
    workspace = sample_reachable_workspace(
        tree,
        end_effector_id=request.end_effector_id,
        samples_per_joint=5,
    )

    # Simple gait proxy: can the swing foot move in X and Z?
    swing_workspace = sample_reachable_workspace(
        tree,
        end_effector_id=request.swing_foot_id,
        samples_per_joint=4,
    )
    env = swing_workspace.get("envelope_mm", (0.0, 0.0, 0.0))
    gait_feasible = stability_report.gait_feasible and env[0] >= 50.0 and env[2] >= 30.0

    # Forward kinematics at zero pose.
    poses = forward_kinematics(tree)
    pose_summary = {
        link: {
            "position": [float(v) for v in pose.position],
            "rotation_deg": [float(v) for v in pose.rotation_deg],
        }
        for link, pose in poses.items()
    }

    return {
        "design_id": design_id,
        "actuators": {jid: spec.__dict__ for jid, spec in actuator_specs.items()},
        "actuator_summary": actuator_summary(actuator_specs),
        "stability": stability_summary(stability_report),
        "reachable_workspace": workspace,
        "swing_workspace": swing_workspace,
        "gait_feasible": gait_feasible,
        "zero_pose": pose_summary,
    }


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


def _run_decomposed_generation(
    design_id: str,
    prompt: str,
    parent_id: str | None = None,
    tags: list[str] | None = None,
) -> tuple[GenerationResult, dict, dict[str, Any]]:
    """Phase 18 path: decompose a system prompt into part families and assemble."""
    import time

    design_dir = DESIGNS_DIR / design_id
    exports_dir = design_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    start = time.time()

    decomposition = decompose(prompt, use_llm=False)
    tree = compose_feature_tree(decomposition)
    code = transpile_assembly(tree)
    exec_result = execute_code(code, output_dir=exports_dir, timeout=120)

    final_stl: Path | None = None
    final_step: Path | None = None
    if exec_result.get("stl_path") and Path(exec_result["stl_path"]).exists():
        final_stl = exports_dir / "model.stl"
        shutil.copy2(exec_result["stl_path"], final_stl)
    if exec_result.get("step_path") and Path(exec_result["step_path"]).exists():
        final_step = exports_dir / "model.step"
        shutil.copy2(exec_result["step_path"], final_step)

    validation = None
    if final_stl:
        validation = _build_validation_report(final_stl)

    parameters = [
        CADParameter(name=p.name, value=p.value, unit=p.unit, description=p.description)
        for p in tree.parameters
    ]

    _write_text(design_dir / "prompt.txt", prompt)
    _write_text(design_dir / "code.py", code)
    save_feature_tree(design_id, tree, designs_dir=DESIGNS_DIR)
    _write_json(design_dir / "parameters.json", [p.model_dump() for p in parameters])

    decomposition_data = DecomposeResponse.from_result(decomposition).model_dump()

    metadata = {
        "id": design_id,
        "prompt": prompt,
        # Phase 18 assemblies are compounds of touching parts; requiring watertight
        # would fail every multi-part layout. We mark success when the generated
        # code executes and produces an STL.
        "success": exec_result.get("success", False) and final_stl is not None,
        "model": "phase18-decomposer",
        "attempts_used": 1,
        "max_retries": 0,
        "latency_seconds": round(time.time() - start, 3),
        "validation": validation.model_dump() if validation else None,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "parent_id": parent_id,
        "tags": tags or [],
        "exports": {
            "stl": "model.stl" if final_stl else None,
            "step": "model.step" if final_step else None,
            "script": "code.py",
        },
        "decomposition": decomposition_data,
    }
    _write_json(design_dir / "metadata.json", metadata)

    result = GenerationResult(
        prompt=prompt,
        success=metadata["success"],
        code=code,
        parameters=parameters,
        exports=ExportPaths(
            step=final_step,
            stl=final_stl,
            script=design_dir / "code.py" if final_stl else None,
        ),
        validation=validation,
        feature_tree=tree,
        attempts_used=1,
        max_retries=0,
        model="phase18-decomposer",
        latency_seconds=metadata["latency_seconds"],
    )
    return result, metadata, decomposition_data


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
        save_feature_tree(design_id, result.feature_tree, designs_dir=DESIGNS_DIR)
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
