"""Repairing a farmer's contact, and asking about one settlement period (DEMO-030).

The property that matters most, and the defect this milestone found:

    **A repaired phone number actually reaches the place a message is sent
    from.** It did not. `update_profile` changed `supplier_profile.phone` and
    published nothing, and the notification directory is built from supplier
    events — so an operator acting on DEMO-029's reachability report could fix
    a farmer's number, watch the report not change, and have the next
    settlement message still go to the wrong place.

And the one that must never stop being true:

    **None of this touches money.** A farmer with no phone is settled, paid and
    owed exactly the same. Communication status is not a financial input.
"""

import uuid

import pytest
from sqlalchemy import func, select

from platform_core.core import db
from platform_core.modules.audit.models import AuditRecord
from platform_core.modules.notification.models import NotificationRecipient
from platform_core.modules.notification.reachability import (
    NOT_IN_DIRECTORY,
    PHONE_MISSING,
)
from tests.test_notifications import _runner, provider_guard  # noqa: F401 — fixture

CONTACT = "/v1/suppliers/{}/contact"
PERIOD = "/v1/notifications/reachability/settlement-period"
GLOBAL = "/v1/notifications/reachability"


async def _directory_entry(supplier_id: uuid.UUID) -> NotificationRecipient | None:
    async with db.get_session_factory()() as session:
        return await session.scalar(
            select(NotificationRecipient).where(NotificationRecipient.subject_id == supplier_id)
        )


async def _profile_phone(supplier_id: uuid.UUID) -> str:
    from platform_core.modules.supplier.models import SupplierProfile

    async with db.get_session_factory()() as session:
        profile = await session.scalar(
            select(SupplierProfile).where(SupplierProfile.supplier_id == supplier_id)
        )
        return profile.phone


async def _audit_entries(supplier_id: uuid.UUID) -> list[AuditRecord]:
    async with db.get_session_factory()() as session:
        rows = await session.scalars(
            select(AuditRecord).where(
                AuditRecord.resource_id == str(supplier_id),
                AuditRecord.action == "supplier.profile_updated",
            )
        )
        return list(rows.all())


async def _settled_env(client):
    """A dairy with one farmer, one settlement, and a populated directory."""
    from tests.test_message_delivery import _settlement_env

    headers, supplier, settlement = await _settlement_env(client)
    await client.post(f"/v1/settlements/{settlement['id']}/finalize", headers=headers)
    await _runner().run_once()  # the directory is built from supplier events
    return headers, supplier, settlement


# --- the defect ----------------------------------------------------------------


async def test_a_repaired_number_reaches_the_directory_a_message_is_sent_from(
    client,
    provider_guard,  # noqa: F811
):
    """THE defect. Before DEMO-030 this test would fail on the last assertion.

    `supplier_profile.phone` changed and `notification_recipient.phone` did
    not, because no event was published and the directory never queries the
    supplier module. The repair looked like it worked and changed nothing that
    mattered.
    """
    headers, supplier, _settlement = await _settled_env(client)
    supplier_id = uuid.UUID(supplier["id"])

    before = await _directory_entry(supplier_id)
    assert before is not None, "the premise: the farmer is in the directory"

    answer = await client.patch(
        CONTACT.format(supplier_id),
        headers=headers,
        json={"phone": "+919845000199", "reason": "farmer changed number"},
    )
    assert answer.status_code == 200, answer.text
    await _runner().run_once()

    assert await _profile_phone(supplier_id) == "+919845000199"
    after = await _directory_entry(supplier_id)
    assert after.phone == "+919845000199", (
        "the repair never reached the directory — a message would still go to the old number"
    )


async def test_clearing_a_wrong_number_actually_clears_it(client, provider_guard):  # noqa: F811
    """The `or` versus `=` distinction in the directory merge.

    Registration COALESCES, so an event omitting a field cannot blank a known
    one. A repair ASSIGNS, because the event carries the complete profile — and
    an operator deliberately removing a wrong number must not be silently
    overruled.
    """
    headers, supplier, _settlement = await _settled_env(client)
    supplier_id = uuid.UUID(supplier["id"])
    assert (await _directory_entry(supplier_id)).phone, "the premise: a number is on file"

    answer = await client.patch(
        CONTACT.format(supplier_id),
        headers=headers,
        json={"phone": "", "reason": "number belongs to somebody else"},
    )
    assert answer.status_code == 200, answer.text
    await _runner().run_once()

    assert await _profile_phone(supplier_id) == ""
    assert (await _directory_entry(supplier_id)).phone == "", "the bad number survived"


async def test_a_repair_makes_an_unreachable_farmer_reachable(client, provider_guard):  # noqa: F811
    """The whole point of the milestone, end to end."""
    headers, supplier, _settlement = await _settled_env(client)
    supplier_id = uuid.UUID(supplier["id"])

    await client.patch(CONTACT.format(supplier_id), headers=headers, json={"phone": ""})
    await _runner().run_once()
    before = (await client.get(GLOBAL, headers=headers)).json()
    assert before["unreachable"] >= 1
    assert PHONE_MISSING in before["reasons"]

    await client.patch(
        CONTACT.format(supplier_id),
        headers=headers,
        json={"phone": "0712345678", "reason": "confirmed at the collection centre"},
    )
    await _runner().run_once()

    after = (await client.get(GLOBAL, headers=headers)).json()
    assert after["reachable"] == before["reachable"] + 1
    assert after["unreachable"] == before["unreachable"] - 1


# --- audit ---------------------------------------------------------------------


async def test_a_repair_records_who_what_before_after_and_why(client, provider_guard):  # noqa: F811
    """§3, and the second half of the defect: the audit had no before or after."""
    headers, supplier, _settlement = await _settled_env(client)
    supplier_id = uuid.UUID(supplier["id"])
    await _profile_phone(supplier_id)

    await client.patch(
        CONTACT.format(supplier_id),
        headers=headers,
        json={"phone": "+919845000123", "reason": "wrong digit on the registration form"},
    )

    entries = await _audit_entries(supplier_id)
    assert entries, "no audit entry was written"
    detail = entries[-1].detail
    assert detail["changed"] == ["phone"]
    assert detail["phone"]["to"] != detail["phone"]["from"]
    assert detail["reason"] == "wrong digit on the registration form"
    assert entries[-1].actor_id is not None, "an audit entry with no actor proves nothing"


async def test_the_audit_trail_masks_the_number_it_records(client, provider_guard):  # noqa: F811
    """An audit log is read far more widely than a contact record.

    An operator needs to verify that a repair happened; they do not need the
    log to become a directory of farmers' phone numbers.
    """
    headers, supplier, _settlement = await _settled_env(client)
    supplier_id = uuid.UUID(supplier["id"])

    await client.patch(
        CONTACT.format(supplier_id), headers=headers, json={"phone": "+919845000456"}
    )
    detail = (await _audit_entries(supplier_id))[-1].detail
    assert "9845000456" not in str(detail), "the audit trail stored a full phone number"
    assert detail["phone"]["to"], "…but it must still show that something changed"


async def test_a_repair_that_changes_nothing_publishes_nothing(client, provider_guard):  # noqa: F811
    """A no-op must not look like a repair in the directory's history."""
    headers, supplier, _settlement = await _settled_env(client)
    supplier_id = uuid.UUID(supplier["id"])
    current = await _profile_phone(supplier_id)

    async with db.get_session_factory()() as session:
        from platform_core.modules.event_relay.models import OutboxEvent

        before = await session.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(OutboxEvent.event_name == "supplier.supplier-profile-updated.v1")
        )

    answer = await client.patch(
        CONTACT.format(supplier_id), headers=headers, json={"phone": current}
    )
    assert answer.status_code == 200

    async with db.get_session_factory()() as session:
        from platform_core.modules.event_relay.models import OutboxEvent

        after = await session.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(OutboxEvent.event_name == "supplier.supplier-profile-updated.v1")
        )
    assert after == before, "a no-op repair published an event"


# --- validation ----------------------------------------------------------------


@pytest.mark.parametrize(
    "phone", ["call the office", "12345", "not-a-number", "+1234567890123456789"]
)
async def test_a_nonsense_number_is_refused(client, provider_guard, phone):  # noqa: F811
    """§4. What must not survive is nonsense in a field a gateway will be handed."""
    headers, supplier, _settlement = await _settled_env(client)
    supplier_id = uuid.UUID(supplier["id"])
    original = await _profile_phone(supplier_id)

    answer = await client.patch(CONTACT.format(supplier_id), headers=headers, json={"phone": phone})
    assert answer.status_code in (400, 422), answer.text
    assert await _profile_phone(supplier_id) == original, (
        "a refused repair still changed the record"
    )


async def test_an_empty_number_is_allowed_because_some_farmers_have_none(
    client,
    provider_guard,  # noqa: F811
):
    """Empty is a legitimate state, reported honestly as `phone_missing`.

    Refusing it would force an operator to invent a number, which is worse than
    recording that there isn't one.
    """
    headers, supplier, _settlement = await _settled_env(client)
    supplier_id = uuid.UUID(supplier["id"])
    answer = await client.patch(CONTACT.format(supplier_id), headers=headers, json={"phone": ""})
    assert answer.status_code == 200


async def test_creating_a_supplier_with_a_nonsense_number_is_refused_too(client):
    """The same rule wherever a number is saved, not only on repair."""
    from tests.test_org_structure import _tenant_admin

    _org, headers = await _tenant_admin(client)
    answer = await client.post(
        "/v1/suppliers",
        headers=headers,
        json={"full_name": "Bad Number", "phone": "ring the shop"},
    )
    assert answer.status_code == 422, answer.text


async def test_a_valid_number_means_contact_valid_not_whatsapp_reachable(client, provider_guard):  # noqa: F811
    """§4's explicit distinction, kept from DEMO-029."""
    from platform_core.modules.notification.reachability import (
        UNKNOWN,
        WHATSAPP_UNKNOWN,
        evaluate,
    )

    answer = evaluate(
        channel="whatsapp",
        phone="+919845000101",
        email=None,
        provider_available=True,
        subject_id=uuid.uuid4(),
        subject_type="supplier",
        name="Farmer",
    )
    assert (answer.status, answer.reason) == (UNKNOWN, WHATSAPP_UNKNOWN)


# --- settlement-period reachability --------------------------------------------


async def test_the_period_report_asks_only_about_the_farmers_being_paid(
    client,
    provider_guard,  # noqa: F811
):
    """§5. The same engine, a different question — and the operational one."""
    headers, _supplier, settlement = await _settled_env(client)

    everyone = (await client.get(GLOBAL, headers=headers)).json()
    period = (
        await client.get(
            PERIOD,
            headers=headers,
            params={
                "period_from": settlement["period_from"],
                "period_to": settlement["period_to"],
            },
        )
    ).json()

    assert period["total"] >= 1
    assert period["total"] <= everyone["total"]
    assert period["channel"] == everyone["channel"], "the same channel resolution"
    assert period["reachable"] + period["unreachable"] + period["unknown"] == period["total"]


async def test_a_period_with_no_settlements_reports_nobody_rather_than_everybody(
    client,
    provider_guard,  # noqa: F811
):
    """Scoping that silently fell back to "all suppliers" would be worse than
    an empty answer — it would look like a full report."""
    headers, _supplier, _settlement = await _settled_env(client)
    body = (
        await client.get(
            PERIOD,
            headers=headers,
            params={"period_from": "2020-01-01", "period_to": "2020-01-31"},
        )
    ).json()
    assert body["total"] == 0
    assert body["affected"] == []


async def test_a_settled_farmer_missing_from_the_directory_is_reported_not_omitted(
    client,
    provider_guard,  # noqa: F811
):
    """Absent from the directory is exactly the kind of unreachable that a
    report listing only known contacts would hide."""
    headers, supplier, settlement = await _settled_env(client)
    supplier_id = uuid.UUID(supplier["id"])

    async with db.get_session_factory()() as session:
        entry = await session.scalar(
            select(NotificationRecipient).where(NotificationRecipient.subject_id == supplier_id)
        )
        await session.delete(entry)
        await session.commit()

    body = (
        await client.get(
            PERIOD,
            headers=headers,
            params={
                "period_from": settlement["period_from"],
                "period_to": settlement["period_to"],
            },
        )
    ).json()
    assert body["total"] == 1
    assert body["unreachable"] == 1
    assert body["reasons"] == {NOT_IN_DIRECTORY: 1}
    assert body["affected"][0]["subject_id"] == str(supplier_id)


async def test_a_settlement_overlapping_the_period_counts(client, provider_guard):  # noqa: F811
    """A monthly settlement is relevant to a question about a fortnight."""
    headers, _supplier, settlement = await _settled_env(client)
    body = (
        await client.get(
            PERIOD,
            headers=headers,
            params={
                "period_from": settlement["period_from"],
                "period_to": settlement["period_from"],
            },
        )
    ).json()
    assert body["total"] == 1, "an overlapping settlement was missed"


async def test_an_inverted_period_is_refused_rather_than_silently_empty(
    client,
    provider_guard,  # noqa: F811
):
    headers, _supplier, _settlement = await _settled_env(client)
    answer = await client.get(
        PERIOD,
        headers=headers,
        params={"period_from": "2026-08-31", "period_to": "2026-08-01"},
    )
    assert answer.status_code in (400, 422)


# --- settlement safety ---------------------------------------------------------


async def test_an_unreachable_farmer_is_still_settled_and_still_paid(client, provider_guard):  # noqa: F811
    """§7, and the line that must never move: money and communication are
    separate domains."""
    from tests.test_message_delivery import _settlement_env

    headers, supplier, settlement = await _settlement_env(client)
    supplier_id = uuid.UUID(supplier["id"])

    # Remove the farmer's number BEFORE finalizing.
    await client.patch(CONTACT.format(supplier_id), headers=headers, json={"phone": ""})

    finalized = await client.post(f"/v1/settlements/{settlement['id']}/finalize", headers=headers)
    assert finalized.status_code == 200, "an unreachable farmer was refused a settlement"
    body = finalized.json()
    assert body["status"] == "finalized"
    assert body["net_amount"]


async def test_repairing_a_contact_moves_no_money(client, provider_guard):  # noqa: F811
    """§15, asserted rather than asserted about."""
    from platform_core.modules.billing.models import CustomerInvoice
    from platform_core.modules.payment.models import Payment
    from platform_core.modules.receipt.models import Receipt
    from platform_core.modules.settlement.models import Settlement

    async def snapshot():
        async with db.get_session_factory()() as session:
            return {
                "settlements": await session.scalar(select(func.count()).select_from(Settlement)),
                "settled": await session.scalar(
                    select(func.coalesce(func.sum(Settlement.net_amount), 0))
                ),
                "invoices": await session.scalar(select(func.count()).select_from(CustomerInvoice)),
                "receivable": await session.scalar(
                    select(func.coalesce(func.sum(CustomerInvoice.amount_due), 0))
                ),
                "payments": await session.scalar(select(func.count()).select_from(Payment)),
                "receipts": await session.scalar(select(func.count()).select_from(Receipt)),
            }

    headers, supplier, settlement = await _settled_env(client)
    supplier_id = uuid.UUID(supplier["id"])
    before = await snapshot()

    await client.patch(CONTACT.format(supplier_id), headers=headers, json={"phone": ""})
    await _runner().run_once()
    await client.patch(
        CONTACT.format(supplier_id), headers=headers, json={"phone": "+254712345678"}
    )
    await _runner().run_once()
    await client.get(
        PERIOD,
        headers=headers,
        params={
            "period_from": settlement["period_from"],
            "period_to": settlement["period_to"],
        },
    )

    assert await snapshot() == before, "repairing a contact changed a financial record"


# --- security ------------------------------------------------------------------


async def test_the_repair_endpoint_refuses_an_anonymous_caller(client, provider_guard):  # noqa: F811
    _headers, supplier, _settlement = await _settled_env(client)
    answer = await client.patch(CONTACT.format(supplier["id"]), json={"phone": "+919845000101"})
    assert answer.status_code == 401


async def test_the_period_report_refuses_an_anonymous_caller(client):
    assert (await client.get(PERIOD)).status_code == 401


async def test_a_viewer_cannot_repair_a_contact(client, provider_guard):  # noqa: F811
    """Reading a farmer's record does not grant changing how they are reached."""
    from tests.conftest import invite
    from tests.test_org_structure import _tenant_admin

    org, admin = await _tenant_admin(client)
    created = await client.post(
        "/v1/suppliers", headers=admin, json={"full_name": "Contact Farmer", "phone": "0712345678"}
    )
    assert created.status_code == 201, created.text
    supplier_id = created.json()["id"]

    _inv, token = await invite(
        client,
        {**admin, "X-Tenant-ID": org["id"]},
        email="viewer@repair.example",
        role_name="tenant-viewer",
    )
    await client.post(
        "/v1/invitations/accept",
        json={"token": token, "password": "viewer-password-1", "full_name": "Viewer"},
    )
    pair = await client.post(
        "/v1/auth/token",
        json={
            "email": "viewer@repair.example",
            "password": "viewer-password-1",
            "tenant_id": org["id"],
        },
    )
    viewer = {"Authorization": f"Bearer {pair.json()['access_token']}"}

    refused = await client.patch(
        CONTACT.format(supplier_id), headers=viewer, json={"phone": "+919845000101"}
    )
    assert refused.status_code == 403


async def test_one_tenant_cannot_repair_another_tenants_contact(client, provider_guard):  # noqa: F811
    """A cross-tenant resource is a 404, never a 403 — the house rule."""
    from tests.test_localization import _tenant_admin_for

    _headers_a, supplier, _settlement = await _settled_env(client)
    _org_b, headers_b = await _tenant_admin_for(
        client, country="IN", slug="repair-other", email="admin@repair-other.example"
    )

    answer = await client.patch(
        CONTACT.format(supplier["id"]), headers=headers_b, json={"phone": "+919845000111"}
    )
    assert answer.status_code == 404, "another tenant reached a farmer's contact"
    # And the record is untouched.
    assert await _profile_phone(uuid.UUID(supplier["id"])) != "+919845000111"


async def test_the_period_report_never_leaves_the_organization(client, provider_guard):  # noqa: F811
    from tests.test_localization import _tenant_admin_for

    headers_a, _supplier, settlement = await _settled_env(client)
    _org_b, headers_b = await _tenant_admin_for(
        client, country="IN", slug="period-other", email="admin@period-other.example"
    )

    params = {
        "period_from": settlement["period_from"],
        "period_to": settlement["period_to"],
    }
    mine = (await client.get(PERIOD, headers=headers_a, params=params)).json()
    theirs = (await client.get(PERIOD, headers=headers_b, params=params)).json()
    assert mine["total"] >= 1
    assert theirs["total"] == 0, "another organization's settled farmers were counted"


# --- the shape of the change ---------------------------------------------------


def test_no_second_contact_directory_was_created():
    """§2. There is one supplier contact record and one notification directory."""
    import pathlib

    import platform_core.modules as modules

    root = pathlib.Path(modules.__file__).parent
    tables = set()
    for path in root.rglob("models.py"):
        for line in path.read_text().splitlines():
            if "__tablename__" in line:
                tables.add(line.split("=")[1].strip().strip('"'))
    contactish = {t for t in tables if "contact" in t or "directory" in t}
    assert not contactish, f"a second contact store appeared: {contactish}"


def test_the_period_report_reuses_the_reachability_engine():
    """§5. One derivation, asked two ways — not two implementations."""
    import inspect

    from platform_core.modules.notification import reachability

    source = inspect.getsource(reachability.ReachabilityService.for_subjects)
    assert "evaluate(" in source, "the period report stopped using the shared decision"
    assert "_summarise(" in source, "the period report grew its own counting"
    # And there is exactly one place that decides.
    assert inspect.getsource(reachability).count("def evaluate(") == 1


def test_reachability_never_queries_the_settlement_tables():
    """The boundary DEMO-029's own test caught this milestone breaking.

    The first draft of the period report imported `Settlement` and queried it
    from the notification module — "never query another module's tables, never
    import its models". The settlement module answers who it is settling; the
    notification module answers whether they can be reached; the route composes
    them. That is what a boundary test is for, and it earned its keep here.
    """
    import pathlib

    import platform_core.modules.notification as package

    root = pathlib.Path(package.__file__).parent
    offenders = [
        path.name
        for path in root.glob("*.py")
        if "modules.settlement" in path.read_text() or "modules.payment" in path.read_text()
    ]
    assert not offenders, f"the notification module reached into the ledger: {offenders}"
