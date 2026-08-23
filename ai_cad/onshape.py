"""Onshape REST API client for RoboCAD.

Authentication follows Onshape's documented HMAC scheme (matching
onshape_client.apikey_headers):
- Access Key + Secret Key (from a generated API key pair)
- String to sign (lowercased before HMAC):
    method + "\\n" + nonce + "\\n" + date + "\\n" + content-type + "\\n" + path + "\\n" + query-string + "\\n"
- Header: On-Nonce
- Authorization: "On " + access_key + ":HmacSHA256:" + signature

Environment variables:
    ONSHAPE_ACCESS_KEY (or ONSHAPE_API_KEY)
    ONSHAPE_SECRET_KEY (or ONSHAPE_API_SECRET)
    ONSHAPE_BASE_URL (default https://cad.onshape.com)
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import random
import string
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urlparse

import requests


class OnshapeAuth(requests.auth.AuthBase):
    """Requests auth plugin that signs each request for Onshape's API."""

    def __init__(self, access_key: str, secret_key: str) -> None:
        self.access_key = access_key
        self.secret_key = secret_key

    def __call__(self, request: requests.PreparedRequest) -> requests.PreparedRequest:
        method = request.method.lower()
        date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        nonce = "".join(random.choice(string.digits + string.ascii_letters) for _ in range(25))
        # Only include a content type in the signature when the request actually
        # carries one. GET requests have no Content-Type header, so the signature
        # must use an empty string to match Onshape's server-side validation.
        content_type = request.headers.get("Content-Type", "")

        parsed = urlparse(request.url)
        path = parsed.path
        # Onshape signs the query string in the same order it appears on the wire.
        query_string = parsed.query

        string_to_sign = (
            f"{method}\n"
            f"{nonce}\n"
            f"{date}\n"
            f"{content_type}\n"
            f"{path}\n"
            f"{query_string}\n"
        ).lower().encode("utf-8")

        signature = base64.b64encode(
            hmac.new(
                self.secret_key.encode("utf-8"),
                string_to_sign,
                hashlib.sha256,
            ).digest()
        ).decode("utf-8")

        request.headers["Date"] = date
        request.headers["On-Nonce"] = nonce
        request.headers["Authorization"] = f"On {self.access_key}:HmacSHA256:{signature}"
        return request


class OnshapeClient:
    """Minimal Onshape client for RoboCAD needs: list/create documents and upload STEP."""

    def __init__(
        self,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        self.access_key = access_key or os.environ.get("ONSHAPE_ACCESS_KEY") or os.environ.get("ONSHAPE_API_KEY")
        self.secret_key = secret_key or os.environ.get("ONSHAPE_SECRET_KEY") or os.environ.get("ONSHAPE_API_SECRET")
        self.base_url = (base_url or os.environ.get("ONSHAPE_BASE_URL", "https://cad.onshape.com")).rstrip("/")

        if not self.access_key or not self.secret_key:
            raise RuntimeError(
                "Onshape access_key and secret_key are required "
                "(env: ONSHAPE_ACCESS_KEY / ONSHAPE_API_KEY and ONSHAPE_SECRET_KEY / ONSHAPE_API_SECRET)."
            )

        self.session = requests.Session()
        self.session.auth = OnshapeAuth(self.access_key, self.secret_key)
        self.session.headers.update({"Accept": "application/json"})

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.base_url}{path}"

    def get_user(self) -> dict[str, Any]:
        """Verify credentials by reading the current user's profile."""
        response = self.session.get(self._url("/api/users/session"))
        response.raise_for_status()
        if response.status_code == 204 or not response.text:
            return {"authenticated": True}
        return response.json()

    def list_documents(
        self,
        query: Optional[str] = None,
        owner_type: Optional[str] = None,
        sort_column: str = "createdAt",
        sort_order: str = "desc",
        offset: int = 0,
        limit: int = 20,
    ) -> dict[str, Any]:
        """List documents the API key can access."""
        params: dict[str, Any] = {
            "offset": offset,
            "limit": limit,
            "sortColumn": sort_column,
            "sortOrder": sort_order,
        }
        if query:
            params["q"] = query
        if owner_type:
            params["ownerType"] = owner_type

        response = self.session.get(self._url("/api/documents"), params=params)
        response.raise_for_status()
        return response.json()

    def create_document(self, name: str, description: str = "") -> dict[str, Any]:
        """Create a new Onshape document and return its metadata."""
        body = {
            "name": name,
            "description": description,
            # Free Onshape accounts can only create public documents.
            "isPublic": True,
            "ownerType": 0,
        }
        response = self.session.post(
            self._url("/api/documents"),
            headers={"Content-Type": "application/json"},
            data=json.dumps(body),
        )
        response.raise_for_status()
        return response.json()

    def upload_step(
        self,
        step_path: Path,
        document_id: str,
        workspace_id: str,
        element_name: str = "Imported part",
    ) -> dict[str, Any]:
        """Upload a STEP file into an existing Onshape workspace as a Part Studio.

        Uses Onshape's translation endpoint:
            POST /api/v6/translations/d/{did}/w/{wid}
        with multipart/form-data containing the STEP file and translation options.
        Polls briefly until the translation completes.
        """
        step_path = Path(step_path)
        if not step_path.exists():
            raise FileNotFoundError(f"STEP file not found: {step_path}")

        boundary = binascii.hexlify(os.urandom(16)).decode("ascii")
        content_type = f"multipart/form-data; boundary={boundary}"

        raw_file = step_path.read_bytes()
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{step_path.name}"\r\n'
            f"Content-Type: application/step\r\n\r\n"
        ).encode("utf-8") + raw_file + b"\r\n"
        body += f"--{boundary}--\r\n".encode("utf-8")

        translate_response = self.session.post(
            self._url(f"/api/v6/translations/d/{document_id}/w/{workspace_id}"),
            headers={"Content-Type": content_type},
            data=body,
        )
        translate_response.raise_for_status()
        translation = translate_response.json()

        # Poll briefly until translation completes.
        translation_id = translation.get("id")
        if translation_id:
            for _ in range(12):
                status_response = self.session.get(
                    self._url(f"/api/v6/translations/{translation_id}")
                )
                status_response.raise_for_status()
                status_data = status_response.json()
                request_state = status_data.get("requestState")
                if request_state == "DONE":
                    translation.update(status_data)
                    translation["completed"] = True
                    break
                if request_state in ("FAILED", "CANCELLED"):
                    translation.update(status_data)
                    translation["completed"] = False
                    break
                time.sleep(2.5)
            else:
                translation["completed"] = False
                translation["message"] = "Translation is still in progress; check Onshape later."

        result_element_ids = translation.get("resultElementIds") or []
        element_url = None
        if result_element_ids:
            element_url = (
                f"{self.base_url}/documents/{document_id}/w/{workspace_id}/e/{result_element_ids[0]}"
            )
        return {
            "document_id": document_id,
            "workspace_id": workspace_id,
            "translation": translation,
            "document_url": f"{self.base_url}/documents/{document_id}/w/{workspace_id}",
            "element_url": element_url,
        }

    def upload_step_to_new_document(
        self,
        step_path: Path,
        document_name: str,
        document_description: str = "",
    ) -> dict[str, Any]:
        """Convenience: create a new document and upload a STEP into it."""
        doc = self.create_document(document_name, document_description)
        document_id = doc["id"]
        workspace_id = doc.get("defaultWorkspace", {}).get("id")
        if not workspace_id:
            raise RuntimeError(f"Created document did not return a default workspace: {doc}")

        result = self.upload_step(step_path, document_id, workspace_id)
        result["document_name"] = document_name
        return result
