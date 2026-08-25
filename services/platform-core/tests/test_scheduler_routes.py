"""Route-aware scheduled generation (DEMO-036).

The claim:

    **When a dairy has routes, the scheduler generates route by route. When it
    has none, it behaves exactly as it did before — byte for byte.**

Two properties carry the milestone and both are about not lying:

* **one claim per tenant-day, many routes within it.** DEMO-035 found that
  claiming the tenant's date PER ROUTE makes the first route win and every
  later one silently generate nothing. The fix is not to drop the claim — it is
  what stops two workers doing the same dairy twice — but to hold it once and
  iterate underneath;
* **a failing route fails the DAY.** A partial round recorded as `success` is
  the worst outcome available here: an operator reading `success` has no reason
  to go looking for the round that never went out.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from platform_core.core import db
from platform_core.modules.delivery.generation import RoundScope
from platform_core.modules.delivery.scheduler import Tenant, run_for_tenant, run_once
from platform_core.modules.logistics.service import scheduled_round_scopes
from tests.test_delivery_scheduler import HOUR, _dairy_with_plans
from tests.test_localization import _tenant_admin_for

DAY = date(2026, 8, 17)


# --- helpers -------------------------------------------------------------------


def _tenant(org) -> Tenant:
    return Tenant(id=uuid.UUID(org["id"]), slug=org["slug"], timezone=org["timezone"])


async def _customers(client, admin):
    page = (await client.get("/v1/customers?limit=100", headers=admin)).json()
    return page["items"]


async def _route(client, admin, code: str, customer_ids: list[str]):
    route = (
        await client.post("/v1/routes", json={"code": code, "name": f"Round {code}"}, headers=admin)
    ).json()
    r = await client.put(
        f"/v1/routes/{route['id']}/stops",
        json={"customer_ids": customer_ids},
        headers=admin,
    )
    assert r.status_code == 200, r.text
    return route


async def _deliveries(client, admin, day=DAY):
    return (
        await client.get(
            "/v1/deliveries",
            params={"date_from": str(day), "date_to": str(day)},
            headers=admin,
        )
    ).json()


async def _scheduled(tenant_id, day=DAY):
    """The provider, called the way the scheduler calls it."""
    from platform_core.core.rls import rebind_tenant

    async with db.get_session_factory()() as session:
        await rebind_tenant(session, tenant_id)
        return await scheduled_round_scopes(session, tenant_id, day)


# --- 1: no routes means no change ------------------------------------------------


async def test_a_dairy_with_no_routes_generates_exactly_as_before(client):
    """The fallback, and the reason route adoption stays optional."""
    org, admin = await _dairy_with_plans(client)

    run = await run_for_tenant(
        _tenant(org),
        generation_hour=HOUR,
        force_date=DAY,
        route_scopes=scheduled_round_scopes,
    )

    assert run is not None
    assert run.status == "success"
    assert run.created == 3
    assert (await _deliveries(client, admin))["total"] == 3


async def test_the_provider_reports_no_rounds_when_there_are_no_routes(client):
    """An empty list is the fallback signal, and it has to be honest."""
    org, _admin = await _dairy_with_plans(client)
    assert await _scheduled(uuid.UUID(org["id"])) == []


async def test_a_dairy_whose_routes_are_all_empty_falls_back(client):
    """A route with no stops is not a round.

    Skipped rather than refused: the scheduler is generating every route a
    dairy has, and one unfinished route must not stop the others going out.
    With NO usable route left, the dairy is indistinguishable from one that
    never adopted routes — so it gets the whole-tenant round.
    """
    org, admin = await _dairy_with_plans(client)
    r = await client.post(
        "/v1/routes", json={"code": "EMPTY", "name": "Not finished yet"}, headers=admin
    )
    assert r.status_code == 201, r.text

    assert await _scheduled(uuid.UUID(org["id"])) == []

    run = await run_for_tenant(
        _tenant(org), generation_hour=HOUR, force_date=DAY, route_scopes=scheduled_round_scopes
    )
    assert run.created == 3, "the whole-tenant fallback did not run"


async def test_an_inactive_route_is_not_scheduled(client):
    org, admin = await _dairy_with_plans(client)
    customers = await _customers(client, admin)
    route = await _route(client, admin, "R-01", [c["id"] for c in customers[:2]])

    async with db.get_session_factory()() as session:
        from platform_core.modules.logistics.models import Route

        row = await session.get(Route, uuid.UUID(route["id"]))
        row.active = False
        await session.commit()

    assert await _scheduled(uuid.UUID(org["id"])) == []


# --- 2-4: routes drive the round -------------------------------------------------


async def test_a_dairy_with_one_route_generates_that_route(client):
    org, admin = await _dairy_with_plans(client)
    customers = await _customers(client, admin)
    await _route(client, admin, "R-01", [c["id"] for c in customers[:2]])

    run = await run_for_tenant(
        _tenant(org), generation_hour=HOUR, force_date=DAY, route_scopes=scheduled_round_scopes
    )

    assert run.status == "success"
    # TWO, not three: the household off the route is not on this round. That
    # difference is the entire milestone.
    assert run.created == 2, run.created
    page = await _deliveries(client, admin)
    assert page["total"] == 2
    assert {d["customer_id"] for d in page["items"]} == {c["id"] for c in customers[:2]}


async def test_every_route_is_generated_exactly_once(client):
    org, admin = await _dairy_with_plans(client, count=4)
    customers = await _customers(client, admin)
    await _route(client, admin, "R-01", [c["id"] for c in customers[:2]])
    await _route(client, admin, "R-02", [c["id"] for c in customers[2:]])

    run = await run_for_tenant(
        _tenant(org), generation_hour=HOUR, force_date=DAY, route_scopes=scheduled_round_scopes
    )

    assert run.created == 4, "a route was skipped or generated twice"
    assert (await _deliveries(client, admin))["total"] == 4


async def test_routes_are_scheduled_in_a_stable_order(client):
    """So a log of two passes reads the same way twice.

    By route CODE, and within a route by the day's own order — morning before
    evening. Deliberately not alphabetical, which would send the evening van
    first.
    """
    org, admin = await _dairy_with_plans(client, count=4)
    customers = await _customers(client, admin)
    await _route(client, admin, "R-02", [c["id"] for c in customers[2:]])
    await _route(client, admin, "R-01", [c["id"] for c in customers[:2]])

    labels = [s.label for s in await _scheduled(uuid.UUID(org["id"]))]
    assert labels == [
        "R-01/morning",
        "R-01/evening",
        "R-02/morning",
        "R-02/evening",
    ], labels

    # Stable: asking twice gives the same sequence.
    assert [s.label for s in await _scheduled(uuid.UUID(org["id"]))] == labels


async def test_each_route_is_scoped_to_its_own_stops(client):
    org, admin = await _dairy_with_plans(client, count=4)
    customers = await _customers(client, admin)
    await _route(client, admin, "R-01", [customers[0]["id"]])
    await _route(client, admin, "R-02", [customers[1]["id"]])

    scopes = {s.label: s for s in await _scheduled(uuid.UUID(org["id"]))}
    assert scopes["R-01/morning"].customer_ids == frozenset({uuid.UUID(customers[0]["id"])})
    assert scopes["R-02/morning"].customer_ids == frozenset({uuid.UUID(customers[1]["id"])})


# --- 5: tenant isolation ---------------------------------------------------------


async def test_another_dairys_routes_are_never_scheduled(client):
    org_a, admin_a = await _dairy_with_plans(client, count=2)
    customers_a = await _customers(client, admin_a)
    await _route(client, admin_a, "R-01", [c["id"] for c in customers_a])

    org_b, _admin_b = await _tenant_admin_for(
        client, country="KE", slug="scheduler-036-b", email="admin@sched036b.example"
    )

    assert await _scheduled(uuid.UUID(org_b["id"])) == []

    # And dairy A's round contains only dairy A's households.
    scopes = await _scheduled(uuid.UUID(org_a["id"]))
    every_id = {cid for s in scopes for cid in s.customer_ids}
    assert every_id == {uuid.UUID(c["id"]) for c in customers_a}


# --- 6-7: the day's rules still decide -------------------------------------------


async def test_a_holiday_suppresses_the_route_round_too(client):
    """The calendar outranks the route: a shut dairy sends no van."""
    org, admin = await _dairy_with_plans(client)
    customers = await _customers(client, admin)
    await _route(client, admin, "R-01", [c["id"] for c in customers])

    r = await client.put(
        "/v1/organization/calendar/days",
        json={"day": str(DAY), "working": False, "kind": "holiday", "name": "Shut"},
        headers=admin,
    )
    assert r.status_code == 200, r.text

    run = await run_for_tenant(
        _tenant(org), generation_hour=HOUR, force_date=DAY, route_scopes=scheduled_round_scopes
    )

    assert run.created == 0, "a holiday round went out"
    assert run.status == "holiday", run.status
    assert (await _deliveries(client, admin))["total"] == 0


# --- 8-9: idempotency and concurrency --------------------------------------------


async def test_a_second_scheduler_pass_generates_nothing_more(client):
    org, admin = await _dairy_with_plans(client, count=4)
    customers = await _customers(client, admin)
    await _route(client, admin, "R-01", [c["id"] for c in customers[:2]])
    await _route(client, admin, "R-02", [c["id"] for c in customers[2:]])

    first = await run_for_tenant(
        _tenant(org), generation_hour=HOUR, force_date=DAY, route_scopes=scheduled_round_scopes
    )
    second = await run_for_tenant(
        _tenant(org), generation_hour=HOUR, force_date=DAY, route_scopes=scheduled_round_scopes
    )

    assert first.created == 4
    # The RECORD is the day's, and the day still created four.
    assert second.created == 4
    assert (await _deliveries(client, admin))["total"] == 4


async def test_the_tenant_day_is_claimed_once_and_routes_run_underneath_it(client):
    """DEMO-035's finding, guarded at the scheduler.

    Exactly ONE `delivery_generation_run` row exists for the tenant's day, no
    matter how many routes it has — the claim is per tenant-day, and the routes
    are iterated inside it. A row per route would mean the second route lost
    the claim and generated nothing.
    """
    from platform_core.modules.delivery.models import DeliveryGenerationRun

    org, admin = await _dairy_with_plans(client, count=4)
    customers = await _customers(client, admin)
    await _route(client, admin, "R-01", [c["id"] for c in customers[:2]])
    await _route(client, admin, "R-02", [c["id"] for c in customers[2:]])

    await run_for_tenant(
        _tenant(org), generation_hour=HOUR, force_date=DAY, route_scopes=scheduled_round_scopes
    )

    async with db.get_session_factory()() as session:
        rows = (
            await session.scalars(
                select(DeliveryGenerationRun).where(
                    DeliveryGenerationRun.tenant_id == uuid.UUID(org["id"]),
                    DeliveryGenerationRun.business_date == DAY,
                )
            )
        ).all()
    assert len(rows) == 1, f"{len(rows)} run rows for one tenant-day"
    assert rows[0].created == 4, "the second route lost the claim and generated nothing"


# --- 10: a failing route must not let the others look fine -----------------------


async def test_a_failing_route_fails_the_day_rather_than_reporting_success(client):
    """The failure mode this milestone must not have.

    A partial round recorded as `success` gives an operator no reason to look
    for the round that never went out.
    """
    org, admin = await _dairy_with_plans(client, count=4)
    customers = await _customers(client, admin)

    async def exploding_scopes(session, tenant_id, day):
        return [
            RoundScope(
                label="R-01/morning",
                customer_ids=frozenset({uuid.UUID(customers[0]["id"])}),
                slot="morning",
            ),
            RoundScope(
                label="R-02/morning", customer_ids=frozenset({"not-a-uuid"}), slot="morning"
            ),
        ]

    run = await run_for_tenant(
        _tenant(org), generation_hour=HOUR, force_date=DAY, route_scopes=exploding_scopes
    )

    assert run.status == "failed", run.status
    assert "R-02/morning" in run.error, run.error


async def test_a_provider_that_raises_fails_the_day(client):
    org, _admin = await _dairy_with_plans(client)

    async def broken(session, tenant_id, day):
        raise RuntimeError("the route service is down")

    run = await run_for_tenant(
        _tenant(org), generation_hour=HOUR, force_date=DAY, route_scopes=broken
    )
    assert run.status == "failed", run.status
    assert "route service is down" in run.error


# --- 11-12: nothing else moved ---------------------------------------------------


async def test_the_scheduler_without_a_provider_is_unchanged(client):
    """Backwards compatibility, asserted rather than assumed.

    `run_for_tenant` called the pre-DEMO-036 way — no provider at all — must
    still generate the whole tenant's round.
    """
    org, admin = await _dairy_with_plans(client)
    customers = await _customers(client, admin)
    await _route(client, admin, "R-01", [customers[0]["id"]])

    run = await run_for_tenant(_tenant(org), generation_hour=HOUR, force_date=DAY)

    assert run.created == 3, "the no-provider path stopped generating the whole tenant"


async def test_route_aware_generation_moves_no_money(client):
    from platform_core.modules.billing.models import CustomerInvoice
    from platform_core.modules.delivery.models import MilkDelivery

    org, admin = await _dairy_with_plans(client, count=4)
    customers = await _customers(client, admin)
    await _route(client, admin, "R-01", [c["id"] for c in customers[:2]])

    async with db.get_session_factory()() as session:
        before = await session.scalar(select(func.count()).select_from(CustomerInvoice))

    await run_for_tenant(
        _tenant(org), generation_hour=HOUR, force_date=DAY, route_scopes=scheduled_round_scopes
    )

    async with db.get_session_factory()() as session:
        after = await session.scalar(select(func.count()).select_from(CustomerInvoice))
        billed = await session.scalar(select(func.coalesce(func.sum(MilkDelivery.amount), 0)))
    assert after == before
    assert Decimal(billed or 0) == Decimal("0.00")


async def test_the_scheduler_loop_is_actually_wired_to_the_provider(client):
    """The wiring is the whole feature, so it is asserted.

    The provider is passed at the composition point in `main.py`. Nothing else
    imports it, so a refactor that dropped the argument would leave every dairy
    silently on the fallback path with no test failing anywhere else.
    """
    import inspect

    from platform_core import main

    source = inspect.getsource(main._delivery_scheduler_loop)
    assert "scheduled_round_scopes" in source
    assert "route_scopes=scheduled_round_scopes" in source


async def test_run_once_passes_the_provider_through(client):
    """`run_once` is what the loop calls; the argument has to survive the hop."""
    seen: list[str] = []

    async def recording(session, tenant_id, day):
        seen.append(str(tenant_id))
        return []

    org, _admin = await _dairy_with_plans(client)
    # An EXPLICIT instant, not the wall clock. `run_once` skips a tenant whose
    # local hour has not yet reached `generation_hour` (HOUR = 5), so reading
    # the real clock made this test fail every night between midnight and
    # 05:00 local — green for nineteen hours a day, which is the worst kind of
    # test. 06:00 UTC is 11:30 IST, comfortably past the gate, and is the same
    # instant the sibling tests in `test_delivery_scheduler.py` already use.
    await run_once(
        generation_hour=HOUR,
        now=datetime(2026, 8, 15, 6, 0, tzinfo=ZoneInfo("UTC")),
        route_scopes=recording,
    )

    assert org["id"] in seen, "run_once did not hand the provider to the tenant pass"


async def test_both_slots_are_scheduled_for_a_route(client):
    """A route serves whichever slots its households' plans use.

    Both are offered; the generator's slot narrowing then produces only what is
    actually due, so a dairy with morning-only plans gets a morning round and
    an empty evening one at no cost.
    """
    org, admin = await _dairy_with_plans(client)
    customers = await _customers(client, admin)
    await _route(client, admin, "R-01", [c["id"] for c in customers])

    scopes = await _scheduled(uuid.UUID(org["id"]))
    assert {s.slot for s in scopes} == {"morning", "evening"}
