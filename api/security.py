"""
JWT access tokens and the authenticated-user dependency.

This module is the **only** place a request's identity may come from. Routers
take `user_id: str = Depends(current_user)`; no endpoint accepts a caller-supplied
user id, so identity cannot be spoofed by editing a request body.

Kept in `api/` because it is a pure HTTP concern — `app/` stays reusable by the
Streamlit application, which has its own session handling.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.settings import get_api_settings

_ALGORITHM = "HS256"
_TOKEN_TYPE = "access"

# auto_error=False so we can raise our own 401 with a WWW-Authenticate header
# instead of FastAPI's bare 403 for a missing Authorization header.
_bearer = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def issue_access_token(username: str) -> tuple[str, int]:
    """
    Mint a short-lived access token.

    Returns:
        (token, expires_in_seconds) — the client uses the second value to
        refresh proactively rather than waiting for a 401.
    """
    cfg = get_api_settings()
    ttl = timedelta(minutes=cfg.access_token_ttl_minutes)
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "type": _TOKEN_TYPE,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    token = jwt.encode(payload, cfg.jwt_secret, algorithm=_ALGORITHM)
    return token, int(ttl.total_seconds())


def decode_access_token(token: str) -> str:
    """Verify an access token and return its subject. Raises 401 when invalid."""
    cfg = get_api_settings()
    try:
        payload = jwt.decode(token, cfg.jwt_secret, algorithms=[_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Access token expired") from None
    except jwt.PyJWTError:
        raise _unauthorized("Invalid access token") from None

    # Reject a refresh token presented where an access token is required.
    if payload.get("type") != _TOKEN_TYPE:
        raise _unauthorized("Wrong token type")

    subject = payload.get("sub")
    if not subject:
        raise _unauthorized("Malformed token")
    return str(subject)


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """
    FastAPI dependency resolving the authenticated user id.

    This is the single source of identity for every protected route.
    """
    if credentials is None or not credentials.credentials:
        raise _unauthorized("Not authenticated")
    return decode_access_token(credentials.credentials)
