"""
Lightweight authentication module using SQLite.

Passwords are hashed with PBKDF2-HMAC-SHA256 (see app/security.py). Accounts
created under the previous salted single-round SHA-256 scheme keep working and
are re-hashed transparently the next time their owner logs in, so no user is
ever locked out by the migration.

No external dependencies beyond the standard library.
"""

import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.security import (
    hash_password,
    needs_rehash,
    validate_password,
    verify_password,
)

_DB_PATH = Path("./data/users.db")


# ─── DB Setup ────────────────────────────────────────────────────────────────

@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    """
    Open a connection and guarantee it is CLOSED.

    ``with sqlite3.connect(...) as db`` commits or rolls back the *transaction*
    but never closes the *connection* — a detail that leaked one file descriptor
    per login, refresh and logout. A worker under sustained token refresh
    eventually hit the fd ulimit and every subsequent connect raised
    "unable to open database file", taking auth down entirely.

    The inner ``with db`` preserves the commit/rollback behaviour every existing
    call site already relies on.
    """
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    try:
        with db:
            yield db
    finally:
        db.close()


def init_auth_db() -> None:
    """Create the users table if it doesn't exist."""
    with _conn() as db:
        # WAL lets readers proceed during a write, which removes the sporadic
        # "database is locked" seen when several requests hit auth at once.
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username     TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                salt         TEXT NOT NULL,
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.commit()


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _normalize(username: str) -> str:
    return username.strip().lower()


# ─── Public API ──────────────────────────────────────────────────────────────

def register_user(username: str, display_name: str, password: str) -> tuple[bool, str]:
    """
    Create a new user account.
    Returns (success: bool, message: str).
    """
    username = _normalize(username)
    display_name = display_name.strip() or username

    # `not isalnum() and "_" not in username` was an and/or inversion: any
    # string containing an underscore skipped the check entirely, so "ab_c!@#"
    # was accepted despite the message promising otherwise.
    if not re.fullmatch(r"[a-z0-9_]{3,32}", username):
        if len(username) < 3:
            return False, "Username minimal 3 karakter."
        return False, "Username hanya boleh huruf, angka, dan underscore (3-32 karakter)."

    # Policy applies to new passwords only — existing accounts are untouched.
    ok, message = validate_password(password)
    if not ok:
        return False, message

    pw_hash = hash_password(password)

    try:
        with _conn() as db:
            db.execute(
                "INSERT INTO users (username, display_name, password_hash, salt) VALUES (?, ?, ?, ?)",
                (username, display_name, pw_hash, ""),
            )
            db.commit()
        return True, "Akun berhasil dibuat! Silakan login."
    except sqlite3.IntegrityError:
        return False, "Username sudah digunakan, coba yang lain."


def login_user(username: str, password: str) -> tuple[bool, str, str]:
    """
    Verify credentials.
    Returns (success: bool, message: str, display_name: str).
    """
    username = _normalize(username)

    with _conn() as db:
        row = db.execute(
            "SELECT password_hash, salt, display_name FROM users WHERE username = ?",
            (username,),
        ).fetchone()

    if not row:
        return False, "Username atau password salah.", ""

    pw_hash, salt, display_name = row
    if not verify_password(password, pw_hash, salt or ""):
        return False, "Username atau password salah.", ""

    # Transparent migration: a legacy SHA-256 row is upgraded to PBKDF2 the
    # first time its owner successfully authenticates. Never blocks the login.
    if needs_rehash(pw_hash):
        try:
            with _conn() as db:
                db.execute(
                    "UPDATE users SET password_hash = ?, salt = '' WHERE username = ?",
                    (hash_password(password), username),
                )
                db.commit()
        except sqlite3.Error:
            pass  # upgrade is best-effort; the user is already authenticated

    return True, f"Selamat datang, {display_name}!", display_name


def change_password(username: str, current_password: str, new_password: str) -> tuple[bool, str]:
    """
    Change a user's password after verifying the current one.

    Returns (success, message). Callers should revoke the user's refresh tokens
    on success (see app.sessions.revoke_all_for_user).
    """
    username = _normalize(username)

    ok, _, _ = login_user(username, current_password)
    if not ok:
        return False, "Password saat ini salah."

    valid, message = validate_password(new_password)
    if not valid:
        return False, message

    with _conn() as db:
        db.execute(
            "UPDATE users SET password_hash = ?, salt = '' WHERE username = ?",
            (hash_password(new_password), username),
        )
        db.commit()
    return True, "Password berhasil diubah."


def user_exists(username: str) -> bool:
    username = _normalize(username)
    with _conn() as db:
        row = db.execute(
            "SELECT 1 FROM users WHERE username = ?", (username,)
        ).fetchone()
    return row is not None
