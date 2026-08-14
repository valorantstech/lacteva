"""Standing orders and daily generation (DEMO-016).

The milestone's claim is that a dairy stops typing its round. What has to be
true for that to be safe, and what each section below asserts:

**The generator cannot deliver twice.** Idempotency is a unique constraint in
the database, not a check in this process — so the test that matters runs the
generator twice and counts rows, and a second run reports `created: 0`.

**The generator cannot invoice anybody.** A generated delivery is `scheduled`,
which is not in `BILLABLE_STATUSES`, so it is worth 0.00 and appears on no
bill until a person says the milk arrived. A generator that could bill would
invoice a dairy's whole round every morning, silently.

**A plan is the source for the FUTURE.** Changing one supersedes it; yesterday
keeps the quantity it was delivered at. §8 is the rule and superseding is the
mechanism that was already there.

**A day belongs to the dairy.** Generating at 00:30 IST produces the Indian
day that has just begun, not the UTC day that is still yesterday.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from platform_core.modules.customer.schedule import (
    EVERY_DAY,
    MONDAY_TO_SATURDAY,
    WEEKDAYS_ONLY,
    delivers_on_weekday,
    describe,
    due_on,
    is_paused,
    next_due,
    normalise_weekdays,
    quantity_for,
    within_dates,
)
from tests.conftest import register_and_login
from tests.test_org_structure import _tenant_admin

# 2026-08-10 is a Monday. Every date below is built from it so the weekday
# arithmetic is legible rather than something the reader has to look up.
MONDAY = date(2026, 8, 10)
SATURDAY = MONDAY + timedelta(days=5)
SUNDAY = MONDAY + timedelta(days=6)


# --- the schedule, as arithmetic ---------------------------------------------


def test_a_mask_is_seven_days_starting_on_monday():
    assert delivers_on_weekday(EVERY_DAY, MONDAY)
    assert delivers_on_weekday(EVERY_DAY, SUNDAY)
    assert delivers_on_weekday(WEEKDAYS_ONLY, MONDAY)
    assert not delivers_on_weekday(WEEKDAYS_ONLY, SATURDAY)
    assert not delivers_on_weekday(WEEKDAYS_ONLY, SUNDAY)
    assert delivers_on_weekday(MONDAY_TO_SATURDAY, SATURDAY)
    assert not delivers_on_weekday(MONDAY_TO_SATURDAY, SUNDAY)


def test_every_day_of_one_week_is_covered_exactly_once():
    """Not a tautology: an off-by-one in the index would still pass any single
    assertion above while shifting the whole round by a day."""
    days = [MONDAY + timedelta(days=i) for i in range(7)]
    for index, day in enumerate(days):
        mask = "".join("1" if i == index else "0" for i in range(7))
        assert delivers_on_weekday(mask, day), day
        assert sum(delivers_on_weekday(mask, d) for d in days) == 1


@pytest.mark.parametrize("bad", ["", "111", "11111111", "1111112", "abcdefg", "0000000"])
def test_a_mask_that_is_not_a_week_is_refused(bad):
    """A mask that is quietly wrong is a household that stops getting milk on
    Tuesdays with nobody knowing why."""
    with pytest.raises(ValueError):
        normalise_weekdays(bad)


def test_no_mask_at_all_means_every_day():
    assert normalise_weekdays(None) == EVERY_DAY


def test_a_plan_delivers_on_its_own_first_day():
    """Inclusive at both ends. A half-open range would skip a customer's very
    first delivery, which is the one they would notice."""
    assert within_dates(MONDAY, MONDAY, None)
    assert not within_dates(MONDAY - timedelta(days=1), MONDAY, None)
    assert within_dates(SUNDAY, MONDAY, SUNDAY)
    assert not within_dates(SUNDAY + timedelta(days=1), MONDAY, SUNDAY)


def test_no_end_date_means_ongoing():
    assert within_dates(MONDAY + timedelta(days=3650), MONDAY, None)


def test_a_pause_covers_both_its_ends():
    assert is_paused(MONDAY, MONDAY, SUNDAY)
    assert is_paused(SUNDAY, MONDAY, SUNDAY)
    assert not is_paused(MONDAY - timedelta(days=1), MONDAY, SUNDAY)
    assert not is_paused(SUNDAY + timedelta(days=1), MONDAY, SUNDAY)


def test_a_pause_with_no_end_runs_until_further_notice():
    """What an operator means when a customer leaves without saying when they
    are back."""
    assert is_paused(MONDAY + timedelta(days=400), MONDAY, None)


def test_a_pause_end_with_no_beginning_is_not_a_pause():
    assert not is_paused(MONDAY, None, SUNDAY)


def test_a_weekday_override_changes_only_that_day():
    overrides = {"5": "30.000"}  # Saturday
    assert quantity_for(SATURDAY, Decimal("20.000"), overrides) == Decimal("30.000")
    assert quantity_for(MONDAY, Decimal("20.000"), overrides) == Decimal("20.000")


def test_a_nonsense_override_falls_back_rather_than_stopping_the_round():
    """At GENERATION time the round has to go out. A mistyped override is a
    wrong quantity for one customer; raising here would be no milk for the
    whole dairy. (The API refuses the same input at the door — see
    `test_an_override_for_a_day_that_is_not_a_weekday_is_refused`.)"""
    assert quantity_for(MONDAY, Decimal("2.000"), {"0": "not a number"}) == Decimal("2.000")
    assert quantity_for(MONDAY, Decimal("2.000"), {"0": "-5"}) == Decimal("2.000")


def test_due_on_needs_all_of_it_to_hold():
    kwargs = dict(
        weekdays=WEEKDAYS_ONLY,
        effective_from=MONDAY,
        effective_to=None,
        paused_from=None,
        paused_to=None,
    )
    assert due_on(MONDAY, **kwargs)
    assert not due_on(SATURDAY, **kwargs)  # mask
    assert not due_on(MONDAY - timedelta(days=1), **kwargs)  # before it starts
    assert not due_on(MONDAY, **{**kwargs, "paused_from": MONDAY, "paused_to": SUNDAY})


def test_next_due_skips_the_days_the_round_does_not_run():
    """Friday's answer for a Monday-to-Saturday plan is Saturday; Sunday's is
    the following Monday."""
    kwargs = dict(
        weekdays=MONDAY_TO_SATURDAY,
        effective_from=MONDAY,
        effective_to=None,
        paused_from=None,
        paused_to=None,
    )
    assert next_due(SATURDAY, **kwargs) == SATURDAY
    assert next_due(SUNDAY, **kwargs) == MONDAY + timedelta(days=7)


def test_next_due_looks_past_a_holiday():
    assert next_due(
        MONDAY,
        weekdays=EVERY_DAY,
        effective_from=MONDAY,
        effective_to=None,
        paused_from=MONDAY,
        paused_to=SUNDAY,
    ) == SUNDAY + timedelta(days=1)


def test_next_due_gives_up_rather_than_looping_forever():
    """A plan that ended, or one paused indefinitely, has no next delivery.
    An unbounded search on such a row would hang the page that asks."""
    assert (
        next_due(
            MONDAY,
            weekdays=EVERY_DAY,
            effective_from=MONDAY,
            effective_to=SUNDAY,
            paused_from=MONDAY,
            paused_to=None,
        )
        is None
    )


def test_a_schedule_is_described_by_key_never_by_a_sentence():
    """The platform does not decide what a Hindi-speaking manager reads."""
    assert describe(EVERY_DAY) == "schedule.daily"
    assert describe(WEEKDAYS_ONLY) == "schedule.weekdays"
    assert describe(MONDAY_TO_SATURDAY) == "schedule.mon_sat"
    assert describe("1010101") == "schedule.custom"
    for key in (describe(EVERY_DAY), describe("1010101")):
        assert key.startswith("schedule.")
        assert " " not in key


# --- the API -----------------------------------------------------------------


async def _plan_env(client, **plan):
    """A customer with a standing order, in a dairy with a manager."""
    _org, admin = await _tenant_admin(client)
    body = {
        "name": "Sharma Household",
        "customer_type": "household",
        "phone": "+919845000101",
        "plan": {
            "product": "RAW-COW-MILK",
            "default_quantity": "2.000",
            "quantity_unit": "L",
            "unit_price": "56.0000",
            "effective_from": str(MONDAY),
            **plan,
        },
    }
    r = await client.post("/v1/customers", json=body, headers=admin)
    assert r.status_code == 201, r.text
    return admin, r.json()


async def _generate(client, admin, day):
    r = await client.post("/v1/deliveries/generate", json={"for_date": str(day)}, headers=admin)
    assert r.status_code == 200, r.text
    return r.json()


async def test_a_plan_carries_its_schedule_back(client):
    admin, customer = await _plan_env(client, weekdays=MONDAY_TO_SATURDAY)
    detail = (await client.get(f"/v1/customers/{customer['id']}", headers=admin)).json()
    plan = detail["plans"][0]
    assert plan["weekdays"] == MONDAY_TO_SATURDAY
    assert plan["schedule_key"] == "schedule.mon_sat"
    assert plan["effective_to"] is None
    assert plan["slot"] == "morning"


async def test_an_existing_plan_without_a_schedule_delivers_every_day(client):
    """The migration's promise: a plan written before DEMO-016 becomes a daily
    standing order, which is what it already meant in practice."""
    admin, customer = await _plan_env(client)
    detail = (await client.get(f"/v1/customers/{customer['id']}", headers=admin)).json()
    assert detail["plans"][0]["weekdays"] == EVERY_DAY
    assert detail["plans"][0]["schedule_key"] == "schedule.daily"


async def test_a_plan_says_when_the_milk_is_next_coming(client):
    admin, customer = await _plan_env(client, weekdays=WEEKDAYS_ONLY)
    detail = (await client.get(f"/v1/customers/{customer['id']}", headers=admin)).json()
    assert detail["plans"][0]["next_delivery"] is not None


async def test_an_override_for_a_day_that_is_not_a_weekday_is_refused(client):
    """A manager typing `{"7": ...}` meaning Sunday is told, rather than
    silently given the default every week until the bill looks wrong."""
    _org, admin = await _tenant_admin(client)
    r = await client.post(
        "/v1/customers",
        json={
            "name": "Bad Override",
            "plan": {
                "unit_price": "50.0000",
                "default_quantity": "1.000",
                "quantity_overrides": {"7": "3.000"},
            },
        },
        headers=admin,
    )
    assert r.status_code == 422, r.text


async def test_a_plan_that_ends_before_it_begins_is_refused(client):
    _org, admin = await _tenant_admin(client)
    r = await client.post(
        "/v1/customers",
        json={
            "name": "Backwards",
            "plan": {
                "unit_price": "50.0000",
                "effective_from": str(SUNDAY),
                "effective_to": str(MONDAY),
            },
        },
        headers=admin,
    )
    assert r.status_code == 409, r.text


# --- generation ---------------------------------------------------------------


async def test_generation_produces_the_days_round(client):
    admin, _customer = await _plan_env(client)
    result = await _generate(client, admin, MONDAY)
    assert result["business_date"] == str(MONDAY)
    assert result["due"] == 1
    assert result["created"] == 1
    assert result["already_present"] == 0

    page = (
        await client.get(
            "/v1/deliveries",
            params={"date_from": str(MONDAY), "date_to": str(MONDAY)},
            headers=admin,
        )
    ).json()
    assert page["total"] == 1
    row = page["items"][0]
    assert row["status"] == "scheduled"
    assert Decimal(row["quantity"]) == Decimal("2.000")
    assert Decimal(row["unit_price"]) == Decimal("56.0000")
    assert row["plan_id"] is not None


async def test_running_it_twice_does_not_deliver_twice(client):
    """THE test. Idempotency is a unique constraint, so this is what proves it
    — not the presence of a check somewhere in the code."""
    admin, _customer = await _plan_env(client)
    first = await _generate(client, admin, MONDAY)
    second = await _generate(client, admin, MONDAY)

    assert first["created"] == 1
    assert second["created"] == 0
    assert second["already_present"] == 1

    page = (
        await client.get(
            "/v1/deliveries",
            params={"date_from": str(MONDAY), "date_to": str(MONDAY)},
            headers=admin,
        )
    ).json()
    assert page["total"] == 1


async def test_a_generated_delivery_is_worth_nothing_until_it_happens(client):
    """The single omission that makes this safe to deploy: `scheduled` is not
    in BILLABLE_STATUSES, so a generated round cannot invoice anybody."""
    admin, customer = await _plan_env(client)
    await _generate(client, admin, MONDAY)

    page = (await client.get("/v1/deliveries", headers=admin)).json()
    assert Decimal(page["items"][0]["amount"]) == Decimal("0.00")
    assert Decimal(page["total_amount"]) == Decimal("0.00")

    balance = (await client.get(f"/v1/customers/{customer['id']}/balance", headers=admin)).json()
    assert Decimal(balance["unbilled_amount"]) == Decimal("0.00")

    bill = await client.post(
        "/v1/invoices",
        json={
            "customer_id": customer["id"],
            "period_from": str(MONDAY),
            "period_to": str(MONDAY),
        },
        headers=admin,
    )
    assert bill.status_code == 409, "a scheduled round must not be billable"


async def test_a_weekday_the_plan_skips_generates_nothing(client):
    admin, _customer = await _plan_env(client, weekdays=MONDAY_TO_SATURDAY)
    result = await _generate(client, admin, SUNDAY)
    assert result["due"] == 0
    assert result["created"] == 0
    assert result["not_due"] == 1


async def test_a_paused_plan_generates_nothing(client):
    admin, customer = await _plan_env(client)
    detail = (await client.get(f"/v1/customers/{customer['id']}", headers=admin)).json()
    plan_id = detail["plans"][0]["id"]

    paused = await client.post(
        f"/v1/customers/plans/{plan_id}/pause",
        json={"paused_from": str(MONDAY), "paused_to": str(SUNDAY)},
        headers=admin,
    )
    assert paused.status_code == 200, paused.text

    result = await _generate(client, admin, SATURDAY)
    assert result["created"] == 0
    assert result["due"] == 0


async def test_resuming_does_not_backfill_the_holiday(client):
    """Milk that was not delivered is not delivered later. Inventing those rows
    would put a fortnight of holiday on the customer's next bill."""
    admin, customer = await _plan_env(client)
    detail = (await client.get(f"/v1/customers/{customer['id']}", headers=admin)).json()
    plan_id = detail["plans"][0]["id"]

    await client.post(
        f"/v1/customers/plans/{plan_id}/pause",
        json={"paused_from": str(MONDAY), "paused_to": str(SATURDAY)},
        headers=admin,
    )
    await _generate(client, admin, SATURDAY)  # nothing, it is paused
    resumed = await client.post(f"/v1/customers/plans/{plan_id}/resume", json={}, headers=admin)
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["paused_from"] is None

    after = await _generate(client, admin, SUNDAY)
    assert after["created"] == 1

    every = (await client.get("/v1/deliveries", headers=admin)).json()
    assert every["total"] == 1, "the paused days must not appear afterwards"


async def test_an_inactive_customer_gets_no_round(client):
    admin, customer = await _plan_env(client)
    await client.post(
        f"/v1/customers/{customer['id']}/status", json={"status": "suspended"}, headers=admin
    )
    result = await _generate(client, admin, MONDAY)
    assert result["created"] == 0
    assert result["inactive_customers"] == 1


async def test_a_zero_override_means_no_delivery_that_day(client):
    """How a plan says "not on Sundays" without changing its mask. Not a
    zero-litre delivery sitting on the round asking to be confirmed."""
    admin, _customer = await _plan_env(client, quantity_overrides={"6": "0"})
    assert (await _generate(client, admin, SUNDAY))["created"] == 0
    assert (await _generate(client, admin, MONDAY))["created"] == 1


async def test_a_saturday_override_delivers_more(client):
    admin, _customer = await _plan_env(
        client, weekdays=EVERY_DAY, quantity_overrides={"5": "30.000"}
    )
    await _generate(client, admin, SATURDAY)
    page = (await client.get("/v1/deliveries", headers=admin)).json()
    assert Decimal(page["items"][0]["quantity"]) == Decimal("30.000")


# --- the operator's day -------------------------------------------------------


async def test_recording_over_a_generated_delivery_confirms_it(client):
    """§11: an operator does not need to know whether the round was generated
    or typed, and cannot tell from the call they make."""
    admin, customer = await _plan_env(client)
    await _generate(client, admin, MONDAY)

    r = await client.post(
        "/v1/deliveries",
        json={
            "customer_id": customer["id"],
            "delivery_date": str(MONDAY),
            "slot": "morning",
            "quantity": "2.500",
            "status": "delivered",
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text
    row = r.json()
    assert row["status"] == "delivered"
    assert Decimal(row["quantity"]) == Decimal("2.500")
    # Priced by the domain from the plan's rate, at confirmation.
    assert Decimal(row["amount"]) == Decimal("140.00")

    page = (await client.get("/v1/deliveries", headers=admin)).json()
    assert page["total"] == 1, "confirming must not create a second delivery"


async def test_confirming_without_a_quantity_takes_the_scheduled_one(client):
    """The common case on a round is "yes, the usual"."""
    admin, customer = await _plan_env(client)
    await _generate(client, admin, MONDAY)
    r = await client.post(
        "/v1/deliveries",
        json={
            "customer_id": customer["id"],
            "delivery_date": str(MONDAY),
            "status": "delivered",
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text
    assert Decimal(r.json()["quantity"]) == Decimal("2.000")
    assert Decimal(r.json()["amount"]) == Decimal("112.00")


async def test_a_generated_delivery_can_be_skipped(client):
    admin, customer = await _plan_env(client)
    await _generate(client, admin, MONDAY)
    r = await client.post(
        "/v1/deliveries",
        json={
            "customer_id": customer["id"],
            "delivery_date": str(MONDAY),
            "status": "skipped",
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "skipped"
    assert Decimal(r.json()["amount"]) == Decimal("0.00")


async def test_a_confirmed_delivery_cannot_be_confirmed_again(client):
    """Only a SCHEDULED row is fillable. Once it has been anywhere, a second
    record is the collision it always was."""
    admin, customer = await _plan_env(client)
    await _generate(client, admin, MONDAY)
    body = {
        "customer_id": customer["id"],
        "delivery_date": str(MONDAY),
        "status": "delivered",
    }
    assert (await client.post("/v1/deliveries", json=body, headers=admin)).status_code == 201
    assert (await client.post("/v1/deliveries", json=body, headers=admin)).status_code == 409


async def test_the_report_separates_planned_from_completed(client):
    """§13's operational question: how many are left?"""
    admin, customer = await _plan_env(client)
    await _generate(client, admin, MONDAY)
    params = {"date_from": str(MONDAY), "date_to": str(MONDAY)}

    before = (await client.get("/v1/deliveries/report", params=params, headers=admin)).json()
    assert before["planned"] == 1
    assert before["scheduled"] == 1
    assert before["deliveries"] == 0

    await client.post(
        "/v1/deliveries",
        json={
            "customer_id": customer["id"],
            "delivery_date": str(MONDAY),
            "status": "delivered",
        },
        headers=admin,
    )
    after = (await client.get("/v1/deliveries/report", params=params, headers=admin)).json()
    assert after["planned"] == 1
    assert after["scheduled"] == 0
    assert after["deliveries"] == 1
    assert Decimal(after["total_amount"]) == Decimal("112.00")


# --- history is not rewritten -------------------------------------------------


async def test_changing_a_plan_leaves_yesterdays_delivery_alone(client):
    """§8, and the mechanism is the superseding DEMO-009 already had."""
    admin, customer = await _plan_env(client)
    await _generate(client, admin, MONDAY)
    await client.post(
        "/v1/deliveries",
        json={
            "customer_id": customer["id"],
            "delivery_date": str(MONDAY),
            "status": "delivered",
        },
        headers=admin,
    )

    # The customer now wants three litres a day.
    changed = await client.post(
        f"/v1/customers/{customer['id']}/plan",
        json={
            "product": "RAW-COW-MILK",
            "default_quantity": "3.000",
            "unit_price": "56.0000",
            "effective_from": str(MONDAY + timedelta(days=1)),
        },
        headers=admin,
    )
    assert changed.status_code == 201, changed.text

    yesterday = (
        await client.get(
            "/v1/deliveries",
            params={"date_from": str(MONDAY), "date_to": str(MONDAY)},
            headers=admin,
        )
    ).json()["items"][0]
    assert Decimal(yesterday["quantity"]) == Decimal("2.000"), "history was rewritten"
    assert Decimal(yesterday["amount"]) == Decimal("112.00")

    await _generate(client, admin, MONDAY + timedelta(days=1))
    tomorrow = (
        await client.get(
            "/v1/deliveries",
            params={
                "date_from": str(MONDAY + timedelta(days=1)),
                "date_to": str(MONDAY + timedelta(days=1)),
            },
            headers=admin,
        )
    ).json()["items"][0]
    assert Decimal(tomorrow["quantity"]) == Decimal("3.000")


async def test_a_superseded_plan_reports_no_next_delivery(client):
    admin, customer = await _plan_env(client)
    await client.post(
        f"/v1/customers/{customer['id']}/plan",
        json={"unit_price": "60.0000", "default_quantity": "2.000"},
        headers=admin,
    )
    detail = (await client.get(f"/v1/customers/{customer['id']}", headers=admin)).json()
    superseded = [p for p in detail["plans"] if not p["active"]]
    assert superseded and superseded[0]["next_delivery"] is None


# --- the whole chain ----------------------------------------------------------


async def test_a_generated_delivery_bills_like_any_other(client):
    """§14: no special billing path. Generate → confirm → bill → pay."""
    admin, customer = await _plan_env(client)
    for offset in range(3):
        day = MONDAY + timedelta(days=offset)
        await _generate(client, admin, day)
        await client.post(
            "/v1/deliveries",
            json={
                "customer_id": customer["id"],
                "delivery_date": str(day),
                "status": "delivered",
            },
            headers=admin,
        )

    invoice = await client.post(
        "/v1/invoices",
        json={
            "customer_id": customer["id"],
            "period_from": str(MONDAY),
            "period_to": str(MONDAY + timedelta(days=2)),
        },
        headers=admin,
    )
    assert invoice.status_code == 201, invoice.text
    body = invoice.json()
    assert body["line_count"] == 3
    assert Decimal(body["total"]) == Decimal("336.00")  # 3 x 2L x 56.00

    issued = await client.post(f"/v1/invoices/{body['id']}/issue", json={}, headers=admin)
    assert issued.status_code == 200
    paid = await client.post(
        "/v1/customer-payments",
        json={"customer_id": customer["id"], "amount": "336.00", "method": "CASH"},
        headers=admin,
    )
    assert paid.status_code == 201, paid.text
    balance = (await client.get(f"/v1/customers/{customer['id']}/balance", headers=admin)).json()
    assert Decimal(balance["outstanding"]) == Decimal("0.00")


# --- security -----------------------------------------------------------------


async def test_generating_needs_its_own_grant(client):
    """Separate from `sales.delivery.record`: recording is what a rider does
    all morning; this creates a whole dairy's day."""
    _org, _admin = await _tenant_admin(client)
    _user, outsider = await register_and_login(client, email="nobody-016@example.com")
    r = await client.post("/v1/deliveries/generate", json={}, headers=outsider)
    assert r.status_code in (401, 403)


async def test_pausing_a_plan_needs_the_manage_grant(client):
    admin, customer = await _plan_env(client)
    detail = (await client.get(f"/v1/customers/{customer['id']}", headers=admin)).json()
    plan_id = detail["plans"][0]["id"]
    _user, outsider = await register_and_login(client, email="nobody-pause@example.com")
    r = await client.post(
        f"/v1/customers/plans/{plan_id}/pause",
        json={"paused_from": str(MONDAY)},
        headers=outsider,
    )
    assert r.status_code in (401, 403)


async def test_another_dairy_cannot_pause_this_ones_plan(client):
    """404, never 403 — and emphatically not a successful pause."""
    from tests.test_payments import _second_tenant

    admin, customer = await _plan_env(client)
    detail = (await client.get(f"/v1/customers/{customer['id']}", headers=admin)).json()
    plan_id = detail["plans"][0]["id"]
    other = await _second_tenant(client)
    r = await client.post(
        f"/v1/customers/plans/{plan_id}/pause",
        json={"paused_from": str(MONDAY)},
        headers=other,
    )
    assert r.status_code == 404


async def test_generation_is_confined_to_its_own_tenant(client):
    """The generator runs over "every active plan", and the sentence that
    matters is which tenant's."""
    from tests.test_payments import _second_tenant

    admin, _customer = await _plan_env(client)
    other = await _second_tenant(client)

    mine = await _generate(client, admin, MONDAY)
    assert mine["created"] == 1

    theirs = await client.post(
        "/v1/deliveries/generate", json={"for_date": str(MONDAY)}, headers=other
    )
    assert theirs.status_code in (200, 403)
    if theirs.status_code == 200:
        assert theirs.json()["created"] == 0, "generated another dairy's round"
    assert (await client.get("/v1/deliveries", headers=other)).json()["total"] == 0


async def test_an_unknown_plan_is_404_not_500(client):
    _org, admin = await _tenant_admin(client)
    r = await client.post(
        f"/v1/customers/plans/{uuid.uuid4()}/pause",
        json={"paused_from": str(MONDAY)},
        headers=admin,
    )
    assert r.status_code == 404


# --- the dairy's own midnight (§6) --------------------------------------------


async def test_generation_uses_the_dairys_day_not_utcs(client):
    """§6, and the defect DEMO-015 found in the portal's date picker.

    At 20:00 UTC Bengaluru is already 01:30 on the NEXT day. A generator that
    took UTC's calendar date would produce yesterday's round — every morning,
    for the first five and a half hours of every Indian day, which is exactly
    when a dairy generates.
    """
    from datetime import datetime
    from unittest.mock import patch
    from zoneinfo import ZoneInfo

    from tests.test_localization import _tenant_admin_for

    _org, admin = await _tenant_admin_for(
        client, country="IN", slug="tz-gen", email="tzgen@india.example"
    )
    r = await client.post(
        "/v1/customers",
        json={
            "name": "Midnight Household",
            "plan": {"unit_price": "56.0000", "default_quantity": "2.000"},
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text

    # 20:00 UTC on the 13th is 01:30 IST on the 14th.
    instant = datetime(2026, 8, 13, 20, 0, tzinfo=ZoneInfo("UTC"))
    with patch("platform_core.core.business_time.datetime") as clock:
        clock.now.return_value = instant
        generated = await client.post("/v1/deliveries/generate", json={}, headers=admin)
    assert generated.status_code == 200, generated.text
    assert generated.json()["business_date"] == "2026-08-14", (
        "the round was filed under UTC's day, not the dairy's"
    )


async def test_a_round_of_three_hundred_is_one_statement(client):
    """§20. Not a benchmark — a guard against `for customer in customers:
    create delivery`, which is what the work order names as the thing not to
    write. Three hundred plans must not become three hundred INSERTs.
    """
    _org, admin = await _tenant_admin(client)
    for index in range(300):
        r = await client.post(
            "/v1/customers",
            json={
                "name": f"Household {index:03d}",
                "plan": {
                    "unit_price": "56.0000",
                    "default_quantity": "1.000",
                    "effective_from": str(MONDAY),
                },
            },
            headers=admin,
        )
        assert r.status_code == 201, r.text

    from platform_core.modules.delivery import generation

    inserts = 0
    original = generation._insert_ignoring_conflicts

    def counting(session, rows):
        nonlocal inserts
        inserts += 1
        return original(session, rows)

    generation._insert_ignoring_conflicts = counting
    try:
        result = await _generate(client, admin, MONDAY)
    finally:
        generation._insert_ignoring_conflicts = original

    assert result["created"] == 300
    assert inserts == 1, f"{inserts} INSERTs for one round — batching is not working"

    # And running it again over three hundred plans still creates nothing.
    again = await _generate(client, admin, MONDAY)
    assert again["created"] == 0
    assert again["already_present"] == 300
