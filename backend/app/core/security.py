"""Password hashing, JWT issuance, and opaque device-token handling."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import settings

_hasher = PasswordHasher()

ALGORITHM = "HS256"
TokenType = Literal["access", "refresh"]


# ---------------------------------------------------------------- passwords


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        _hasher.verify(hashed, plain)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    return True


def needs_rehash(hashed: str) -> bool:
    try:
        return _hasher.check_needs_rehash(hashed)
    except InvalidHashError:
        return True


# --------------------------------------------------------------------- JWT


def create_token(
    *,
    subject: str,
    org_id: str,
    role: str,
    token_type: TokenType = "access",
    extra: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(UTC)
    if token_type == "access":
        expires = now + timedelta(minutes=settings.access_token_ttl_minutes)
    else:
        expires = now + timedelta(days=settings.refresh_token_ttl_days)

    payload: dict[str, Any] = {
        "sub": subject,
        "org": org_id,
        "role": role,
        "typ": token_type,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "jti": secrets.token_urlsafe(12),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


class TokenError(Exception):
    """Raised when a JWT is absent, malformed, expired, or of the wrong type."""


def decode_token(token: str, *, expect_type: TokenType | None = None) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("token expired") from exc
    except jwt.PyJWTError as exc:
        raise TokenError("token invalid") from exc

    if expect_type and payload.get("typ") != expect_type:
        raise TokenError(f"expected a {expect_type} token")
    return payload


# ------------------------------------------------------- device & pair codes

# Device tokens are opaque random strings, not JWTs: they are long-lived, so we
# need the ability to revoke one immediately, which means a database lookup.
# Only the hash is stored, so a database leak does not yield usable tokens.


def generate_device_token() -> tuple[str, str]:
    """Return `(plaintext_token, sha256_hash)`. Only the hash is persisted."""
    token = secrets.token_urlsafe(40)
    return token, hash_opaque_token(token)


def hash_opaque_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


_PAIRING_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no I/O/0/1


def generate_pairing_code(length: int = 8) -> tuple[str, str]:
    """Return `(display_code, hash)` for an agent to type into the handset."""
    raw = "".join(secrets.choice(_PAIRING_ALPHABET) for _ in range(length))
    display = f"{raw[: length // 2]}-{raw[length // 2 :]}"
    return display, hash_opaque_token(raw)


def normalize_pairing_code(code: str) -> str:
    return code.replace("-", "").replace(" ", "").strip().upper()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)
