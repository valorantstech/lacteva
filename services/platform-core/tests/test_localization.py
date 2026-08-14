"""Country, currency, timezone and language (DEMO-013).

The milestone's real requirement is not "support India". It is that **nothing
in the application branches on which country a tenant is in** — so these tests
are written to fail if Kenya is ever special-cased back in, and to pass for a
country nobody has thought about yet.

Three things are asserted repeatedly:

**A country proposes, an organization decides.** Onboarding asks one question
and fills in the rest; every part is still overridable, and an unknown country
is onboardable provided the caller says what the money and the clock are.

**A day belongs to the dairy's calendar.** Not to UTC's. This is the one that
would have gone unnoticed: Nairobi is UTC+3, so every date in the Kenyan demo
agrees with UTC, and the first Indian customer's morning round would have been
filed under the previous day.

**Money never guesses.** A missing currency is an error, never a default.
"""

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from platform_core.core.business_time import (
    business_date_of,
    business_today,
    day_bounds,
    month_bounds,
    range_bounds,
)
from platform_core.core.locales import (
    COUNTRIES,
    CURRENCIES,
    UnknownCountryError,
    base_language,
    resolve,
)
from tests.conftest import register_and_login

# --- the registry ------------------------------------------------------------


def test_india_proposes_rupees_kolkata_and_hindi():
    settings = resolve("IN")
    assert settings.currency_code == "INR"
    assert settings.timezone == "Asia/Kolkata"
    assert settings.default_language == "en-IN"
    assert "hi-IN" in settings.supported_languages


def test_kenya_proposes_shillings_and_nairobi():
    settings = resolve("KE")
    assert settings.currency_code == "KES"
    assert settings.timezone == "Africa/Nairobi"
    assert settings.default_language == "en-KE"


def test_a_lowercase_country_is_the_same_country():
    assert resolve("in").country_code == "IN"


def test_every_country_in_the_registry_is_internally_consistent():
    """The registry is data, and data rots quietly.

    Each country must name a currency the platform knows, a real IANA zone,
    and languages it has catalogs for — checked here rather than discovered
    when somebody onboards that country.
    """
    for code in COUNTRIES:
        settings = resolve(code)
        assert settings.currency_code in CURRENCIES, code
        assert ZoneInfo(settings.timezone), code
        assert settings.default_language in settings.supported_languages, code


def test_an_unknown_country_is_onboardable_but_never_guessed_at():
    """A platform that refused an unlisted country would be exactly the
    country-coupling this milestone removes. One that guessed would be worse:
    the dairy discovers it on the first bill."""
    with pytest.raises(UnknownCountryError):
        resolve("ZZ")

    settings = resolve("ZZ", currency_code="EUR", timezone="Europe/Berlin")
    assert settings.currency_code == "EUR"
    assert settings.timezone == "Europe/Berlin"


def test_a_country_proposes_and_an_organization_overrides():
    """India is one country and more than one dairy: a tenant may run its
    books in USD if that is what it agreed to."""
    settings = resolve("IN", currency_code="USD", timezone="Asia/Kolkata")
    assert settings.currency_code == "USD"
    assert settings.country_code == "IN"


def test_nonsense_is_refused_at_the_boundary():
    with pytest.raises(ValueError, match="currency"):
        resolve("IN", currency_code="ZZZ")
    with pytest.raises(ValueError, match="IANA"):
        resolve("IN", timezone="Mars/Olympus")
    with pytest.raises(ValueError, match="catalog"):
        resolve("IN", supported_languages=["kl-IN"])


def test_a_default_language_must_be_one_the_organization_enabled():
    with pytest.raises(ValueError, match="not among the supported"):
        resolve("IN", default_language="hi-IN", supported_languages=["en-IN"])


def test_a_regional_tag_reads_the_language_catalog():
    assert base_language("hi-IN") == "hi"
    assert base_language("en-KE") == "en"


# --- business time -----------------------------------------------------------


def test_a_morning_round_in_india_is_not_yesterday():
    """THE defect this milestone exists to prevent.

    05:00 in Bengaluru is 23:30 UTC the day before. Asking UTC what day it is
    files the round under yesterday, which moves it into the previous month's
    bill at the turn of a month.
    """
    dawn_in_india = datetime(2026, 8, 14, 5, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert dawn_in_india.astimezone(ZoneInfo("UTC")).date() == date(2026, 8, 13)
    assert business_date_of(dawn_in_india, "Asia/Kolkata") == date(2026, 8, 14)


def test_the_same_round_in_kenya_agrees_with_utc():
    """Which is why this was never visible in the Kenyan demo."""
    dawn_in_kenya = datetime(2026, 8, 14, 5, 0, tzinfo=ZoneInfo("Africa/Nairobi"))
    assert dawn_in_kenya.astimezone(ZoneInfo("UTC")).date() == date(2026, 8, 14)
    assert business_date_of(dawn_in_kenya, "Africa/Nairobi") == date(2026, 8, 14)


def test_today_differs_between_two_dairies_at_the_same_instant():
    late_utc = datetime(2026, 8, 13, 22, 0, tzinfo=ZoneInfo("UTC"))
    assert business_today("Asia/Kolkata", now=late_utc) == date(2026, 8, 14)
    assert business_today("Africa/Nairobi", now=late_utc) == date(2026, 8, 14)

    early_utc = datetime(2026, 8, 13, 20, 0, tzinfo=ZoneInfo("UTC"))
    assert business_today("Asia/Kolkata", now=early_utc) == date(2026, 8, 14)
    assert business_today("Africa/Nairobi", now=early_utc) == date(2026, 8, 13)


def test_a_day_is_half_open_so_midnight_belongs_to_exactly_one_day():
    start, end = day_bounds(date(2026, 8, 14), "Asia/Kolkata")
    assert start == datetime(2026, 8, 13, 18, 30, tzinfo=ZoneInfo("UTC"))
    assert end == datetime(2026, 8, 14, 18, 30, tzinfo=ZoneInfo("UTC"))
    # The next day starts exactly where this one ended: no gap, no overlap.
    next_start, _ = day_bounds(date(2026, 8, 15), "Asia/Kolkata")
    assert next_start == end


def test_a_range_covers_whole_local_days_at_both_ends():
    start, end = range_bounds(date(2026, 8, 1), date(2026, 8, 31), "Asia/Kolkata")
    assert start == datetime(2026, 7, 31, 18, 30, tzinfo=ZoneInfo("UTC"))
    assert end == datetime(2026, 8, 31, 18, 30, tzinfo=ZoneInfo("UTC"))


def test_a_day_is_not_always_twenty_four_hours():
    """Europe/London is in the registry and does observe DST. Bounds built by
    adding 24 hours would be an hour wrong twice a year."""
    start, end = day_bounds(date(2026, 3, 29), "Europe/London")  # clocks go forward
    assert (end - start).total_seconds() == 23 * 3600


def test_a_billing_month_is_the_dairys_month():
    first, last = month_bounds(date(2026, 8, 14), "Asia/Kolkata")
    assert (first, last) == (date(2026, 8, 1), date(2026, 8, 31))
    first, last = month_bounds(date(2026, 2, 5), "Asia/Kolkata")
    assert (first, last) == (date(2026, 2, 1), date(2026, 2, 28))


def test_a_broken_timezone_reports_in_utc_rather_than_failing():
    """A hand-edited row must not take a dairy manager's report down."""
    assert business_today(
        "Not/AZone", now=datetime(2026, 8, 13, 12, 0, tzinfo=ZoneInfo("UTC"))
    ) == date(2026, 8, 13)


# --- organizations -----------------------------------------------------------


async def _platform_admin(client, email="root-l10n@example.com"):
    _id, headers = await register_and_login(client, email, admin=True)
    return headers


async def _make_org(client, headers, **body):
    return await client.post("/v1/organizations", json=body, headers=headers)


async def test_onboarding_an_indian_dairy_asks_only_for_the_country(client):
    headers = await _platform_admin(client)
    r = await _make_org(
        client, headers, name="Lacteva India Demo", slug="india-demo", country_code="IN"
    )
    assert r.status_code == 201, r.text
    org = r.json()
    assert org["currency_code"] == "INR"
    assert org["timezone"] == "Asia/Kolkata"
    assert org["default_locale"] == "en-IN"
    assert org["supported_languages"] == ["en-IN", "hi-IN"]


async def test_onboarding_a_kenyan_dairy_gets_kenyan_settings(client):
    headers = await _platform_admin(client)
    r = await _make_org(client, headers, name="Kilima", slug="kilima-l10n", country_code="KE")
    assert r.status_code == 201, r.text
    org = r.json()
    assert org["currency_code"] == "KES"
    assert org["timezone"] == "Africa/Nairobi"


async def test_an_override_at_onboarding_is_honoured(client):
    headers = await _platform_admin(client)
    r = await _make_org(
        client,
        headers,
        name="Gulf Dairy",
        slug="gulf-dairy",
        country_code="AE",
        timezone="Asia/Dubai",
        supported_languages=["en-AE", "ar-AE"],
        default_locale="ar-AE",
    )
    assert r.status_code == 201, r.text
    assert r.json()["default_locale"] == "ar-AE"
    assert r.json()["currency_code"] == "AED"


async def test_the_country_list_is_served_rather_than_shipped(client):
    """So the portal and the app offer the same countries without either
    holding a copy that can drift."""
    _id, headers = await register_and_login(client, "reader-l10n@example.com")
    r = await client.get("/v1/locales/countries", headers=headers)
    assert r.status_code == 200, r.text
    countries = {c["code"]: c for c in r.json()["countries"]}
    assert countries["IN"]["currency_code"] == "INR"
    assert countries["IN"]["timezone"] == "Asia/Kolkata"
    assert countries["KE"]["currency_code"] == "KES"


async def test_the_country_list_needs_a_signed_in_caller(client):
    assert (await client.get("/v1/locales/countries")).status_code == 401


# --- settings, guarded by the permissions DEMO-008 already registered --------


async def _tenant_admin_for(client, *, country: str, slug: str, email: str):
    """A tenant administrator inside a freshly onboarded organization."""
    from tests.conftest import invite

    headers = await _platform_admin(client, f"root-{slug}@example.com")
    org = (
        await _make_org(client, headers, name=f"Dairy {slug}", slug=slug, country_code=country)
    ).json()
    _inv, token = await invite(
        client, {**headers, "X-Tenant-ID": org["id"]}, email=email, role_name="tenant-admin"
    )
    r = await client.post(
        "/v1/invitations/accept",
        json={"token": token, "password": "admin-password-1", "full_name": "Admin"},
    )
    assert r.status_code == 201, r.text
    pair = await client.post(
        "/v1/auth/token",
        json={"email": email, "password": "admin-password-1", "tenant_id": org["id"]},
    )
    assert pair.status_code == 200, pair.text
    return org, {"Authorization": f"Bearer {pair.json()['access_token']}"}


async def test_an_administrator_can_read_the_organizations_locale(client):
    _org, headers = await _tenant_admin_for(
        client, country="IN", slug="settings-in", email="admin@india.example"
    )
    r = await client.get("/v1/organizations/settings/locale", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["country_name"] == "India"
    assert body["currency_code"] == "INR"
    assert body["currency_symbol"] == "₹"
    assert body["timezone"] == "Asia/Kolkata"
    assert {lang["tag"] for lang in body["languages"]} == {"en-IN", "hi-IN"}


async def test_settings_changes_go_through_the_same_validation_as_onboarding(client):
    _org, headers = await _tenant_admin_for(
        client, country="IN", slug="settings-valid", email="admin2@india.example"
    )
    bad = await client.put(
        "/v1/organizations/settings/locale", json={"timezone": "Mars/Olympus"}, headers=headers
    )
    assert bad.status_code == 422, bad.text

    good = await client.put(
        "/v1/organizations/settings/locale",
        json={"supported_languages": ["en-IN"], "default_language": "en-IN"},
        headers=headers,
    )
    assert good.status_code == 200, good.text
    assert good.json()["supported_languages"] == ["en-IN"]


async def test_changing_locale_settings_needs_the_manage_grant(client):
    """Reading is `organization.read`; changing is `organization.manage`. No
    new authorization mechanism — DEMO-008's registry decides."""
    from tests.conftest import invite

    org, admin = await _tenant_admin_for(
        client, country="KE", slug="settings-rbac", email="admin@rbac.example"
    )
    _inv, token = await invite(
        client, admin, email="viewer@rbac.example", role_name="tenant-viewer"
    )
    r = await client.post(
        "/v1/invitations/accept",
        json={"token": token, "password": "viewer-password-1", "full_name": "Viewer"},
    )
    assert r.status_code == 201, r.text
    pair = await client.post(
        "/v1/auth/token",
        json={
            "email": "viewer@rbac.example",
            "password": "viewer-password-1",
            "tenant_id": org["id"],
        },
    )
    viewer = {"Authorization": f"Bearer {pair.json()['access_token']}"}

    assert (
        await client.get("/v1/organizations/settings/locale", headers=viewer)
    ).status_code == 200
    denied = await client.put(
        "/v1/organizations/settings/locale", json={"timezone": "UTC"}, headers=viewer
    )
    assert denied.status_code == 403


# --- a person's own language -------------------------------------------------


async def test_a_user_chooses_a_language_the_organization_enabled(client):
    _org, headers = await _tenant_admin_for(
        client, country="IN", slug="lang-in", email="hindi@india.example"
    )
    r = await client.put("/v1/auth/me/language", json={"language": "hi-IN"}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["locale"] == "hi-IN"

    me = (await client.get("/v1/auth/me", headers=headers)).json()
    assert me["user"]["locale"] == "hi-IN"


async def test_a_user_cannot_choose_a_language_the_organization_has_not_enabled(client):
    """Kenya has not switched Hindi on. A dairy that has not translated its
    process does not want one supervisor's screen in a language its manager
    cannot read."""
    _org, headers = await _tenant_admin_for(
        client, country="KE", slug="lang-ke", email="admin@kenya.example"
    )
    r = await client.put("/v1/auth/me/language", json={"language": "hi-IN"}, headers=headers)
    assert r.status_code == 403, r.text
    assert (await client.get("/v1/auth/me", headers=headers)).json()["user"]["locale"] != "hi-IN"


async def test_english_remains_the_default_until_somebody_chooses(client):
    _org, headers = await _tenant_admin_for(
        client, country="IN", slug="lang-default", email="default@india.example"
    )
    me = (await client.get("/v1/auth/me", headers=headers)).json()
    assert base_language(me["user"]["locale"]) == "en"


async def test_narrowing_the_organizations_languages_leaves_a_users_choice_alone(client):
    """An administrator turning Hindi off is not an administrator editing
    other people's preferences — which is not recoverable when it comes back
    on. Negotiation falls back at render time instead."""
    _org, headers = await _tenant_admin_for(
        client, country="IN", slug="lang-narrow", email="narrow@india.example"
    )
    await client.put("/v1/auth/me/language", json={"language": "hi-IN"}, headers=headers)
    await client.put(
        "/v1/organizations/settings/locale",
        json={"supported_languages": ["en-IN"], "default_language": "en-IN"},
        headers=headers,
    )
    me = (await client.get("/v1/auth/me", headers=headers)).json()
    assert me["user"]["locale"] == "hi-IN"
    assert me["organization"]["supported_languages"] == ["en-IN"]


# --- money -------------------------------------------------------------------


async def test_an_indian_customer_is_billed_in_rupees_without_anyone_saying_so(client):
    """The currency nobody typed. It used to be `"KES"`."""
    _org, headers = await _tenant_admin_for(
        client, country="IN", slug="money-in", email="money@india.example"
    )
    r = await client.post(
        "/v1/customers",
        json={
            "name": "Sharma Household",
            "customer_type": "household",
            "plan": {
                "product": "RAW-COW-MILK",
                "default_quantity": "1.000",
                "quantity_unit": "L",
                "unit_price": "56.0000",
            },
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["currency"] == "INR"


async def test_a_kenyan_customer_is_still_billed_in_shillings(client):
    _org, headers = await _tenant_admin_for(
        client, country="KE", slug="money-ke", email="money@kenya.example"
    )
    r = await client.post(
        "/v1/customers",
        json={"name": "Mama Njeri", "customer_type": "household"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["currency"] == "KES"


async def test_money_is_still_decimal_all_the_way_out(client):
    """DEMO-013 must not have quietly introduced a float on the way to
    rendering a currency. The API returns money as STRINGS, and a string is
    what a Decimal serializes to — a float would arrive as a JSON number."""
    import json

    _org, headers = await _tenant_admin_for(
        client, country="IN", slug="money-decimal", email="decimal@india.example"
    )
    customer = (
        await client.post(
            "/v1/customers",
            json={
                "name": "Decimal Household",
                "customer_type": "household",
                "plan": {
                    "product": "RAW-COW-MILK",
                    "default_quantity": "2.500",
                    "quantity_unit": "L",
                    "unit_price": "56.5000",
                },
            },
            headers=headers,
        )
    ).json()
    r = await client.post(
        "/v1/deliveries",
        json={
            "customer_id": customer["id"],
            "delivery_date": "2026-08-12",
            "slot": "morning",
            "status": "delivered",
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    raw = json.loads(r.text)
    assert isinstance(raw["amount"], str), "money came back as a JSON number"
    assert Decimal(raw["amount"]) == Decimal("141.25")  # 2.500 x 56.5000, exactly


# --- tenant isolation --------------------------------------------------------


async def test_an_indian_dairy_cannot_see_a_kenyan_one(client):
    _india, india_admin = await _tenant_admin_for(
        client, country="IN", slug="iso-in", email="iso@india.example"
    )
    _kenya, kenya_admin = await _tenant_admin_for(
        client, country="KE", slug="iso-ke", email="iso@kenya.example"
    )
    await client.post(
        "/v1/customers",
        json={"name": "Kenyan Household", "customer_type": "household"},
        headers=kenya_admin,
    )
    await client.post(
        "/v1/customers",
        json={"name": "Indian Household", "customer_type": "household"},
        headers=india_admin,
    )

    mine = (await client.get("/v1/customers?limit=50", headers=india_admin)).json()
    assert [c["name"] for c in mine["items"]] == ["Indian Household"]
    assert {c["currency"] for c in mine["items"]} == {"INR"}

    theirs = (await client.get("/v1/customers?limit=50", headers=kenya_admin)).json()
    assert [c["name"] for c in theirs["items"]] == ["Kenyan Household"]
    assert {c["currency"] for c in theirs["items"]} == {"KES"}


async def test_neither_dairy_can_read_the_others_locale_settings(client):
    _india, india_admin = await _tenant_admin_for(
        client, country="IN", slug="iso2-in", email="iso2@india.example"
    )
    _kenya, kenya_admin = await _tenant_admin_for(
        client, country="KE", slug="iso2-ke", email="iso2@kenya.example"
    )
    assert (await client.get("/v1/organizations/settings/locale", headers=india_admin)).json()[
        "currency_code"
    ] == "INR"
    assert (await client.get("/v1/organizations/settings/locale", headers=kenya_admin)).json()[
        "currency_code"
    ] == "KES"
    # Reading ANOTHER organization's row by id is stopped by RLS, which is a
    # PostgreSQL feature and does not exist on the SQLite this suite runs on.
    # Asserting it here would be a green that proves nothing — see
    # `test_rls_postgres.py::test_one_dairys_locale_is_invisible_to_another`.
