"""Financial periods and organization holidays, through the API (DEMO-020).

The capability this milestone adds, exercised the way a dairy would: onboard
an organization by country, ask the platform what day it is *there*, declare a
holiday, close a month, and watch the guard refuse.

**The refusal is the point.** A period that can be closed but never stops
anything is a status column, not a boundary — so every guard test here asserts
that the closed period is what changed the answer, not merely that a closed
period exists.
"""

from datetime import date, timedelta

import pytest

from tests.test_localization import _tenant_admin_for

INDIA_ZONE = "Asia/Kolkata"


async def _india(client, slug="cal-in", email="cal-admin@india.example"):
    return await _tenant_admin_for(client, country="IN", slug=slug, email=email)


async def _kenya(client, slug="cal-ke", email="cal-admin@kenya.example"):
    return await _tenant_admin_for(client, country="KE", slug=slug, email=email)


# --- the calendar overview ---------------------------------------------------


async def test_the_calendar_reports_the_organizations_own_clock(client):
    """India's calendar is Asia/Kolkata's, and every date on it follows."""
    _org, headers = await _india(client)
    r = await client.get("/v1/organization/calendar", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["timezone"] == INDIA_ZONE
    business_date = date.fromisoformat(body["business_date"])
    # The month must actually contain the business date, and end on a real
    # last-of-month — the two things a hand-rolled month gets wrong.
    assert date.fromisoformat(body["month_start"]) == business_date.replace(day=1)
    assert date.fromisoformat(body["month_start"]) <= business_date
    assert date.fromisoformat(body["month_end"]) >= business_date
    assert (date.fromisoformat(body["month_end"]) + timedelta(days=1)).day == 1
    # The previous month ends the day before this one starts. No gap, no overlap.
    assert date.fromisoformat(body["previous_month_end"]) + timedelta(days=1) == (
        date.fromisoformat(body["month_start"])
    )
    # Nothing declared yet, so every day works and no period covers today.
    assert body["is_working_day"] is True
    assert body["current_period"] is None


async def test_two_countries_get_two_calendars(client):
    """Kenya's clock is not India's, and neither is the server's."""
    _in, india = await _india(client, slug="cal-in2", email="cal2@india.example")
    _ke, kenya = await _kenya(client, slug="cal-ke2", email="cal2@kenya.example")

    india_body = (await client.get("/v1/organization/calendar", headers=india)).json()
    kenya_body = (await client.get("/v1/organization/calendar", headers=kenya)).json()

    assert india_body["timezone"] == "Asia/Kolkata"
    assert kenya_body["timezone"] == "Africa/Nairobi"
    # The dates may agree for most of the day; the CLOCKS never do.
    assert india_body["timezone"] != kenya_body["timezone"]


# --- 11: holiday lookup ------------------------------------------------------


async def test_a_declared_holiday_becomes_a_non_working_day(client):
    _org, headers = await _india(client, slug="cal-hol", email="hol@india.example")
    today = (await client.get("/v1/organization/calendar", headers=headers)).json()["business_date"]

    before = (await client.get("/v1/organization/calendar", headers=headers)).json()
    assert before["is_working_day"] is True, "the premise: an ordinary day works"

    r = await client.put(
        "/v1/organization/calendar/days",
        json={"day": today, "working": False, "kind": "holiday", "name": "Independence Day"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Independence Day"

    after = (await client.get("/v1/organization/calendar", headers=headers)).json()
    assert after["is_working_day"] is False, "the holiday must change the answer"

    listed = (
        await client.get(
            f"/v1/organization/calendar/days?date_from={today}&date_to={today}",
            headers=headers,
        )
    ).json()
    assert [d["day"] for d in listed] == [today]

    # Removing it puts the day back to working — the guard is reversible.
    assert (
        await client.delete(f"/v1/organization/calendar/days/{today}", headers=headers)
    ).status_code == 204
    restored = (await client.get("/v1/organization/calendar", headers=headers)).json()
    assert restored["is_working_day"] is True


async def test_recording_the_same_day_twice_amends_it(client):
    """PUT means the day either is or is not an exception."""
    _org, headers = await _india(client, slug="cal-idem", email="idem@india.example")
    day = "2026-10-02"
    for name in ("Gandhi Jayanti", "Gandhi Jayanti (observed)"):
        r = await client.put(
            "/v1/organization/calendar/days",
            json={"day": day, "working": False, "kind": "holiday", "name": name},
            headers=headers,
        )
        assert r.status_code == 200, r.text
    listed = (
        await client.get(
            f"/v1/organization/calendar/days?date_from={day}&date_to={day}", headers=headers
        )
    ).json()
    assert len(listed) == 1
    assert listed[0]["name"] == "Gandhi Jayanti (observed)"


async def test_a_working_exception_is_expressible(client):
    """The other direction: open on a day that would not normally be worked."""
    _org, headers = await _india(client, slug="cal-work", email="work@india.example")
    day = (await client.get("/v1/organization/calendar", headers=headers)).json()["business_date"]
    await client.put(
        "/v1/organization/calendar/days",
        json={"day": day, "working": True, "kind": "working", "name": "Stocktake"},
        headers=headers,
    )
    body = (await client.get("/v1/organization/calendar", headers=headers)).json()
    assert body["is_working_day"] is True


async def test_an_unknown_calendar_kind_is_refused(client):
    _org, headers = await _india(client, slug="cal-kind", email="kind@india.example")
    r = await client.put(
        "/v1/organization/calendar/days",
        json={"day": "2026-09-01", "kind": "bank-ish", "working": False},
        headers=headers,
    )
    assert r.status_code == 422, r.text


# --- 9: financial period creation --------------------------------------------


async def test_a_period_is_created_from_the_dairys_month(client):
    _org, headers = await _india(client, slug="fp-create", email="fp@india.example")
    cal = (await client.get("/v1/organization/calendar", headers=headers)).json()

    r = await client.post(
        "/v1/organization/financial-periods",
        json={
            "period_start": cal["month_start"],
            "period_end": cal["month_end"],
            "label": "This month",
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "open"

    # And the overview now knows which period today falls in.
    after = (await client.get("/v1/organization/calendar", headers=headers)).json()
    assert after["current_period"] is not None
    assert after["current_period"]["status"] == "open"


async def test_overlapping_periods_are_refused_by_name(client):
    _org, headers = await _india(client, slug="fp-overlap", email="ovl@india.example")
    base = {"period_start": "2026-08-01", "period_end": "2026-08-31"}
    assert (
        await client.post("/v1/organization/financial-periods", json=base, headers=headers)
    ).status_code == 201

    r = await client.post(
        "/v1/organization/financial-periods",
        json={"period_start": "2026-08-15", "period_end": "2026-09-15"},
        headers=headers,
    )
    assert r.status_code == 409, r.text
    # RFC 9457: `detail` is the translated generic, `extra` carries the
    # specific — the platform's own error contract.
    assert "2026-08-01" in r.json()["extra"], "the refusal must name what it collides with"


async def test_a_period_cannot_end_before_it_begins(client):
    _org, headers = await _india(client, slug="fp-order", email="ord@india.example")
    r = await client.post(
        "/v1/organization/financial-periods",
        json={"period_start": "2026-08-31", "period_end": "2026-08-01"},
        headers=headers,
    )
    assert r.status_code == 422, r.text


# --- 10: closed period protection --------------------------------------------


async def test_closing_a_period_changes_what_the_guard_allows(client):
    """The guard must REFUSE, not merely be present."""
    from platform_core.core.errors import ConflictError
    from platform_core.modules.business_calendar.service import BusinessCalendarService

    org, headers = await _india(client, slug="fp-close", email="close@india.example")
    created = (
        await client.post(
            "/v1/organization/financial-periods",
            json={"period_start": "2026-08-01", "period_end": "2026-08-31"},
            headers=headers,
        )
    ).json()

    import uuid

    from platform_core.core import db

    tenant_id = uuid.UUID(org["id"])
    inside = date(2026, 8, 15)
    outside = date(2026, 9, 15)

    async with db.get_session_factory()() as session:
        service = BusinessCalendarService(session, tenant_id)
        # Open: allowed. This is the premise, and it must be asserted before
        # the refusal means anything.
        assert (await service.check_open(inside)).allowed is True
        await service.assert_open(inside, operation="billing")

    assert (
        await client.post(
            f"/v1/organization/financial-periods/{created['id']}/close", headers=headers
        )
    ).status_code == 200

    async with db.get_session_factory()() as session:
        service = BusinessCalendarService(session, tenant_id)
        guard = await service.check_open(inside)
        assert guard.allowed is False, "a closed period must refuse"
        with pytest.raises(ConflictError) as excinfo:
            await service.assert_open(inside, operation="billing")
        assert "closed financial period" in str(excinfo.value)
        # A date OUTSIDE the closed period is unaffected — the guard is not a
        # global switch.
        assert (await service.check_open(outside)).allowed is True


async def test_a_closed_period_can_be_reopened_and_the_guard_follows(client):
    _org, headers = await _india(client, slug="fp-reopen", email="reo@india.example")
    created = (
        await client.post(
            "/v1/organization/financial-periods",
            json={"period_start": "2026-08-01", "period_end": "2026-08-31"},
            headers=headers,
        )
    ).json()
    await client.post(f"/v1/organization/financial-periods/{created['id']}/close", headers=headers)
    # Closing twice is a conflict, not a silent success.
    assert (
        await client.post(
            f"/v1/organization/financial-periods/{created['id']}/close", headers=headers
        )
    ).status_code == 409

    r = await client.post(
        f"/v1/organization/financial-periods/{created['id']}/reopen", headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "open"
    assert r.json()["closed_at"] is None, "a reopened period must not look closed"


# --- 15: cross-tenant isolation ----------------------------------------------


async def test_one_dairy_cannot_see_or_close_anothers_period(client):
    _india_org, india = await _india(client, slug="fp-iso-in", email="iso@india.example")
    _ke_org, kenya = await _kenya(client, slug="fp-iso-ke", email="iso@kenya.example")

    created = (
        await client.post(
            "/v1/organization/financial-periods",
            json={"period_start": "2026-08-01", "period_end": "2026-08-31"},
            headers=india,
        )
    ).json()

    # Kenya's list is its own, and it is empty.
    assert (await client.get("/v1/organization/financial-periods", headers=kenya)).json() == []

    # And India's period is NOT FOUND from Kenya — 404, never 403.
    r = await client.post(
        f"/v1/organization/financial-periods/{created['id']}/close", headers=kenya
    )
    assert r.status_code == 404, r.text

    # India's own period is still open: Kenya's attempt changed nothing.
    assert (await client.get("/v1/organization/financial-periods", headers=india)).json()[0][
        "status"
    ] == "open"


async def test_one_dairys_holiday_is_not_anothers(client):
    _in_org, india = await _india(client, slug="cal-iso-in", email="calio@india.example")
    _ke_org, kenya = await _kenya(client, slug="cal-iso-ke", email="calio@kenya.example")
    day = "2026-08-15"

    await client.put(
        "/v1/organization/calendar/days",
        json={"day": day, "working": False, "kind": "holiday", "name": "Independence Day"},
        headers=india,
    )
    kenya_days = (
        await client.get(
            f"/v1/organization/calendar/days?date_from={day}&date_to={day}", headers=kenya
        )
    ).json()
    assert kenya_days == [], "a holiday belongs to the dairy that declared it"


# --- the endpoints are guarded -----------------------------------------------


async def test_the_calendar_requires_authentication(client):
    assert (await client.get("/v1/organization/calendar")).status_code == 401
    assert (await client.get("/v1/organization/financial-periods")).status_code == 401


async def test_reading_the_calendar_does_not_grant_closing_a_period(client):
    """A viewer may look at the calendar and may not shut the books."""
    from tests.conftest import invite

    org, admin = await _india(client, slug="fp-perm", email="perm@india.example")
    _inv, token = await invite(
        client,
        {**admin, "X-Tenant-ID": org["id"]},
        email="viewer@india.example",
        role_name="tenant-viewer",
    )
    await client.post(
        "/v1/invitations/accept",
        json={"token": token, "password": "viewer-password-1", "full_name": "Viewer"},
    )
    pair = await client.post(
        "/v1/auth/token",
        json={
            "email": "viewer@india.example",
            "password": "viewer-password-1",
            "tenant_id": org["id"],
        },
    )
    viewer = {"Authorization": f"Bearer {pair.json()['access_token']}"}

    assert (await client.get("/v1/organization/calendar", headers=viewer)).status_code == 200
    r = await client.post(
        "/v1/organization/financial-periods",
        json={"period_start": "2026-08-01", "period_end": "2026-08-31"},
        headers=viewer,
    )
    assert r.status_code == 403, r.text
