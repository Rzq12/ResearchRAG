"""
Auth endpoints — thin wrappers over ``app.auth`` and ``app.sessions``.

Flow:
    POST /api/auth/login    → access token (short) + refresh token (rotating)
    POST /api/auth/refresh  → rotates the refresh token, returns a new pair
    POST /api/auth/logout   → revokes the refresh token family
    GET  /api/auth/me       → who the bearer token belongs to

The user id used everywhere else in the API is derived from the access token
only (see ``api.security.current_user``); it is never accepted from a request
body.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.auth import login_user, register_user
from app.sessions import (
    consume_refresh_token,
    issue_refresh_token,
    revoke_refresh_token,
)

from api.rate_limit import limiter
from api.schemas import (
    LoginRequest,
    MeResponse,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
)
from api.security import current_user, issue_access_token
from api.settings import get_api_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _token_response(username: str, display_name: str, family_id: str | None = None) -> TokenResponse:
    """Mint an access + refresh pair for a verified user."""
    cfg = get_api_settings()
    access_token, expires_in = issue_access_token(username)
    refresh_token = issue_refresh_token(
        username, ttl_days=cfg.refresh_token_ttl_days, family_id=family_id
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        user_id=username,
        display_name=display_name,
    )


@router.post("/register", response_model=RegisterResponse)
@limiter.limit("5/minute")
def register(request: Request, body: RegisterRequest) -> RegisterResponse:
    """Create a new account. Password policy is enforced in ``app.security``."""
    ok, msg = register_user(body.username, body.display_name, body.password)
    if not ok:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg)
    return RegisterResponse(success=True, message=msg)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
def login(request: Request, body: LoginRequest) -> TokenResponse:
    """
    Verify credentials and issue a token pair.

    Rate limited to blunt credential stuffing. The response is deliberately
    identical for "unknown user" and "wrong password".
    """
    ok, msg, display_name = login_user(body.username, body.password)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=msg,
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _token_response(body.username.strip().lower(), display_name)


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("30/minute")
def refresh(request: Request, body: RefreshRequest) -> TokenResponse:
    """
    Rotate a refresh token.

    The presented token is burned. Re-presenting a spent token is treated as
    theft and revokes the whole family (handled in ``app.sessions``).
    """
    result = consume_refresh_token(body.refresh_token)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    username, family_id = result
    # Display name is not security-relevant; re-read it cheaply for the client.
    from app.auth import _conn  # local import keeps the module surface small

    with _conn() as db:
        row = db.execute(
            "SELECT display_name FROM users WHERE username = ?", (username,)
        ).fetchone()
    display_name = row[0] if row else username

    return _token_response(username, display_name, family_id=family_id)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(body: RefreshRequest) -> None:
    """Revoke the refresh token family. Idempotent by design."""
    revoke_refresh_token(body.refresh_token)


@router.get("/me", response_model=MeResponse)
def me(user_id: str = Depends(current_user)) -> MeResponse:
    """Identity of the bearer token — used by the client to validate a session."""
    from app.auth import _conn

    with _conn() as db:
        row = db.execute(
            "SELECT display_name FROM users WHERE username = ?", (user_id,)
        ).fetchone()
    return MeResponse(user_id=user_id, display_name=row[0] if row else user_id)
