"""Unit tests for the AI code generator utilities."""
from __future__ import annotations

import os

import pytest

from ai_cad.generator import _extract_code_block, generate_model


EXAMPLE_RESPONSE = """
Here is the code:

```python
from build123d import *

with BuildPart() as p:
    Box(10, 10, 10)

result = p.part
```
"""


def test_extract_code_block_python():
    code = _extract_code_block(EXAMPLE_RESPONSE)
    assert code is not None
    assert "from build123d import *" in code
    assert "result = p.part" in code


def test_extract_code_block_no_fence():
    text = "from build123d import *\n\nresult = Box(1,2,3)"
    code = _extract_code_block(text)
    assert code is not None
    assert "result = Box" in code


def test_generate_model_without_api_key():
    # Ensure the function fails gracefully without an API key.
    original = os.environ.get("ANTHROPIC_API_KEY")
    if "ANTHROPIC_API_KEY" in os.environ:
        del os.environ["ANTHROPIC_API_KEY"]
    try:
        result = generate_model("a cube 10 mm")
        assert result["success"] is False
        assert "ANTHROPIC_API_KEY" in result["error"]
    finally:
        if original:
            os.environ["ANTHROPIC_API_KEY"] = original
