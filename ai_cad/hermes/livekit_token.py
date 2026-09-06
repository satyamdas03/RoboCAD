"""LiveKit token generation for HERMES voice sessions.

Generates short-lived tokens so the React frontend can join a LiveKit room
associated with a HERMES session. Tokens are signed with the LiveKit API
secret read from the environment.
"""
from __future__ import annotations

import os
from datetime import timedelta

from livekit.api import AccessToken, VideoGrants


ENV_MISSING_MESSAGE = (
    "LiveKit credentials are not configured. "
    "Set LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET in the .env file."
)


def _require_env() -> tuple[str, str, str]:
    """Return (url, api_key, api_secret) from environment or raise a clear error."""
    url = os.environ.get("LIVEKIT_URL", "")
    api_key = os.environ.get("LIVEKIT_API_KEY", "")
    api_secret = os.environ.get("LIVEKIT_API_SECRET", "")
    if not url or not api_key or not api_secret:
        raise RuntimeError(ENV_MISSING_MESSAGE)
    return url, api_key, api_secret


def livekit_url() -> str:
    """Return the configured LiveKit URL (e.g., wss://...)."""
    url, _, _ = _require_env()
    return url


def create_token(
    session_id: str,
    identity: str | None = None,
    ttl_minutes: int = 60,
) -> dict[str, str]:
    """Create a LiveKit access token for the HERMES voice room.

    Args:
        session_id: HERMES session id; used as the LiveKit room name.
        identity: Participant identity; defaults to ``hermes-user-{session_id[:8]}``.
        ttl_minutes: Token lifetime in minutes.

    Returns:
        Dict with ``url``, ``token``, ``room``, and ``identity``.
    """
    url, api_key, api_secret = _require_env()
    room = f"hermes-{session_id}"
    identity = identity or f"hermes-user-{session_id[:8]}"

    token = (
        AccessToken(api_key, api_secret)
        .with_identity(identity)
        .with_name("HERMES User")
        .with_grants(
            VideoGrants(
                room_join=True,
                room=room,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
                room_record=False,
            )
        )
        .with_ttl(timedelta(minutes=ttl_minutes))
        .to_jwt()
    )

    return {
        "url": url,
        "token": token,
        "room": room,
        "identity": identity,
    }


def create_agent_token(
    session_id: str,
    identity: str = "hermes-agent",
    ttl_minutes: int = 120,
) -> dict[str, str]:
    """Create a LiveKit access token for the HERMES voice agent worker.

    The agent needs to publish audio and data, and subscribe to the user's audio.
    """
    url, api_key, api_secret = _require_env()
    room = f"hermes-{session_id}"

    token = (
        AccessToken(api_key, api_secret)
        .with_identity(identity)
        .with_name("HERMES Agent")
        .with_grants(
            VideoGrants(
                room_join=True,
                room=room,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
                room_record=False,
                agent=True,
                hidden=True,
            )
        )
        .with_ttl(timedelta(minutes=ttl_minutes))
        .to_jwt()
    )

    return {
        "url": url,
        "token": token,
        "room": room,
        "identity": identity,
    }
