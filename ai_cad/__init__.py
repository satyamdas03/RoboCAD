"""RoboCAD core package: AI-driven parametric CAD generation."""

from ai_cad.api import RoboCADBackend, generate
from ai_cad.code_ops import update_parameter, update_parameters
from ai_cad.executor import execute_code
from ai_cad.exporter import export_model
from ai_cad.generator import generate_model
from ai_cad.models import CADParameter, ExportPaths, GenerationResult, ValidationReport
from ai_cad.parameters import extract_parameters
from ai_cad.validator import validate_model

__all__ = [
    "RoboCADBackend",
    "generate",
    "generate_model",
    "execute_code",
    "validate_model",
    "export_model",
    "extract_parameters",
    "update_parameter",
    "update_parameters",
    "CADParameter",
    "ExportPaths",
    "GenerationResult",
    "ValidationReport",
]
