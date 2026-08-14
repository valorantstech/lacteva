"""The round goes out by itself (DEMO-017).

DEMO-016 left generation on demand. What has to be true for it to be automatic
and safe, and what each section below asserts:

**Each dairy's own morning.** A single cron expression cannot be 05:00 in
Bengaluru and 05:00 in Nairobi at once. The scheduler asks each tenant about
its own clock, so three tenants at ONE UTC instant can legitimately hold three
different business dates — §20 asks for exactly this, and warns against a test
premise that assumes the countries always differ. They do not: the tests below
name the instant that separates them and the instant that does not.

**A retry cannot duplicate.** The delivery constraint from DEMO-009 is what
makes that true; this milestone only has to not get in its way. So the test
that matters injects a REAL failure, retries, and counts rows.

**Yesterday is never invented.** A missed day stays missed. Generating a
physical delivery after the fact would put milk nobody carried onto a bill.
"""

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from platform_core.modules.delivery.models import MAX_ATTEMPTS, DeliveryGenerationRun
from platform_core.modules.delivery.scheduler import (
    Tenant,
    business_date_and_hour,
    run_for_tenant,
    should_run,
)
from tests.conftest import register_and_login
from tests.test_org_structure import _tenant_admin

HOUR = 5  # the generation hour, local


def _run(day: date, status: str, attempts: int = 1) -> DeliveryGenerationRun:
    return DeliveryGenerationRun(
        tenant_id=uuid.uuid4(), business_date=day, status=status, attempts=attempts
    )


# --- the decision, as arithmetic ---------------------------------------------


def test_before_the_generation_hour_nothing_happens():
    """A round generated at midnight would sit on an operator's screen for
    five hours looking like work already done."""
    at_0400_ist = datetime(2026, 8, 14, 22, 30, tzinfo=ZoneInfo("UTC"))  # 04:00 IST on the 15th
    assert (
        should_run(now=at_0400_ist, timezone="Asia/Kolkata", generation_hour=HOUR, last=None)
        is None
    )


def test_at_the_generation_hour_the_day_is_due():
    at_0530_ist = datetime(2026, 8, 15, 0, 0, tzinfo=ZoneInfo("UTC"))  # 05:30 IST
    assert should_run(
        now=at_0530_ist, timezone="Asia/Kolkata", generation_hour=HOUR, last=None
    ) == date(2026, 8, 15)


def test_a_finished_day_is_not_run_again():
    """What stops a loop that wakes every minute from re-running a completed
    round sixty times an hour."""
    now = datetime(2026, 8, 15, 6, 0, tzinfo=ZoneInfo("UTC"))
    today, _ = business_date_and_hour(now, "Asia/Kolkata")
    assert (
        should_run(
            now=now, timezone="Asia/Kolkata", generation_hour=HOUR, last=_run(today, "success")
        )
        is None
    )


def test_a_failed_day_is_retried_but_not_forever():
    now = datetime(2026, 8, 15, 6, 0, tzinfo=ZoneInfo("UTC"))
    today, _ = business_date_and_hour(now, "Asia/Kolkata")
    assert (
        should_run(
            now=now, timezone="Asia/Kolkata", generation_hour=HOUR, last=_run(today, "failed", 1)
        )
        == today
    )
    assert (
        should_run(
            now=now,
            timezone="Asia/Kolkata",
            generation_hour=HOUR,
            last=_run(today, "failed", MAX_ATTEMPTS),
        )
        is None
    )


def test_a_run_in_flight_is_left_alone():
    now = datetime(2026, 8, 15, 6, 0, tzinfo=ZoneInfo("UTC"))
    today, _ = business_date_and_hour(now, "Asia/Kolkata")
    assert (
        should_run(
            now=now, timezone="Asia/Kolkata", generation_hour=HOUR, last=_run(today, "running")
        )
        is None
    )


def test_a_missed_day_is_never_backfilled():
    """§8. The platform was down all of Thursday; Friday generates Friday.

    Inventing Thursday's round on Friday would put a day of milk nobody
    carried onto a customer's bill.
    """
    friday = datetime(2026, 8, 21, 6, 0, tzinfo=ZoneInfo("UTC"))
    today, _ = business_date_and_hour(friday, "Asia/Kolkata")
    answer = should_run(
        now=friday,
        timezone="Asia/Kolkata",
        generation_hour=HOUR,
        last=_run(date(2026, 8, 19), "success"),  # Wednesday; Thursday never ran
    )
    assert answer == today
    assert answer != date(2026, 8, 20), "the scheduler backfilled a day nobody delivered"


# --- three dairies, one instant (§20) -----------------------------------------


def test_three_countries_at_one_instant_that_separates_them():
    """20:00 UTC: India is already tomorrow, Kenya and Qatar are not.

    The window is narrow and worth naming. India is UTC+5:30 and crosses
    midnight at 18:30 UTC; Kenya and Qatar are UTC+3 and cross at 21:00. So
    the countries hold different dates for exactly two and a half hours a day,
    and **20:00 is inside it while 23:00 is not** — at 23:00 all three are
    already on the 15th.

    That is not a detail: picking 23:00 was the first draft of this test, and
    it is precisely the false premise §20 warns against. Asserting that Kenya
    and Qatar AGREE here is the other half — they are both UTC+3, and a design
    that made them differ would be wrong in a way that looks impressive.
    """
    instant = datetime(2026, 8, 14, 20, 0, tzinfo=ZoneInfo("UTC"))
    india, _ = business_date_and_hour(instant, "Asia/Kolkata")
    kenya, _ = business_date_and_hour(instant, "Africa/Nairobi")
    qatar, _ = business_date_and_hour(instant, "Asia/Qatar")

    assert india == date(2026, 8, 15)
    assert kenya == date(2026, 8, 14)
    assert qatar == date(2026, 8, 14)
    assert kenya == qatar, "Kenya and Qatar are both UTC+3 and must agree"


def test_an_instant_where_all_three_agree():
    """Midday UTC. The same code must not manufacture a difference that is not
    there — which is the other half of §20's warning."""
    instant = datetime(2026, 8, 14, 12, 0, tzinfo=ZoneInfo("UTC"))
    dates = {
        business_date_and_hour(instant, tz)[0]
        for tz in ("Asia/Kolkata", "Africa/Nairobi", "Asia/Qatar")
    }
    assert dates == {date(2026, 8, 14)}


def test_the_generation_hour_arrives_at_a_different_utc_time_in_each_country():
    """The reason this is a loop and not a cron line.

    05:00 local is 23:30 UTC in India and 02:00 UTC in Kenya and Qatar. One
    schedule cannot be all three.
    """

    def utc_hour_of_local_five(tz: str) -> tuple[int, int]:
        for minutes in range(0, 24 * 60, 30):
            instant = datetime(2026, 8, 14, 0, 0, tzinfo=ZoneInfo("UTC")) + timedelta(
                minutes=minutes
            )
            local = instant.astimezone(ZoneInfo(tz))
            if local.hour == 5 and local.minute == 0:
                return instant.hour, instant.minute
        raise AssertionError(f"05:00 never occurred in {tz}")

    india = utc_hour_of_local_five("Asia/Kolkata")
    kenya = utc_hour_of_local_five("Africa/Nairobi")
    qatar = utc_hour_of_local_five("Asia/Qatar")
    assert india == (23, 30)
    assert kenya == (2, 0)
    assert qatar == (2, 0)
    assert india != kenya


# --- against the database ------------------------------------------------------


async def _dairy_with_plans(client, count: int = 3):
    """A tenant, a manager, and `count` customers on daily standing orders."""
    org, admin = await _tenant_admin(client)
    for index in range(count):
        r = await client.post(
            "/v1/customers",
            json={
                "name": f"Household {index}",
                "plan": {
                    "unit_price": "56.0000",
                    "default_quantity": "2.000",
                    "effective_from": "2026-01-01",
                },
            },
            headers=admin,
        )
        assert r.status_code == 201, r.text
    return org, admin


async def test_the_scheduler_generates_a_tenants_round(client):
    org, admin = await _dairy_with_plans(client)
    tenant = Tenant(id=uuid.UUID(org["id"]), slug=org["slug"], timezone=org["timezone"])

    run = await run_for_tenant(tenant, generation_hour=HOUR, force_date=date(2026, 8, 17))
    assert run is not None
    assert run.status == "success"
    assert run.created == 3
    assert run.trigger == "scheduler"
    assert run.attempts == 1
    assert run.finished_at is not None

    page = (
        await client.get(
            "/v1/deliveries",
            params={"date_from": "2026-08-17", "date_to": "2026-08-17"},
            headers=admin,
        )
    ).json()
    assert page["total"] == 3
    assert all(row["status"] == "scheduled" for row in page["items"])


async def test_running_the_scheduler_twice_creates_nothing_the_second_time(client):
    org, admin = await _dairy_with_plans(client)
    tenant = Tenant(id=uuid.UUID(org["id"]), slug=org["slug"], timezone=org["timezone"])
    day = date(2026, 8, 17)

    first = await run_for_tenant(tenant, generation_hour=HOUR, force_date=day)
    second = await run_for_tenant(tenant, generation_hour=HOUR, force_date=day)

    # `run_for_tenant` returns the RECORD, which is the day's. A second
    # scheduler pass finds the day owned and finished, so it neither
    # re-generates nor blanks what the first pass recorded.
    assert first.created == 3
    assert second.created == 3, "the day's count must survive a second pass"
    assert second.attempts == 1, "a finished day is not re-claimed by the scheduler"

    page = (
        await client.get(
            "/v1/deliveries", params={"date_from": str(day), "date_to": str(day)}, headers=admin
        )
    ).json()
    assert page["total"] == 3


async def test_a_transient_failure_is_recorded_and_the_retry_succeeds(client, monkeypatch):
    """§19. A REAL failure injected into the generator, then a retry.

    This is the test the milestone turns on: a scheduler that cannot fail
    safely is worse than one that does not run, because the failure mode is
    duplicated milk on somebody's bill.
    """
    org, admin = await _dairy_with_plans(client)
    tenant = Tenant(id=uuid.UUID(org["id"]), slug=org["slug"], timezone=org["timezone"])
    day = date(2026, 8, 17)

    from platform_core.modules.delivery import scheduler as scheduler_module

    calls = {"n": 0}
    real = scheduler_module.generate_for_day

    async def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("database went away")
        return await real(*args, **kwargs)

    monkeypatch.setattr(scheduler_module, "generate_for_day", flaky)

    failed = await run_for_tenant(tenant, generation_hour=HOUR, force_date=day)
    assert failed is not None
    assert failed.status == "failed"
    assert "database went away" in failed.error
    assert failed.attempts == 1

    # Nothing was created by the failed attempt.
    empty = (
        await client.get(
            "/v1/deliveries", params={"date_from": str(day), "date_to": str(day)}, headers=admin
        )
    ).json()
    assert empty["total"] == 0

    recovered = await run_for_tenant(tenant, generation_hour=HOUR, force_date=day)
    assert recovered.status == "success"
    assert recovered.created == 3
    assert recovered.attempts == 2

    page = (
        await client.get(
            "/v1/deliveries", params={"date_from": str(day), "date_to": str(day)}, headers=admin
        )
    ).json()
    assert page["total"] == 3, "the retry duplicated the round"


async def test_a_manual_run_and_a_scheduled_run_cannot_duplicate(client):
    """§9. Both go through the same path, and the delivery constraint is the
    guarantee either way."""
    org, admin = await _dairy_with_plans(client)
    tenant = Tenant(id=uuid.UUID(org["id"]), slug=org["slug"], timezone=org["timezone"])
    day = date(2026, 8, 17)

    manual = await client.post(
        "/v1/deliveries/generate", json={"for_date": str(day)}, headers=admin
    )
    assert manual.status_code == 200, manual.text
    assert manual.json()["created"] == 3

    scheduled = await run_for_tenant(tenant, generation_hour=HOUR, force_date=day)
    # The day's record, which the manual run already filled in.
    assert scheduled.created == 3

    page = (
        await client.get(
            "/v1/deliveries", params={"date_from": str(day), "date_to": str(day)}, headers=admin
        )
    ).json()
    assert page["total"] == 3


async def test_a_manual_run_is_recorded_as_manual(client):
    _org, admin = await _dairy_with_plans(client)
    await client.post("/v1/deliveries/generate", json={"for_date": "2026-08-17"}, headers=admin)
    runs = (await client.get("/v1/deliveries/generation-runs", headers=admin)).json()
    assert runs[0]["trigger"] == "manual"
    assert runs[0]["status"] == "success"
    assert runs[0]["created"] == 3


async def test_the_scheduler_never_touches_another_tenant(client):
    """§6, and the reason it cannot: generation runs inside the tenant's own
    binding, so the database filters it exactly as it would a request."""
    org_a, _admin_a = await _dairy_with_plans(client, count=2)
    tenant_a = Tenant(id=uuid.UUID(org_a["id"]), slug=org_a["slug"], timezone=org_a["timezone"])

    from tests.test_payments import _second_tenant

    other = await _second_tenant(client)
    day = date(2026, 8, 17)

    run = await run_for_tenant(tenant_a, generation_hour=HOUR, force_date=day)
    assert run.created == 2

    theirs = (await client.get("/v1/deliveries", headers=other)).json()
    assert theirs["total"] == 0, "the scheduler generated another dairy's deliveries"
    their_runs = (await client.get("/v1/deliveries/generation-runs", headers=other)).json()
    assert their_runs == [], "another tenant's run history leaked"


async def test_the_run_record_answers_the_operators_question(client):
    """§5: date, status, plans evaluated, created, already existed, duration."""
    _org, admin = await _dairy_with_plans(client)
    await client.post("/v1/deliveries/generate", json={"for_date": "2026-08-17"}, headers=admin)
    await client.post("/v1/deliveries/generate", json={"for_date": "2026-08-17"}, headers=admin)

    runs = (await client.get("/v1/deliveries/generation-runs", headers=admin)).json()
    assert len(runs) == 1, "one row per business date, updated in place"
    row = runs[0]
    assert row["business_date"] == "2026-08-17"
    assert row["status"] == "success"
    assert row["plans_due"] == 3
    # The RECORD is the day's: three were created for 2026-08-17, whichever
    # attempt created them. The per-CALL answer is what the endpoint returns,
    # and `test_running_the_scheduler_twice...` asserts that separately.
    assert row["created"] == 3
    assert row["already_present"] == 3
    assert row["attempts"] == 2
    assert row["duration_ms"] >= 0


async def test_reading_the_run_history_needs_the_read_grant(client):
    _org, _admin = await _dairy_with_plans(client)
    _user, outsider = await register_and_login(client, email="nobody-017@example.com")
    r = await client.get("/v1/deliveries/generation-runs", headers=outsider)
    assert r.status_code in (401, 403)


async def test_a_generated_round_still_bills_normally(client):
    """§15: the scheduler creates no financial record. The bill comes from the
    ordinary workflow once a person says the milk arrived."""
    org, admin = await _dairy_with_plans(client, count=1)
    tenant = Tenant(id=uuid.UUID(org["id"]), slug=org["slug"], timezone=org["timezone"])
    day = date(2026, 8, 17)
    await run_for_tenant(tenant, generation_hour=HOUR, force_date=day)

    customer_id = (await client.get("/v1/customers", headers=admin)).json()["items"][0]["id"]

    # Nothing billable yet — the scheduler created no money.
    premature = await client.post(
        "/v1/invoices",
        json={"customer_id": customer_id, "period_from": str(day), "period_to": str(day)},
        headers=admin,
    )
    assert premature.status_code == 409

    await client.post(
        "/v1/deliveries",
        json={"customer_id": customer_id, "delivery_date": str(day), "status": "delivered"},
        headers=admin,
    )
    invoice = await client.post(
        "/v1/invoices",
        json={"customer_id": customer_id, "period_from": str(day), "period_to": str(day)},
        headers=admin,
    )
    assert invoice.status_code == 201, invoice.text
    assert Decimal(invoice.json()["total"]) == Decimal("112.00")


@pytest.mark.parametrize(
    "timezone,expected",
    [("Asia/Kolkata", date(2026, 8, 15)), ("Africa/Nairobi", date(2026, 8, 14))],
)
async def test_each_tenant_generates_its_own_date_at_one_instant(client, timezone, expected):
    """The end-to-end form of §20, against the database rather than a helper.

    20:00 UTC on the 14th — inside the two-and-a-half-hour window where the
    countries genuinely differ: an Indian dairy's scheduler produces the 15th
    and a Kenyan one produces the 14th, from the same call at the same moment.

    `generation_hour=0` here on purpose. Inside that window it is 01:30 in
    India, which is BEFORE any sensible generation hour — so with the real
    hour the Indian answer would be "not yet", correctly, and the test would
    be measuring the hour rule instead of the date rule. Zero removes the
    hour from the question and leaves exactly one variable: the timezone.
    """
    org, _admin = await _dairy_with_plans(client, count=1)
    tenant = Tenant(id=uuid.UUID(org["id"]), slug=org["slug"], timezone=timezone)
    instant = datetime(2026, 8, 14, 20, 0, tzinfo=ZoneInfo("UTC"))

    run = await run_for_tenant(tenant, now=instant, generation_hour=0)
    assert run is not None
    assert run.business_date == expected


# --- what production taught us (DEMO-018) ------------------------------------


# `test_concurrent_schedulers_do_not_overwrite_each_others_record` lives in
# `test_scheduler_concurrency_postgres.py`, not here. On SQLite the test stack
# shares ONE connection through a StaticPool, so four "concurrent" sessions are
# one transaction and a rollback in any of them discards the others' work — the
# race cannot be expressed, let alone proven. This is the same reason
# `test_payment_concurrency_postgres.py` exists.


async def test_a_retry_accumulates_what_it_created(client, monkeypatch):
    """A retry that creates the deliveries a failed attempt missed must show
    them as created FOR THE DAY. An operator reads this row to answer "did the
    round go out", and the answer is about the day, not about the attempt."""
    org, _admin = await _dairy_with_plans(client, count=3)
    tenant = Tenant(id=uuid.UUID(org["id"]), slug=org["slug"], timezone=org["timezone"])
    day = date(2026, 8, 17)

    from platform_core.modules.delivery import scheduler as scheduler_module

    calls = {"n": 0}
    real = scheduler_module.generate_for_day

    async def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient")
        return await real(*args, **kwargs)

    monkeypatch.setattr(scheduler_module, "generate_for_day", flaky)

    await run_for_tenant(tenant, generation_hour=HOUR, force_date=day)
    recovered = await run_for_tenant(tenant, generation_hour=HOUR, force_date=day)
    assert recovered.status == "success"
    assert recovered.created == 3
    assert recovered.attempts == 2


async def test_a_manual_run_can_always_take_the_day(client):
    """§9. An operator who presses the button has asked for it, even on a day
    the scheduler already finished — the constraint means the worst case is a
    round that finds everything already there."""
    org, admin = await _dairy_with_plans(client, count=2)
    tenant = Tenant(id=uuid.UUID(org["id"]), slug=org["slug"], timezone=org["timezone"])
    day = date(2026, 8, 17)

    await run_for_tenant(tenant, generation_hour=HOUR, force_date=day)
    manual = await client.post(
        "/v1/deliveries/generate", json={"for_date": str(day)}, headers=admin
    )
    assert manual.status_code == 200, manual.text
    assert manual.json()["created"] == 0
    assert manual.json()["already_present"] == 2

    runs = (await client.get("/v1/deliveries/generation-runs", headers=admin)).json()
    assert runs[0]["trigger"] == "manual"
    assert runs[0]["created"] == 2, "the day's created count must survive a manual re-run"


async def test_a_second_scheduler_pass_does_not_reset_the_days_count(client):
    """The narrow form of the production defect: a later pass that creates
    nothing must not blank what an earlier pass created."""
    org, admin = await _dairy_with_plans(client, count=3)
    tenant = Tenant(id=uuid.UUID(org["id"]), slug=org["slug"], timezone=org["timezone"])
    day = date(2026, 8, 17)

    await run_for_tenant(tenant, generation_hour=HOUR, force_date=day)
    await run_for_tenant(tenant, generation_hour=HOUR, force_date=day)

    runs = (await client.get("/v1/deliveries/generation-runs", headers=admin)).json()
    assert runs[0]["created"] == 3
