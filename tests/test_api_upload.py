"""
Upload-validation and configuration-hardening regression tests.

The audit reproduced two crashes here: an empty file and a text file renamed to
.pdf both returned 500. Malformed input is a client error and must never take
a worker down or pollute error monitoring.
"""

from __future__ import annotations

import io

import pytest

from tests.conftest import auth_header, register_and_login


@pytest.mark.parametrize(
    "name,payload,label",
    [
        ("empty.pdf", b"", "empty file"),
        ("text.pdf", b"just plain text, definitely not a pdf", "renamed text file"),
        ("corrupt.pdf", b"%PDF-1.7\n<<GARBAGE", "valid header, corrupt body"),
        ("nul.pdf", b"\x00" * 512, "binary noise"),
    ],
)
def test_malformed_upload_returns_422_never_500(client, name, payload, label):
    """AUDIT H4: every malformed upload is a 422 with an actionable message."""
    tokens = register_and_login(client, "alice")
    res = client.post(
        "/api/documents/upload",
        headers=auth_header(tokens),
        files={"file": (name, io.BytesIO(payload), "application/pdf")},
    )
    assert res.status_code == 422, f"{label} returned {res.status_code}"
    assert res.json()["message"], "422 must explain what is wrong"


def test_truncated_pdf_is_rejected(client, make_pdf):
    """A structurally broken PDF passes the magic-byte check but must still 422."""
    tokens = register_and_login(client, "alice")
    valid = make_pdf()
    res = client.post(
        "/api/documents/upload",
        headers=auth_header(tokens),
        files={"file": ("trunc.pdf", io.BytesIO(valid[: len(valid) // 3]), "application/pdf")},
    )
    assert res.status_code == 422


def test_disallowed_content_type_is_rejected(client):
    tokens = register_and_login(client, "alice")
    res = client.post(
        "/api/documents/upload",
        headers=auth_header(tokens),
        files={"file": ("payload.exe", io.BytesIO(b"MZ\x90\x00"), "application/x-msdownload")},
    )
    assert res.status_code == 422


def test_oversized_upload_returns_413(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "max_upload_mb", 1)
    tokens = register_and_login(client, "alice")
    res = client.post(
        "/api/documents/upload",
        headers=auth_header(tokens),
        files={"file": ("big.pdf", io.BytesIO(b"%PDF-1.7" + b"\x00" * (2 * 1024 * 1024)), "application/pdf")},
    )
    assert res.status_code == 413


def test_valid_pdf_still_ingests(client, pdf_upload):
    """The guard must not break the happy path."""
    tokens = register_and_login(client, "alice")
    res = client.post("/api/documents/upload", headers=auth_header(tokens), files=pdf_upload())
    assert res.status_code == 200
    body = res.json()
    assert body["chunks_added"] > 0
    assert body["coverage"]["coverage_pct"] == 100.0


# ─── Configuration hardening (C2, H6) ────────────────────────────────────────

def test_production_requires_explicit_cors_allowlist(monkeypatch):
    """AUDIT C2: wildcard CORS must be impossible in production."""
    from api.settings import ApiSettings, ConfigurationError

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", "x" * 48)

    monkeypatch.setenv("CORS_ORIGINS", "")
    with pytest.raises(ConfigurationError):
        ApiSettings().validate_runtime()

    monkeypatch.setenv("CORS_ORIGINS", "*")
    with pytest.raises(ConfigurationError):
        ApiSettings().cors_origins_list

    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")
    assert ApiSettings().cors_origins_list == ["https://app.example.com"]


def test_production_requires_strong_jwt_secret(monkeypatch):
    from api.settings import ApiSettings, ConfigurationError

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")

    monkeypatch.setenv("JWT_SECRET", "")
    with pytest.raises(ConfigurationError):
        ApiSettings().validate_runtime()

    monkeypatch.setenv("JWT_SECRET", "tooshort")
    with pytest.raises(ConfigurationError):
        ApiSettings().validate_runtime()

    monkeypatch.setenv("JWT_SECRET", "x" * 48)
    ApiSettings().validate_runtime()  # must not raise


def test_docs_hidden_in_production(monkeypatch):
    from api.settings import ApiSettings

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", "x" * 48)
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")
    monkeypatch.setenv("EXPOSE_DOCS", "false")
    assert ApiSettings().docs_url is None
