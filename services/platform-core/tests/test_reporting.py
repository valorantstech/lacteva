"""Reporting Foundation (REP-001): aggregation accuracy, filters, date
boundaries, pagination, permissions, tenant isolation, query bounds."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import update

from tests.conftest import count_statements, invite, register_and_login
from tests.test_org_structure import _tenant_admin
from tests.test_procurement_e2e import _accept_complete, _procurement_env, _run_collection

TODAY = date(2026, 8, 4)  # matches utcnow().date() in this test run window


async def _reported_env(client):
    """Procurement env + three transactions: accepted@fat4.2/25kg (1125.00),
    accepted@fat3.5/15kg (600.00), rejected@fat4.5/25kg."""
    headers, center, supplier, session = await _procurement_env(client)
    a = await _run_collection(client, headers, session["id"], supplier)  # 25kg @45
    await _accept_complete(client, headers, a["id"])
    b = await _run_collection(
        client, headers, session["id"], supplier, fat=3.5, gross=20.0, tare=5.0
    )  # 15kg @40 = 600.00
    await _accept_complete(client, headers, b["id"])
    c = await _run_collection(client, headers, session["id"], supplier, fat=4.5)
    r = await client.post(
        f"/v1/milk-transactions/{c['id']}/reject",
        json={"reason": "spoiled"},
        headers=headers,
    )
    assert r.status_code == 200
    await client.post(f"/v1/milk-transactions/{c['id']}/complete", headers=headers)
    return headers, center, supplier, session


async def _daily(client, headers, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    r = await client.get(f"/v1/reports/collection/daily?{query}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# --- daily collection summary ------------------------------------------------


async def test_daily_summary_accuracy(client):
    headers, _, _, _ = await _reported_env(client)
    body = await _daily(client, headers)
    assert body["transactions"] == 3
    assert body["accepted"] == 2
    assert body["rejected"] == 1
    assert body["cancelled"] == 0 and body["in_progress"] == 0
    assert body["suppliers_served"] == 1
    assert body["total_net_weight_kg"] == 40.0  # 25 + 15; rejected excluded
    assert body["payable_by_currency"] == {"KES": "1725.00"}  # 1125 + 600
    assert body["unpriced_accepted"] == 0
    # Weighted FAT: (4.2*25 + 3.5*15) / 40 = 3.9375 -> 3.94
    assert body["weighted_avg_fat"] == 3.94
    assert body["weighted_avg_snf"] == 8.5


async def test_rejected_milk_excluded_from_totals_but_counted(client):
    headers, _, _, _ = await _reported_env(client)
    body = await _daily(client, headers)
    # The rejected 25kg (fat 4.5) influences neither weight, payable, nor FAT.
    assert body["total_net_weight_kg"] == 40.0
    assert body["weighted_avg_fat"] == 3.94


async def test_unpriced_accepted_counted_in_weight_not_payable(client):
    headers, _center, supplier, session = await _procurement_env(client, with_pricing=False)
    tx = await _run_collection(client, headers, session["id"], supplier)
    await _accept_complete(client, headers, tx["id"])
    body = await _daily(client, headers)
    assert body["accepted"] == 1
    assert body["total_net_weight_kg"] == 25.0
    assert body["payable_by_currency"] == {}
    assert body["unpriced_accepted"] == 1


async def test_daily_filter_by_center_and_supplier(client):
    headers, center, supplier, _ = await _reported_env(client)
    scoped = await _daily(client, headers, center_id=center["id"])
    assert scoped["transactions"] == 3
    other = await _daily(client, headers, center_id=str(uuid.uuid4()))
    assert other["transactions"] == 0
    by_supplier = await _daily(client, headers, supplier_id=supplier["id"])
    assert by_supplier["accepted"] == 2
    assert (await _daily(client, headers, supplier_id=str(uuid.uuid4())))["transactions"] == 0


async def test_daily_filter_by_branch(client):
    headers, center, _, _ = await _reported_env(client)
    branch_id = (
        await client.get(f"/v1/collection-centers/{center['id']}", headers=headers)
    ).json()["center"]["branch_id"]
    scoped = await _daily(client, headers, branch_id=branch_id)
    assert scoped["transactions"] == 3
    assert (await _daily(client, headers, branch_id=str(uuid.uuid4())))["transactions"] == 0


async def test_date_boundaries(client):
    """A transaction moved to 23:59 yesterday leaves today's report and
    appears in a range starting yesterday (half-open day boundaries)."""
    headers, _, _, _ = await _reported_env(client)
    from platform_core.core import db
    from platform_core.modules.milk_collection.models import MilkCollectionTransaction

    today = (await _daily(client, headers))["transactions"]
    assert today == 3
    async with db.get_session_factory()() as s:
        from sqlalchemy import select

        tx = (
            await s.scalars(
                select(MilkCollectionTransaction).where(
                    MilkCollectionTransaction.rejected_reason.is_not(None)
                )
            )
        ).first()
        yesterday = tx.created_at - timedelta(days=1)
        await s.execute(
            update(MilkCollectionTransaction)
            .where(MilkCollectionTransaction.id == tx.id)
            .values(created_at=yesterday)
        )
        await s.commit()
        moved_day = yesterday.date().isoformat()
        today_str = (yesterday.date() + timedelta(days=1)).isoformat()
    assert (await _daily(client, headers))["transactions"] == 2
    ranged = await _daily(client, headers, date_from=moved_day, date_to=today_str)
    assert ranged["transactions"] == 3
    only_yesterday = await _daily(client, headers, date_from=moved_day, date_to=moved_day)
    assert only_yesterday["transactions"] == 1 and only_yesterday["rejected"] == 1


async def test_empty_dataset_returns_zeros(client):
    _org, headers = await _tenant_admin(client)
    body = await _daily(client, headers)
    assert body["transactions"] == 0
    assert body["total_net_weight_kg"] == 0.0
    assert body["payable_by_currency"] == {}
    assert body["weighted_avg_fat"] is None and body["weighted_avg_snf"] is None


# --- per-center summary --------------------------------------------------------


async def test_center_summary_groups_and_orders(client):
    headers, center, supplier, _session = await _reported_env(client)
    # Second center with a smaller collection.
    branch_id = (
        await client.get(f"/v1/collection-centers/{center['id']}", headers=headers)
    ).json()["center"]["branch_id"]
    center2 = (
        await client.post(
            "/v1/collection-centers",
            json={"branch_id": branch_id, "name": "South Center", "code": "KH-C9"},
            headers=headers,
        )
    ).json()
    from tests.test_milk_collection import _ready_center

    await _ready_center(client, headers, center2)
    session2 = (
        await client.post(
            "/v1/collection-sessions",
            json={"center_id": center2["id"], "label": "south"},
            headers=headers,
        )
    ).json()
    await client.post(
        f"/v1/suppliers/{supplier['id']}/centers",
        json={"center_id": center2["id"]},
        headers=headers,
    )
    tx = await _run_collection(
        client, headers, session2["id"], supplier, fat=3.5, gross=10.0, tare=5.0
    )  # 5kg
    await _accept_complete(client, headers, tx["id"])

    r = await client.get("/v1/reports/collection/by-center", headers=headers)
    assert r.status_code == 200, r.text
    page = r.json()
    assert page["total"] == 2
    first, second = page["items"]
    assert first["center_code"] == "KH-C1" and first["total_net_weight_kg"] == 40.0
    assert second["center_code"] == "KH-C9" and second["total_net_weight_kg"] == 5.0
    assert Decimal(str(first["payable_amount"])) == Decimal("1725.00")
    assert first["currency"] == "KES"
    assert first["accepted"] == 2 and first["transactions"] == 3


async def test_center_summary_pagination(client):
    headers, _, _, _ = await _reported_env(client)
    page = (
        await client.get("/v1/reports/collection/by-center?limit=1&offset=0", headers=headers)
    ).json()
    assert page["total"] == 1 and len(page["items"]) == 1
    page = (
        await client.get("/v1/reports/collection/by-center?limit=1&offset=1", headers=headers)
    ).json()
    assert page["items"] == []


# --- per-supplier summary -------------------------------------------------------


async def test_supplier_summary_accuracy(client):
    headers, center, supplier, session = await _reported_env(client)
    # A second supplier with one small accepted delivery.
    from tests.test_suppliers import _create_supplier

    other = await _create_supplier(client, headers, name="Baraka Otieno")
    await client.post(
        f"/v1/suppliers/{other['id']}/centers",
        json={"center_id": center["id"]},
        headers=headers,
    )
    await client.post(
        f"/v1/suppliers/{other['id']}/status", json={"status": "active"}, headers=headers
    )
    tx = await _run_collection(
        client, headers, session["id"], other, fat=3.2, gross=8.0, tare=5.0
    )  # 3kg @40 = 120
    await _accept_complete(client, headers, tx["id"])

    page = (await client.get("/v1/reports/collection/by-supplier", headers=headers)).json()
    assert page["total"] == 2
    first, second = page["items"]
    assert first["supplier_id"] == supplier["id"]  # 40kg beats 3kg
    assert first["supplier_name"] == "Amina Njoroge"
    assert first["deliveries"] == 3 and first["accepted"] == 2
    assert Decimal(str(first["payable_amount"])) == Decimal("1725.00")
    assert second["supplier_name"] == "Baraka Otieno"
    assert second["total_net_weight_kg"] == 3.0
    assert Decimal(str(second["payable_amount"])) == Decimal("120.00")
    assert second["weighted_avg_fat"] == 3.2


async def test_supplier_summary_center_filter_and_pagination(client):
    headers, center, _, _ = await _reported_env(client)
    page = (
        await client.get(
            f"/v1/reports/collection/by-supplier?center_id={center['id']}&limit=1&offset=0",
            headers=headers,
        )
    ).json()
    assert page["total"] == 1 and len(page["items"]) == 1
    none = (
        await client.get(
            f"/v1/reports/collection/by-supplier?center_id={uuid.uuid4()}", headers=headers
        )
    ).json()
    assert none["total"] == 0


# --- settlement summary ---------------------------------------------------------


async def test_settlement_summary(client):
    headers, center, supplier, _ = await _reported_env(client)
    settlement = (
        await client.post(
            "/v1/settlements",
            json={
                "supplier_id": supplier["id"],
                "center_id": center["id"],
                "currency": "KES",
                "period_from": "2026-08-01",
                "period_to": "2026-08-31",
            },
            headers=headers,
        )
    ).json()
    await client.post(f"/v1/settlements/{settlement['id']}/collect", headers=headers)
    await client.post(f"/v1/settlements/{settlement['id']}/calculate", headers=headers)
    await client.post(f"/v1/settlements/{settlement['id']}/finalize", headers=headers)

    body = (await client.get("/v1/reports/settlements", headers=headers)).json()
    assert body["total_settlements"] == 1
    assert body["total_lines"] == 2
    assert Decimal(str(body["finalized_net_total"])) == Decimal("1725.00")
    finalized = next(r for r in body["by_status"] if r["status"] == "finalized")
    assert finalized["count"] == 1

    filtered = (
        await client.get(f"/v1/reports/settlements?supplier_id={supplier['id']}", headers=headers)
    ).json()
    assert filtered["total_settlements"] == 1
    empty = (
        await client.get("/v1/reports/settlements?date_from=2030-01-01", headers=headers)
    ).json()
    assert empty["total_settlements"] == 0 and empty["by_status"] == []


# --- pricing summary -------------------------------------------------------------


async def test_pricing_summary(client):
    headers, _, _, _ = await _reported_env(client)
    body = (await client.get("/v1/reports/pricing", headers=headers)).json()
    assert body["priced_transactions"] == 3  # rejected one was priced too
    assert body["unpriced_transactions"] == 0
    assert body["gross_by_currency"]["KES"] == "2850.00"  # 1125 + 600 + 1125
    assert Decimal(str(body["min_unit_price"])) == Decimal("40")
    assert Decimal(str(body["max_unit_price"])) == Decimal("45")
    assert body["avg_unit_price"] is not None
    assert body["published_rate_cards"] == 1
    assert body["active_matrices"] == 1
    assert body["active_bands"] == 3


async def test_pricing_summary_counts_unavailable(client):
    headers, _, supplier, session = await _procurement_env(client, with_pricing=False)
    tx = await _run_collection(client, headers, session["id"], supplier)
    await _accept_complete(client, headers, tx["id"])
    body = (await client.get("/v1/reports/pricing", headers=headers)).json()
    assert body["priced_transactions"] == 0
    assert body["unpriced_transactions"] == 1
    assert body["published_rate_cards"] == 0


# --- authorization & isolation ---------------------------------------------------


async def test_reports_require_authentication(client):
    assert (await client.get("/v1/reports/collection/daily")).status_code == 401


async def test_reports_require_permission(client):
    await _tenant_admin(client)
    _, nobody = await register_and_login(client, "repnoperm@example.com")
    assert (await client.get("/v1/reports/collection/daily", headers=nobody)).status_code == 403


async def test_viewer_can_read_reports(client):
    org, headers = await _tenant_admin(client)
    _inv, inv_token = await invite(
        client,
        headers,
        email="viewer@kilima.example",
        role_name="tenant-viewer",
    )
    await client.post(
        "/v1/invitations/accept",
        json={
            "token": inv_token,
            "password": "viewer-password-1",
            "full_name": "Read Only",
        },
    )
    pair = (
        await client.post(
            "/v1/auth/token",
            json={
                "email": "viewer@kilima.example",
                "password": "viewer-password-1",
                "tenant_id": org["id"],
            },
        )
    ).json()
    viewer = {"Authorization": f"Bearer {pair['access_token']}"}
    assert (await client.get("/v1/reports/collection/daily", headers=viewer)).status_code == 200


async def test_tenant_isolation(client):
    headers, _, _, _ = await _reported_env(client)
    assert (await _daily(client, headers))["transactions"] == 3
    # A second organization sees only its own (empty) numbers.
    _, root2 = await register_and_login(client, "root2@example.com", admin=True)
    org2 = (
        await client.post(
            "/v1/organizations",
            json={"name": "Rift Valley Dairy", "slug": "rift", "country_code": "ke"},
            headers=root2,
        )
    ).json()
    _inv, inv_token = await invite(
        client,
        {**root2, "X-Tenant-ID": org2["id"]},
        email="manager@rift.example",
        role_name="tenant-admin",
    )
    await client.post(
        "/v1/invitations/accept",
        json={
            "token": inv_token,
            "password": "manager-password-2",
            "full_name": "Rift Manager",
        },
    )
    pair = (
        await client.post(
            "/v1/auth/token",
            json={
                "email": "manager@rift.example",
                "password": "manager-password-2",
                "tenant_id": org2["id"],
            },
        )
    ).json()
    other = {"Authorization": f"Bearer {pair['access_token']}"}
    body = await _daily(client, other)
    assert body["transactions"] == 0 and body["payable_by_currency"] == {}
    assert (await client.get("/v1/reports/collection/by-supplier", headers=other)).json()[
        "total"
    ] == 0


# --- query performance -----------------------------------------------------------


async def _count_selects(client, headers, path):
    response, statements = await count_statements(lambda: client.get(path, headers=headers))
    assert response.status_code == 200, response.text
    return statements


async def test_daily_report_query_count_bounded(client):
    """The daily report must not scale queries with transaction count: the
    bound covers auth/permission lookups plus its 2 fixed aggregates."""
    headers, _, _, _ = await _reported_env(client)  # 3 transactions
    selects = await _count_selects(client, headers, "/v1/reports/collection/daily")
    assert selects <= 11, f"expected fixed query budget, saw {selects}"


async def test_supplier_report_no_n_plus_one(client):
    """Grouped join, not per-supplier lookups."""
    headers, _, _, _ = await _reported_env(client)
    selects = await _count_selects(client, headers, "/v1/reports/collection/by-supplier")
    assert selects <= 11, f"per-supplier lookups detected: {selects} SELECTs"
