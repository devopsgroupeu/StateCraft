"""Service-to-service authentication for the StateCraft API.

StateCraft creates and irreversibly deletes Terraform state buckets, so it must
only be callable by the OpenPrime backend. A shared service token (sent as the
``X-Service-Token`` header) is validated on every mutating endpoint.

Auth fails closed: without ``SERVICE_TOKEN`` the API refuses to start and every
request is rejected. ``STATECRAFT_AUTH_DISABLED=true`` lifts that for local
development only, and has no effect once a token is set. NetworkPolicy remains a
second, independent layer.
"""

import logging
import os
import secrets
from typing import Optional

from fastapi import Header, HTTPException

logger = logging.getLogger(__name__)

SERVICE_TOKEN = os.getenv("SERVICE_TOKEN")


def _auth_disabled() -> bool:
    """True when auth was explicitly disabled for local development."""
    return os.getenv("STATECRAFT_AUTH_DISABLED", "").lower() == "true"


def token_is_authorized(
    provided: Optional[str], expected: Optional[str], auth_disabled: bool = False
) -> bool:
    """Return True if the request is authorized.

    With a token configured, the provided token must match it in constant time.
    With none configured, every request is rejected unless auth was explicitly
    disabled.
    """
    if not expected:
        return auth_disabled
    return bool(provided) and secrets.compare_digest(provided, expected)


def ensure_auth_configured():
    """Refuse to serve without a token unless auth was explicitly disabled.

    Runs at API startup, so a deployment that lost its token fails to start
    instead of quietly answering every request with 401.
    """
    if SERVICE_TOKEN:
        return
    if not _auth_disabled():
        raise RuntimeError(
            "SERVICE_TOKEN is not set. Set it, or set STATECRAFT_AUTH_DISABLED=true "
            "for local development."
        )
    logger.warning(
        "SERVICE_TOKEN not set and STATECRAFT_AUTH_DISABLED=true — StateCraft request "
        "authentication is DISABLED (local development only)"
    )


async def require_service_token(x_service_token: Optional[str] = Header(default=None)):
    """FastAPI dependency that rejects requests lacking a valid service token."""
    if not token_is_authorized(x_service_token, SERVICE_TOKEN, _auth_disabled()):
        raise HTTPException(status_code=401, detail="Invalid or missing service token")
