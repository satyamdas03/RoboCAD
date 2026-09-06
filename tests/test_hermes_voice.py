"""Tests for HERMES LiveKit + NVIDIA voice integration."""
from __future__ import annotations

import os
import sys
import wave
import io
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient
from livekit import rtc

from web.backend import main as main_module
from web.backend.main import app

from ai_cad.hermes.livekit_token import create_token, create_agent_token
from ai_cad.hermes.nvidia_voice import NvidiaSTT, NvidiaTTS, NvidiaVoiceError
from ai_cad.hermes.voice_plugins import NvidiaSTTPlugin, NvidiaTTSPlugin


client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_designs(tmp_path: Path):
    """Use a temporary designs directory for every test."""
    original = main_module.DESIGNS_DIR
    test_dir = tmp_path / "designs"
    test_dir.mkdir(parents=True, exist_ok=True)
    main_module.DESIGNS_DIR = test_dir
    yield
    main_module.DESIGNS_DIR = original


@pytest.fixture(autouse=True)
def livekit_env(monkeypatch):
    """Provide dummy LiveKit credentials for token tests."""
    monkeypatch.setenv("LIVEKIT_URL", "wss://fake.livekit.cloud")
    monkeypatch.setenv("LIVEKIT_API_KEY", "test_key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "test_secret")


@pytest.fixture(autouse=True)
def nvidia_env(monkeypatch):
    """Clear NVIDIA API key so plugin tests without an explicit key fail cleanly."""
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.delenv("NVIDIA_BASE_URL", raising=False)


# -----------------------------------------------------------------------------
# LiveKit token generation
# -----------------------------------------------------------------------------

def test_create_user_token():
    data = create_token("sess_abc123")
    assert data["url"] == "wss://fake.livekit.cloud"
    assert data["room"] == "hermes-sess_abc123"
    assert data["identity"].startswith("hermes-user-")
    assert isinstance(data["token"], str)
    assert "." in data["token"]


def test_create_agent_token():
    data = create_agent_token("sess_abc123")
    assert data["room"] == "hermes-sess_abc123"
    assert data["identity"] == "hermes-agent"
    assert isinstance(data["token"], str)


def test_create_token_missing_env(monkeypatch):
    monkeypatch.delenv("LIVEKIT_API_SECRET", raising=False)
    with pytest.raises(RuntimeError):
        create_token("sess_x")


# -----------------------------------------------------------------------------
# Backend token endpoint
# -----------------------------------------------------------------------------

def _create_hermes_session() -> str:
    response = client.post("/hermes/session", json={})
    assert response.status_code == 200
    return response.json()["session_id"]


def test_hermes_livekit_token_endpoint():
    session_id = _create_hermes_session()
    response = client.post(
        f"/hermes/session/{session_id}/livekit-token",
        json={"session_id": session_id},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == session_id
    assert data["room"] == f"hermes-{session_id}"
    assert "token" in data
    assert "url" in data


def test_hermes_livekit_token_session_mismatch():
    session_id = _create_hermes_session()
    response = client.post(
        f"/hermes/session/{session_id}/livekit-token",
        json={"session_id": "different"},
    )
    assert response.status_code == 400


def test_hermes_livekit_token_session_not_found():
    response = client.post(
        "/hermes/session/hermes_missing/livekit-token",
        json={"session_id": "hermes_missing"},
    )
    assert response.status_code == 404


# -----------------------------------------------------------------------------
# NVIDIA REST voice clients
# -----------------------------------------------------------------------------

def _fake_wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 160)
    return buffer.getvalue()


def test_nvidia_stt_transcribe(monkeypatch):
    stt = NvidiaSTT(api_key="nvidia-key")

    def fake_post(url, **kwargs):
        class Resp:
            status_code = 200
            text = '{"text":"hello world"}'
            def raise_for_status(self): pass
            def json(self):
                return {"text": "hello world"}
        return Resp()

    monkeypatch.setattr("ai_cad.hermes.nvidia_voice.httpx.post", fake_post)
    result = stt.transcribe(_fake_wav())
    assert result == "hello world"


def test_nvidia_stt_returns_alternative_field(monkeypatch):
    stt = NvidiaSTT(api_key="nvidia-key")

    def fake_post(url, **kwargs):
        class Resp:
            status_code = 200
            text = '{"transcription":"alternate"}'
            def raise_for_status(self): pass
            def json(self):
                return {"transcription": "alternate"}
        return Resp()

    monkeypatch.setattr("ai_cad.hermes.nvidia_voice.httpx.post", fake_post)
    result = stt.transcribe(_fake_wav())
    assert result == "alternate"


def test_nvidia_stt_api_error(monkeypatch):
    stt = NvidiaSTT(api_key="nvidia-key")

    def fake_post(url, **kwargs):
        class Resp:
            status_code = 401
            text = "unauthorized"
            def raise_for_status(self):
                import httpx
                raise httpx.HTTPStatusError(
                    "unauthorized",
                    request=None,
                    response=self,
                )
            def json(self): return {}
        return Resp()

    monkeypatch.setattr("ai_cad.hermes.nvidia_voice.httpx.post", fake_post)
    with pytest.raises(NvidiaVoiceError):
        stt.transcribe(_fake_wav())


def test_nvidia_stt_requires_api_key():
    stt = NvidiaSTT(api_key="")
    with pytest.raises(NvidiaVoiceError):
        stt.transcribe(b"")


def test_nvidia_tts_synthesize(monkeypatch):
    tts = NvidiaTTS(api_key="nvidia-key")
    wav = _fake_wav()

    def fake_post(url, **kwargs):
        class Resp:
            status_code = 200
            text = ""
            content = wav
            def raise_for_status(self): pass
        return Resp()

    monkeypatch.setattr("ai_cad.hermes.nvidia_voice.httpx.post", fake_post)
    result = tts.synthesize("hello")
    assert result.startswith(b"RIFF")


def test_nvidia_tts_requires_api_key():
    tts = NvidiaTTS(api_key="")
    with pytest.raises(NvidiaVoiceError):
        tts.synthesize("hello")


# -----------------------------------------------------------------------------
# LiveKit plugin adapters
# -----------------------------------------------------------------------------

def test_stt_plugin_no_api_key():
    plugin = NvidiaSTTPlugin(api_key="")
    assert plugin._client.available() is False


def test_tts_plugin_no_api_key():
    plugin = NvidiaTTSPlugin(api_key="")
    assert plugin._client.available() is False


def test_stt_plugin_recognize_no_key_raises():
    plugin = NvidiaSTTPlugin(api_key="")
    frame = rtc.AudioFrame(
        data=b"\x00\x00" * 160,
        sample_rate=16000,
        num_channels=1,
        samples_per_channel=160,
    )
    import asyncio
    with pytest.raises(Exception):
        asyncio.run(plugin._recognize_impl(frame))
