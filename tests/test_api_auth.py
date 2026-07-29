"""
Authentication tests: password policy, hashing migration, token lifecycle.
"""

from __future__ import annotations

import hashlib
import secrets

import pytest

from tests.conftest import VALID_PASSWORD, auth_header, register_and_login


# ─── Password policy (H2) ────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "password,reason",
    [
        ("short1!A", "too short"),
        ("alllowercase123!", "no uppercase"),
        ("ALLUPPERCASE123!", "no lowercase"),
        ("NoDigitsHere!!!!", "no digit"),
        ("NoSymbolsHere123", "no special character"),
    ],
)
def test_register_rejects_weak_password(client, password, reason):
    res = client.post(
        "/api/auth/register",
        json={"username": "weakuser", "display_name": "W", "password": password},
    )
    assert res.status_code == 422, f"accepted a password with {reason}"


def test_register_accepts_strong_password(client):
    res = client.post(
        "/api/auth/register",
        json={"username": "stronguser", "display_name": "S", "password": VALID_PASSWORD},
    )
    assert res.status_code == 200
    assert res.json()["success"] is True


def test_passwords_are_never_stored_in_plaintext(client, temp_auth_db):
    register_and_login(client, "alice")
    from app.auth import _conn

    with _conn() as db:
        stored = db.execute(
            "SELECT password_hash FROM users WHERE username = 'alice'"
        ).fetchone()[0]

    assert VALID_PASSWORD not in stored
    assert stored.startswith("pbkdf2_sha256$"), "not using the PBKDF2 scheme"
    assert int(stored.split("$")[1]) >= 600_000, "iteration count below OWASP guidance"


# ─── Legacy migration (H1) ───────────────────────────────────────────────────

def test_legacy_sha256_user_logs_in_and_is_rehashed(client, temp_auth_db):
    """
    AUDIT H1: accounts created under salted single-round SHA-256 must keep
    working and be silently upgraded — a migration that locks users out is not
    a migration.
    """
    from app.auth import _conn, login_user
    from app.security import needs_rehash

    username, password = "legacy", "oldpassword"
    salt = secrets.token_hex(16)
    legacy_hash = hashlib.sha256((salt + password).encode()).hexdigest()

    with _conn() as db:
        db.execute(
            "INSERT INTO users (username, display_name, password_hash, salt) VALUES (?,?,?,?)",
            (username, "Legacy", legacy_hash, salt),
        )
        db.commit()

    def stored() -> str:
        with _conn() as db:
            return db.execute(
                "SELECT password_hash FROM users WHERE username = ?", (username,)
            ).fetchone()[0]

    assert needs_rehash(stored())

    ok, _, display = login_user(username, password)
    assert ok and display == "Legacy"

    upgraded = stored()
    assert upgraded.startswith("pbkdf2_sha256$")
    assert not needs_rehash(upgraded)

    # Still usable after the upgrade, and still rejects the wrong password.
    assert login_user(username, password)[0] is True
    assert login_user(username, "wrong")[0] is False


# ─── Token lifecycle ─────────────────────────────────────────────────────────

def test_login_returns_token_pair(client):
    tokens = register_and_login(client, "alice")
    assert tokens["token_type"] == "bearer"
    assert tokens["access_token"].count(".") == 2, "access token is not a JWT"
    assert tokens["refresh_token"]
    assert tokens["expires_in"] > 0


def test_login_with_wrong_password_is_401(client):
    register_and_login(client, "alice")
    res = client.post("/api/auth/login", json={"username": "alice", "password": "Wr0ng!Passw0rd"})
    assert res.status_code == 401


def test_access_token_grants_access(client):
    tokens = register_and_login(client, "alice")
    me = client.get("/api/auth/me", headers=auth_header(tokens))
    assert me.status_code == 200
    assert me.json()["user_id"] == "alice"


def test_expired_access_token_is_rejected(client, monkeypatch):
    from api.settings import get_api_settings

    tokens = register_and_login(client, "alice")

    # Re-issue with a negative TTL to simulate expiry deterministically.
    cfg = get_api_settings()
    monkeypatch.setattr(cfg, "access_token_ttl_minutes", -1)
    from api.security import issue_access_token

    expired, _ = issue_access_token("alice")
    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert res.status_code == 401
    assert "expired" in res.json()["message"].lower()

    # The original (valid) token still works — we only invalidated the new one.
    assert client.get("/api/auth/me", headers=auth_header(tokens)).status_code == 200


def test_refresh_rotates_and_detects_reuse(client):
    """
    Rotation + theft detection: a spent refresh token must not work twice, and
    presenting one is treated as compromise, killing the whole family.
    """
    tokens = register_and_login(client, "alice")
    original = tokens["refresh_token"]

    first = client.post("/api/auth/refresh", json={"refresh_token": original})
    assert first.status_code == 200
    rotated = first.json()["refresh_token"]
    assert rotated != original

    # Replay of the spent token → rejected.
    assert client.post("/api/auth/refresh", json={"refresh_token": original}).status_code == 401

    # …and the family is revoked, so the legitimate successor dies too.
    assert client.post("/api/auth/refresh", json={"refresh_token": rotated}).status_code == 401


def test_logout_revokes_refresh_token(client):
    tokens = register_and_login(client, "alice")
    assert client.post(
        "/api/auth/logout", json={"refresh_token": tokens["refresh_token"]}
    ).status_code == 204
    assert client.post(
        "/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    ).status_code == 401


def test_refresh_token_cannot_be_used_as_access_token(client):
    """Token type confusion: a refresh token must not authenticate a data route."""
    tokens = register_and_login(client, "alice")
    res = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"}
    )
    assert res.status_code == 401
