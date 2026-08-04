"""Signing key registry (SEC-001).

The platform signs tokens with RS256 and publishes the public half at a JWKS
endpoint. That split is what makes rotation survivable: verification needs
only public material, so a key can be replaced without a coordinated restart
and without invalidating a single live session.

**The registry is the whole rotation story.** It holds every key the platform
will accept, each with a `kid`, an activation time, and an expiry:

- exactly one key is CURRENT (the newest activated, unexpired, unretired key)
  and signs new tokens;
- every other unexpired key still VERIFIES, so tokens minted before a
  rotation keep working until they expire naturally;
- a retired key verifies nothing — the emergency revocation path.

Rotation is therefore additive: publish a new key, let it become current,
and let the old one age out. Nothing is invalidated on the way through.

**Secrets never live in source.** Keys arrive as environment configuration
(`LACTEVA_JWT_KEYS`, a JSON array). In dev and test, where no operator is
present to provision one, an ephemeral in-memory keypair is generated at
first use — it dies with the process and is refused outright in prod.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

import structlog
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from platform_core.core.config import get_settings
from platform_core.core.db import utcnow

log = structlog.get_logger("security.keys")

ALGORITHM = "RS256"
_KEY_SIZE = 2048


class KeyRegistryError(Exception):
    """The registry cannot satisfy a signing or verification request."""


@dataclass(frozen=True)
class SigningKey:
    """One key in the registry. `private_pem` is absent for verify-only keys —
    a deployment may publish a predecessor's public half without ever holding
    its private material again."""

    kid: str
    public_pem: str
    private_pem: str | None = None
    activates_at: datetime | None = None
    expires_at: datetime | None = None
    retired: bool = False

    def can_sign(self, now: datetime) -> bool:
        return self.private_pem is not None and self.is_active(now)

    def is_active(self, now: datetime) -> bool:
        if self.retired:
            return False
        if self.activates_at is not None and now < self.activates_at:
            return False
        if self.expires_at is not None and now >= self.expires_at:
            return False
        return True

    def status(self, now: datetime) -> str:
        if self.retired:
            return "retired"
        if self.activates_at is not None and now < self.activates_at:
            return "pending"
        if self.expires_at is not None and now >= self.expires_at:
            return "expired"
        return "active"

    def to_jwk(self) -> dict:
        """Public JWK for the discovery endpoint. Private material never
        appears here — that is the point of publishing at all."""
        from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

        public = serialization.load_pem_public_key(self.public_pem.encode())
        if not isinstance(public, RSAPublicKey):  # pragma: no cover - config error
            raise KeyRegistryError(f"key {self.kid} is not an RSA public key")
        numbers = public.public_numbers()
        return {
            "kty": "RSA",
            "use": "sig",
            "alg": ALGORITHM,
            "kid": self.kid,
            "n": _b64u(numbers.n),
            "e": _b64u(numbers.e),
        }


def _b64u(value: int) -> str:
    import base64

    raw = value.to_bytes((value.bit_length() + 7) // 8 or 1, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def generate_keypair(kid: str | None = None) -> SigningKey:
    """Mint a fresh RSA keypair. Used by dev/test bootstrap and by the
    documented rotation procedure to produce material an operator installs."""
    private = rsa.generate_private_key(public_exponent=65537, key_size=_KEY_SIZE)
    private_pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = (
        private.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return SigningKey(
        kid=kid or f"dev-{uuid.uuid4().hex[:12]}",
        public_pem=public_pem,
        private_pem=private_pem,
        activates_at=utcnow() - timedelta(seconds=1),
    )


class KeyRegistry:
    """Every key the platform accepts, and the one it signs with."""

    def __init__(self, keys: list[SigningKey]):
        if not keys:
            raise KeyRegistryError("a key registry needs at least one key")
        self._keys = {key.kid: key for key in keys}

    @property
    def keys(self) -> list[SigningKey]:
        return list(self._keys.values())

    def current(self, now: datetime | None = None) -> SigningKey:
        """The signing key: the most recently activated key that can sign.

        Newest-wins means installing a key with a future `activates_at`
        schedules a rotation; when the clock passes it, new tokens carry the
        new kid and nothing else changes.
        """
        now = now or utcnow()
        candidates = [key for key in self._keys.values() if key.can_sign(now)]
        if not candidates:
            raise KeyRegistryError(
                "no signing key is active — check LACTEVA_JWT_KEYS activation and expiry windows"
            )
        return max(candidates, key=lambda k: k.activates_at or datetime.min.replace(tzinfo=None))

    def verification_key(self, kid: str | None, now: datetime | None = None) -> SigningKey:
        """Resolve the key a token names. An unknown, retired, or expired kid
        is a verification failure — never a silent fallback to another key."""
        now = now or utcnow()
        if kid is None:
            raise KeyRegistryError("token carries no key id")
        key = self._keys.get(kid)
        if key is None:
            raise KeyRegistryError(f"unknown key id {kid!r}")
        if not key.is_active(now):
            raise KeyRegistryError(f"key {kid!r} is {key.status(now)}")
        return key

    def jwks(self) -> dict:
        """Public discovery document. Expired and retired keys are withheld:
        a client should never be encouraged to trust them."""
        now = utcnow()
        return {"keys": [key.to_jwk() for key in self._keys.values() if key.is_active(now)]}

    def describe(self) -> list[dict]:
        """Operational view for the ops API — never includes private keys."""
        now = utcnow()
        return sorted(
            (
                {
                    "kid": key.kid,
                    "status": key.status(now),
                    "can_sign": key.can_sign(now),
                    "activates_at": key.activates_at.isoformat() if key.activates_at else None,
                    "expires_at": key.expires_at.isoformat() if key.expires_at else None,
                }
                for key in self._keys.values()
            ),
            key=lambda entry: entry["kid"],
        )


_registry: KeyRegistry | None = None


def _parse_configured_keys(raw: str) -> list[SigningKey]:
    try:
        entries = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise KeyRegistryError(f"LACTEVA_JWT_KEYS is not valid JSON: {exc}") from exc
    if not isinstance(entries, list):
        raise KeyRegistryError("LACTEVA_JWT_KEYS must be a JSON array of key objects")
    keys = []
    for entry in entries:
        if "kid" not in entry or "public_pem" not in entry:
            raise KeyRegistryError("each key needs at least 'kid' and 'public_pem'")
        keys.append(
            SigningKey(
                kid=entry["kid"],
                public_pem=_unescape(entry["public_pem"]),
                private_pem=_unescape(entry["private_pem"]) if entry.get("private_pem") else None,
                activates_at=_parse_time(entry.get("activates_at")),
                expires_at=_parse_time(entry.get("expires_at")),
                retired=bool(entry.get("retired", False)),
            )
        )
    return keys


def _unescape(pem: str) -> str:
    # Environment variables carry PEMs with literal \n more often than not.
    return pem.replace("\\n", "\n")


def _parse_time(value) -> datetime | None:
    if value in (None, ""):
        return None
    parsed = datetime.fromisoformat(str(value))
    from datetime import UTC

    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def get_key_registry() -> KeyRegistry:
    global _registry
    if _registry is None:
        settings = get_settings()
        if settings.jwt_keys:
            _registry = KeyRegistry(_parse_configured_keys(settings.jwt_keys))
            log.info("jwt_key_registry_loaded", keys=len(_registry.keys), source="configuration")
        elif settings.env == "prod":  # pragma: no cover - guarded by settings validation
            raise KeyRegistryError("LACTEVA_JWT_KEYS must be configured in prod")
        else:
            # Dev/test convenience: an ephemeral key that never touches disk,
            # never reaches git, and dies with the process.
            _registry = KeyRegistry([generate_keypair(kid="ephemeral-dev")])
            log.warning("jwt_key_registry_ephemeral", env=settings.env)
    return _registry


def reset_key_registry(registry: KeyRegistry | None = None) -> None:
    """Install a registry (rotation drills and tests) or clear the cache."""
    global _registry
    _registry = registry
