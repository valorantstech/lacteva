"""Codes are not the owner's job (WO-107 §3 · LACTEVA-SALES-005).

Products, routes and drivers all asked a shop owner to invent a CODE
("DAHI-500G", "DRV-1") before the thing they actually cared about. The code
is the platform's stable handle — yesterday's deliveries point at it, so it
never changes — but its SPELLING can be derived from the name: an upper-case
slug, letters, digits and hyphens, made unique with a numeric suffix. A
caller who cares can still supply one.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable

_KEEP = re.compile(r"[^A-Z0-9]+")


def slug_code(name: str, *, max_length: int = 24) -> str:
    """`Cow milk (full cream)` → `COW-MILK-FULL-CREAM`, cut to `max_length`
    without ending on a hyphen. An empty result is `ITEM`."""
    slug = _KEEP.sub("-", name.strip().upper()).strip("-")
    slug = slug[:max_length].rstrip("-")
    return slug or "ITEM"


async def unique_code(
    name: str,
    taken: Callable[[str], Awaitable[bool]],
    *,
    max_length: int = 24,
) -> str:
    """The name's slug, or the first `-2`, `-3`… variant `taken` does not
    already know. The suffix fits inside `max_length` too."""
    base = slug_code(name, max_length=max_length)
    if not await taken(base):
        return base
    for n in range(2, 1000):
        suffix = f"-{n}"
        candidate = base[: max_length - len(suffix)].rstrip("-") + suffix
        if not await taken(candidate):
            return candidate
    raise ValueError(f"could not find a free code for {name!r}")
