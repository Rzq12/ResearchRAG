"""
Lightweight authentication module using SQLite + salted SHA-256.
No external dependencies beyond the standard library.
"""

import hashlib
import secrets
import sqlite3
from pathlib import Path

_DB_PATH = Path("./data/users.db")


# ─── DB Setup ────────────────────────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(_DB_PATH), check_same_thread=False)


def init_auth_db() -> None:
    """Create the users table if it doesn't exist."""
    with _conn() as db:
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

def _hash(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


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

    if len(username) < 3:
        return False, "Username minimal 3 karakter."
    if not username.isalnum() and "_" not in username:
        return False, "Username hanya boleh huruf, angka, dan underscore."
    if len(password) < 6:
        return False, "Password minimal 6 karakter."

    salt = secrets.token_hex(16)
    pw_hash = _hash(password, salt)

    try:
        with _conn() as db:
            db.execute(
                "INSERT INTO users (username, display_name, password_hash, salt) VALUES (?, ?, ?, ?)",
                (username, display_name, pw_hash, salt),
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
    if _hash(password, salt) == pw_hash:
        return True, f"Selamat datang, {display_name}!", display_name
    return False, "Username atau password salah.", ""


def user_exists(username: str) -> bool:
    username = _normalize(username)
    with _conn() as db:
        row = db.execute(
            "SELECT 1 FROM users WHERE username = ?", (username,)
        ).fetchone()
    return row is not None
