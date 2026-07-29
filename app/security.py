"""
Password hashing and policy for ResearchRAG.

Replaces the legacy single-round SHA-256 scheme with PBKDF2-HMAC-SHA256 at the
iteration count OWASP currently recommends. Hashes are *scheme-tagged* so old
and new formats coexist and users migrate transparently on their next login:

    pbkdf2_sha256$600000$<salt_hex>$<hash_hex>     ← current
    <64 hex chars>                                 ← legacy (salt in its own column)

Pure standard library — no native build step, so the Docker image is unchanged.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets

# OWASP Password Storage Cheat Sheet (2023+) for PBKDF2-HMAC-SHA256.
_ALGORITHM = "sha256"
_SCHEME = "pbkdf2_sha256"
_ITERATIONS = 600_000
_SALT_BYTES = 16

# Password policy — applied to NEW passwords only (registration / change), so
# existing accounts are never locked out by a policy change.
MIN_PASSWORD_LENGTH = 12

_POLICY_RULES: tuple[tuple[str, str], ...] = (
    (r"[a-z]", "one lowercase letter"),
    (r"[A-Z]", "one uppercase letter"),
    (r"[0-9]", "one number"),
    (r"[^A-Za-z0-9]", "one special character"),
)


class PasswordPolicyError(ValueError):
    """Raised when a proposed password does not meet the policy."""


def validate_password(password: str) -> tuple[bool, str]:
    """
    Check a candidate password against the policy.

    Returns:
        (ok, message) — message is user-facing and lists what is missing.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        return False, f"Password minimal {MIN_PASSWORD_LENGTH} karakter."

    missing = [label for pattern, label in _POLICY_RULES if not re.search(pattern, password)]
    if missing:
        return False, "Password harus mengandung " + ", ".join(missing) + "."

    return True, "OK"


def hash_password(password: str) -> str:
    """Hash a password with PBKDF2-HMAC-SHA256. Returns a scheme-tagged string."""
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(_ALGORITHM, password.encode("utf-8"), salt, _ITERATIONS)
    return f"{_SCHEME}${_ITERATIONS}${salt.hex()}${digest.hex()}"


def _verify_pbkdf2(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt_hex, hash_hex = stored.split("$")
    except ValueError:
        return False
    if scheme != _SCHEME:
        return False
    try:
        digest = hashlib.pbkdf2_hmac(
            _ALGORITHM, password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), hash_hex)


def _verify_legacy_sha256(password: str, stored_hash: str, salt: str) -> bool:
    """The pre-migration scheme: sha256(salt + password), salt in its own column."""
    candidate = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return hmac.compare_digest(candidate, stored_hash)


def verify_password(password: str, stored_hash: str, legacy_salt: str = "") -> bool:
    """
    Verify a password against either the current or the legacy scheme.

    Args:
        password:    the plaintext candidate.
        stored_hash: value from the users.password_hash column.
        legacy_salt: value from the users.salt column (only used for legacy rows).

    Both branches use constant-time comparison.
    """
    if not stored_hash:
        return False
    if stored_hash.startswith(f"{_SCHEME}$"):
        return _verify_pbkdf2(password, stored_hash)
    return _verify_legacy_sha256(password, stored_hash, legacy_salt)


def needs_rehash(stored_hash: str) -> bool:
    """True when the stored hash uses an outdated scheme or iteration count."""
    if not stored_hash.startswith(f"{_SCHEME}$"):
        return True
    parts = stored_hash.split("$")
    if len(parts) != 4:
        return True
    try:
        return int(parts[1]) < _ITERATIONS
    except ValueError:
        return True
