"""The current organization's locale context (DEMO-013).

Business code needs three facts constantly — what currency this tenant counts
in, what clock its days run on, what language to write to it in — and needs
them in places that have a session and a tenant and nothing else: a service
building an invoice, a consumer rendering a notification, a report choosing
where a day begins.

Rather than have each of those `session.get(Organization, tenant_id)` and
invent its own fallback, they ask here. One SELECT per tenant per request,
memoized in a contextvar, and one definition of what happens when the row is
missing.

**Why `core` may read the organization row.** `Organization` IS the tenant —
its id is the `tenant_id` every other table carries — so this is not one
module reaching into another's business tables. `core/tenant_lifecycle.py` and
`payment/service.py` already read it directly for the same reason. The import
is function-local to keep `core` importable before the model registry is
populated.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.errors import ValidationError
from platform_core.core.locales import CURRENCIES, LocaleSettings
from platform_core.core.tenancy import get_current_tenant
from platform_core.core.units import ConversionTerms

#: Per-request memo, keyed by tenant so a cross-tenant worker cannot be served
#: the previous tenant's currency.
_locale_cache: ContextVar[dict[uuid.UUID, LocaleSettings] | None] = ContextVar(
    "locale_cache", default=None
)

#: What a caller gets when there is no organization to ask: no tenant bound
#: (a platform-level request), or a tenant row that has gone. Deliberately
#: NOT Kenya — this is the platform's own neutral context, and anything that
#: would print money in it should be asking a tenant instead.
PLATFORM_DEFAULT = LocaleSettings(
    country_code="",
    currency_code="",
    timezone="UTC",
    default_language="en",
    supported_languages=("en",),
    # D-21: the platform's own context measures in kilograms only in the
    # sense that every row written before WO-70 did. Nothing that prices milk
    # should be reading this — it should be asking a tenant.
    quantity_unit="kg",
)

#: D-21 ruling 3, per tenant per request: what the organisation measures in,
#: what it trades in, and the declared factor between them.
_units_cache: ContextVar[dict[uuid.UUID, ConversionTerms] | None] = ContextVar(
    "units_cache", default=None
)


def _cache() -> dict[uuid.UUID, LocaleSettings]:
    cache = _locale_cache.get()
    if cache is None:
        cache = {}
        _locale_cache.set(cache)
    return cache


def reset_locale_cache() -> None:
    """Forget everything memoized. Called when settings change, and by tests."""
    _locale_cache.set({})
    _units_cache.set({})


async def require_tenant_unit(
    session: AsyncSession, claimed: str | None, tenant_id: uuid.UUID | None = None
) -> str:
    """The organisation's measured unit — and a refusal if the caller
    claims another (D-21 / WO-70).

    This replaces `if cmd.unit != "kg": raise`. The error is still an error;
    it is now relative to the tenant rather than to a constant, and a reading
    in the wrong unit is refused as firmly as before — `test_units.py` proves
    this did not become "accept anything". `None` means the caller did not
    say, and gets the organisation's unit.
    """
    from platform_core.core.errors import ConflictError
    from platform_core.core.units import UnknownUnitError, normalise_unit, unit_label

    terms = await tenant_units(session, tenant_id)
    if claimed is None or not str(claimed).strip():
        return terms.measured_unit
    try:
        unit = normalise_unit(claimed)
    except UnknownUnitError as exc:
        raise ConflictError(str(exc)) from exc
    if unit != terms.measured_unit:
        raise ConflictError(
            f"this organisation measures milk in {unit_label(terms.measured_unit)}; "
            f"a reading in {unit_label(unit)} was refused — the unit is set in "
            "organisation settings and applies to future collections"
        )
    return unit


async def tenant_units(
    session: AsyncSession, tenant_id: uuid.UUID | None = None
) -> ConversionTerms:
    """This organisation's intake unit and conversion terms (D-21 / WO-70),
    memoized for the request like the locale.

    Read from the organisation row — never from the country registry — for
    the same reason the currency is: an organisation's unit must not move
    when the world's does, and a change is an owner's act on future
    transactions, not a lookup that retro-labels history.
    """
    from platform_core.modules.organization.models import Organization

    resolved = tenant_id or get_current_tenant()
    if resolved is None:
        return ConversionTerms(measured_unit=PLATFORM_DEFAULT.quantity_unit)
    cache = _units_cache.get()
    if cache is None:
        cache = {}
        _units_cache.set(cache)
    hit = cache.get(resolved)
    if hit is not None:
        return hit
    org = await session.get(Organization, resolved)
    if org is None:
        return ConversionTerms(measured_unit=PLATFORM_DEFAULT.quantity_unit)
    terms = ConversionTerms(
        measured_unit=org.quantity_unit or PLATFORM_DEFAULT.quantity_unit,
        trade_unit=org.trade_unit,
        factor=org.conversion_factor,
        effective_from=org.conversion_effective_from,
    )
    cache[resolved] = terms
    return terms


def remember_locale(tenant_id: uuid.UUID, settings: LocaleSettings) -> None:
    _cache()[tenant_id] = settings


async def tenant_locale(
    session: AsyncSession, tenant_id: uuid.UUID | None = None
) -> LocaleSettings:
    """This organization's locale context, memoized for the request."""
    from platform_core.modules.organization.models import Organization

    resolved = tenant_id or get_current_tenant()
    if resolved is None:
        return PLATFORM_DEFAULT
    cache = _cache()
    hit = cache.get(resolved)
    if hit is not None:
        return hit

    org = await session.get(Organization, resolved)
    if org is None:
        return PLATFORM_DEFAULT
    settings = LocaleSettings(
        country_code=org.country_code or "",
        currency_code=org.currency_code or "",
        timezone=org.timezone or "UTC",
        default_language=org.default_locale or "en",
        supported_languages=tuple(org.supported_languages or ["en"]),
        quantity_unit=org.quantity_unit or PLATFORM_DEFAULT.quantity_unit,
    )
    cache[resolved] = settings
    return settings


async def tenant_currency(session: AsyncSession, tenant_id: uuid.UUID | None = None) -> str:
    """The ISO 4217 code new money records are denominated in.

    Raises rather than guessing. An organization whose currency is unset, or
    is `XXX` — ISO 4217's own code for "no currency involved", which the
    DEMO-013 migration assigns to a country the registry had never met — must
    not be able to write a priced row. The alternative is an invoice in a
    currency nobody chose, discovered by the customer.
    """
    settings = await tenant_locale(session, tenant_id)
    if settings.currency_code not in CURRENCIES:
        # A 422, not a bare ValueError: this is the CALLER's to fix (an
        # administrator sets the currency in organization settings), and a
        # ValueError would surface as a 500 telling them the platform broke.
        raise ValidationError(
            "this organization has no usable currency "
            f"({settings.currency_code or 'unset'!r}) — set it in organization settings "
            "before recording money"
        )
    return settings.currency_code


async def tenant_timezone(session: AsyncSession, tenant_id: uuid.UUID | None = None) -> str:
    """The IANA zone this organization's business days are measured in.

    Falls back to UTC rather than raising: a report drawn in the wrong zone is
    a wrong report, but a report that refuses to draw is a dairy manager who
    cannot work. Money is the opposite, which is why `tenant_currency` raises.
    """
    return (await tenant_locale(session, tenant_id)).timezone
