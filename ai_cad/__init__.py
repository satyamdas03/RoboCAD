"""RoboCAD core package: AI-driven parametric CAD generation.

The public names below are resolved on first use rather than imported here. A process that only
wants the compiler -- ``python -m robocad twin compile|summary|page|unpack`` -- has no use for the
Anthropic SDK, and importing it eagerly made those commands fail on a machine where the SDK is not
installed. Attribute access is unchanged: ``ai_cad.transpile`` and ``from ai_cad import transpile``
both work exactly as before, they just import their module when they are asked for it.
"""

import importlib
import sys

# The anthropic SDK depends on a vendored "httpx2" fork that has a recursion
# bug when making HTTPS requests on Python 3.14. Replace it with the standard
# httpx/httpcore packages before any Anthropic import resolves. We also map the
# low-level httpcore2 dependency because the fork uses the same broken fork
# pattern.
try:
    import httpx  # noqa: F401
    import httpcore  # noqa: F401

    sys.modules["httpx2"] = httpx
    sys.modules["httpcore2"] = httpcore
except ImportError:
    pass

# name -> module that defines it. One entry per name in ``__all__``, so nothing is reachable only
# through an eager import that would drag the LLM client back in.
_LAZY: dict[str, str] = {
    "RoboCADBackend": "ai_cad.api",
    "generate": "ai_cad.api",
    "update_parameter": "ai_cad.code_ops",
    "update_parameters": "ai_cad.code_ops",
    "execute_code": "ai_cad.executor",
    "export_model": "ai_cad.exporter",
    "generate_model": "ai_cad.generator",
    "CADParameter": "ai_cad.models",
    "ExportPaths": "ai_cad.models",
    "GenerationResult": "ai_cad.models",
    "ValidationReport": "ai_cad.models",
    "extract_parameters": "ai_cad.parameters",
    "transpile_assembly": "ai_cad.assembly",
    "transpile": "ai_cad.transpiler",
    "validate_model": "ai_cad.validator",
}

__all__ = list(_LAZY)


def __getattr__(name: str):
    module_name = _LAZY.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(importlib.import_module(module_name), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(list(globals()) + __all__))
