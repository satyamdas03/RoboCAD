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
from typing import Any

# Add repo root so we can import the ai_cad package.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from ai_cad.api import RoboCADBackend
from ai_cad.models import CADParameter, GenerationResult

app = FastAPI(title="RoboCAD", version="0.2.0")

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


class DesignSummary(BaseModel):
    id: str
    prompt: str
    success: bool
    model: str
    attempts_used: int
    latency_seconds: float | None
    created_at: str
    export_urls: dict[str, str | None]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/generate", response_model=GenerateResponse)
def generate(request: GenerateRequest) -> GenerateResponse:
    if not backend.api_key:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not configured.")

    design_id = uuid.uuid4().hex
    design_dir = DESIGNS_DIR / design_id
    exports_dir = design_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    result = backend.generate(
        request.prompt,
        model=request.model,
        max_retries=request.max_retries,
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
    _write_text(design_dir / "prompt.txt", request.prompt)
    if result.code:
        _write_text(design_dir / "code.py", result.code)
    _write_json(design_dir / "parameters.json", [p.model_dump() for p in result.parameters])

    metadata = {
        "id": design_id,
        "prompt": request.prompt,
        "success": result.success,
        "model": result.model,
        "attempts_used": result.attempts_used,
        "max_retries": result.max_retries,
        "latency_seconds": result.latency_seconds,
        "validation": result.validation.model_dump() if result.validation else None,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "exports": {
            "stl": "model.stl" if final_stl else None,
            "step": "model.step" if final_step else None,
            "script": "code.py" if result.code else None,
        },
    }
    _write_json(design_dir / "metadata.json", metadata)

    export_urls = _build_export_urls(design_id, metadata["exports"])

    return GenerateResponse(
        **result.model_dump(),
        design_id=design_id,
        export_urls=export_urls,
    )


@app.get("/designs")
def list_designs() -> list[DesignSummary]:
    summaries: list[DesignSummary] = []
    if not DESIGNS_DIR.exists():
        return summaries

    for design_dir in sorted(DESIGNS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        meta_path = design_dir / "metadata.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
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

    return {
        **meta,
        "code": code,
        "parameters": parameters,
        "export_urls": _build_export_urls(design_id, meta.get("exports", {})),
    }


@app.get("/exports/{design_id}/{filename}")
def get_export(design_id: str, filename: str) -> FileResponse:
    safe_filename = Path(filename).name
    file_path = DESIGNS_DIR / design_id / "exports" / safe_filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found.")

    media_type = "application/octet-stream"
    if filename.lower().endswith(".stl"):
        media_type = "model/stl"
    elif filename.lower().endswith(".step") or filename.lower().endswith(".stp"):
        media_type = "application/step"
    elif filename.lower().endswith(".py"):
        media_type = "text/x-python"

    return FileResponse(file_path, media_type=media_type, filename=filename)


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
