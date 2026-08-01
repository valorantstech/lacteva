"""Password hashing (argon2) and JWT issuing/verification."""

import uuid
from datetime import timedelta
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from platform_core.core.config import get_settings
from platform_core.core.db import utcnow

_hasher = PasswordHasher()

TokenType = Literal["access", "refresh"]


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, plain)
    except VerifyMismatchError:
        return False


def create_token(
    *,
    subject: uuid.UUID,
    token_type: TokenType,
    tenant_id: uuid.UUID | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    settings = get_settings()
    ttl = (
        settings.jwt_access_ttl_seconds
        if token_type == "access"
        else settings.jwt_refresh_ttl_seconds
    )
    now = utcnow()
    payload: dict[str, Any] = {
        "sub": str(subject),
        "typ": token_type,
        "iat": now,
        "exp": now + timedelta(seconds=ttl),
        "iss": settings.service_name,
        "jti": str(uuid.uuid4()),
    }
    if tenant_id is not None:
        payload["tenant_id"] = str(tenant_id)
    if extra_claims:
        payload |= extra_claims
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str, *, expected_type: TokenType) -> dict[str, Any]:
    """Decode and validate; raises jwt.InvalidTokenError on any failure."""
    settings = get_settings()
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        issuer=settings.service_name,
    )
    if payload.get("typ") != expected_type:
        raise jwt.InvalidTokenError("wrong token type")
    return payload


# TODO(M1): refresh-token rotation with server-side revocation (jti denylist in
# Redis) — currently refresh tokens are stateless and irrevocable before expiry.
