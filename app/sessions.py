"""
Refresh-token persistence for ResearchRAG.

Lives in the same SQLite file as the user table so there is no new
infrastructure to deploy. Only the SHA-256 of each token is stored — a database
leak therefore does not yield usable tokens.

Rotation with reuse detection:
  - Every refresh issues a new token and revokes the one presented.
  - Presenting an already-revoked token means it leaked, so the entire family
    (that login session's chain) is revoked immediately.
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from app.auth import _conn  # single source of truth for the DB connection

_TOKEN_BYTES = 32


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fingerprint(token: str) -> str:
    """Tokens are high-entropy random, so a fast hash is appropriate here."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def init_sessions_db() -> None:
    """Create the refresh-token table. Safe to call on every startup."""
    with _conn() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS refresh_tokens (
                token_hash TEXT PRIMARY KEY,
                username   TEXT NOT NULL,
                family_id  TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # Indexed because every refresh and logout filters on these.
        db.execute("CREATE INDEX IF NOT EXISTS idx_rt_username ON refresh_tokens(username)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_rt_family ON refresh_tokens(family_id)")
        db.commit()


def issue_refresh_token(username: str, ttl_days: int, family_id: str | None = None) -> str:
    """
    Mint a refresh token for a user and persist its hash.

    A new login starts a new family; a rotation continues the existing one.
    Returns the raw token — it is never stored and cannot be recovered later.
    """
    token = secrets.token_urlsafe(_TOKEN_BYTES)
    expires = _now() + timedelta(days=ttl_days)
    with _conn() as db:
        db.execute(
            "INSERT INTO refresh_tokens (token_hash, username, family_id, expires_at) "
            "VALUES (?, ?, ?, ?)",
            (_fingerprint(token), username, family_id or secrets.token_hex(8), expires.isoformat()),
        )
        db.commit()
    return token


def _revoke_family(db: sqlite3.Connection, family_id: str) -> None:
    db.execute(
        "UPDATE refresh_tokens SET revoked_at = ? WHERE family_id = ? AND revoked_at IS NULL",
        (_now().isoformat(), family_id),
    )


def consume_refresh_token(token: str) -> tuple[str, str] | None:
    """
    Validate and rotate a refresh token.

    Returns:
        (username, family_id) when the token is valid — the caller then issues a
        replacement in the same family. None when the token is unknown, expired,
        or already used (in which case the whole family is revoked as a
        suspected theft).
    """
    fingerprint = _fingerprint(token)
    with _conn() as db:
        row = db.execute(
            "SELECT username, family_id, expires_at, revoked_at FROM refresh_tokens "
            "WHERE token_hash = ?",
            (fingerprint,),
        ).fetchone()

        if row is None:
            return None

        username, family_id, expires_at, revoked_at = row

        # Reuse of a spent token → assume compromise, kill the whole chain.
        if revoked_at is not None:
            _revoke_family(db, family_id)
            db.commit()
            return None

        if datetime.fromisoformat(expires_at) <= _now():
            db.execute(
                "UPDATE refresh_tokens SET revoked_at = ? WHERE token_hash = ?",
                (_now().isoformat(), fingerprint),
            )
            db.commit()
            return None

        # Valid: burn this token, the caller mints the next one in the family.
        db.execute(
            "UPDATE refresh_tokens SET revoked_at = ? WHERE token_hash = ?",
            (_now().isoformat(), fingerprint),
        )
        db.commit()
        return username, family_id


def revoke_refresh_token(token: str) -> None:
    """Revoke a single token and its family — used by logout."""
    fingerprint = _fingerprint(token)
    with _conn() as db:
        row = db.execute(
            "SELECT family_id FROM refresh_tokens WHERE token_hash = ?", (fingerprint,)
        ).fetchone()
        if row:
            _revoke_family(db, row[0])
            db.commit()


def revoke_all_for_user(username: str) -> int:
    """Revoke every active token for a user (password change, 'sign out everywhere')."""
    with _conn() as db:
        cur = db.execute(
            "UPDATE refresh_tokens SET revoked_at = ? WHERE username = ? AND revoked_at IS NULL",
            (_now().isoformat(), username.strip().lower()),
        )
        db.commit()
        return cur.rowcount


def purge_expired(retain_days: int = 7) -> int:
    """Housekeeping: drop rows long past expiry so the table stays small."""
    cutoff = (_now() - timedelta(days=retain_days)).isoformat()
    with _conn() as db:
        cur = db.execute("DELETE FROM refresh_tokens WHERE expires_at < ?", (cutoff,))
        db.commit()
        return cur.rowcount
