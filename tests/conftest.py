"""
Shared fixtures for the API test-suite.

Each test module gets an isolated SQLite database and Chroma directory via
monkeypatched paths, so running the suite never touches a developer's real
`data/users.db` or vector store.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest


@pytest.fixture
def temp_auth_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point app.auth (and therefore app.sessions) at a throwaway database."""
    import app.auth as auth_module

    db_path = tmp_path / "users.db"
    monkeypatch.setattr(auth_module, "_DB_PATH", db_path)

    auth_module.init_auth_db()
    from app.sessions import init_sessions_db

    init_sessions_db()
    return db_path


@pytest.fixture
def temp_vector_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    Give each test its own Chroma directory.

    Without this, collections persist across tests in one session. That matters
    more than usual here because chunk ids are derived from the filename (see
    the RAG audit, finding R1), so a second upload of the same filename is
    silently deduplicated and a later test sees `chunks_added: 0`.
    """
    import app.database as database
    import app.retriever as retriever
    from app.config import get_settings

    store = tmp_path / "chroma"
    monkeypatch.setattr(get_settings(), "chroma_path", str(store))

    # Drop the module-level singletons so the new path is actually used.
    monkeypatch.setattr(database, "_client", None)
    monkeypatch.setattr(database, "_collections", {})
    monkeypatch.setattr(retriever, "_bm25_cache", {})

    yield store

    monkeypatch.setattr(database, "_client", None)
    monkeypatch.setattr(database, "_collections", {})


@pytest.fixture
def client(temp_auth_db: Path, temp_vector_store: Path, monkeypatch: pytest.MonkeyPatch):
    """
    TestClient with a deterministic JWT secret and rate limiting disabled.

    Rate limiting is exercised explicitly in its own test; leaving it on here
    would make unrelated tests flaky as they share a limiter key.
    """
    monkeypatch.setenv("JWT_SECRET", "test-secret-" + "x" * 40)
    monkeypatch.setenv("ENVIRONMENT", "development")

    from fastapi.testclient import TestClient

    import api.main as api_main
    from api.settings import get_api_settings

    get_api_settings.cache_clear()
    api_main.app.state.limiter.enabled = False

    with TestClient(api_main.app, raise_server_exceptions=False) as c:
        yield c

    api_main.app.state.limiter.enabled = True
    get_api_settings.cache_clear()


VALID_PASSWORD = "Str0ng!Passw0rd"


def register_and_login(client, username: str = "alice") -> dict:
    """Create a user and return the auth header for it."""
    client.post(
        "/api/auth/register",
        json={"username": username, "display_name": username.title(), "password": VALID_PASSWORD},
    )
    res = client.post("/api/auth/login", json={"username": username, "password": VALID_PASSWORD})
    assert res.status_code == 200, res.text
    return res.json()


def auth_header(tokens: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.fixture
def make_pdf():
    """Factory producing a small but genuinely valid PDF."""

    def _make(text: str = "Regression test document. " * 20) -> bytes:
        import fitz

        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 100), text, fontsize=11)
        data = doc.tobytes()
        doc.close()
        return data

    return _make


@pytest.fixture
def pdf_upload(make_pdf):
    """Ready-to-post multipart payload for a valid PDF."""

    def _upload(name: str = "test.pdf", data: bytes | None = None):
        return {"file": (name, io.BytesIO(data if data is not None else make_pdf()), "application/pdf")}

    return _upload
