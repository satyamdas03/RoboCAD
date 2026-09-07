"""Tests for the installer build script skeleton."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import build_installer


def test_write_spec_creates_file(tmp_path: Path, monkeypatch):
    spec_path = tmp_path / "robocad.spec"
    monkeypatch.setattr(build_installer, "SPEC_PATH", spec_path)
    build_installer._write_spec(onefile=True)
    assert spec_path.exists()
    text = spec_path.read_text(encoding="utf-8")
    assert "Analysis" in text
    assert "start.py" in text


def test_find_pyinstaller_returns_string_or_none():
    result = build_installer._find_pyinstaller()
    assert result is None or isinstance(result, str)


def test_main_without_pyinstaller_exits_with_message(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setattr(build_installer, "DIST_DIR", tmp_path / "dist")
    monkeypatch.setattr(build_installer, "_find_pyinstaller", lambda: None)
    monkeypatch.setattr(build_installer, "SPEC_PATH", tmp_path / "robocad.spec")
    with pytest.raises(SystemExit) as exc_info:
        build_installer.main([])
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "PyInstaller not found" in captured.out
