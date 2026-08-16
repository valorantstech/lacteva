"""Verifying that a webhook came from who it claims (DEMO-029).

**One mechanism, and this is it.** DEMO-027 introduced signature-verified
webhooks for payment providers, with the HMAC built inline inside the payment
provider's own adapter. DEMO-029 needs the same guarantee for delivery
receipts, and the wrong answer would have been a second implementation — two
places to get constant-time comparison right, two places to change when a
signature scheme moves, and two chances for one of them to be subtly weaker.

So the mechanism moved here and both callers use it. Nothing about the payment
path changed; it now imports what it used to inline.

What this module is NOT: a policy about which secret to use, which header a
particular vendor sends, or what an event means. Those belong to the adapter
for that vendor, because they differ per vendor. What is identical everywhere
is the arithmetic, and that is what lives here.

A real gateway that signs differently — a timestamped prefix, a versioned
scheme, base64 rather than hex — implements its own `parse_*` and uses
`compare` for the final step. The one thing no adapter should do is write its
own comparison.
"""

from __future__ import annotations

import hashlib
import hmac

#: The header Lacteva's own documented contract uses. A vendor that sends a
#: differently-named header is read by its own adapter; this is the default and
#: the one the test providers speak.
SIGNATURE_HEADER = "x-lacteva-signature"


def sign(secret: str, body: bytes) -> str:
    """The hex HMAC-SHA256 a sender computes over the RAW body.

    Raw, deliberately: a signature over a re-serialised payload verifies a
    string the sender never sent, and any difference in key order or whitespace
    silently changes the digest. Every caller must hand over the bytes it
    received.
    """
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def compare(supplied: str, expected: str) -> bool:
    """Constant-time comparison.

    A comparison that returns early leaks the length of the matching prefix,
    and a signature is then guessable one byte at a time by anyone who can
    measure the difference. This is the only correct way to check one.
    """
    return hmac.compare_digest(supplied or "", expected or "")


def verify(secret: str, body: bytes, supplied: str | None) -> bool:
    """`compare(supplied, sign(secret, body))`, for the common case.

    Returns False rather than raising, so a caller decides what a failure
    means — every webhook route in this platform answers the same way whether
    a signature was wrong, absent or unparseable, because an attacker probing
    the endpoint learns from the difference.
    """
    if not secret:
        # No secret configured means nothing can be verified, which must never
        # read as "verified". A deployment that selects a provider without a
        # secret is refused at startup; this is the belt to that brace.
        return False
    return compare(supplied or "", sign(secret, body))


def header_value(headers: dict[str, str], name: str = SIGNATURE_HEADER) -> str:
    """Read a signature header regardless of how the sender cased it.

    HTTP header names are case-insensitive and gateways differ. Callers that
    already lower-case their headers get the same answer.
    """
    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            return value
    return ""


__all__ = ["SIGNATURE_HEADER", "compare", "header_value", "sign", "verify"]
