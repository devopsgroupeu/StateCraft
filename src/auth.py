"""Service-to-service authentication for the StateCraft API.

StateCraft creates and irreversibly deletes Terraform state buckets, so it must
only be callable by the OpenPrime backend. A shared service token (sent as the
``X-Service-Token`` header) is validated on every mutating endpoint.

Auth is only enforced when ``SERVICE_TOKEN`` is configured; when it is unset the
dependency is a no-op (backward-compatible until the secret is wired into the
backend and this service), which is logged loudly at startup. NetworkPolicy
remains a second, independent layer.
"""

import logging
import os
import secrets
from typing import Optional

from fastapi import Header, HTTPException

logger = logging.getLogger(__name__)

SERVICE_TOKEN = os.getenv("SERVICE_TOKEN")

if not SERVICE_TOKEN:
    logger.warning(
        "SERVICE_TOKEN not set — StateCraft request authentication is DISABLED (dev only)"
    )


def token_is_authorized(provided: Optional[str], expected: Optional[str]) -> bool:
    """Return True if the request is authorized.

    Authorization passes when no token is configured (auth disabled) or when the
    provided token matches the expected one in constant time.
    """
    if not expected:
        return True
    return bool(provided) and secrets.compare_digest(provided, expected)


async def require_service_token(x_service_token: Optional[str] = Header(default=None)):
    """FastAPI dependency that rejects requests lacking a valid service token."""
    if not token_is_authorized(x_service_token, SERVICE_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid or missing service token")
