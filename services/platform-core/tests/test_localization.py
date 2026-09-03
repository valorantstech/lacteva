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

    # D-21 / WO-70: the intake unit follows the currency path exactly — an
    # unknown country must be TOLD it, by name, or the platform would be
    # guessing the measure a stranger's milk is priced in.
    with pytest.raises(UnknownCountryError, match="quantity_unit"):
        resolve("ZZ", currency_code="EUR", timezone="Europe/Berlin")
    settings = resolve(
        "ZZ", currency_code="EUR", timezone="Europe/Berlin", quantity_unit="litre"
    )
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
    """DEMO-020: this now asserts what its name has always claimed.

    It used to pass a timezone to `month_bounds`, which never read it — so
    the "dairy's month" part was decided entirely by the date the test handed
    in, and the call would have returned the same answer for any zone on
    earth. The timezone belongs one step earlier, in resolving WHICH date it
    is; `month_bounds` is pure calendar arithmetic from there.

    So the instant is the subject now: 20:00 UTC on 31 July is already
    1 August in Bengaluru and still 31 July in Nairobi, and the two dairies
    are therefore billing different months at the same moment.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    instant = datetime(2026, 7, 31, 20, 0, tzinfo=ZoneInfo("UTC"))
    assert month_bounds(business_today("Asia/Kolkata", now=instant)) == (
        date(2026, 8, 1),
        date(2026, 8, 31),
    )
    assert month_bounds(business_today("Africa/Nairobi", now=instant)) == (
        date(2026, 7, 1),
        date(2026, 7, 31),
    )

    # And the calendar arithmetic itself, including the short month.
    assert month_bounds(date(2026, 2, 5)) == (date(2026, 2, 1), date(2026, 2, 28))


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


# --- reporting and billing use the dairy's calendar --------------------------


async def test_a_daily_report_defaults_to_the_organizations_today(client):
    """DEMO-013 §9. The dates are optional precisely so a client can ask for
    "today" without owning a timezone database — and the platform answers with
    ITS today, echoing the dates it used."""
    from datetime import timedelta

    _org, headers = await _tenant_admin_for(
        client, country="IN", slug="report-in", email="report@india.example"
    )
    r = await client.get("/v1/deliveries/report", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    expected = business_today("Asia/Kolkata")
    assert body["date_from"] == str(expected)
    assert body["date_to"] == str(expected)

    # And a Kenyan dairy gets Kenya's today, from the same endpoint.
    _ke, kenya = await _tenant_admin_for(
        client, country="KE", slug="report-ke", email="report@kenya.example"
    )
    ke_body = (await client.get("/v1/deliveries/report", headers=kenya)).json()
    assert ke_body["date_from"] == str(business_today("Africa/Nairobi"))
    # The two answers differ for five and a half hours out of every
    # twenty-four; asserting they are equal would be asserting the bug.
    assert abs(
        date.fromisoformat(body["date_from"]) - date.fromisoformat(ke_body["date_from"])
    ) <= timedelta(days=1)


async def test_a_monthly_bill_covers_the_dairys_month(client):
    """A bill for August is August in the dairy's calendar. The period is what
    the caller asked for, and the platform stores it verbatim — this asserts
    the round trip, so a future change that shifted the period by a timezone
    would be visible."""
    _org, headers = await _tenant_admin_for(
        client, country="IN", slug="bill-in", email="bill@india.example"
    )
    customer = (
        await client.post(
            "/v1/customers",
            json={
                "name": "Monthly Household",
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
    ).json()
    for day in ("2026-07-01", "2026-07-15", "2026-07-31"):
        r = await client.post(
            "/v1/deliveries",
            json={
                "customer_id": customer["id"],
                "delivery_date": day,
                "slot": "morning",
                "status": "delivered",
            },
            headers=headers,
        )
        assert r.status_code == 201, r.text

    invoice = (
        await client.post(
            "/v1/invoices",
            json={
                "customer_id": customer["id"],
                "period_from": "2026-07-01",
                "period_to": "2026-07-31",
            },
            headers=headers,
        )
    ).json()
    assert invoice["period_from"] == "2026-07-01"
    assert invoice["period_to"] == "2026-07-31"
    assert invoice["currency"] == "INR"
    assert invoice["line_count"] == 3
    assert Decimal(invoice["subtotal"]) == Decimal("168.00")  # 3 x 1.000 x 56


async def test_a_notification_defaults_to_the_organizations_language(client):
    """DEMO-013 §14 — not the literal "en". An event carries no language of
    its own; whose language it is written in is a fact about the dairy."""
    import uuid as _uuid

    from platform_core.core import db, tenancy
    from platform_core.modules.notification.service import (
        NotificationRequest,
        NotificationService,
    )

    _org, headers = await _tenant_admin_for(
        client, country="IN", slug="notify-in", email="notify@india.example"
    )
    me = (await client.get("/v1/auth/me", headers=headers)).json()
    tenant_id = _uuid.UUID(me["tenant_id"])

    tenancy.set_current_tenant(tenant_id)
    try:
        async with db.get_session_factory()() as session:
            notification = await NotificationService(session).dispatch(
                NotificationRequest(
                    tenant_id=tenant_id,
                    event_id=_uuid.uuid4(),
                    event_name="sales.invoice-issued.v1",
                    template_key="invoice_issued",
                    channel="push",
                    recipient_ref=_uuid.uuid4(),  # nobody registered: no device
                    variables={"number": "INV-1", "period": "2026-08"},
                )
            )
            assert notification is not None
            assert notification.language == "en-IN"
            await session.commit()
    finally:
        tenancy.set_current_tenant(None)


async def test_the_whole_procurement_chain_uses_the_organizations_currency(client):
    """DEMO-013, found by looking at the Indian dashboard in a browser.

    The sales side reported rupees while procurement reported **KES** — the
    rate card, the settlement and the payment all REQUIRED a currency from the
    caller, and the demo seeder had been stating "KES" since there was only
    one country. Requiring it is the defect: every caller then has to know,
    and one of them will be wrong.
    """
    _org, headers = await _tenant_admin_for(
        client, country="IN", slug="procure-in", email="procure@india.example"
    )
    r = await client.post(
        "/v1/rate-cards",
        json={
            "code": "RC-IN-1",
            "name": "Season rates",
            "effective_from": "2026-01-01",
            "description": "no currency stated",
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["currency"] == "INR", "a rate card in the wrong money"

    # And a Kenyan dairy is unaffected by the same omission.
    _ke, kenya = await _tenant_admin_for(
        client, country="KE", slug="procure-ke", email="procure@kenya.example"
    )
    ke = await client.post(
        "/v1/rate-cards",
        json={"code": "RC-KE-1", "name": "Season rates", "effective_from": "2026-01-01"},
        headers=kenya,
    )
    assert ke.status_code == 201, ke.text
    assert ke.json()["currency"] == "KES"


async def test_a_new_member_starts_in_the_organizations_language(client):
    """DEMO-013 §8, surfaced by reconciling a real database.

    Every seeded user's locale was the bare `en` the registration command
    defaults to, which is not among an Indian dairy's supported tags — so the
    language chooser highlighted nothing until the person picked one, and a
    tenant that defaulted to Hindi would have started every new member in
    English.

    Nothing reads differently today (both are English), which is exactly why
    it needed a test rather than a glance.
    """
    _org, headers = await _tenant_admin_for(
        client, country="IN", slug="member-lang", email="member@india.example"
    )
    me = (await client.get("/v1/auth/me", headers=headers)).json()
    assert me["user"]["locale"] == "en-IN"
    assert me["user"]["locale"] in me["organization"]["supported_languages"]

    _ke, kenya = await _tenant_admin_for(
        client, country="KE", slug="member-lang-ke", email="member@kenya.example"
    )
    ke_me = (await client.get("/v1/auth/me", headers=kenya)).json()
    assert ke_me["user"]["locale"] == "en-KE"


async def test_an_organization_can_always_change_its_own_settings(client):
    """The failure `b8d41f7e2a95` repairs, stated as a rule.

    `update_locale_settings` validates through the same `resolve` onboarding
    uses, and `resolve` refuses a default language that is not among the
    supported ones. So an organization whose two fields disagree cannot change
    ANY of its settings — currency, timezone or languages — and the error
    names a value the administrator never set.

    The DEMO-013 migration created exactly that state on every pre-existing
    tenant: it back-filled `supported_languages` from the country and left
    `default_locale` at the bare `en` it already held. Found by reconciling
    production, not by testing.

    A settings update that changes only the timezone must therefore work
    without the caller restating their languages.
    """
    _org, headers = await _tenant_admin_for(
        client, country="IN", slug="settings-selfconsistent", email="self@india.example"
    )
    before = (await client.get("/v1/organizations/settings/locale", headers=headers)).json()
    assert before["default_language"] in before["supported_languages"], (
        "a freshly created organization already contradicts itself"
    )

    r = await client.put(
        "/v1/organizations/settings/locale",
        json={"timezone": "Asia/Kolkata"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["default_language"] in r.json()["supported_languages"]


# --- DEMO-014: the registries as a contract ----------------------------------


def test_every_country_the_milestone_names_is_onboardable():
    """DEMO-014 §1's list, asserted rather than assumed.

    A country missing from the registry is not a subtle failure — onboarding
    refuses it outright — but it is a silent one until somebody tries.
    """
    expected = {
        "IN": ("INR", "Asia/Kolkata"),
        "KE": ("KES", "Africa/Nairobi"),
        "SA": ("SAR", "Asia/Riyadh"),
        "AE": ("AED", "Asia/Dubai"),
        "QA": ("QAR", "Asia/Qatar"),
        "US": ("USD", None),  # six zones: the registry proposes one, and says so
        "GB": ("GBP", "Europe/London"),
    }
    for code, (currency, timezone) in expected.items():
        settings = resolve(code)
        assert settings.currency_code == currency, code
        if timezone:
            assert settings.timezone == timezone, code


def test_the_gulf_countries_lead_with_arabic():
    """A Saudi dairy's staff read Arabic; English is the second language there.

    The ORDER in the registry is the entire mechanism — no code anywhere asks
    which country this is.
    """
    for code in ("SA", "AE", "QA"):
        settings = resolve(code)
        assert base_language(settings.default_language) == "ar", code
        assert any(base_language(t) == "en" for t in settings.supported_languages), code


def test_india_and_kenya_still_lead_with_english():
    """The regression that adding Arabic markets could have caused: reordering
    somebody else's languages."""
    assert base_language(resolve("IN").default_language) == "en"
    assert base_language(resolve("KE").default_language) == "en"
    assert "hi-IN" in resolve("IN").supported_languages


def test_every_registered_language_has_a_backend_catalog():
    """Listing a language in the registry is a CLAIM that the platform speaks
    it. This is what makes the claim true, or the build red."""
    from platform_core.core.i18n import CATALOGS

    for country in COUNTRIES.values():
        for tag in country.languages:
            assert base_language(tag) in CATALOGS, f"{tag} has no catalog"


def test_every_registered_currency_states_its_own_scale():
    """`minor_units` is what `core/money.py` reads instead of assuming two."""
    for code, entry in CURRENCIES.items():
        assert entry.minor_units in (0, 2, 3), f"{code} has an implausible scale"


async def test_onboarding_a_gulf_dairy_needs_only_the_country(client):
    headers = await _platform_admin(client, "root-gulf@example.com")
    r = await _make_org(client, headers, name="Gulf Dairy", slug="gulf-demo", country_code="SA")
    assert r.status_code == 201, r.text
    org = r.json()
    assert org["currency_code"] == "SAR"
    assert org["timezone"] == "Asia/Riyadh"
    assert org["default_locale"] == "ar-SA"
    assert org["supported_languages"] == ["ar-SA", "en-SA"]


async def test_a_person_may_choose_the_clock_they_read(client):
    """DEMO-014 §4 — display only, and it cannot move a business date."""
    _org, headers = await _tenant_admin_for(
        client, country="IN", slug="tz-pref", email="tz@india.example"
    )
    r = await client.put(
        "/v1/auth/me/timezone", json={"timezone": "Europe/London"}, headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["timezone"] == "Europe/London"

    # The dairy's day is unchanged: the report still answers in Asia/Kolkata.
    report = (await client.get("/v1/deliveries/report", headers=headers)).json()
    assert report["date_from"] == str(business_today("Asia/Kolkata"))

    # And it can be given back.
    back = await client.put("/v1/auth/me/timezone", json={"timezone": None}, headers=headers)
    assert back.status_code == 200, back.text
    assert back.json()["timezone"] is None


async def test_a_timezone_that_is_not_a_timezone_is_refused(client):
    """Stored nonsense would fall back forever, and the person would never
    learn their setting had not taken."""
    _org, headers = await _tenant_admin_for(
        client, country="KE", slug="tz-bad", email="tzbad@kenya.example"
    )
    r = await client.put("/v1/auth/me/timezone", json={"timezone": "Mars/Olympus"}, headers=headers)
    assert r.status_code == 422, r.text
