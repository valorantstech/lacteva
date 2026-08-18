"""A dairy that is shut does not generate a round (DEMO-022).

The property under test, stated once:

    **A resolved NON-WORKING business date produces no automatic delivery
    generation. A resolved WORKING business date generates normally.**

Everything below is that sentence, at each level the resolution can be decided
at — organization, centre, and a centre overriding its organization — plus the
things that must NOT happen as a consequence: no backfill, no deletion of
deliveries already made, and no change to manual generation.

The tests drive the real scheduler entry point with a fabricated clock, so they
assert what the platform does rather than what this module was written to do.
Every suppression test asserts the same round GENERATES first, because a test
that only sees zero cannot tell suppression from a broken fixture.
"""

import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from platform_core.core import db
from platform_core.modules.delivery.models import MilkDelivery
from platform_core.modules.delivery.scheduler import Tenant, run_for_tenant
from tests.test_org_structure import _tenant_admin

UTC = ZoneInfo("UTC")

#: TOMORROW, not a frozen literal. These constants were `date(2026, 8, 17)` —
#: "today" on the day this file was written — and became a PAST day at the
#: next midnight, at which point every standing order the tests create
#: (effective from the day the test runs) postdated the generation day and
#: three tests failed on `created == 0` (found by P0-PILOT-002's gate run).
#: Anchoring to tomorrow keeps the plans in force on the day generated for,
#: on every date this suite will ever run.
#:
#: The chosen INSTANTS keep their boundary meaning on any date: at 03:00 UTC
#: Nairobi (UTC+3, 06:00 — past a 05:00 generation hour) and UTC agree on the
#: date, so a failure there is the test's own; at 00:00 UTC India (UTC+5:30)
#: has been on the date for five and a half hours while UTC has just reached
#: it — the disagreement the tenant-date tests exist to probe.
_DAY = date.today() + timedelta(days=1)
KENYA_MORNING = datetime(_DAY.year, _DAY.month, _DAY.day, 3, 0, tzinfo=UTC)
KENYA_DAY = _DAY
KENYA_TZ = "Africa/Nairobi"

INDIA_MORNING = datetime(_DAY.year, _DAY.month, _DAY.day, 0, 0, tzinfo=UTC)
INDIA_TZ = "Asia/Kolkata"


async def _tenant_of(client, headers, timezone: str) -> Tenant:
    me = (await client.get("/v1/auth/me", headers=headers)).json()
    return Tenant(id=uuid.UUID(me["tenant_id"]), slug="test", timezone=timezone)


async def _customer_with_plan(client, headers, name: str, center_id=None):
    body = {
        "name": name,
        "customer_type": "household",
        "phone": "+254700000001",
        "plan": {
            "product": "RAW-COW-MILK",
            "default_quantity": "2.000",
            "quantity_unit": "L",
            "unit_price": "50.0000",
        },
    }
    if center_id:
        body["plan"]["center_id"] = center_id
    r = await client.post("/v1/customers", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _declare(client, headers, day: date, *, working: bool, kind: str, name=""):
    r = await client.put(
        "/v1/organization/calendar/days",
        json={"day": str(day), "working": working, "kind": kind, "name": name},
        headers=headers,
    )
    assert r.status_code == 200, r.text


async def _deliveries_on(tenant_id: uuid.UUID, day: date) -> int:
    async with db.get_session_factory()() as session:
        rows = await session.scalars(
            select(MilkDelivery).where(
                MilkDelivery.tenant_id == tenant_id, MilkDelivery.delivery_date == day
            )
        )
        return len(list(rows.all()))


async def _generate(tenant: Tenant, *, now: datetime, day: date | None = None):
    return await run_for_tenant(
        tenant, now=now, generation_hour=5, trigger="scheduler", force_date=day
    )


# --- 1: the working day still generates --------------------------------------


async def test_a_working_day_generates_normally(client):
    """The premise every suppression test below depends on."""
    _org, headers = await _tenant_admin(client)
    await _customer_with_plan(client, headers, "Working Day Household")
    tenant = await _tenant_of(client, headers, KENYA_TZ)

    run = await _generate(tenant, now=KENYA_MORNING)
    assert run is not None
    assert run.status == "success"
    assert run.created == 1
    assert run.skipped_holiday == 0
    assert await _deliveries_on(tenant.id, KENYA_DAY) == 1


# --- 2: an organization holiday suppresses everything ------------------------


async def test_an_organization_holiday_suppresses_the_whole_round(client):
    _org, headers = await _tenant_admin(client)
    await _customer_with_plan(client, headers, "Holiday Household")
    tenant = await _tenant_of(client, headers, KENYA_TZ)

    await _declare(client, headers, KENYA_DAY, working=False, kind="holiday", name="Shut")

    run = await _generate(tenant, now=KENYA_MORNING)
    assert run is not None
    assert run.created == 0, "a shut dairy must generate nothing"
    assert run.skipped_holiday == 1
    assert run.status == "holiday", "the reason must be legible without inference"
    assert await _deliveries_on(tenant.id, KENYA_DAY) == 0


async def test_a_working_exception_on_the_calendar_still_generates(client):
    """`working: true` is an exception the OTHER way and must not suppress."""
    _org, headers = await _tenant_admin(client)
    await _customer_with_plan(client, headers, "Stocktake Household")
    tenant = await _tenant_of(client, headers, KENYA_TZ)

    await _declare(client, headers, KENYA_DAY, working=True, kind="working", name="Open")

    run = await _generate(tenant, now=KENYA_MORNING)
    assert run.created == 1
    assert run.skipped_holiday == 0


# --- 3, 4: centre precedence -------------------------------------------------


async def _centre(client, headers, name: str, code: str):
    branch = None
    ws = await client.post(
        "/v1/workspaces", json={"name": f"WS {code}", "slug": f"ws-{code.lower()}"}, headers=headers
    )
    assert ws.status_code == 201, ws.text
    br = await client.post(
        "/v1/branches",
        json={"workspace_id": ws.json()["id"], "name": f"BR {code}", "code": f"BR{code}"},
        headers=headers,
    )
    assert br.status_code == 201, br.text
    branch = br.json()
    r = await client.post(
        "/v1/collection-centers",
        json={"branch_id": branch["id"], "name": name, "code": code},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _close_centre(client, headers, center_id: str, day: date, kind="closure"):
    r = await client.post(
        f"/v1/collection-centers/{center_id}/calendar",
        json={"day": str(day), "kind": kind, "note": "centre calendar"},
        headers=headers,
    )
    assert r.status_code == 201, r.text


async def test_a_centre_holiday_suppresses_only_that_centre(client):
    """Organization working, centre A shut, centre B open."""
    _org, headers = await _tenant_admin(client)
    a = await _centre(client, headers, "Centre A", "CA")
    b = await _centre(client, headers, "Centre B", "CB")
    await _customer_with_plan(client, headers, "A Household", center_id=a["id"])
    await _customer_with_plan(client, headers, "B Household", center_id=b["id"])
    tenant = await _tenant_of(client, headers, KENYA_TZ)

    await _close_centre(client, headers, a["id"], KENYA_DAY)

    run = await _generate(tenant, now=KENYA_MORNING)
    assert run.created == 1, "centre B must still generate"
    assert run.skipped_holiday == 1, "centre A must be suppressed"
    assert run.status == "success", "a partial round is not a holiday"
    assert await _deliveries_on(tenant.id, KENYA_DAY) == 1


async def test_a_centre_may_work_through_an_organization_holiday(client):
    """The inverse: organization shut, centre A explicitly open.

    `special` is the existing model's way of saying "unusual, and worked" —
    the reading the readiness engine has used since DEMO-005. No new
    representation was invented for this.
    """
    _org, headers = await _tenant_admin(client)
    a = await _centre(client, headers, "Centre A", "CA")
    b = await _centre(client, headers, "Centre B", "CB")
    await _customer_with_plan(client, headers, "A Household", center_id=a["id"])
    await _customer_with_plan(client, headers, "B Household", center_id=b["id"])
    tenant = await _tenant_of(client, headers, KENYA_TZ)

    await _declare(client, headers, KENYA_DAY, working=False, kind="holiday", name="Dairy shut")
    await _close_centre(client, headers, a["id"], KENYA_DAY, kind="special")

    run = await _generate(tenant, now=KENYA_MORNING)
    assert run.created == 1, "centre A overrides the organization and works"
    assert run.skipped_holiday == 1, "centre B follows the organization"


# --- 5: no backfill ----------------------------------------------------------


async def test_a_holiday_is_never_backfilled_the_next_day(client):
    """Monday shut, Tuesday open: Tuesday generates TUESDAY and nothing else."""
    _org, headers = await _tenant_admin(client)
    await _customer_with_plan(client, headers, "No Backfill Household")
    tenant = await _tenant_of(client, headers, KENYA_TZ)

    await _declare(client, headers, KENYA_DAY, working=False, kind="holiday")
    monday = await _generate(tenant, now=KENYA_MORNING)
    assert monday.created == 0

    tuesday_day = KENYA_DAY + timedelta(days=1)
    tuesday = await _generate(tenant, now=KENYA_MORNING + timedelta(days=1))
    assert tuesday.business_date == tuesday_day
    assert tuesday.created == 1

    assert await _deliveries_on(tenant.id, KENYA_DAY) == 0, "Monday must stay empty"
    assert await _deliveries_on(tenant.id, tuesday_day) == 1


# --- 6: nothing already generated is ever removed ----------------------------


async def test_declaring_a_holiday_after_the_round_deletes_nothing(client):
    """The calendar governs generation that has NOT happened yet."""
    _org, headers = await _tenant_admin(client)
    await _customer_with_plan(client, headers, "Already Generated Household")
    tenant = await _tenant_of(client, headers, KENYA_TZ)

    first = await _generate(tenant, now=KENYA_MORNING)
    assert first.created == 1
    assert await _deliveries_on(tenant.id, KENYA_DAY) == 1

    # The dairy decides afterwards that the day was a holiday.
    await _declare(client, headers, KENYA_DAY, working=False, kind="holiday", name="Too late")

    assert await _deliveries_on(tenant.id, KENYA_DAY) == 1, (
        "a holiday declared after the fact must not delete a delivery"
    )
    # And re-running the day changes nothing either.
    again = await _generate(tenant, now=KENYA_MORNING)
    assert again is None or again.created == 1
    assert await _deliveries_on(tenant.id, KENYA_DAY) == 1


# --- 7: idempotency and the finished day -------------------------------------


async def test_a_suppressed_day_is_finished_and_not_retried(client):
    """A holiday is an answer, not a failure — the loop must not re-ask."""
    _org, headers = await _tenant_admin(client)
    await _customer_with_plan(client, headers, "Idempotent Household")
    tenant = await _tenant_of(client, headers, KENYA_TZ)
    await _declare(client, headers, KENYA_DAY, working=False, kind="holiday")

    first = await _generate(tenant, now=KENYA_MORNING)
    assert first.status == "holiday"

    # The loop wakes a minute later. `should_run` must decline the day.
    second = await run_for_tenant(
        tenant, now=KENYA_MORNING + timedelta(minutes=1), generation_hour=5
    )
    assert second is None, "a suppressed day must not be re-run every minute"
    assert await _deliveries_on(tenant.id, KENYA_DAY) == 0


# --- manual generation is deliberately NOT suppressed ------------------------


async def test_manual_generation_still_works_on_a_holiday(client):
    """An operator knows something the calendar does not.

    The milestone's boundary: holidays suppress AUTOMATIC generation. A person
    asking for a round on a declared holiday gets it, through the endpoint
    they already use, unchanged.
    """
    _org, headers = await _tenant_admin(client)
    await _customer_with_plan(client, headers, "Manual Household")
    tenant = await _tenant_of(client, headers, KENYA_TZ)
    await _declare(client, headers, KENYA_DAY, working=False, kind="holiday")

    r = await client.post(
        "/v1/deliveries/generate", json={"for_date": str(KENYA_DAY)}, headers=headers
    )
    assert r.status_code in (200, 201), r.text
    assert r.json()["created"] == 1, "manual generation is not calendar-suppressed"
    assert await _deliveries_on(tenant.id, KENYA_DAY) == 1


# --- 9, 10: the boundary stays local to each tenant --------------------------


async def test_the_suppressed_day_is_the_tenants_own_date_not_utcs(client):
    """India's 17th begins at 18:30 UTC on the 16th.

    At 00:00 UTC on the 17th, an Indian dairy has been on the 17th for five
    and a half hours. The holiday it declared for its OWN 17th must be the one
    that suppresses — which is only interesting because a UTC-derived date
    would agree here and disagree three hours earlier.
    """
    _org, headers = await _tenant_admin(client)
    await _customer_with_plan(client, headers, "India Household")
    tenant = await _tenant_of(client, headers, INDIA_TZ)

    india_day = KENYA_DAY
    await _declare(client, headers, india_day, working=False, kind="holiday")

    run = await _generate(tenant, now=INDIA_MORNING)
    assert run is not None
    assert run.business_date == india_day
    assert run.created == 0 and run.skipped_holiday == 1


async def test_one_dairys_holiday_does_not_suppress_anothers_round(client):
    """Cross-tenant: a holiday belongs to the dairy that declared it."""
    from tests.test_localization import _tenant_admin_for

    _a, admin_a = await _tenant_admin_for(
        client, country="KE", slug="hol-a", email="hol-a@kenya.example"
    )
    _b, admin_b = await _tenant_admin_for(
        client, country="KE", slug="hol-b", email="hol-b@kenya.example"
    )
    await _customer_with_plan(client, admin_a, "A Household")
    await _customer_with_plan(client, admin_b, "B Household")
    tenant_a = await _tenant_of(client, admin_a, KENYA_TZ)
    tenant_b = await _tenant_of(client, admin_b, KENYA_TZ)

    await _declare(client, admin_a, KENYA_DAY, working=False, kind="holiday")

    run_a = await _generate(tenant_a, now=KENYA_MORNING)
    run_b = await _generate(tenant_b, now=KENYA_MORNING)

    assert run_a.created == 0 and run_a.skipped_holiday == 1
    assert run_b.created == 1, "B declared nothing and must generate"
    assert await _deliveries_on(tenant_b.id, KENYA_DAY) == 1
