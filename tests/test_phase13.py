"""Unit tests for Phase 13 model-specialization scripts.

These tests use small synthetic datasets so they do not require a running
Ollama instance or the full complexity ladder.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import build_ollama_modelfile as modelfile_script
from scripts import build_training_dataset as dataset_script
from scripts import evaluate_finetuned as eval_script
from scripts import finetune_model as finetune_script


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """A fresh temp directory that mimics the repo layout for script I/O."""
    return tmp_path


def test_split_data_deterministic() -> None:
    data = [{"id": f"p{i}"} for i in range(10)]
    train, test = dataset_script._split_data(data, 0.2)
    assert len(train) == 8
    assert len(test) == 2
    # Every 1/0.2 = 5th item goes to test (indices 0 and 5)
    assert test[0]["id"] == "p0"
    assert test[1]["id"] == "p5"


def test_split_data_zero_test_fraction() -> None:
    data = [{"id": f"p{i}"} for i in range(3)]
    train, test = dataset_script._split_data(data, 0.0)
    assert len(train) == 3
    assert test == []


def test_write_jsonl_roundtrip(tmp_repo: Path) -> None:
    path = tmp_repo / "rows.jsonl"
    rows = [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]
    dataset_script._write_jsonl(path, rows)
    loaded = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert loaded == rows


def test_build_ollama_modelfile_with_examples(tmp_repo: Path) -> None:
    rows = [
        {
            "prompt": "A cube 10 mm on a side.",
            "feature_tree": {"schema_version": "1.0.0", "parts": []},
            "metadata": {"tier": "T1 - Primitive", "parameter_count": 1},
        },
        {
            "prompt": "A bracket with two holes.",
            "feature_tree": {"schema_version": "1.0.0", "parts": [{}]},
            "metadata": {"tier": "T3 - Intermediate", "parameter_count": 5},
        },
    ]
    dataset_path = tmp_repo / "feature_tree_train.jsonl"
    dataset_script._write_jsonl(dataset_path, rows)

    modelfile_path = tmp_repo / "robocad-ft" / "Modelfile"
    modelfile_path.parent.mkdir(parents=True, exist_ok=True)

    # Simulate command-line invocation with a synthetic dataset.
    parser = modelfile_script._build_arg_parser()
    args = parser.parse_args(
        ["--dataset", str(dataset_path), "--output", str(modelfile_path), "--examples", "2"]
    )
    modelfile_script.main_with_args(args)

    text = modelfile_path.read_text(encoding="utf-8")
    assert text.startswith("FROM qwen3-coder:latest")
    assert 'SYSTEM """' in text
    assert "A cube 10 mm on a side." in text
    assert "A bracket with two holes." in text

    create_script = modelfile_path.parent / "create_model.bat"
    assert create_script.exists()
    assert "ollama create robocad-ft" in create_script.read_text(encoding="utf-8")


def test_build_ollama_modelfile_empty_dataset_raises(tmp_repo: Path) -> None:
    dataset_path = tmp_repo / "empty.jsonl"
    dataset_script._write_jsonl(dataset_path, [])
    parser = modelfile_script._build_arg_parser()
    args = parser.parse_args(["--dataset", str(dataset_path)])
    with pytest.raises(ValueError, match="Dataset is empty"):
        modelfile_script.main_with_args(args)


def test_finetune_load_dataset_and_format(tmp_repo: Path) -> None:
    rows = [
        {
            "prompt": "A cube.",
            "feature_tree": {"schema_version": "1.0.0", "parts": []},
            "metadata": {"id": "t1.1", "tier": "T1 - Primitive"},
        },
        {
            "prompt": "A cylinder.",
            "feature_tree": {"schema_version": "1.0.0", "parts": [{}]},
            "metadata": {"id": "t1.2", "tier": "T1 - Primitive"},
        },
    ]
    dataset_path = tmp_repo / "train.jsonl"
    dataset_script._write_jsonl(dataset_path, rows)

    prompts, completions = finetune_script._load_dataset(dataset_path)
    assert prompts == ["A cube.", "A cylinder."]
    assert len(completions) == 2
    assert json.loads(completions[0]) == rows[0]["feature_tree"]

    alpaca = finetune_script._format_alpaca_prompts(prompts, completions)
    assert len(alpaca) == 2
    assert "### Instruction:" in alpaca[0]["text"]
    assert "### Response:" in alpaca[0]["text"]
    assert '"schema_version":"1.0.0"' in alpaca[0]["text"]


def test_finetune_load_dataset_too_small(tmp_repo: Path) -> None:
    dataset_path = tmp_repo / "tiny.jsonl"
    dataset_script._write_jsonl(dataset_path, [{"prompt": "x", "feature_tree": {}}])
    with pytest.raises(FileNotFoundError):
        finetune_script._load_dataset(tmp_repo / "missing.jsonl")


def test_eval_load_test_prompts_from_jsonl(tmp_repo: Path) -> None:
    rows = [
        {
            "prompt": "A cube.",
            "feature_tree": {},
            "metadata": {"id": "t1.1", "tier": "T1 - Primitive"},
        }
    ]
    dataset_path = tmp_repo / "test.jsonl"
    dataset_script._write_jsonl(dataset_path, rows)
    prompts = eval_script._load_test_prompts(dataset_path)
    assert prompts == [{"id": "t1.1", "tier": "T1 - Primitive", "prompt": "A cube."}]


def test_eval_load_test_prompts_missing_dataset_falls_back_to_ladder(tmp_repo: Path) -> None:
    prompts = eval_script._load_test_prompts(tmp_repo / "does_not_exist.jsonl")
    # Should return the full 30-prompt complexity ladder.
    assert len(prompts) == 30
    assert prompts[0]["id"].startswith("t")
