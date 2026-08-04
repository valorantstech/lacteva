"""Password hashing (argon2) and JWT issuing/verification (SEC-001: RS256).

Tokens are signed with RS256 using a key drawn from the registry
(`core/keys.py`) and carry that key's `kid` in the header, so verification
resolves exactly one key and never guesses. Asymmetric signing means the
verification side needs no secret at all — which is what makes the JWKS
endpoint, and therefore rotation without downtime, possible.

HS256 remains reachable as a **documented rollback path only**
(`LACTEVA_JWT_ALGORITHM=HS256`). Production configuration refuses it without
an explicitly provisioned secret, and it is never used by default.

Clock skew is tolerated by an explicit leeway rather than by widening
expiry: two nodes disagreeing by a few seconds must not log a farmer out.
"""

import uuid
from datetime import timedelta
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from platform_core.core.config import get_settings
from platform_core.core.db import utcnow
from platform_core.core.keys import ALGORITHM, KeyRegistryError, get_key_registry

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
        "nbf": now,
        "exp": now + timedelta(seconds=ttl),
        "iss": settings.service_name,
        "jti": str(uuid.uuid4()),
    }
    if tenant_id is not None:
        payload["tenant_id"] = str(tenant_id)
    if extra_claims:
        payload |= extra_claims

    if settings.jwt_algorithm == "HS256":  # rollback path
        return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    key = get_key_registry().current(now)
    return jwt.encode(
        payload,
        key.private_pem,
        algorithm=ALGORITHM,
        headers={"kid": key.kid},
    )


def decode_token(token: str, *, expected_type: TokenType) -> dict[str, Any]:
    """Decode and validate. Raises `jwt.InvalidTokenError` on ANY failure —
    unknown kid, retired key, bad signature, wrong issuer, wrong type, or
    expiry — so callers have exactly one failure mode to handle."""
    settings = get_settings()
    common = {
        "algorithms": [settings.jwt_algorithm],
        "issuer": settings.service_name,
        "leeway": settings.jwt_leeway_seconds,
        "options": {"require": ["exp", "iat", "iss", "sub", "typ"]},
    }

    if settings.jwt_algorithm == "HS256":  # rollback path
        payload = jwt.decode(token, settings.jwt_secret, **common)
    else:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.InvalidTokenError:
            raise
        except Exception as exc:  # malformed token
            raise jwt.InvalidTokenError("malformed token header") from exc
        try:
            key = get_key_registry().verification_key(header.get("kid"))
        except KeyRegistryError as exc:
            # A key problem is a token problem from the caller's point of
            # view: never leak which key was asked for.
            raise jwt.InvalidTokenError(str(exc)) from exc
        payload = jwt.decode(token, key.public_pem, **common)

    if payload.get("typ") != expected_type:
        raise jwt.InvalidTokenError("wrong token type")
    return payload


def token_key_id(token: str) -> str | None:
    """The `kid` a token claims, without verifying it — for diagnostics and
    audit only. Never use this to make a trust decision."""
    try:
        return jwt.get_unverified_header(token).get("kid")
    except Exception:
        return None
