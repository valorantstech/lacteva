"""WO-86 — the customer's own way in: a bound login, a bill link, a notice.

DEMO-012 built the READ side of the customer experience — a customer-scoped
principal sees its own rows and nobody else's — and left the way IN as a
known limitation: nothing but a hand in the database could bind an account
to a customer. `test_customer_scope._customer_login` did exactly that.

This file is the way in, and the properties it pins:

  * an invitation issued from the customer's page creates an account that is
    bound BEFORE its first request, and that account sees its own bill only;
  * the two wrong shapes are refused at the invitation — the customer role
    with no customer (the hole), and a customer bound to a staff role;
  * a customer-role account that is somehow unbound is refused outright,
    because its permissions are tenant-wide reads on every household's bill;
  * the dairy can see where a household's login stands, withdraw an
    invitation, and cannot invite twice over a live account;
  * a bill link opens the household's bills with no account, cannot reach
    another household's invoice, dies on rotation and on revocation with the
    same 404 a link that never existed gets, stays out of indexes and caches,
    and is rate-limited;
  * issuing a bill leaves an in-app notice the household reads back, and
    nobody else does;
  * the month-end pass that drafted bills nudges the administrators once;
  * the migration goes up, down and up, and the new table is under RLS.
"""

import sqlite3
import uuid
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from platform_core.core import rate_limit
from tests.clock import reference_date
from tests.test_customer_scope import _bill, _customer, _customer_login, _deliver
from tests.test_org_structure import _tenant_admin, invite
from tests.test_payments import _second_tenant
from tests.test_units import _alembic

TODAY = reference_date()


async def _household_with_bill(client, admin, name, email, org_id, rate="60.0000"):
    customer = await _customer(client, admin, name, rate=rate)
    await _deliver(client, admin, customer["id"])
    bill = await _bill(client, admin, customer["id"])
    login = await _customer_login(client, admin, org_id, customer["id"], email)
    return customer, bill, login


# --- the login ----------------------------------------------------------------


async def test_an_invited_customer_is_bound_before_its_first_request(client):
    org, admin = await _tenant_admin(client)
    mine, my_bill, me = await _household_with_bill(
        client, admin, "Bound Household", "bound@household.example", org["id"]
    )
    _theirs, their_bill, _ = await _household_with_bill(
        client, admin, "Other Household", "other@household.example", org["id"], rate="70.0000"
    )

    who = (await client.get("/v1/auth/me", headers=me)).json()
    assert who["customer_id"] == mine["id"]
    assert [r["name"] for r in who["roles"]] == ["CUSTOMER_PORTAL"]

    page = (await client.get("/v1/invoices", headers=me)).json()
    assert [i["id"] for i in page["items"]] == [my_bill["id"]]
    assert (await client.get(f"/v1/invoices/{their_bill['id']}", headers=me)).status_code == 404

    status = (await client.get(f"/v1/customers/{mine['id']}/login", headers=admin)).json()
    assert status["state"] == "active"
    assert status["email"] == "bound@household.example"
    assert status["user_id"] == who["user"]["id"]


async def test_the_staff_route_refuses_the_customer_role_and_the_customer_route_refuses_staff(
    client,
):
    """Both wrong shapes, refused where the shape is decided."""
    org, admin = await _tenant_admin(client)
    headers = {**admin, "X-Tenant-ID": org["id"]}
    r = await client.post(
        "/v1/invitations",
        json={"email": "loose@household.example", "role_name": "CUSTOMER_PORTAL"},
        headers=headers,
    )
    assert r.status_code == 422, r.text
    assert "customer" in r.text

    # The other way round has no route at all — the customer route hardcodes
    # the role — so it is proven at the service, which is where the rule is.
    from platform_core.core.errors import ValidationError
    from platform_core.core.rls import platform_factory
    from platform_core.core.tenancy import set_current_tenant
    from platform_core.infrastructure.events import get_event_bus
    from platform_core.modules.audit.service import AuditService
    from platform_core.modules.event_relay.service import OutboxEventBus
    from platform_core.modules.organization.service import InvitationService

    async with platform_factory("test: a staff role bound to a customer")() as session:
        set_current_tenant(uuid.UUID(org["id"]))
        service = InvitationService(
            session, OutboxEventBus(session, get_event_bus()), AuditService(session)
        )
        with pytest.raises(ValidationError):
            await service.invite(
                email="manager@household.example",
                role_name="tenant-viewer",
                actor_id=uuid.uuid4(),
                customer_id=uuid.uuid4(),
            )
        set_current_tenant(None)


async def test_an_unbound_customer_role_account_is_refused(client):
    """The DEMO-012 hole, closed from the other side: a CUSTOMER_PORTAL account
    whose scope is missing holds tenant-wide `sales.invoice.read`. It gets
    nothing — not the bills, not even its own session."""
    org, admin = await _tenant_admin(client)
    _mine, _, me = await _household_with_bill(
        client, admin, "Unbound Household", "unbound@household.example", org["id"]
    )
    assert (await client.get("/v1/invoices", headers=me)).status_code == 200

    from platform_core.core.rls import platform_factory
    from platform_core.modules.identity.models import User

    who = (await client.get("/v1/auth/me", headers=me)).json()
    async with platform_factory("test: unbind a customer login by hand")() as session:
        user = await session.get(User, uuid.UUID(who["user"]["id"]))
        user.customer_id = None
        await session.commit()

    assert (await client.get("/v1/invoices", headers=me)).status_code == 403
    assert (await client.get("/v1/auth/me", headers=me)).status_code == 403
    # Staff are untouched by the guard.
    assert (await client.get("/v1/invoices", headers=admin)).status_code == 200


async def test_the_login_lifecycle_as_the_dairy_sees_it(client):
    org, admin = await _tenant_admin(client)
    customer = await _customer(client, admin, "Slow Household")
    url = f"/v1/customers/{customer['id']}"

    assert (await client.get(f"{url}/login", headers=admin)).json()["state"] == "none"
    # Nothing to withdraw yet.
    assert (await client.delete(f"{url}/invitation", headers=admin)).status_code == 404

    first, first_token = await invite(
        client,
        {**admin, "X-Tenant-ID": org["id"]},
        email="slow@household.example",
        role_name="CUSTOMER_PORTAL",
        customer_id=customer["id"],
    )
    assert first["state"] == "invited"
    assert first["email"] == "slow@household.example"
    assert first["invitation_id"]

    # Inviting again withdraws the first: the old code is dead.
    second, second_token = await invite(
        client,
        {**admin, "X-Tenant-ID": org["id"]},
        email="slow2@household.example",
        role_name="CUSTOMER_PORTAL",
        customer_id=customer["id"],
    )
    assert second["invitation_id"] != first["invitation_id"]
    r = await client.post(
        "/v1/invitations/accept",
        json={"token": first_token, "password": "household-password-1", "full_name": "H"},
    )
    assert r.status_code in (400, 401, 404, 410, 422), r.text

    # Withdraw the second by hand.
    r = await client.delete(f"{url}/invitation", headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "none"
    r = await client.post(
        "/v1/invitations/accept",
        json={"token": second_token, "password": "household-password-1", "full_name": "H"},
    )
    assert r.status_code in (400, 401, 404, 410, 422), r.text

    # A third one goes through, and then the customer HAS a login: no more.
    _third, third_token = await invite(
        client,
        {**admin, "X-Tenant-ID": org["id"]},
        email="slow3@household.example",
        role_name="CUSTOMER_PORTAL",
        customer_id=customer["id"],
    )
    r = await client.post(
        "/v1/invitations/accept",
        json={"token": third_token, "password": "household-password-1", "full_name": "H"},
    )
    assert r.status_code == 201, r.text
    assert (await client.get(f"{url}/login", headers=admin)).json()["state"] == "active"
    r = await client.post(f"{url}/invite", json={"email": "slow4@household.example"}, headers=admin)
    assert r.status_code == 409, r.text

    # Another tenant's customer id is a 404 on every one of these.
    other_admin = await _second_tenant(client)
    for method, path in (("get", f"{url}/login"), ("get", f"{url}/bill-link")):
        r = await getattr(client, method)(path, headers=other_admin)
        assert r.status_code == 404, (path, r.text)
    r = await client.post(f"{url}/invite", json={"email": "x@y.example"}, headers=other_admin)
    assert r.status_code == 404
    r = await client.post(f"{url}/bill-link", headers=other_admin)
    assert r.status_code == 404


# --- the bill link --------------------------------------------------------------


async def _mint(client, admin, customer_id) -> str:
    r = await client.post(f"/v1/customers/{customer_id}/bill-link", headers=admin)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["active"] is True
    assert body["token"]
    return body["token"]


async def test_a_bill_link_opens_the_household_s_bills_and_nothing_else(client):
    org, admin = await _tenant_admin(client)
    mine, my_bill, _ = await _household_with_bill(
        client, admin, "Linked Household", "linked@household.example", org["id"]
    )
    theirs, their_bill, _ = await _household_with_bill(
        client, admin, "Unlinked Household", "unlinked@household.example", org["id"]
    )
    # A payment with a receipt, so the page has one to show against the bill.
    r = await client.post(
        "/v1/customer-payments",
        json={
            "customer_id": mine["id"],
            "amount": "100.00",
            "method": "CASH",
            "invoice_ids": [my_bill["id"]],
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text
    # Receipts are a projection of the payment event: run the consumers.
    from platform_core.core.rls import platform_factory
    from platform_core.modules.event_relay.consumers import ConsumerRunner

    await ConsumerRunner(platform_factory("test: generate receipts")).run_once()

    token = await _mint(client, admin, mine["id"])
    # The status view never carries the token.
    status = (await client.get(f"/v1/customers/{mine['id']}/bill-link", headers=admin)).json()
    assert status["active"] is True and "token" not in status
    assert status["last_seen_at"] is None

    r = await client.get(f"/v1/public/bill/{token}")
    assert r.status_code == 200, r.text
    assert r.headers["x-robots-tag"] == "noindex, nofollow"
    assert r.headers["cache-control"] == "no-store"
    page = r.json()
    assert page["customer"]["name"] == "Linked Household"
    assert page["organization"]
    assert [i["id"] for i in page["invoices"]] == [my_bill["id"]]
    assert their_bill["id"] not in r.text
    assert theirs["id"] not in r.text
    assert page["statement"]["customer_id"] == mine["id"]
    assert page["balance"]["customer_id"] == mine["id"]
    receipts = page["invoices"][0]["receipts"]
    assert len(receipts) == 1 and receipts[0]["receipt_number"]
    # WO-86: the statement's payment row names its receipt.
    payments = [e for e in page["statement"]["entries"] if e["kind"] == "payment"]
    assert payments and payments[0]["receipt_number"] == receipts[0]["receipt_number"]

    # Opening it left a trace the dairy can see.
    status = (await client.get(f"/v1/customers/{mine['id']}/bill-link", headers=admin)).json()
    assert status["last_seen_at"] is not None

    # The link is anonymous: it carries no session and grants no other route.
    assert (
        await client.get("/v1/invoices", headers={"Authorization": f"Bearer {token}"})
    ).status_code == 401


async def test_a_bill_link_dies_on_rotation_and_revocation_like_one_that_never_existed(client):
    org, admin = await _tenant_admin(client)
    mine, _, _ = await _household_with_bill(
        client, admin, "Rotating Household", "rotating@household.example", org["id"]
    )
    never = (await client.get("/v1/public/bill/this-token-never-existed")).status_code
    assert never == 404

    first = await _mint(client, admin, mine["id"])
    assert (await client.get(f"/v1/public/bill/{first}")).status_code == 200
    second = await _mint(client, admin, mine["id"])
    r = await client.get(f"/v1/public/bill/{first}")
    assert r.status_code == never
    assert (await client.get(f"/v1/public/bill/{second}")).status_code == 200

    r = await client.delete(f"/v1/customers/{mine['id']}/bill-link", headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["active"] is False
    assert (await client.get(f"/v1/public/bill/{second}")).status_code == never
    assert (await client.get(f"/v1/customers/{mine['id']}/bill-link", headers=admin)).json()[
        "active"
    ] is False
    # Nothing left to revoke.
    assert (
        await client.delete(f"/v1/customers/{mine['id']}/bill-link", headers=admin)
    ).status_code == 404

    # Only the hash is stored, and the raw token is not in the audit trail.
    from sqlalchemy import select

    from platform_core.core.rls import platform_factory
    from platform_core.modules.audit.models import AuditRecord
    from platform_core.modules.customer_access.models import CustomerBillToken

    async with platform_factory("test: inspect bill tokens")() as session:
        rows = (await session.scalars(select(CustomerBillToken))).all()
        assert len(rows) == 2
        assert all(len(row.token_hash) == 64 for row in rows)
        assert all(row.revoked_at is not None for row in rows)
        assert first not in {row.token_hash for row in rows}
        audit = (await session.scalars(select(AuditRecord))).all()
        text = " ".join(str(a.detail) for a in audit)
        assert first not in text and second not in text
        assert any(a.action == "customer.bill_link.issued" for a in audit)
        assert any(a.action == "customer.bill_link.revoked" for a in audit)


async def test_the_public_bill_page_is_rate_limited(client, monkeypatch):
    org, admin = await _tenant_admin(client)
    mine, _, _ = await _household_with_bill(
        client, admin, "Hammered Household", "hammered@household.example", org["id"]
    )
    token = await _mint(client, admin, mine["id"])
    monkeypatch.setattr(
        rate_limit,
        "PUBLIC_BILL",
        rate_limit.RateLimitRule(
            "public-bill-test", limit=3, window_seconds=60, scope="ip", fail_closed=True
        ),
    )
    statuses = [(await client.get(f"/v1/public/bill/{token}")).status_code for _ in range(4)]
    assert statuses == [200, 200, 200, 429], statuses
    # And a guessed token is charged the same budget — it does not get more
    # attempts for being wrong.
    assert (await client.get("/v1/public/bill/guess")).status_code == 429


# --- the notice ---------------------------------------------------------------------


async def test_issuing_a_bill_leaves_a_notice_the_household_reads_back(client):
    from platform_core.core.rls import platform_factory
    from platform_core.modules.event_relay.consumers import ConsumerRunner

    org, admin = await _tenant_admin(client)
    mine = await _customer(client, admin, "Noticed Household")
    theirs = await _customer(client, admin, "Quiet Household")
    await _deliver(client, admin, mine["id"])
    await _deliver(client, admin, theirs["id"])
    me = await _customer_login(client, admin, org["id"], mine["id"], "noticed@household.example")
    them = await _customer_login(client, admin, org["id"], theirs["id"], "quiet@household.example")

    assert (await client.get("/v1/notifications/mine", headers=me)).json()["total"] == 0
    my_bill = await _bill(client, admin, mine["id"])
    await ConsumerRunner(platform_factory("test: run consumers")).run_once()

    page = (await client.get("/v1/notifications/mine", headers=me)).json()
    assert page["total"] == 1
    notice = page["items"][0]
    assert notice["channel"] == "inapp"
    assert notice["template_key"] == "invoice_issued"
    assert notice["status"] == "sent"
    assert my_bill["invoice_number"] in notice["rendered_text"]
    assert notice["source_id"] == my_bill["id"]
    # The signed-in reader may see the amount; a lock screen may not.
    assert my_bill["amount_due"] in notice["rendered_text"]

    assert (await client.get("/v1/notifications/mine", headers=them)).json()["total"] == 0
    assert (await client.get("/v1/notifications/mine", headers=admin)).json()["total"] == 0
    # The operator's history still has both the push and the notice.
    history = (
        await client.get(
            "/v1/notifications", params={"template_key": "invoice_issued"}, headers=admin
        )
    ).json()
    assert sorted(n["channel"] for n in history["items"]) == ["inapp", "push"]
    # A replay of the log re-sends nothing.
    await ConsumerRunner(platform_factory("test: run consumers again")).run_once()
    assert (await client.get("/v1/notifications/mine", headers=me)).json()["total"] == 1


async def test_the_month_end_pass_nudges_the_administrators_once(client):
    from platform_core.modules.delivery.scheduler import Tenant, draft_month_end_for_tenant

    org, admin = await _tenant_admin(client)
    household = await _customer(client, admin, "Monthly Household")
    await _deliver(client, admin, household["id"])
    who = (await client.get("/v1/auth/me", headers=admin)).json()
    tz = (who.get("organization") or {}).get("timezone") or "Africa/Nairobi"

    # The first of the month AFTER the deliveries, past the generation hour,
    # in the dairy's own zone: the pass drafts last month's bill.
    first_next = (TODAY.replace(day=1) + timedelta(days=32)).replace(day=1)
    now = datetime.combine(first_next, time(hour=9), tzinfo=ZoneInfo(tz)).astimezone(UTC)
    tenant = Tenant(id=uuid.UUID(org["id"]), slug=org["slug"], timezone=tz)

    # The pass reads the calendar from the interpreter's clock (WO-62), so the
    # clock travels to that morning rather than the test pretending.
    import time_machine

    with time_machine.travel(now, tick=False):
        await draft_month_end_for_tenant(tenant, now=now, generation_hour=5)
    page = (await client.get("/v1/notifications/mine", headers=admin)).json()
    assert page["total"] == 1, page
    notice = page["items"][0]
    assert notice["template_key"] == "month_end_drafted"
    assert notice["channel"] == "inapp"
    assert notice["status"] == "sent"
    assert "1 " in notice["title"] or "1" in notice["title"]
    assert "Billing" in notice["rendered_text"]

    # The same morning again — or the 1st's evening — nudges nobody twice.
    with time_machine.travel(now + timedelta(hours=6), tick=False):
        await draft_month_end_for_tenant(tenant, now=now + timedelta(hours=6), generation_hour=5)
    assert (await client.get("/v1/notifications/mine", headers=admin)).json()["total"] == 1

    # And a month with nothing to draft says nothing.
    later = (first_next + timedelta(days=32)).replace(day=1)
    now2 = datetime.combine(later, time(hour=9), tzinfo=ZoneInfo(tz)).astimezone(UTC)
    with time_machine.travel(now2, tick=False):
        await draft_month_end_for_tenant(tenant, now=now2, generation_hour=5)
    assert (await client.get("/v1/notifications/mine", headers=admin)).json()["total"] == 1


# --- the schema --------------------------------------------------------------------


def test_the_bill_token_table_is_tenant_owned_and_under_policy():
    from migrations.versions.a7c3e9d14b56_wo86_customer_access import POLICY_TABLES

    from platform_core.core.rls import tenant_tables

    assert "customer_bill_token" in tenant_tables()
    assert POLICY_TABLES == ("customer_bill_token",)


def test_the_migration_goes_up_down_and_up(tmp_path):
    db = tmp_path / "wo86.db"
    _alembic(db, "upgrade", "f4a9d2c71b83")
    conn = sqlite3.connect(db)
    columns = [r[1] for r in conn.execute("PRAGMA table_info(invitation)")]
    assert "customer_id" not in columns
    conn.close()

    _alembic(db, "upgrade", "head")
    conn = sqlite3.connect(db)
    columns = [r[1] for r in conn.execute("PRAGMA table_info(invitation)")]
    assert "customer_id" in columns
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "customer_bill_token" in tables
    token_columns = [r[1] for r in conn.execute("PRAGMA table_info(customer_bill_token)")]
    assert {"tenant_id", "customer_id", "token_hash", "expires_at", "revoked_at"} <= set(
        token_columns
    )
    conn.close()

    _alembic(db, "downgrade", "f4a9d2c71b83")
    conn = sqlite3.connect(db)
    columns = [r[1] for r in conn.execute("PRAGMA table_info(invitation)")]
    assert "customer_id" not in columns
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "customer_bill_token" not in tables
    conn.close()

    _alembic(db, "upgrade", "head")
