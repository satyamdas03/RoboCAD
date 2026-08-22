"""Safe code-level operations on generated build123d scripts.

Right now this module supports replacing module-level numeric parameter values
while preserving comments, formatting, and unrelated lines. It is intentionally
conservative: it only edits assignments that already exist in the source.
"""
from __future__ import annotations

import re
from typing import Optional


def update_parameter(code: str, name: str, value: float | int) -> str:
    """Replace the module-level assignment ``name = ...`` with the new value.

    The value is rendered as an int when it is an int, otherwise as a float.
    Preserves the same line's inline comment.

    Raises:
        ValueError: if the parameter cannot be found or is not a simple assignment.
    """
    # Normalize value rendering.
    if isinstance(value, bool):
        raise ValueError("Boolean values are not supported as numeric parameters.")
    value_str = str(int(value)) if isinstance(value, int) and value == int(value) else str(float(value))

    lines = code.splitlines()
    pattern = re.compile(rf"^(\s*{re.escape(name)}\s*=\s*)[^#\n]+(.*)$")

    found = False
    for i, line in enumerate(lines):
        # Skip if this line looks like an expression or is inside a function/class.
        if not _is_module_level_assignment(line):
            continue

        match = pattern.match(line)
        if match:
            prefix = match.group(1)
            suffix = match.group(2)
            lines[i] = f"{prefix}{value_str}{suffix}"
            found = True
            break

    if not found:
        raise ValueError(f"Parameter '{name}' not found or not a simple module-level assignment.")

    return "\n".join(lines)


def update_parameters(code: str, updates: dict[str, float | int]) -> str:
    """Apply multiple parameter updates to the code in one pass.

    Updates are applied in the order provided. If any parameter is missing, a
    ValueError is raised and no changes are persisted.
    """
    # Validate all names exist first so we don't apply partial edits.
    for name in updates:
        if not _has_parameter(code, name):
            raise ValueError(f"Parameter '{name}' not found.")

    new_code = code
    for name, value in updates.items():
        new_code = update_parameter(new_code, name, value)
    return new_code


def _is_module_level_assignment(line: str) -> bool:
    """Heuristic: line is a simple assignment at module indent level."""
    stripped = line.lstrip()
    if not stripped:
        return False
    if stripped.startswith("#"):
        return False
    if not stripped[0].isalpha() and stripped[0] != "_":
        return False
    if "=" not in stripped:
        return False
    # Reject augmented assignments.
    before_eq = stripped.split("=", 1)[0].rstrip()
    if before_eq.endswith(("+", "-", "*", "/", "//", "%", "**", "@", "&", "|", "^", "<<", ">>")):
        return False
    # Must be at indent level 0 (module level).
    if line[: len(line) - len(stripped)]:
        return False
    return True


def _has_parameter(code: str, name: str) -> bool:
    """Return True if a module-level assignment for ``name`` exists in the code."""
    for line in code.splitlines():
        if not _is_module_level_assignment(line):
            continue
        match = re.match(rf"^\s*{re.escape(name)}\s*=", line)
        if match:
            return True
    return False
