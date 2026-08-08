"""Tenant export and offboarding (PROD-001).

QR-0007 found that a tenant could be onboarded but not offboarded. These tests
cover the capability that closes it, and they are written around the property
that actually matters: after offboarding, the financial history is still
answerable and the people in it are not identifiable.
"""

import uuid

import pytest

from tests.conftest import register_and_login

_ROOT: dict = {}


async def _admin(client, slug="alpha"):
    """A tenant admin for a NEW organization.

    `test_org_structure._tenant_admin` hardcodes one slug, and these tests need
    two tenants inside a single client to say anything about isolation — so the
    flow is repeated here with the slug parameterised rather than made
    conditional there.
    """
    if "headers" not in _ROOT:
        _, _ROOT["headers"] = await register_and_login(client, "root@example.com", admin=True)
    admin_headers = _ROOT["headers"]
    org = (
        await client.post(
            "/v1/organizations",
            json={"name": f"{slug.title()} Dairy Cooperative", "slug": slug, "country_code": "ke"},
            headers=admin_headers,
        )
    ).json()
    invitation = (
        await client.post(
            "/v1/invitations",
            json={"email": f"manager@{slug}.example", "role_name": "tenant-admin"},
            headers={**admin_headers, "X-Tenant-ID": org["id"]},
        )
    ).json()
    accepted = await client.post(
        "/v1/invitations/accept",
        json={
            "token": invitation["invitation_token"],
            "password": "manager-password-1",
            "full_name": f"{slug.title()} Manager",
        },
    )
    assert accepted.status_code == 201, accepted.text
    pair = (
        await client.post(
            "/v1/auth/token",
            json={
                "email": f"manager@{slug}.example",
                "password": "manager-password-1",
                "tenant_id": org["id"],
            },
        )
    ).json()
    return {"Authorization": f"Bearer {pair['access_token']}"}


@pytest.fixture(autouse=True)
def _reset_root():
    _ROOT.clear()
    yield
    _ROOT.clear()


# --- classification ---------------------------------------------------------


def test_every_declared_table_still_exists():
    """A retention promise about a table that was renamed is worse than none.

    PURGE is the default, so a NEW table is always covered; the failure mode
    that needs a test is the opposite one — a declaration left pointing at
    nothing after a rename.
    """
    from platform_core.core.tenant_lifecycle import unclassified_for_offboarding

    assert unclassified_for_offboarding() == ()


def test_financial_tables_are_retained_and_personal_tables_are_not():
    """The two halves of the tension this module exists to resolve."""
    from platform_core.core.tenant_lifecycle import ANONYMIZE, PURGE, RETAIN, treatment_for

    for table in ("settlement", "payment", "payment_line", "receipt_line"):
        assert treatment_for(table).treatment == RETAIN, f"{table} is a financial record"

    for table in ("supplier_profile", "supplier_bank_account", "user_account"):
        assert treatment_for(table).treatment == ANONYMIZE, f"{table} holds personal data"

    # Anything nobody classified is deleted, not kept.
    assert treatment_for("some_future_module_table").treatment == PURGE


def test_every_treatment_states_a_reason():
    """`core/rls.py`'s rule, applied here: a decision to keep or destroy
    somebody's data must be written down where the next reviewer looks."""
    from platform_core.core.rls import tenant_tables
    from platform_core.core.tenant_lifecycle import treatment_for

    for table in tenant_tables():
        assert treatment_for(table).reason.strip(), f"{table} has no stated reason"


# --- export -----------------------------------------------------------------


async def test_a_tenant_admin_can_export_everything_their_tenant_holds(client):
    headers = await _admin(client)
    response = await client.get("/v1/tenant-data/export", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["row_count"] > 0
    assert "organization" in body["tables"]
    # The export is portable: no ORM objects, no bytes, just JSON.
    import json

    json.dumps(body)


async def test_the_export_contains_only_the_callers_tenant(client):
    """There is no request shape that can name another tenant — the id comes
    from the authenticated principal — but the data still has to prove it."""
    import json

    first = await _admin(client, "alpha")
    second = await _admin(client, "beta")

    a = (await client.get("/v1/tenant-data/export", headers=first)).json()
    b = (await client.get("/v1/tenant-data/export", headers=second)).json()

    assert a["tenant_id"] != b["tenant_id"]

    # The backup encoder wraps typed values, so ids arrive as tagged dicts.
    def _ids(export):
        return {
            json.dumps(row["id"], sort_keys=True)
            for rows in export["tables"].values()
            for row in rows
            if "id" in row
        }

    a_ids, b_ids = _ids(a), _ids(b)
    assert not (a_ids & b_ids), "the two exports share rows"


async def test_export_requires_its_own_permission(client):
    """A plain member administers nothing and exports nothing."""
    _, headers = await register_and_login(client, "member@example.com")
    response = await client.get("/v1/tenant-data/export", headers=headers)
    assert response.status_code in (401, 403)


# --- offboarding ------------------------------------------------------------


async def test_the_plan_is_not_destructive_and_names_the_confirmation(client):
    headers = await _admin(client, "alpha")
    plan = (await client.get("/v1/tenant-data/offboarding-plan", headers=headers)).json()

    assert plan["confirmation_required"] == plan["organization_name"]
    assert plan["purge"] and plan["retain"], "both treatments should be represented"
    # Still there afterwards.
    assert (await client.get("/v1/tenant-data/export", headers=headers)).json()["row_count"] > 0


async def test_offboarding_refuses_without_the_exact_organization_name(client):
    headers = await _admin(client, "alpha")
    for confirmation in ("yes", "DELETE", "", "wrong name"):
        response = await client.post(
            "/v1/tenant-data/offboard", json={"confirmation": confirmation}, headers=headers
        )
        assert response.status_code in (409, 422), f"accepted {confirmation!r}"

    # Nothing happened.
    assert (await client.get("/v1/tenant-data/export", headers=headers)).json()["row_count"] > 0


async def test_offboarding_purges_operations_keeps_finance_and_erases_identity(client):
    """The property the whole module exists for.

    After offboarding: "what did this dairy pay" is still answerable, and
    "who was this supplier" is not.
    """
    from sqlalchemy import select

    from platform_core.core.db import get_session_factory
    from platform_core.modules.organization.models import Organization
    from platform_core.modules.supplier.models import Supplier, SupplierProfile

    headers = await _admin(client, "alpha")
    plan = (await client.get("/v1/tenant-data/offboarding-plan", headers=headers)).json()
    tenant_id = uuid.UUID(plan["tenant_id"])

    # A supplier with a real person behind it.
    created = await client.post(
        "/v1/suppliers",
        json={"full_name": "Grace Njeri", "phone": "+254700111222", "national_id": "12345678"},
        headers=headers,
    )
    assert created.status_code == 201, created.text

    response = await client.post(
        "/v1/tenant-data/offboard",
        json={"confirmation": plan["organization_name"]},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    outcome = response.json()
    assert outcome["status"] == "offboarded"

    async with get_session_factory()() as session:
        organization = await session.get(Organization, tenant_id)
        assert organization is not None, "the tombstone must remain"
        assert organization.status == "offboarded"
        assert organization.offboarded_at is not None
        assert str(tenant_id) in organization.name

        # The supplier row survives (financial records reference it)…
        suppliers = (
            await session.scalars(select(Supplier).where(Supplier.tenant_id == tenant_id))
        ).all()
        # …but the person behind it does not.
        profiles = (
            await session.scalars(
                select(SupplierProfile).where(SupplierProfile.tenant_id == tenant_id)
            )
        ).all()
        for profile in profiles:
            assert profile.full_name == "", "the supplier's name survived offboarding"
            assert profile.phone == "", "the supplier's phone survived offboarding"
            assert profile.national_id == "", "the national id survived offboarding"
        # The supplier row is RETAINED (settlement lines reference it) while
        # its profile is anonymized — the parent/child pair must stay
        # consistent, which is what caught the original classification bug.
        assert suppliers, "the supplier row was purged, orphaning its profile"


async def test_offboarding_one_tenant_leaves_the_other_untouched(client):
    """The assertion that would matter most if this went wrong."""
    victim = await _admin(client, "alpha")
    bystander = await _admin(client, "beta")

    before = (await client.get("/v1/tenant-data/export", headers=bystander)).json()
    plan = (await client.get("/v1/tenant-data/offboarding-plan", headers=victim)).json()
    response = await client.post(
        "/v1/tenant-data/offboard",
        json={"confirmation": plan["organization_name"]},
        headers=victim,
    )
    assert response.status_code == 200

    after = (await client.get("/v1/tenant-data/export", headers=bystander)).json()

    # Compared per table, and NOT by total: exporting is itself an audited
    # action, so the bystander's own `audit_record` count legitimately grows
    # between the two reads. Asserting on the total made the test fail for the
    # one reason that is correct behaviour.
    for table, count in before["counts"].items():
        if table == "audit_record":
            assert after["counts"].get(table, 0) >= count, "audit history was lost"
            continue
        assert after["counts"].get(table, 0) == count, f"a bystander lost rows from {table}"
    assert after["organization_name"] == before["organization_name"]


async def test_offboarding_requires_the_delete_permission(client):
    _, headers = await register_and_login(client, "nodelete@example.com")
    response = await client.post(
        "/v1/tenant-data/offboard", json={"confirmation": "anything"}, headers=headers
    )
    assert response.status_code in (401, 403)


@pytest.mark.parametrize("path", ["/v1/tenant-data/export", "/v1/tenant-data/offboarding-plan"])
async def test_tenant_data_endpoints_reject_anonymous_callers(client, path):
    assert (await client.get(path)).status_code == 401
