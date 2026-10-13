"""Safe arithmetic expression evaluator.

Replaces restricted ``eval()`` calls in feature-tree/assembly/morphology paths.
Only allows +, -, *, /, //, %, **, parentheses, whitelisted names, and a small
set of math functions/constants.
"""
from __future__ import annotations

import ast
import math
import operator
from typing import Any, Callable

_ALLOWED_NAMES: dict[str, Any] = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "atan2": math.atan2,
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "pow": pow,
}

_BIN_OPS: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY_OPS: dict[type[ast.unaryop], Callable[[Any], Any]] = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


class UnsafeExpressionError(ValueError):
    """Raised when an expression contains disallowed nodes."""


def _eval_node(node: ast.AST, ctx: dict[str, float]) -> Any:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, ctx)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise UnsafeExpressionError(f"Unsupported constant: {node.value!r}")
    if isinstance(node, ast.Name):
        if node.id in ctx:
            return ctx[node.id]
        if node.id in _ALLOWED_NAMES:
            return _ALLOWED_NAMES[node.id]
        raise UnsafeExpressionError(f"Unknown name: {node.id}")
    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _BIN_OPS:
            raise UnsafeExpressionError(f"Unsupported binary operator: {op_type.__name__}")
        return _BIN_OPS[op_type](_eval_node(node.left, ctx), _eval_node(node.right, ctx))
    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _UNARY_OPS:
            raise UnsafeExpressionError(f"Unsupported unary operator: {op_type.__name__}")
        return _UNARY_OPS[op_type](_eval_node(node.operand, ctx))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise UnsafeExpressionError("Only simple function calls are allowed")
        func_name = node.func.id
        if func_name not in _ALLOWED_NAMES:
            raise UnsafeExpressionError(f"Unknown function: {func_name}")
        args = [_eval_node(a, ctx) for a in node.args]
        kwargs = {kw.arg: _eval_node(kw.value, ctx) for kw in node.keywords}
        return _ALLOWED_NAMES[func_name](*args, **kwargs)
    raise UnsafeExpressionError(f"Unsupported expression node: {type(node).__name__}")


def safe_eval_float(expr: str, parameters: dict[str, float] | None = None) -> float:
    """Evaluate a simple numeric expression and return a float.

    Args:
        expr: The expression string.
        parameters: Mapping of parameter names to numeric values.

    Raises:
        ValueError: If parsing or evaluation fails.
    """
    parameters = parameters or {}
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Invalid expression: {expr!r}") from exc
    try:
        result = _eval_node(tree, parameters)
    except UnsafeExpressionError as exc:
        raise ValueError(f"Disallowed expression: {expr!r}: {exc}") from exc
    try:
        return float(result)
    except Exception as exc:
        raise ValueError(f"Expression did not evaluate to a number: {expr!r}") from exc
