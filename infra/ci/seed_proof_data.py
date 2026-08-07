"""Seed a real dairy into the configured database (CI-001).

The backup/restore proof is only worth running against **real business data**:
an empty database restores perfectly and proves nothing. This drives the
platform's own API — the same endpoints an operator uses — to produce a
complete chain: organization, center, supplier, rate card, collection,
pricing, settlement, payment, receipt, notifications.

It talks to the app in-process over ASGI rather than over the network, so it
needs no running server, and it uses the database named by
`LACTEVA_DATABASE_URL` — which under the proof script is a real PostgreSQL.

Run with `LACTEVA_ENV=staging` so the app does NOT create tables itself: the
schema must come from Alembic, because applying migrations from empty is one
of the things being proven.
"""

import asyncio
import json
import os
import pathlib
import sys
from datetime import date, timedelta

from httpx import ASGITransport, AsyncClient

PASSWORD = os.environ.get("SEED_PASSWORD", "correct-horse-battery")


async def _expect(response, *codes: int, what: str):
    if response.status_code not in codes:
        raise SystemExit(f"seed failed at {what}: {response.status_code} {response.text[:400]}")
    return response.json() if response.content else {}


async def seed() -> dict:
    from platform_core.main import create_app

    await _bootstrap()
    app = create_app()
    # Deliberately NOT the app lifespan: it starts background loops (relay,
    # consumers, health sampling) whose sessions would interleave with the
    # seeding requests. On SQLite's StaticPool that shares one connection and
    # silently loses writes; on PostgreSQL it merely adds nondeterminism.
    # Seeding drives the consumers explicitly instead, below.
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://seed") as c:
        # --- platform admin, organization, tenant admin -----------------
        await _expect(
            await c.post(
                "/v1/auth/register",
                json={"email": "root@proof.example", "password": PASSWORD, "full_name": "Root"},
            ),
            201,
            what="register root",
        )
        await _grant_platform_admin("root@proof.example")
        pair = await _expect(
            await c.post(
                "/v1/auth/token",
                json={"email": "root@proof.example", "password": PASSWORD},
            ),
            200,
            what="root login",
        )
        root = {"Authorization": f"Bearer {pair['access_token']}"}

        org = await _expect(
            await c.post(
                "/v1/organizations",
                json={"name": "Proof Dairy", "slug": "proof", "country_code": "ke"},
                headers=root,
            ),
            201,
            what="create organization",
        )
        inv = await _expect(
            await c.post(
                "/v1/invitations",
                json={"email": "manager@proof.example", "role_name": "tenant-admin"},
                headers={**root, "X-Tenant-ID": org["id"]},
            ),
            201,
            what="invite manager",
        )
        accepted = await _expect(
            await c.post(
                "/v1/invitations/accept",
                json={
                    "token": inv["invitation_token"],
                    "password": PASSWORD,
                    "full_name": "Proof Manager",
                },
            ),
            201,
            what="accept invitation",
        )
        manager_id = accepted["id"]
        pair = await _expect(
            await c.post(
                "/v1/auth/token",
                json={
                    "email": "manager@proof.example",
                    "password": PASSWORD,
                    "tenant_id": org["id"],
                },
            ),
            200,
            what="manager login",
        )
        h = {"Authorization": f"Bearer {pair['access_token']}"}

        # --- structure ---------------------------------------------------
        ws = await _expect(
            await c.post("/v1/workspaces", json={"name": "North", "slug": "north"}, headers=h),
            201,
            what="workspace",
        )
        branch = await _expect(
            await c.post(
                "/v1/branches",
                json={"workspace_id": ws["id"], "name": "Kilima Hill", "code": "KH"},
                headers=h,
            ),
            201,
            what="branch",
        )
        center = await _expect(
            await c.post(
                "/v1/collection-centers",
                json={"branch_id": branch["id"], "name": "Kilima Center", "code": "KH-C1"},
                headers=h,
            ),
            201,
            what="center",
        )
        supplier = await _expect(
            await c.post(
                "/v1/suppliers",
                json={"full_name": "Amina Njoroge", "phone": "+254700000001"},
                headers=h,
            ),
            201,
            what="supplier",
        )

        # --- pricing ------------------------------------------------------
        card = await _expect(
            await c.post(
                "/v1/rate-cards",
                json={
                    "name": "Proof Card",
                    "currency": "KES",
                    "effective_from": "2026-01-01",
                    "description": "CI-001 proof",
                },
                headers=h,
            ),
            201,
            what="rate card",
        )
        await _expect(
            await c.post(
                f"/v1/rate-cards/{card['id']}/centers",
                json={"center_id": center["id"]},
                headers=h,
            ),
            201,
            what="card center scope",
        )
        await _expect(
            await c.post(
                f"/v1/rate-cards/{card['id']}/products",
                json={"product_code": "RAW-COW-MILK"},
                headers=h,
            ),
            201,
            what="card product scope",
        )
        matrix = await _expect(
            await c.post(
                "/v1/pricing-matrices",
                json={
                    "rate_card_id": card["id"],
                    "product_code": "RAW-COW-MILK",
                    "dimension_code": "FAT",
                    "name": "FAT bands",
                },
                headers=h,
            ),
            201,
            what="matrix",
        )
        for lo, hi, price in ((3.0, 4.0, 40.0), (4.0, 5.0, 45.0), (5.0, 6.0, 50.0)):
            await _expect(
                await c.post(
                    f"/v1/pricing-matrices/{matrix['id']}/rows",
                    json={"from_value": lo, "to_value": hi, "unit_price": price},
                    headers=h,
                ),
                201,
                what="matrix row",
            )
        for step in ("submit", "approve", "publish"):
            await _expect(
                await c.post(f"/v1/rate-cards/{card['id']}/{step}", headers=h),
                200,
                what=f"card {step}",
            )

        # --- milk collection ------------------------------------------------
        # DR-001. The recovery proof compares source and restored fact for
        # fact, and a table with no rows compares equal trivially — so the
        # seed has to produce real collection activity, not just the
        # settlement chain that sits downstream of it.
        #
        # Driven through the platform's own endpoints, so the transaction
        # event log, the completion snapshot and the metrics rows are written
        # by the code that writes them in production rather than by fixtures.
        # A center opens only once it has operating hours and is active —
        # both are real preconditions, so the seed satisfies them the way an
        # operator would rather than writing the status directly.
        await _expect(
            await c.put(
                f"/v1/collection-centers/{center['id']}/operating-hours",
                json={
                    "windows": [
                        {"day_of_week": d, "opens": "05:00:00", "closes": "20:00:00"}
                        for d in range(7)
                    ]
                },
                headers=h,
            ),
            200,
            what="operating hours",
        )
        await _expect(
            await c.post(
                f"/v1/collection-centers/{center['id']}/status",
                json={"status": "active"},
                headers=h,
            ),
            200,
            what="activate center",
        )
        # A supplier delivers milk only once activated — and cannot be
        # activated before being attached to a center that receives it, so
        # the order here is the platform's rule, not a preference.
        await _expect(
            await c.post(
                f"/v1/suppliers/{supplier['id']}/centers",
                json={"center_id": center["id"]},
                headers=h,
            ),
            201,
            what="attach supplier to center",
        )
        await _expect(
            await c.post(
                f"/v1/suppliers/{supplier['id']}/status",
                json={"status": "active"},
                headers=h,
            ),
            200,
            what="activate supplier",
        )

        # A center is only READY with an operator and working equipment. The
        # readiness rules are real, so the seed satisfies them the way a
        # depot would — which also gives the recovery proof device, health
        # and operator-assignment rows to compare.
        await _expect(
            await c.post(
                f"/v1/collection-centers/{center['id']}/operators",
                json={"user_id": manager_id, "role_label": "operator"},
                headers=h,
            ),
            201,
            what="assign operator",
        )
        for category, serial in (
            ("scale", "SCALE-0001"),
            ("milk_analyzer", "ANALYZER-0001"),
            ("printer", "PRINTER-0001"),
        ):
            device = await _expect(
                await c.post(
                    "/v1/devices",
                    json={
                        "category": category,
                        "name": f"Kilima {category}",
                        "serial_number": serial,
                    },
                    headers=h,
                ),
                201,
                what=f"device {category}",
            )
            await _expect(
                await c.post(
                    f"/v1/devices/{device['id']}/assign",
                    json={"center_id": center["id"]},
                    headers=h,
                ),
                200,
                what=f"assign {category}",
            )
            await _expect(
                await c.post(
                    f"/v1/devices/{device['id']}/status",
                    json={"status": "active"},
                    headers=h,
                ),
                200,
                what=f"activate {category}",
            )

        session_row = await _expect(
            await c.post(
                "/v1/collection-sessions",
                json={"center_id": center["id"], "label": "morning"},
                headers=h,
            ),
            201,
            what="collection session",
        )
        collections_made = []
        # One accepted and one rejected: a rejection exercises a different
        # terminal state, and a restore that loses the distinction between
        # "accepted" and "rejected" milk is a restore that changes what a
        # farmer is owed.
        for index, (fat, decision) in enumerate(((4.2, "accept"), (2.1, "reject")), start=1):
            tx = await _expect(
                await c.post(
                    "/v1/milk-transactions",
                    json={"session_id": session_row["id"], "center_id": center["id"]},
                    headers=h,
                ),
                201,
                what=f"transaction {index}",
            )
            await _expect(
                await c.post(
                    f"/v1/milk-transactions/{tx['id']}/identify",
                    json={"method": "manual", "supplier_id": supplier["id"]},
                    headers=h,
                ),
                200,
                what=f"identify {index}",
            )
            await _expect(
                await c.post(
                    f"/v1/milk-transactions/{tx['id']}/milk",
                    json={
                        "milk_type": "cow",
                        "container_type": "can",
                        "container_identifier": f"CAN-{index:03d}",
                        "temperature_c": 4.0,
                    },
                    headers=h,
                ),
                200,
                what=f"milk info {index}",
            )
            await _expect(
                await c.post(
                    f"/v1/milk-transactions/{tx['id']}/weight",
                    json={"source": "manual", "unit": "kg", "gross": 45.5, "tare": 5.5},
                    headers=h,
                ),
                200,
                what=f"weight {index}",
            )
            await _expect(
                await c.post(
                    f"/v1/milk-transactions/{tx['id']}/quality",
                    json={"source": "manual", "fat": fat, "snf": 8.5, "clr": 28.0},
                    headers=h,
                ),
                200,
                what=f"quality {index}",
            )
            body = {"reason": "fat below the accepted floor"} if decision == "reject" else None
            await _expect(
                await c.post(
                    f"/v1/milk-transactions/{tx['id']}/{decision}",
                    json=body,
                    headers=h,
                ),
                200,
                what=f"{decision} {index}",
            )
            await _expect(
                await c.post(f"/v1/milk-transactions/{tx['id']}/complete", headers=h),
                200,
                what=f"complete {index}",
            )
            collections_made.append(tx["id"])

        await _expect(
            await c.post(
                f"/v1/collection-sessions/{session_row['id']}/close",
                headers=h,
            ),
            200,
            what="close session",
        )

        # --- settlement, payment, receipt ---------------------------------
        today = date.today()
        settlement = await _expect(
            await c.post(
                "/v1/settlements",
                json={
                    "supplier_id": supplier["id"],
                    "center_id": center["id"],
                    "period_from": (today - timedelta(days=30)).isoformat(),
                    "period_to": today.isoformat(),
                    "currency": "KES",
                },
                headers=h,
            ),
            201,
            what="settlement",
        )
        calc = await _price_one(c, h, center["id"])
        await _expect(
            await c.post(
                f"/v1/settlements/{settlement['id']}/calculations",
                json={"calculation_id": calc},
                headers=h,
            ),
            201,
            what="settlement line",
        )
        for step in ("calculate", "finalize"):
            settlement = await _expect(
                await c.post(f"/v1/settlements/{settlement['id']}/{step}", headers=h),
                200,
                what=f"settlement {step}",
            )

        payment = await _expect(
            await c.post(
                "/v1/payments",
                json={
                    "supplier_id": supplier["id"],
                    "currency": "KES",
                    "method": "MOBILE_MONEY",
                    "allocations": [{"settlement_id": settlement["id"]}],
                },
                headers=h,
            ),
            201,
            what="payment",
        )
        for step, body in (
            ("submit", {}),
            ("execute", {}),
            ("complete", {"reference": "MPESA-PROOF"}),
        ):
            await _expect(
                await c.post(f"/v1/payments/{payment['id']}/{step}", json=body, headers=h),
                200,
                what=f"payment {step}",
            )

        # Drive the consumers so the receipt and notifications exist.
        await _run_consumers(times=3)

        receipts = await _expect(await c.get("/v1/receipts", headers=h), 200, what="receipts")
        if receipts["total"] != 1:
            raise SystemExit(f"expected exactly one receipt, got {receipts['total']}")

        return {
            "organization": org["id"],
            "collection_session": session_row["id"],
            "collections": len(collections_made),
            "settlement": settlement["settlement_number"],
            "settlement_net": str(settlement["net_amount"]),
            "payment": payment["payment_number"],
            "payment_amount": str(payment["amount"]),
            "receipt": receipts["items"][0]["receipt_number"],
        }


async def _bootstrap() -> None:
    """What the app lifespan would do, minus the background loops: register
    the consumer/projection models and seed the system roles."""
    from platform_core.core.rls import platform_factory
    from platform_core.modules.authz.service import AuthzService
    from platform_core.modules.event_relay.consumers import discover_consumers
    from platform_core.modules.event_relay.projections import discover_projections

    discover_consumers()
    discover_projections()
    async with platform_factory("proof seed: system-role catalog")() as session:
        await AuthzService(session).ensure_system_roles()
        await session.commit()


async def _price_one(c, headers, center_id: str) -> str:
    resolved = await _expect(
        await c.post(
            "/v1/pricing/resolve",
            json={
                "center_id": center_id,
                "product_code": "RAW-COW-MILK",
                "transaction_date": date.today().isoformat(),
                "dimension_code": "FAT",
                "value": 4.2,
            },
            headers=headers,
        ),
        200,
        what="pricing resolve",
    )
    calculated = await _expect(
        await c.post(
            "/v1/pricing/calculate",
            json={
                "row_id": resolved["row_id"],
                "quantity": 125.5,
                "transaction_date": date.today().isoformat(),
            },
            headers=headers,
        ),
        200,
        what="pricing calculate",
    )
    return calculated["calculation_id"]


async def _run_consumers(times: int) -> None:
    from platform_core.core.rls import platform_factory
    from platform_core.modules.event_relay.consumers import ConsumerRunner

    # VER-001: `platform_factory`, not the plain session factory. A consumer
    # drains the log for EVERY tenant, so its session has no tenant to bind
    # and row-level security makes an unbound session see nothing at all. With
    # a plain factory the runner found zero events, produced no receipt, and
    # reported success — which is how this ran green until a real PostgreSQL
    # enforced the policies.
    #
    # `main.py` already builds it this way; only the seeder did not.
    runner = ConsumerRunner(platform_factory("proof seed: drive consumers to completion"))
    for _ in range(times):
        await runner.run_once()


async def _grant_platform_admin(email: str) -> None:
    """Registration cannot grant platform-admin to itself, by design."""
    from sqlalchemy import select

    from platform_core.core.rls import platform_factory
    from platform_core.modules.authz.models import Role, UserRole
    from platform_core.modules.identity.models import User

    # Cross-tenant by definition: it grants a PLATFORM role, and the lookup
    # spans tenants. Under RLS an unbound session would find neither row.
    async with platform_factory("proof seed: grant platform-admin")() as session:
        user = await session.scalar(select(User).where(User.email == email))
        role = await session.scalar(select(Role).where(Role.name == "platform-admin"))
        if user is None or role is None:
            raise SystemExit("could not grant platform-admin: user or role missing")
        session.add(UserRole(user_id=user.id, role_id=role.id, tenant_id=None))
        await session.commit()


if __name__ == "__main__":
    if not os.environ.get("LACTEVA_DATABASE_URL"):
        raise SystemExit("LACTEVA_DATABASE_URL must point at the database to seed")
    summary = asyncio.run(seed())
    payload = json.dumps(summary, indent=2)
    # VER-001: the application's structured logs also go to stdout, so
    # redirecting stdout to a file produced a "summary" that was one truncated
    # log line — which is what the proof's report then quoted as evidence.
    # An explicit path keeps the machine-readable result separate from the
    # human-readable log.
    if len(sys.argv) > 1:
        pathlib.Path(sys.argv[1]).write_text(payload + "\n")
    sys.stdout.write(payload + "\n")
