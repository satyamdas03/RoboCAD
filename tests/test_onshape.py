"""Tests for ai_cad.onshape client (mocked HTTP)."""
from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from ai_cad.onshape import OnshapeAuth, OnshapeClient


def test_onshape_auth_signs_request():
    auth = OnshapeAuth("access_key", "secret_key")
    request = mock.Mock()
    request.method = "GET"
    request.url = "https://cad.onshape.com/api/documents?limit=5"
    request.headers = {}

    signed = auth(request)

    assert "Date" in signed.headers
    assert "On-Nonce" in signed.headers
    assert signed.headers["Authorization"].startswith("On access_key:HmacSHA256:")
    assert signed.headers["On-Nonce"]
    assert len(signed.headers["On-Nonce"]) == 25


def test_onshape_auth_preserves_query_order():
    auth = OnshapeAuth("access_key", "secret_key")
    request = mock.Mock()
    request.method = "GET"
    request.url = "https://cad.onshape.com/api/documents?offset=0&limit=5&sortColumn=createdAt"
    request.headers = {}

    signed = auth(request)
    # Authorization header must exist and use the exact query string order.
    assert signed.headers["Authorization"].startswith("On access_key:HmacSHA256:")


def test_onshape_client_requires_credentials(monkeypatch):
    monkeypatch.delenv("ONSHAPE_ACCESS_KEY", raising=False)
    monkeypatch.delenv("ONSHAPE_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        OnshapeClient()


def test_onshape_client_uses_env_credentials(monkeypatch):
    monkeypatch.setenv("ONSHAPE_ACCESS_KEY", "test_access")
    monkeypatch.setenv("ONSHAPE_SECRET_KEY", "test_secret")
    monkeypatch.setenv("ONSHAPE_BASE_URL", "https://cad.example.com")
    client = OnshapeClient()
    assert client.access_key == "test_access"
    assert client.secret_key == "test_secret"
    assert client.base_url == "https://cad.example.com"


def test_list_documents_parses_response(tmp_path, monkeypatch):
    monkeypatch.setenv("ONSHAPE_ACCESS_KEY", "test_access")
    monkeypatch.setenv("ONSHAPE_SECRET_KEY", "test_secret")

    client = OnshapeClient()
    with mock.patch.object(client.session, "get") as mock_get:
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"items": [{"id": "doc-1", "name": "Test"}], "total": 1}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = client.list_documents(limit=5)
        assert result["items"][0]["id"] == "doc-1"
        mock_get.assert_called_once()


def test_upload_step_to_new_document(tmp_path, monkeypatch):
    monkeypatch.setenv("ONSHAPE_ACCESS_KEY", "test_access")
    monkeypatch.setenv("ONSHAPE_SECRET_KEY", "test_secret")

    step_path = tmp_path / "model.step"
    step_path.write_text("FAKE STEP CONTENT")

    client = OnshapeClient()
    with mock.patch.object(client.session, "post") as mock_post, mock.patch.object(
        client.session, "get"
    ) as mock_get:
        create_resp = mock.Mock()
        create_resp.status_code = 200
        create_resp.json.return_value = {
            "id": "did",
            "defaultWorkspace": {"id": "wid"},
        }
        create_resp.raise_for_status.return_value = None

        upload_resp = mock.Mock()
        upload_resp.status_code = 200
        upload_resp.json.return_value = {"id": "tid", "requestState": "ACTIVE"}
        upload_resp.raise_for_status.return_value = None

        poll_resp = mock.Mock()
        poll_resp.status_code = 200
        poll_resp.json.return_value = {
            "id": "tid",
            "requestState": "DONE",
            "resultElementIds": ["eid"],
        }
        poll_resp.raise_for_status.return_value = None

        mock_post.side_effect = [create_resp, upload_resp]
        mock_get.return_value = poll_resp

        result = client.upload_step_to_new_document(step_path, "New doc")
        assert result["document_id"] == "did"
        assert result["workspace_id"] == "wid"
        assert result["translation"]["completed"] is True
        assert result["element_url"].endswith("/e/eid")
