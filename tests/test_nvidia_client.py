"""Tests for the NVIDIA NIM client and HERMES caller integration."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_cad.nvidia_client import NvidiaClient, NvidiaError, build_nvidia_caller
from ai_cad.render_critique import critique_render


@pytest.fixture(autouse=True)
def clear_nvidia_env(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.delenv("NVIDIA_BASE_URL", raising=False)


def test_client_available_with_key():
    client = NvidiaClient(api_key="secret")
    assert client.available() is True


def test_client_unavailable_without_key():
    client = NvidiaClient(api_key="")
    assert client.available() is False


def test_chat_returns_assistant_text(monkeypatch):
    client = NvidiaClient(api_key="secret")

    def fake_post(url, **kwargs):
        class Resp:
            status_code = 200
            text = '{"choices":[{"message":{"content":"hello"}}]}'
            def raise_for_status(self): pass
            def json(self):
                return {"choices": [{"message": {"content": "hello"}}]}
        return Resp()

    monkeypatch.setattr("ai_cad.nvidia_client.httpx.post", fake_post)
    result = client.chat([{"role": "user", "content": "hi"}], model="nvidia/nemotron")
    assert result == "hello"


def test_chat_bad_response_raises(monkeypatch):
    client = NvidiaClient(api_key="secret")

    def fake_post(url, **kwargs):
        class Resp:
            status_code = 200
            text = '{"unexpected": true}'
            def raise_for_status(self): pass
            def json(self):
                return {"unexpected": True}
        return Resp()

    monkeypatch.setattr("ai_cad.nvidia_client.httpx.post", fake_post)
    with pytest.raises(NvidiaError):
        client.chat([{"role": "user", "content": "hi"}])


def test_vision_sends_base64_image(monkeypatch):
    client = NvidiaClient(api_key="secret")
    captured = {}

    def fake_post(url, **kwargs):
        captured["json"] = kwargs.get("json")
        captured["url"] = url
        class Resp:
            status_code = 200
            def raise_for_status(self): pass
            def json(self):
                return {"choices": [{"message": {"content": "looks good"}}]}
        return Resp()

    monkeypatch.setattr("ai_cad.nvidia_client.httpx.post", fake_post)
    result = client.vision("describe this", b"fake-image", model="meta/llama-vision")
    assert result == "looks good"
    assert captured["url"].endswith("/chat/completions")
    content = captured["json"]["messages"][0]["content"]
    assert any(item.get("type") == "image_url" for item in content)
    assert "ZmFrZS1pbWFnZQ" in content[1]["image_url"]["url"]  # base64 of "fake-image"


def test_generate_scenario_passes_prompt(monkeypatch):
    client = NvidiaClient(api_key="secret")

    def fake_post(url, **kwargs):
        class Resp:
            status_code = 200
            def raise_for_status(self): pass
            def json(self):
                return {"description": "robot walking on stairs", "video_url": "https://example.com/v.mp4"}
        return Resp()

    monkeypatch.setattr("ai_cad.nvidia_client.httpx.post", fake_post)
    result = client.generate_scenario("humanoid robot climbing stairs")
    assert result["description"] == "robot walking on stairs"
    assert result["video_url"] == "https://example.com/v.mp4"


def test_build_nvidia_caller_returns_text(monkeypatch):
    def fake_post(url, **kwargs):
        class Resp:
            status_code = 200
            def raise_for_status(self): pass
            def json(self):
                return {"choices": [{"message": {"content": '{"tool_calls": []}'}}]}
        return Resp()

    monkeypatch.setattr("ai_cad.nvidia_client.httpx.post", fake_post)
    caller = build_nvidia_caller(model="nemotron-lightning", api_key="secret")
    text = caller([{"role": "user", "content": "hello"}])
    assert '"tool_calls": []' in text


def test_build_nvidia_caller_no_key_returns_error_json():
    caller = build_nvidia_caller(model="nemotron-lightning", api_key="")
    text = caller([{"role": "user", "content": "hello"}])
    assert "NVIDIA_API_KEY" in text
    assert "tool_calls" in text


def test_critique_render_with_mock_vision(monkeypatch):
    client = NvidiaClient(api_key="secret")

    def fake_post(url, **kwargs):
        class Resp:
            status_code = 200
            def raise_for_status(self): pass
            def json(self):
                return {
                    "choices": [
                        {
                            "message": {
                                "content": '```json\n{"score": 88, "issues": [], "suggestions": ["good"], "safe_to_show_user": true}\n```'
                            }
                        }
                    ]
                }
        return Resp()

    monkeypatch.setattr("ai_cad.nvidia_client.httpx.post", fake_post)
    result = critique_render(b"fake-image", api_key="secret")
    assert result["score"] == 88
    assert result["safe_to_show_user"] is True
    assert result["issues"] == []


def test_critique_render_no_key_fallback():
    result = critique_render(b"fake-image", api_key="")
    assert result["safe_to_show_user"] is True
    assert "NVIDIA_API_KEY" in result["suggestions"][0]
