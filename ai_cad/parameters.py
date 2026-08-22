"""Extract editable named parameters from generated build123d code."""
from __future__ import annotations

import ast
import re
from typing import Optional

from ai_cad.models import CADParameter


_PARAM_COMMENT_RE = re.compile(r"#\s*param:\s*(.+)", re.IGNORECASE)


def _is_numeric(value: ast.expr) -> bool:
    """Return True if the AST expression is a numeric literal."""
    return isinstance(value, ast.Constant) and isinstance(value.value, (int, float))


def _numeric_value(value: ast.expr) -> float | int:
    """Return the numeric value of a numeric literal expression."""
    assert isinstance(value, ast.Constant)
    return value.value


def _extract_comment(source_lines: list[str], node: ast.AST) -> Optional[str]:
    """Look for a `# param: ...` comment on the same line as the assignment."""
    if node.lineno is None or node.lineno > len(source_lines):
        return None
    line = source_lines[node.lineno - 1]
    match = _PARAM_COMMENT_RE.search(line)
    if match:
        return match.group(1).strip()
    return None


def _is_valid_parameter_name(name: str) -> bool:
    """Heuristic: reject imports, constants, private variables, and the result variable."""
    if name.startswith("_"):
        return False
    if name.isupper():
        return False
    if name in {"result", "__all__"}:
        return False
    if not name[0].isalpha() and name[0] != "_":
        return False
    return True


def extract_parameters(code: str) -> list[CADParameter]:
    """Parse generated code and return module-level numeric parameters.

    Parameters are identified by module-level assignments of numeric literals,
    e.g. ``length = 120.0``. Optional ``# param: description`` comments are
    captured as the parameter description.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    source_lines = code.splitlines()
    params: list[CADParameter] = []
    seen: set[str] = set()

    # Collect imported names so we do not treat `from build123d import *` names as params.
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    # We cannot know the imported names; rely on name heuristic below.
                    continue
                imported_names.add(alias.asname or alias.name)

    for node in tree.body:
        name: str | None = None
        value: ast.expr | None = None

        if isinstance(node, ast.Assign):
            if len(node.targets) != 1:
                continue
            target = node.targets[0]
            if isinstance(target, ast.Name):
                name = target.id
                value = node.value
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                name = node.target.id
                value = node.value

        if name is None or value is None:
            continue
        if not _is_valid_parameter_name(name):
            continue
        if name in imported_names:
            continue
        if not _is_numeric(value):
            continue
        if name in seen:
            continue

        seen.add(name)
        description = _extract_comment(source_lines, node)
        params.append(
            CADParameter(
                name=name,
                value=_numeric_value(value),
                unit="mm",
                description=description,
            )
        )

    return params
