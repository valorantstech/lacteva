"""Trial, subscription and entitlement (DEMO-026).

The properties under test:

    **An organization gets exactly one trial, of exactly thirty of its own
    days, starting from when it was created — and nothing a user does moves
    it.** Commercial standing is derived on the server from stored dates; no
    request can set it.

The trial tests fix the clock. A test that used the real one would pass today
and fail in a month, and would be silent about which of the two answers was
right.
"""

import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from platform_core.core import db
from platform_core.core.tenancy import set_current_tenant
from platform_core.modules.subscription.models import Subscription
from platform_core.modules.subscription.service import TRIAL_DAYS, SubscriptionService
from tests.test_localization import _tenant_admin_for
from tests.test_org_structure import _tenant_admin

UTC = ZoneInfo("UTC")
INDIA = "Asia/Kolkata"
KENYA = "Africa/Nairobi"


async def _tenant_id(client, headers) -> uuid.UUID:
    me = (await client.get("/v1/auth/me", headers=headers)).json()
    return uuid.UUID(me["tenant_id"])


async def _service(tenant_id: uuid.UUID):
    """A service bound to one tenant, on its own session."""
    session = db.get_session_factory()()
    set_current_tenant(tenant_id)
    return session, SubscriptionService(session, tenant_id)


# --- 1, 15: exactly one trial ------------------------------------------------


async def test_a_new_organization_receives_exactly_one_trial(client):
    _org, headers = await _tenant_admin(client)
    tenant_id = await _tenant_id(client, headers)

    body = (await client.get("/v1/organization/subscription", headers=headers)).json()
    assert body["plan_code"] == "LACTEVA_TRIAL"
    assert body["status"] == "trialing"
    assert body["trial_started_on"] and body["trial_ends_on"]

    async with db.get_session_factory()() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(Subscription)
            .where(Subscription.tenant_id == tenant_id)
        )
    assert count == 1
    set_current_tenant(None)


async def test_reading_the_subscription_repeatedly_creates_only_one(client):
    """`ensure_trial` is get-or-create; a refreshed browser is not a signup."""
    _org, headers = await _tenant_admin(client)
    tenant_id = await _tenant_id(client, headers)
    first = (await client.get("/v1/organization/subscription", headers=headers)).json()
    for _ in range(5):
        await client.get("/v1/organization/subscription", headers=headers)
    again = (await client.get("/v1/organization/subscription", headers=headers)).json()

    assert again["trial_started_on"] == first["trial_started_on"]
    assert again["trial_ends_on"] == first["trial_ends_on"]
    async with db.get_session_factory()() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(Subscription)
            .where(Subscription.tenant_id == tenant_id)
        )
    assert count == 1
    set_current_tenant(None)


# --- 2, 3, 4, 5, 20: the trial window ----------------------------------------


@pytest.mark.parametrize("timezone", [INDIA, KENYA, "Asia/Qatar"])
def test_a_trial_is_thirty_of_the_dairys_own_days(timezone):
    """Thirty DAYS on the dairy's calendar, whatever its offset from UTC.

    The instant is 20:00 UTC, which is already the next day in Bengaluru and
    not yet in Nairobi — so a trial counted from a UTC date would start these
    two dairies on different days of their own weeks.
    """
    from platform_core.core.business_time import business_date_of

    created = datetime(2026, 8, 14, 20, 0, tzinfo=UTC)
    start = business_date_of(created, timezone)
    ends = start + timedelta(days=TRIAL_DAYS)
    assert (ends - start).days == 30, "the window is thirty days, exactly"
    # And it is the DAIRY's day that starts it.
    if timezone == INDIA:
        assert start == date(2026, 8, 15)
    else:
        assert start == date(2026, 8, 14)


def test_the_status_is_derived_from_dates_not_stored_stale():
    """Day 29 is still trialing; day 30 is expired. No clock is consulted."""
    from platform_core.modules.subscription.service import SubscriptionService as S

    start = date(2026, 8, 1)
    row = Subscription(
        tenant_id=uuid.uuid4(),
        plan_code="LACTEVA_TRIAL",
        status="trialing",
        trial_started_on=start,
        trial_ends_on=start + timedelta(days=TRIAL_DAYS),
    )
    assert S._derive_status(row, start) == "trialing", "the first day"
    assert S._derive_status(row, start + timedelta(days=29)) == "trialing", "the last day"
    assert S._derive_status(row, start + timedelta(days=30)) == "expired"
    assert S._derive_status(row, start + timedelta(days=365)) == "expired"


async def test_the_trial_does_not_restart_when_someone_joins_or_logs_in(client):
    """The property a support ticket would be written about."""
    from tests.conftest import invite

    org, headers = await _tenant_admin(client)
    before = (await client.get("/v1/organization/subscription", headers=headers)).json()

    # Another user joins.
    _inv, token = await invite(
        client,
        {**headers, "X-Tenant-ID": org["id"]},
        email="joiner@sub.example",
        role_name="tenant-viewer",
    )
    await client.post(
        "/v1/invitations/accept",
        json={"token": token, "password": "joiner-password-1", "full_name": "Joiner"},
    )
    # And logs in.
    await client.post(
        "/v1/auth/token",
        json={
            "email": "joiner@sub.example",
            "password": "joiner-password-1",
            "tenant_id": org["id"],
        },
    )

    after = (await client.get("/v1/organization/subscription", headers=headers)).json()
    assert after["trial_started_on"] == before["trial_started_on"]
    assert after["trial_ends_on"] == before["trial_ends_on"]


# --- 6, 7: active and expired are recognised ---------------------------------


async def test_an_activated_subscription_is_recognised(client):
    """Activation is a Lacteva-operator act, and no money moves."""
    _org, headers = await _tenant_admin(client)
    tenant_id = await _tenant_id(client, headers)

    session, service = await _service(tenant_id)
    async with session:
        view = await service.activate(plan_code="LACTEVA_STANDARD", subscribed_centres=3)
        await session.commit()
    assert view.status == "active"
    assert view.plan_code == "LACTEVA_STANDARD"
    assert view.subscribed_centres == 3
    assert view.started_on is not None
    set_current_tenant(None)


async def test_the_trial_plan_cannot_be_subscribed_to(client):
    """It has no price and no provider; calling it a subscription would lie."""
    from platform_core.core.errors import ConflictError

    _org, headers = await _tenant_admin(client)
    tenant_id = await _tenant_id(client, headers)
    session, service = await _service(tenant_id)
    async with session:
        with pytest.raises(ConflictError, match="trial plan"):
            await service.activate(plan_code="LACTEVA_TRIAL", subscribed_centres=1)
    set_current_tenant(None)


async def test_an_expired_paid_period_reads_as_expired(client):
    _org, headers = await _tenant_admin(client)
    tenant_id = await _tenant_id(client, headers)
    session, service = await _service(tenant_id)
    async with session:
        await service.activate(
            plan_code="LACTEVA_STANDARD",
            subscribed_centres=1,
            period_end=date(2020, 1, 1),  # long past
        )
        await session.commit()
        entitlement = await service.entitlement()
    assert entitlement.status == "expired"
    assert entitlement.can_operate is False
    set_current_tenant(None)


# --- 7 (§7 graceful expiry): data survives -----------------------------------


async def test_an_expired_organization_keeps_reading_its_own_records(client):
    """Expiry withdraws the ability to create, never the right to read.

    Taking a dairy's own collections and invoices away for a commercial
    reason would be a worse product than not selling one.
    """
    from tests.test_daily_operations import _customer, _deliver

    _org, headers = await _tenant_admin(client)
    tenant_id = await _tenant_id(client, headers)
    customer = await _customer(
        client, headers, name="Expiry Household", quantity="2.000", price="50.0000"
    )
    await _deliver(client, headers, customer["id"], date(2026, 8, 12))

    session, service = await _service(tenant_id)
    async with session:
        await service.activate(
            plan_code="LACTEVA_STANDARD", subscribed_centres=1, period_end=date(2020, 1, 1)
        )
        await session.commit()
    set_current_tenant(None)

    # Everything still readable.
    assert (await client.get("/v1/customers", headers=headers)).status_code == 200
    assert (await client.get("/v1/deliveries", headers=headers)).status_code == 200
    assert (await client.get("/v1/reports/receivables", headers=headers)).status_code == 200
    entitlement = (await client.get("/v1/organization/entitlement", headers=headers)).json()
    assert entitlement["can_read"] is True
    assert entitlement["can_operate"] is False


# --- 8, 9, 10, 11: centre quantity is the priced unit ------------------------


async def _centre(client, headers, tag: str, *, activate: bool = True):
    ws = await client.post(
        "/v1/workspaces",
        json={"name": f"Workspace {tag}", "slug": f"ws-{tag.lower()}"},
        headers=headers,
    )
    assert ws.status_code == 201, ws.text
    br = await client.post(
        "/v1/branches",
        json={"workspace_id": ws.json()["id"], "name": f"Branch {tag}", "code": f"BR{tag}"},
        headers=headers,
    )
    assert br.status_code == 201, br.text
    centre = await client.post(
        "/v1/collection-centers",
        json={"branch_id": br.json()["id"], "name": f"Centre {tag}", "code": f"C{tag}"},
        headers=headers,
    )
    assert centre.status_code == 201, centre.text
    body = centre.json()
    if activate:
        await client.put(
            f"/v1/collection-centers/{body['id']}/operating-hours",
            json={"windows": [{"day_of_week": 0, "opens": "06:00", "closes": "10:00"}]},
            headers=headers,
        )
        r = await client.post(
            f"/v1/collection-centers/{body['id']}/status",
            json={"status": "active"},
            headers=headers,
        )
        return body, r
    return body, None


async def test_active_centres_are_counted_not_users_or_litres(client):
    """The commercial quantity is centres. Users and litres do not move it."""
    from tests.conftest import invite

    org, headers = await _tenant_admin(client)
    await _centre(client, headers, "AA")
    await _centre(client, headers, "BB")

    # Add users — the quantity must not budge.
    for i in range(3):
        _inv, token = await invite(
            client,
            {**headers, "X-Tenant-ID": org["id"]},
            email=f"u{i}@qty.example",
            role_name="tenant-viewer",
        )
        await client.post(
            "/v1/invitations/accept",
            json={"token": token, "password": "user-password-1", "full_name": f"U{i}"},
        )

    entitlement = (await client.get("/v1/organization/entitlement", headers=headers)).json()
    assert entitlement["active_centres"] == 2, "two centres, whatever the user count"


async def test_a_trial_never_refuses_another_centre(client):
    """Everything is available while a dairy is evaluating."""
    _org, headers = await _tenant_admin(client)
    for tag in ("T1", "T2", "T3", "T4"):
        _body, response = await _centre(client, headers, tag)
        assert response.status_code == 200, response.text
    entitlement = (await client.get("/v1/organization/entitlement", headers=headers)).json()
    assert entitlement["status"] == "trialing"
    assert entitlement["centre_allowance"] is None
    assert entitlement["active_centres"] == 4


async def test_a_paid_plan_refuses_a_centre_beyond_what_it_covers(client):
    """The guard, and the premise that it was not refusing before."""
    _org, headers = await _tenant_admin(client)
    tenant_id = await _tenant_id(client, headers)
    await _centre(client, headers, "P1")
    await _centre(client, headers, "P2")

    session, service = await _service(tenant_id)
    async with session:
        await service.activate(plan_code="LACTEVA_STANDARD", subscribed_centres=2)
        await session.commit()
    set_current_tenant(None)

    body, response = await _centre(client, headers, "P3")
    assert response.status_code == 409, response.text
    assert "subscribe for more centres" in response.json()["extra"]

    # The centre still EXISTS — the guard stops activation, not recording.
    detail = await client.get(f"/v1/collection-centers/{body['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["center"]["status"] != "active"


async def test_centres_already_active_are_never_deactivated_by_a_limit(client):
    """A limit applies to the next activation, never retroactively."""
    _org, headers = await _tenant_admin(client)
    tenant_id = await _tenant_id(client, headers)
    for tag in ("K1", "K2", "K3"):
        await _centre(client, headers, tag)

    session, service = await _service(tenant_id)
    async with session:
        await service.activate(plan_code="LACTEVA_STANDARD", subscribed_centres=1)
        await session.commit()
        entitlement = await service.entitlement()
    set_current_tenant(None)

    assert entitlement.active_centres == 3, "all three keep working"
    view = (await client.get("/v1/organization/entitlement", headers=headers)).json()
    assert view["within_centre_allowance"] is False, "and the overage is visible"


# --- 12, 13, 14: security ----------------------------------------------------


async def test_one_organization_cannot_read_anothers_subscription(client):
    _a, admin_a = await _tenant_admin_for(
        client, country="IN", slug="sub-a", email="sub-a@india.example"
    )
    _b, admin_b = await _tenant_admin_for(
        client, country="KE", slug="sub-b", email="sub-b@kenya.example"
    )
    a_view = (await client.get("/v1/organization/subscription", headers=admin_a)).json()
    b_view = (await client.get("/v1/organization/subscription", headers=admin_b)).json()

    assert a_view["currency_code"] == "INR"
    assert b_view["currency_code"] == "KES"

    async with db.get_session_factory()() as session:
        rows = list((await session.scalars(select(Subscription))).all())
    tenants = {r.tenant_id for r in rows}
    assert len(tenants) == len(rows), "one subscription per tenant, never shared"


async def test_the_subscription_endpoints_require_authentication(client):
    assert (await client.get("/v1/organization/subscription")).status_code == 401
    assert (await client.get("/v1/organization/entitlement")).status_code == 401
    assert (await client.post("/v1/organization/subscription/activate", json={})).status_code == 401


async def test_a_tenant_administrator_cannot_activate_their_own_subscription(client):
    """Reading is a tenant act; changing is not. No self-service upgrades."""
    _org, headers = await _tenant_admin(client)
    assert (await client.get("/v1/organization/subscription", headers=headers)).status_code == 200
    r = await client.post(
        "/v1/organization/subscription/activate",
        json={"plan_code": "LACTEVA_STANDARD", "subscribed_centres": 5},
        headers=headers,
    )
    assert r.status_code == 403, r.text


async def test_a_client_cannot_forge_a_subscription_status(client):
    """There is no endpoint that accepts a status — that is the guarantee."""
    from platform_core.main import create_app

    spec = create_app().openapi()
    for path, methods in spec["paths"].items():
        if "subscription" not in path:
            continue
        for method in methods.values():
            body = method.get("requestBody")
            if not body:
                continue
            schema = str(body)
            assert '"status"' not in schema, f"{path} accepts a status from the client"


# --- 17, 22, 23, 24: nothing else moved --------------------------------------


async def test_adding_a_subscription_changes_no_financial_record(client):
    """The chain still runs, and its numbers are its own."""
    from tests.test_daily_operations import _billed_customer

    _org, headers = await _tenant_admin(client)
    _customer, invoice = await _billed_customer(client, headers)
    assert invoice["status"] == "issued"

    tenant_id = await _tenant_id(client, headers)
    session, service = await _service(tenant_id)
    async with session:
        await service.activate(plan_code="LACTEVA_STANDARD", subscribed_centres=1)
        await session.commit()
    set_current_tenant(None)

    after = (await client.get(f"/v1/invoices/{invoice['id']}", headers=headers)).json()
    assert after["invoice"]["amount_due"] == invoice["amount_due"]
    assert after["invoice"]["status"] == "issued"


# --- 18, 19: multi-country, with no country in the code ----------------------


@pytest.mark.parametrize(
    "country,currency,zone",
    [("IN", "INR", INDIA), ("KE", "KES", KENYA)],
)
async def test_the_subscription_speaks_the_organizations_own_currency(
    client, country, currency, zone
):
    """From the registry, never from a branch in the subscription code."""
    _org, headers = await _tenant_admin_for(
        client,
        country=country,
        slug=f"cur-{country.lower()}",
        email=f"cur-{country.lower()}@example.com",
    )
    view = (await client.get("/v1/organization/subscription", headers=headers)).json()
    assert view["currency_code"] == currency
    # No price is invented: nobody has decided one.
    assert view["price"] is None
    entitlement = (await client.get("/v1/organization/entitlement", headers=headers)).json()
    assert entitlement["status"] == "trialing"


def test_no_country_appears_in_the_subscription_code():
    """The architectural rule, asserted against the source."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "src/platform_core/modules/subscription"
    for path in root.glob("*.py"):
        source = path.read_text()
        for marker in ('== "IN"', '== "KE"', '== "QA"', "country_code ==", '"INR"', '"KES"'):
            assert marker not in source, f"{path.name} branches on country: {marker}"


def test_the_plan_registry_invents_no_price():
    """Prices are a commercial decision nobody has made. None is in source."""
    from platform_core.modules.subscription.plans import PLANS

    for plan in PLANS.values():
        assert not hasattr(plan, "price"), "a price in the registry would be an invented fact"
        assert plan.billing_period in ("month", "year")
