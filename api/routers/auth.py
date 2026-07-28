"""
Auth endpoints — thin wrappers over ``app.auth``.

The backend uses username-scoped isolation (the normalized username *is* the
``user_id`` that scopes every ChromaDB collection). We keep that model: on
successful login the client receives ``user_id`` and sends it back with each
request. No tokens are minted here, mirroring the existing Streamlit design.
"""

from fastapi import APIRouter

from app.auth import login_user, register_user

from api.schemas import (
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RegisterResponse,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse)
def register(body: RegisterRequest) -> RegisterResponse:
    """Create a new account (SQLite + salted SHA-256, handled by app.auth)."""
    ok, msg = register_user(body.username, body.display_name, body.password)
    return RegisterResponse(success=ok, message=msg)


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest) -> LoginResponse:
    """Verify credentials and return the display name + user_id scope key."""
    ok, msg, display_name = login_user(body.username, body.password)
    user_id = body.username.strip().lower() if ok else ""
    return LoginResponse(
        success=ok,
        message=msg,
        display_name=display_name,
        user_id=user_id,
    )
