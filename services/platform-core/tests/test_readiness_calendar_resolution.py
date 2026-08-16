"""Readiness and the scheduler agree about what day it is (DEMO-023).

DEMO-022 left one reader of the working-day rule outside the resolver: the
readiness engine queried `center_calendar_entry` itself and decided from the
row. That was correct for a centre and **blind to the organization** — a dairy
could declare a public holiday and every one of its centres would still report
itself ready.

The property under test:

    **Readiness and the delivery scheduler return the SAME effective
    working-day decision, for the same tenant, centre and business date.**

That is stronger than "readiness respects holidays", and it is the one that
cannot rot: it fails if either side is changed alone.
"""

import uuid
from datetime import date

import pytest

from platform_core.core import db
from platform_core.core.tenancy import set_current_tenant
from platform_core.modules.business_calendar.service import WorkingDayResolver
from tests.test_collection_centers import _center_fixture

KENYA_TZ = "Africa/Nairobi"
INDIA_TZ = "Asia/Kolkata"


async def _today_for(client, headers) -> date:
    cal = (await client.get("/v1/organization/calendar", headers=headers)).json()
    return date.fromisoformat(cal["business_date"])


async def _readiness(client, headers, center_id):
    r = await client.get(f"/v1/collection-centers/{center_id}/readiness", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _calendar_check(result) -> dict:
    return next(c for c in result["checks"] if c["rule"] == "center.calendar")


async def _declare_org(client, headers, day: date, *, working: bool, kind: str, name=""):
    r = await client.put(
        "/v1/organization/calendar/days",
        json={"day": str(day), "working": working, "kind": kind, "name": name},
        headers=headers,
    )
    assert r.status_code == 200, r.text


async def _declare_centre(client, headers, center_id, day: date, kind: str, note="note"):
    r = await client.post(
        f"/v1/collection-centers/{center_id}/calendar",
        json={"day": str(day), "kind": kind, "note": note},
        headers=headers,
    )
    assert r.status_code == 201, r.text


async def _centre_for(client, headers, tag: str):
    """A workspace, branch and centre for an already-onboarded admin."""
    ws = await client.post(
        "/v1/workspaces",
        json={"name": f"Workspace {tag}", "slug": f"w-{tag.lower()}"},
        headers=headers,
    )
    assert ws.status_code == 201, ws.text
    br = await client.post(
        "/v1/branches",
        json={"workspace_id": ws.json()["id"], "name": f"Branch {tag}", "code": f"B{tag}"},
        headers=headers,
    )
    assert br.status_code == 201, br.text
    center = await client.post(
        "/v1/collection-centers",
        json={"branch_id": br.json()["id"], "name": f"Centre {tag}", "code": f"C{tag}"},
        headers=headers,
    )
    assert center.status_code == 201, center.text
    return center.json()


# --- 6: the ordinary day is unchanged ----------------------------------------


async def test_an_ordinary_day_still_passes_the_calendar_check(client):
    """The premise: nothing declared anywhere means nothing to report."""
    headers, _branch, center = await _center_fixture(client)
    check = _calendar_check(await _readiness(client, headers, center["id"]))
    assert check["passed"] is True
    assert check["severity"] == "blocking"
    assert check["detail"] == "no calendar exception today"


# --- 2: the organization's holiday now reaches readiness ---------------------


async def test_an_organization_holiday_closes_every_centre(client):
    """The defect DEMO-023 fixes, stated as a test.

    Before this milestone readiness had never heard of the organization
    calendar: a dairy-wide holiday left every centre reporting itself ready.
    """
    headers, _branch, center = await _center_fixture(client)
    today = await _today_for(client, headers)

    before = _calendar_check(await _readiness(client, headers, center["id"]))
    assert before["passed"] is True, "the premise: an ordinary day passes"

    await _declare_org(client, headers, today, working=False, kind="holiday", name="Dairy shut")

    after = _calendar_check(await _readiness(client, headers, center["id"]))
    assert after["passed"] is False, "an organization holiday must close the centre"
    assert after["severity"] == "blocking"
    assert "organization calendar" in after["detail"], (
        "the reason must name the organization — a centre with no entry of its "
        "own would otherwise send an operator hunting"
    )
    assert (await _readiness(client, headers, center["id"]))["status"] == "NOT_READY"


# --- 3: the centre's own closure, unchanged in shape -------------------------


async def test_a_centre_closure_closes_that_centre_and_names_itself(client):
    headers, _branch, center = await _center_fixture(client)
    today = await _today_for(client, headers)
    await _declare_centre(client, headers, center["id"], today, "closure", note="Stocktaking")

    check = _calendar_check(await _readiness(client, headers, center["id"]))
    assert check["passed"] is False and check["severity"] == "blocking"
    assert "closure" in check["detail"] and "Stocktaking" in check["detail"]


# --- 4: the centre overrides its organization --------------------------------


async def test_a_centre_may_work_through_an_organization_holiday(client):
    """`special` means unusual-and-worked, so the centre is not closed.

    It is still reported as a WARNING, exactly as before: the resolver decides
    whether the day is worked, and readiness keeps saying that the day is not
    an ordinary one.
    """
    headers, _branch, center = await _center_fixture(client)
    today = await _today_for(client, headers)

    await _declare_org(client, headers, today, working=False, kind="holiday", name="Dairy shut")
    await _declare_centre(client, headers, center["id"], today, "special", note="Festival run")

    check = _calendar_check(await _readiness(client, headers, center["id"]))
    assert check["passed"] is False
    assert check["severity"] == "warning", "worked, and worth mentioning — not closed"
    assert "special day today" in check["detail"]
    assert "Festival run" in check["detail"]


# --- 5: no centre opinion falls back to the organization ---------------------


async def test_a_centre_with_no_entry_follows_the_organization(client):
    headers, _branch, center = await _center_fixture(client)
    today = await _today_for(client, headers)

    # The organization says the day IS worked — an exception the other way.
    await _declare_org(client, headers, today, working=True, kind="working", name="Open")
    check = _calendar_check(await _readiness(client, headers, center["id"]))
    assert check["passed"] is True


# --- 1, 9: readiness and the scheduler cannot disagree -----------------------


@pytest.mark.parametrize(
    "org_working,centre_kind,expected_working",
    [
        (None, None, True),  # nothing declared
        (False, None, False),  # organization shut
        (True, None, True),  # organization open
        (None, "closure", False),  # centre shut
        (None, "special", True),  # centre worked
        (False, "special", True),  # centre overrides a shut organization
        (True, "holiday", False),  # centre overrides an open organization
    ],
)
async def test_readiness_and_the_resolver_return_the_same_decision(
    client, org_working, centre_kind, expected_working
):
    """The property, across every combination the model can express.

    Readiness is asked through its HTTP endpoint and the resolver is asked
    directly — the same question, two doors. If they ever diverge, one of them
    has grown its own copy of the rule, which is the thing this milestone
    exists to prevent.
    """
    headers, _branch, center = await _center_fixture(client)
    today = await _today_for(client, headers)

    if org_working is not None:
        await _declare_org(
            client,
            headers,
            today,
            working=org_working,
            kind="working" if org_working else "holiday",
        )
    if centre_kind is not None:
        await _declare_centre(client, headers, center["id"], today, centre_kind)

    me = (await client.get("/v1/auth/me", headers=headers)).json()
    tenant_id = uuid.UUID(me["tenant_id"])
    async with db.get_session_factory()() as session:
        set_current_tenant(tenant_id)
        resolved = await WorkingDayResolver(session, tenant_id, today).is_working(
            uuid.UUID(center["id"])
        )
    set_current_tenant(None)

    assert resolved is expected_working, "the resolver's own answer moved"

    check = _calendar_check(await _readiness(client, headers, center["id"]))
    readiness_says_closed = check["passed"] is False and check["severity"] == "blocking"
    assert readiness_says_closed is (not expected_working), (
        f"readiness and the resolver disagree: resolver working={resolved}, readiness check={check}"
    )


# --- 7, 8: the business date is the tenant's own -----------------------------


@pytest.mark.parametrize("country,zone", [("IN", INDIA_TZ), ("KE", KENYA_TZ)])
async def test_readiness_evaluates_the_tenants_own_business_date(client, country, zone):
    """A holiday declared for the DAIRY's today is the one readiness sees.

    No country branching anywhere: the zone comes from the organization the
    country registry configured at onboarding, and the same code runs for both.
    """
    from tests.test_localization import _tenant_admin_for

    _org, headers = await _tenant_admin_for(
        client,
        country=country,
        slug=f"rdy-{country.lower()}",
        email=f"rdy-{country.lower()}@example.com",
    )
    cal = (await client.get("/v1/organization/calendar", headers=headers)).json()
    assert cal["timezone"] == zone, "the registry decides the zone, not a branch in this test"

    center = await _centre_for(client, headers, country)

    today = await _today_for(client, headers)
    await _declare_org(client, headers, today, working=False, kind="holiday", name="Local holiday")

    check = _calendar_check(await _readiness(client, headers, center["id"]))
    assert check["passed"] is False, f"{zone}: the dairy's own today must be the one evaluated"


# --- 10: cross-tenant --------------------------------------------------------


async def test_one_dairys_holiday_does_not_close_anothers_centre(client):
    headers_a, _b, center_a = await _center_fixture(client)
    today = await _today_for(client, headers_a)
    await _declare_org(client, headers_a, today, working=False, kind="holiday")

    from tests.test_localization import _tenant_admin_for

    _org_b, headers_b = await _tenant_admin_for(
        client, country="KE", slug="rdy-iso-b", email="rdy-iso-b@example.com"
    )
    center_b = await _centre_for(client, headers_b, "ISOB")
    check_b = _calendar_check(await _readiness(client, headers_b, center_b["id"]))
    assert check_b["passed"] is True, "another dairy's holiday must not close this centre"

    # And A's centre is not readable from B at all.
    r = await client.get(f"/v1/collection-centers/{center_a['id']}/readiness", headers=headers_b)
    assert r.status_code == 404


# --- the regression guard ----------------------------------------------------


def test_readiness_does_not_read_the_centre_calendar_table_directly():
    """The guard that would fail if the direct read came back (DEMO-023).

    Asserted against the source because that is where the rule lives: any
    future edit that reaches for `CalendarEntry` here is re-creating the second
    reader this milestone removed, and it would pass every behavioural test
    above on the day it was written — the divergence only appears later, when
    one of the two copies is changed.
    """
    import pathlib

    source = (
        pathlib.Path(__file__).resolve().parents[1]
        / "src/platform_core/modules/operational_readiness/service.py"
    ).read_text()

    assert "CalendarEntry" not in source, (
        "operational_readiness reads the centre calendar table again — the "
        "working-day decision belongs to WorkingDayResolver, which readiness "
        "and the delivery scheduler must both go through"
    )
    assert "WorkingDayResolver" in source, "readiness no longer resolves through WorkingDayResolver"
