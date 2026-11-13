"""The Labs toggle.

One flag decides whether the frozen multi-domain product is mounted: ``ROBOCAD_LABS=1`` turns it
on, anything else (including unset) leaves it off. See ``docs/DECISIONS.md`` for why the old
surface is frozen rather than deleted.

The backend exposes the resolved value on ``/health`` so a running server, the launcher and the
frontend build can be compared instead of each guessing.
"""
from __future__ import annotations

import os

LABS_ENV_VAR = "ROBOCAD_LABS"


def labs_enabled() -> bool:
    """Return True only for an explicit opt-in.

    Deliberately strict: ``"true"``, ``"yes"`` and ``"on"`` do not count, because a typo in an
    environment file should not silently re-enable a surface the README says is frozen.
    """
    return os.environ.get(LABS_ENV_VAR, "0").strip() == "1"


__all__ = ["LABS_ENV_VAR", "labs_enabled"]
