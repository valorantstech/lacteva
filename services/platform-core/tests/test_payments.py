"""Payment Execution Engine (PAY-001): allocation against finalized
settlements, outstanding balance, lifecycle, attempts, retry, cancel,
idempotency, events, permissions, tenant isolation.

A settlement built by `_payable` is worth 7897.50 KES (125.5 kg + 50 kg at
45.00) — every balance assertion below is anchored on that number.
"""

import uuid
from decimal import Decimal

from tests.conftest import register_and_login
from tests.test_settlement_lifecycle import _post, _with_lines
from tests.test_settlements import (
    _add_calculation,
    _calculation_id,
    _create_settlement,
)
from tests.test_suppliers import _create_supplier

FULL = Decimal("7897.50")


async def _payable(client, quantities=(125.5, 50.0)):
    """Tenant admin + a FINALIZED settlement ready to be paid."""
    headers, center, supplier, settlement = await _with_lines(client, quantities)
    await _post(client, headers, settlement["id"], "calculate")
    r = await _post(client, headers, settlement["id"], "finalize")
    assert r.status_code == 200, r.text
    return headers, center, supplier, r.json()


async def _second_settlement(client, headers, center, supplier, *, on="2026-11-15"):
    """A second finalized settlement for the SAME supplier (November — periods
    must not overlap, BR-0009)."""
    settlement = await _create_settlement(
        client,
        headers,
        supplier["id"],
        center["id"],
        period_from="2026-11-01",
        period_to="2026-11-30",
    )
    calc_id = await _calculation_id(client, headers, center["id"], quantity=10.0, on=on)
    r = await _add_calculation(client, headers, settlement["id"], calc_id)
    assert r.status_code == 201, r.text
    await _post(client, headers, settlement["id"], "calculate")
    r = await _post(client, headers, settlement["id"], "finalize")
    assert r.status_code == 200, r.text
    return r.json()


async def _create_payment(client, headers, supplier_id, allocations, **overrides):
    body = {
        "supplier_id": supplier_id,
        "currency": "KES",
        "method": "BANK_TRANSFER",
        "allocations": allocations,
        **overrides,
    }
    return await client.post("/v1/payments", json=body, headers=headers)


async def _pay(client, headers, settlement, *, amount=None, **overrides):
    """Create a payment for one settlement (full outstanding unless amount)."""
    allocation = {"settlement_id": settlement["id"]}
    if amount is not None:
        allocation["amount"] = str(amount)
    r = await _create_payment(client, headers, settlement["supplier_id"], [allocation], **overrides)
    assert r.status_code == 201, r.text
    return r.json()


async def _action(client, headers, payment_id, action, body=None):
    return await client.post(
        f"/v1/payments/{payment_id}/{action}",
        json=body if body is not None else {},
        headers=headers,
    )


async def _complete(client, headers, payment_id, *, reference="BNK-1"):
    """Drive a draft payment all the way to completed."""
    assert (await _action(client, headers, payment_id, "submit")).status_code == 200
    assert (await _action(client, headers, payment_id, "execute")).status_code == 200
    r = await _action(client, headers, payment_id, "complete", {"reference": reference})
    assert r.status_code == 200, r.text
    return r.json()


async def _balance(client, headers, settlement_id) -> dict:
    r = await client.get(f"/v1/settlements/{settlement_id}/balance", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def _viewer(client, headers):
    """A tenant-viewer inside the SAME tenant as `headers`."""
    tenant_id = (await client.get("/v1/auth/me", headers=headers)).json()["tenant_id"]
    inv = (
        await client.post(
            "/v1/invitations",
            json={"email": "viewer@kilima.example", "role_name": "tenant-viewer"},
            headers=headers,
        )
    ).json()
    await client.post(
        "/v1/invitations/accept",
        json={
            "token": inv["invitation_token"],
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
                "tenant_id": tenant_id,
            },
        )
    ).json()
    return {"Authorization": f"Bearer {pair['access_token']}"}


async def _second_tenant(client):
    """A separate organization with its own tenant admin (distinct root user —
    `_tenant_admin` may only be called once per test)."""
    _, root = await register_and_login(client, "root2@example.com", admin=True)
    org = (
        await client.post(
            "/v1/organizations",
            json={"name": "Rift Valley Dairy", "slug": "rift", "country_code": "ke"},
            headers=root,
        )
    ).json()
    inv = (
        await client.post(
            "/v1/invitations",
            json={"email": "manager@rift.example", "role_name": "tenant-admin"},
            headers={**root, "X-Tenant-ID": org["id"]},
        )
    ).json()
    await client.post(
        "/v1/invitations/accept",
        json={
            "token": inv["invitation_token"],
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
                "tenant_id": org["id"],
            },
        )
    ).json()
    return {"Authorization": f"Bearer {pair['access_token']}"}


# --- creation & allocation ---------------------------------------------------


async def test_payment_pays_the_full_outstanding_balance(client):
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement)
    assert Decimal(payment["amount"]) == FULL
    assert payment["status"] == "draft" and payment["line_count"] == 1
    assert payment["payment_number"].startswith("PAY-")


async def test_partial_payment_leaves_the_remainder_outstanding(client):
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement, amount="3000.00")
    assert Decimal(payment["amount"]) == Decimal("3000.00")
    balance = await _balance(client, headers, settlement["id"])
    assert Decimal(balance["payable"]) == FULL
    assert Decimal(balance["allocated"]) == Decimal("3000.00")
    assert Decimal(balance["outstanding"]) == Decimal("4897.50")
    assert balance["fully_paid"] is False


async def test_remaining_balance_can_be_paid_by_a_second_payment(client):
    headers, _center, _supplier, settlement = await _payable(client)
    first = await _pay(client, headers, settlement, amount="3000.00")
    await _complete(client, headers, first["id"])
    # No amount = "the rest of it".
    second = await _pay(client, headers, settlement)
    assert Decimal(second["amount"]) == Decimal("4897.50")
    await _complete(client, headers, second["id"], reference="BNK-2")
    balance = await _balance(client, headers, settlement["id"])
    assert Decimal(balance["outstanding"]) == Decimal("0.00")
    assert Decimal(balance["paid"]) == FULL
    assert balance["fully_paid"] is True


async def test_payment_covers_multiple_settlements(client):
    headers, center, supplier, october = await _payable(client)
    november = await _second_settlement(client, headers, center, supplier)
    r = await _create_payment(
        client,
        headers,
        supplier["id"],
        [{"settlement_id": october["id"]}, {"settlement_id": november["id"]}],
    )
    assert r.status_code == 201, r.text
    payment = r.json()
    assert payment["line_count"] == 2
    assert Decimal(payment["amount"]) == FULL + Decimal(november["net_amount"])
    detail = (await client.get(f"/v1/payments/{payment['id']}", headers=headers)).json()
    numbers = {line["settlement_number"] for line in detail["lines"]}
    assert numbers == {october["settlement_number"], november["settlement_number"]}
    assert detail["totals_match_lines"] is True


async def test_only_finalized_settlements_can_be_paid(client):
    headers, center, supplier, _settlement = await _with_lines(client)
    draft = await _create_settlement(
        client,
        headers,
        supplier["id"],
        center["id"],
        period_from="2026-11-01",
        period_to="2026-11-30",
    )
    r = await _create_payment(client, headers, supplier["id"], [{"settlement_id": draft["id"]}])
    assert r.status_code == 409
    assert "only finalized settlements can be paid" in r.text


async def test_payment_never_modifies_the_settlement(client):
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement)
    await _complete(client, headers, payment["id"])
    after = (await client.get(f"/v1/settlements/{settlement['id']}", headers=headers)).json()
    assert after["settlement"]["status"] == "finalized"
    assert Decimal(after["settlement"]["net_amount"]) == FULL
    assert after["settlement"]["finalized_at"] == settlement["finalized_at"]


async def test_currency_mismatch_is_rejected(client):
    headers, _center, _supplier, settlement = await _payable(client)
    r = await _create_payment(
        client,
        headers,
        settlement["supplier_id"],
        [{"settlement_id": settlement["id"]}],
        currency="USD",
    )
    assert r.status_code == 409
    assert "currency conversion is not a payment operation" in r.text


async def test_settlement_of_another_supplier_is_rejected(client):
    headers, _center, _supplier, settlement = await _payable(client)
    other = await _create_supplier(client, headers, name="Other Farmer", phone="+254700000999")
    r = await _create_payment(client, headers, other["id"], [{"settlement_id": settlement["id"]}])
    assert r.status_code == 409
    assert "different supplier" in r.text


async def test_unknown_method_is_rejected(client):
    headers, _center, _supplier, settlement = await _payable(client)
    r = await _create_payment(
        client,
        headers,
        settlement["supplier_id"],
        [{"settlement_id": settlement["id"]}],
        method="CRYPTO",
    )
    assert r.status_code == 422


async def test_every_supported_method_is_accepted(client):
    headers, _center, _supplier, settlement = await _payable(client)
    for method in ("BANK_TRANSFER", "CASH", "CHEQUE", "MOBILE_MONEY"):
        r = await _create_payment(
            client,
            headers,
            settlement["supplier_id"],
            [{"settlement_id": settlement["id"], "amount": "1000.00"}],
            method=method,
            method_details={"note": "metadata only — no gateway is called"},
        )
        assert r.status_code == 201, r.text
        assert r.json()["method"] == method
        assert r.json()["method_details"]["note"].startswith("metadata only")


# --- duplicate prevention (BR-0018) -----------------------------------------


async def test_over_allocation_is_rejected(client):
    headers, _center, _supplier, settlement = await _payable(client)
    r = await _create_payment(
        client,
        headers,
        settlement["supplier_id"],
        [{"settlement_id": settlement["id"], "amount": "9000.00"}],
    )
    assert r.status_code == 409
    assert "exceeds the outstanding" in r.text


async def test_second_payment_for_a_fully_allocated_settlement_is_rejected(client):
    headers, _center, _supplier, settlement = await _payable(client)
    await _pay(client, headers, settlement)  # a DRAFT already reserves it
    r = await _create_payment(
        client, headers, settlement["supplier_id"], [{"settlement_id": settlement["id"]}]
    )
    assert r.status_code == 409
    assert "already fully paid or allocated" in r.text


async def test_partial_over_allocation_across_two_payments_is_rejected(client):
    headers, _center, _supplier, settlement = await _payable(client)
    await _pay(client, headers, settlement, amount="5000.00")
    r = await _create_payment(
        client,
        headers,
        settlement["supplier_id"],
        [{"settlement_id": settlement["id"], "amount": "5000.00"}],
    )
    assert r.status_code == 409
    assert "exceeds the outstanding" in r.text


async def test_same_settlement_twice_in_one_payment_is_rejected(client):
    headers, _center, _supplier, settlement = await _payable(client)
    r = await _create_payment(
        client,
        headers,
        settlement["supplier_id"],
        [
            {"settlement_id": settlement["id"], "amount": "100.00"},
            {"settlement_id": settlement["id"], "amount": "100.00"},
        ],
    )
    assert r.status_code == 409
    assert "twice in one payment" in r.text


async def test_zero_and_negative_allocations_are_rejected(client):
    headers, _center, _supplier, settlement = await _payable(client)
    for amount in ("0.00", "-10.00"):
        r = await _create_payment(
            client,
            headers,
            settlement["supplier_id"],
            [{"settlement_id": settlement["id"], "amount": amount}],
        )
        assert r.status_code == 409, amount
        assert "positive amount" in r.text


async def test_cancelled_payment_releases_the_allocation(client):
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement)
    assert Decimal((await _balance(client, headers, settlement["id"]))["outstanding"]) == 0
    r = await _action(client, headers, payment["id"], "cancel", {"reason": "wrong account"})
    assert r.status_code == 200, r.text
    balance = await _balance(client, headers, settlement["id"])
    assert Decimal(balance["outstanding"]) == FULL
    # …and the settlement can be paid again.
    again = await _pay(client, headers, settlement)
    assert Decimal(again["amount"]) == FULL


async def test_failed_payment_releases_the_allocation(client):
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement)
    await _action(client, headers, payment["id"], "submit")
    await _action(client, headers, payment["id"], "execute")
    r = await _action(client, headers, payment["id"], "fail", {"reason": "account closed"})
    assert r.status_code == 200, r.text
    balance = await _balance(client, headers, settlement["id"])
    assert Decimal(balance["outstanding"]) == FULL
    assert Decimal(balance["allocated"]) == 0


# --- idempotency -------------------------------------------------------------


async def test_repeating_an_idempotency_key_returns_the_same_payment(client):
    headers, _center, _supplier, settlement = await _payable(client)
    first = await _pay(client, headers, settlement, amount="100.00", idempotency_key="op-1")
    second = await _pay(client, headers, settlement, amount="100.00", idempotency_key="op-1")
    assert first["id"] == second["id"]
    page = (await client.get("/v1/payments", headers=headers)).json()
    assert page["total"] == 1  # one payment, not two


async def test_idempotency_key_does_not_double_allocate(client):
    headers, _center, _supplier, settlement = await _payable(client)
    await _pay(client, headers, settlement, idempotency_key="op-full")
    await _pay(client, headers, settlement, idempotency_key="op-full")
    balance = await _balance(client, headers, settlement["id"])
    assert Decimal(balance["allocated"]) == FULL


async def test_distinct_idempotency_keys_are_distinct_payments(client):
    headers, _center, _supplier, settlement = await _payable(client)
    a = await _pay(client, headers, settlement, amount="100.00", idempotency_key="a")
    b = await _pay(client, headers, settlement, amount="100.00", idempotency_key="b")
    assert a["id"] != b["id"]


# --- lifecycle ---------------------------------------------------------------


async def test_full_lifecycle_draft_to_completed(client):
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement)
    assert payment["status"] == "draft"
    assert (await _action(client, headers, payment["id"], "submit")).json()["status"] == "pending"
    body = (await _action(client, headers, payment["id"], "execute")).json()
    assert body["status"] == "processing" and body["attempt_count"] == 1
    done = (
        await _action(client, headers, payment["id"], "complete", {"reference": "BNK-77"})
    ).json()
    assert done["status"] == "completed"
    assert done["reference"] == "BNK-77" and done["completed_at"] is not None


async def test_completed_payment_is_immutable(client):
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement)
    await _complete(client, headers, payment["id"])
    for action, body in (
        ("submit", {}),
        ("execute", {}),
        ("complete", {}),
        ("fail", {"reason": "no"}),
        ("cancel", {"reason": "no"}),
    ):
        r = await _action(client, headers, payment["id"], action, body)
        assert r.status_code == 409, action
        assert "completed payments are immutable" in r.text


async def test_cancelled_payment_is_terminal(client):
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement)
    await _action(client, headers, payment["id"], "cancel", {"reason": "duplicate"})
    for action in ("submit", "execute", "complete"):
        r = await _action(client, headers, payment["id"], action, {})
        assert r.status_code == 409, action
        assert "cancelled payments are terminal" in r.text


async def test_execute_requires_pending(client):
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement)  # still draft
    r = await _action(client, headers, payment["id"], "execute")
    assert r.status_code == 409
    assert "cannot become processing" in r.text


async def test_complete_requires_processing(client):
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement)
    await _action(client, headers, payment["id"], "submit")
    r = await _action(client, headers, payment["id"], "complete")
    assert r.status_code == 409
    assert "cannot become completed" in r.text


async def test_processing_payment_cannot_be_cancelled(client):
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement)
    await _action(client, headers, payment["id"], "submit")
    await _action(client, headers, payment["id"], "execute")
    r = await _action(client, headers, payment["id"], "cancel", {"reason": "changed my mind"})
    assert r.status_code == 409
    assert "record the failure first" in r.text


async def test_cancel_requires_a_reason(client):
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement)
    r = await _action(client, headers, payment["id"], "cancel", {"reason": ""})
    assert r.status_code == 422


# --- attempts & retry --------------------------------------------------------


async def test_failure_records_the_reason_and_closes_the_attempt(client):
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement)
    await _action(client, headers, payment["id"], "submit")
    await _action(client, headers, payment["id"], "execute", {"provider": "KCB"})
    await _action(client, headers, payment["id"], "fail", {"reason": "account closed"})
    detail = (await client.get(f"/v1/payments/{payment['id']}", headers=headers)).json()
    assert detail["payment"]["status"] == "failed"
    assert detail["payment"]["failure_reason"] == "account closed"
    attempt = detail["attempts"][0]
    assert attempt["attempt_number"] == 1 and attempt["provider"] == "KCB"
    assert attempt["status"] == "failed" and attempt["failure_reason"] == "account closed"
    assert attempt["completed_at"] is not None and attempt["operator_id"] is not None


async def test_retry_opens_a_new_attempt_and_can_succeed(client):
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement)
    await _action(client, headers, payment["id"], "submit")
    await _action(client, headers, payment["id"], "execute")
    await _action(client, headers, payment["id"], "fail", {"reason": "timeout"})
    r = await _action(client, headers, payment["id"], "retry", {"reference": "BNK-RETRY"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "processing" and r.json()["attempt_count"] == 2
    await _action(client, headers, payment["id"], "complete")
    detail = (await client.get(f"/v1/payments/{payment['id']}", headers=headers)).json()
    assert detail["payment"]["status"] == "completed"
    # The failure history survives the success (BR-0019).
    assert [a["attempt_number"] for a in detail["attempts"]] == [1, 2]
    assert detail["attempts"][0]["status"] == "failed"
    assert detail["attempts"][1]["status"] == "completed"
    assert detail["payment"]["failure_reason"] is None


async def test_retry_requires_a_failed_payment(client):
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement)
    r = await _action(client, headers, payment["id"], "retry")
    assert r.status_code == 409
    assert "only a failed payment can be retried" in r.text


async def test_failed_payment_can_be_cancelled_instead_of_retried(client):
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement)
    await _action(client, headers, payment["id"], "submit")
    await _action(client, headers, payment["id"], "execute")
    await _action(client, headers, payment["id"], "fail", {"reason": "wrong account"})
    r = await _action(client, headers, payment["id"], "cancel", {"reason": "will re-issue"})
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"


async def test_repeated_failures_accumulate_attempts(client):
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement)
    await _action(client, headers, payment["id"], "submit")
    for i in range(3):
        action = "execute" if i == 0 else "retry"
        await _action(client, headers, payment["id"], action)
        await _action(client, headers, payment["id"], "fail", {"reason": f"attempt {i}"})
    detail = (await client.get(f"/v1/payments/{payment['id']}", headers=headers)).json()
    assert detail["payment"]["attempt_count"] == 3
    assert len(detail["attempts"]) == 3
    assert all(a["status"] == "failed" for a in detail["attempts"])


# --- concurrency -------------------------------------------------------------


async def test_concurrent_completion_only_succeeds_once(client):
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement)
    await _action(client, headers, payment["id"], "submit")
    await _action(client, headers, payment["id"], "execute")
    first = await _action(client, headers, payment["id"], "complete")
    second = await _action(client, headers, payment["id"], "complete")
    assert first.status_code == 200
    assert second.status_code == 409  # CAS: the second caller loses
    balance = await _balance(client, headers, settlement["id"])
    assert Decimal(balance["paid"]) == FULL  # paid once, not twice


async def test_concurrent_submit_only_succeeds_once(client):
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement)
    first = await _action(client, headers, payment["id"], "submit")
    second = await _action(client, headers, payment["id"], "submit")
    assert first.status_code == 200 and second.status_code == 409


# --- outstanding balance -----------------------------------------------------


async def test_balance_of_an_unpaid_settlement_is_the_full_payable(client):
    headers, _center, _supplier, settlement = await _payable(client)
    balance = await _balance(client, headers, settlement["id"])
    assert Decimal(balance["payable"]) == FULL
    assert Decimal(balance["allocated"]) == 0 and Decimal(balance["paid"]) == 0
    assert Decimal(balance["outstanding"]) == FULL
    assert balance["settlement_number"] == settlement["settlement_number"]


async def test_allocated_and_paid_are_distinct(client):
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement, amount="1000.00")
    balance = await _balance(client, headers, settlement["id"])
    assert Decimal(balance["allocated"]) == Decimal("1000.00")
    assert Decimal(balance["paid"]) == 0  # still a draft — reserved, not paid
    await _complete(client, headers, payment["id"])
    balance = await _balance(client, headers, settlement["id"])
    assert Decimal(balance["paid"]) == Decimal("1000.00")


async def test_balances_list_shows_only_outstanding_by_default(client):
    headers, center, supplier, october = await _payable(client)
    november = await _second_settlement(client, headers, center, supplier)
    payment = await _pay(client, headers, october)
    await _complete(client, headers, payment["id"])
    page = (await client.get("/v1/payments/balances", headers=headers)).json()
    ids = [b["settlement_id"] for b in page["items"]]
    assert october["id"] not in ids and november["id"] in ids
    every = (
        await client.get("/v1/payments/balances?outstanding_only=false", headers=headers)
    ).json()
    assert {b["settlement_id"] for b in every["items"]} == {october["id"], november["id"]}


async def test_balances_filter_by_supplier(client):
    headers, center, supplier, _october = await _payable(client)
    await _second_settlement(client, headers, center, supplier)
    stranger = await _create_supplier(client, headers, name="Zawadi", phone="+254700000888")
    page = (
        await client.get(f"/v1/payments/balances?supplier_id={stranger['id']}", headers=headers)
    ).json()
    assert page["total"] == 0
    mine = (
        await client.get(f"/v1/payments/balances?supplier_id={supplier['id']}", headers=headers)
    ).json()
    assert mine["total"] == 2


async def test_balances_paginate(client):
    headers, center, supplier, _october = await _payable(client)
    await _second_settlement(client, headers, center, supplier)
    page = (await client.get("/v1/payments/balances?limit=1&offset=0", headers=headers)).json()
    assert page["total"] == 2 and len(page["items"]) == 1
    second = (await client.get("/v1/payments/balances?limit=1&offset=1", headers=headers)).json()
    assert second["items"][0]["settlement_id"] != page["items"][0]["settlement_id"]


async def test_balance_of_an_unknown_settlement_is_404(client):
    headers, _center, _supplier, _settlement = await _payable(client)
    r = await client.get(f"/v1/settlements/{uuid.uuid4()}/balance", headers=headers)
    assert r.status_code == 404


# --- events ------------------------------------------------------------------


async def test_payment_lifecycle_emits_every_event(client, bus):
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement)
    await _action(client, headers, payment["id"], "submit")
    await _action(client, headers, payment["id"], "execute")
    await _action(client, headers, payment["id"], "fail", {"reason": "bounced"})
    await _action(client, headers, payment["id"], "retry")
    await _action(client, headers, payment["id"], "complete", {"reference": "OK-1"})
    types = [e.type for e in bus.published if e.type.startswith("payment.")]
    assert "payment.created.v1" in types
    assert "payment.processing.v1" in types
    assert "payment.failed.v1" in types
    assert "payment.retry.v1" in types
    assert "payment.completed.v1" in types


async def test_cancellation_emits_its_event(client, bus):
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement)
    await _action(client, headers, payment["id"], "cancel", {"reason": "duplicate"})
    cancelled = [e for e in bus.published if e.type == "payment.cancelled.v1"]
    assert len(cancelled) == 1
    assert cancelled[0].data["reason"] == "duplicate"
    assert cancelled[0].aggregate_type == "payment"


async def test_completed_event_carries_what_the_notification_needs(client, bus):
    """The notification engine (NOT-001) consumes payment.completed.v1 and
    renders supplier name, amount, currency, settlement number, reference."""
    headers, _center, supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement)
    await _complete(client, headers, payment["id"], reference="MPESA-XY7")
    event = next(e for e in bus.published if e.type == "payment.completed.v1")
    assert event.data["supplier_id"] == supplier["id"]
    assert Decimal(event.data["amount"]) == FULL
    assert event.data["currency"] == "KES"
    assert event.data["settlement_number"] == settlement["settlement_number"]
    assert event.data["reference"] == "MPESA-XY7"


async def test_multi_settlement_completion_names_the_payment(client, bus):
    """One message per payment: with several settlements the payment number is
    the reference a farmer can quote, not an arbitrary settlement."""
    headers, center, supplier, october = await _payable(client)
    november = await _second_settlement(client, headers, center, supplier)
    r = await _create_payment(
        client,
        headers,
        supplier["id"],
        [{"settlement_id": october["id"]}, {"settlement_id": november["id"]}],
    )
    payment = r.json()
    await _complete(client, headers, payment["id"])
    event = next(e for e in bus.published if e.type == "payment.completed.v1")
    assert event.data["settlement_number"] == payment["payment_number"]
    assert len(event.data["settlement_ids"]) == 2


# --- history, search, pagination ---------------------------------------------


async def test_history_lists_payments_newest_first(client):
    headers, _center, _supplier, settlement = await _payable(client)
    await _pay(client, headers, settlement, amount="10.00")
    await _pay(client, headers, settlement, amount="20.00")
    page = (await client.get("/v1/payments", headers=headers)).json()
    assert page["total"] == 2
    assert Decimal(page["items"][0]["amount"]) == Decimal("20.00")


async def test_history_filters_by_status_and_method(client):
    headers, _center, _supplier, settlement = await _payable(client)
    first = await _pay(client, headers, settlement, amount="10.00")
    await _pay(client, headers, settlement, amount="20.00", method="CASH")
    await _complete(client, headers, first["id"])
    completed = (await client.get("/v1/payments?status=completed", headers=headers)).json()
    assert completed["total"] == 1 and completed["items"][0]["id"] == first["id"]
    cash = (await client.get("/v1/payments?method=CASH", headers=headers)).json()
    assert cash["total"] == 1 and cash["items"][0]["method"] == "CASH"


async def test_history_search_by_number_and_reference(client):
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement, reference="CHQ-00042")
    found = (await client.get("/v1/payments?q=chq-000", headers=headers)).json()
    assert found["total"] == 1 and found["items"][0]["id"] == payment["id"]
    by_number = (
        await client.get(f"/v1/payments?q={payment['payment_number'][4:]}", headers=headers)
    ).json()
    assert by_number["total"] == 1


async def test_history_filters_by_settlement(client):
    headers, center, supplier, october = await _payable(client)
    november = await _second_settlement(client, headers, center, supplier)
    await _pay(client, headers, october)
    nov_payment = await _pay(client, headers, november)
    page = (
        await client.get(f"/v1/payments?settlement_id={november['id']}", headers=headers)
    ).json()
    assert page["total"] == 1 and page["items"][0]["id"] == nov_payment["id"]


async def test_history_paginates(client):
    headers, _center, _supplier, settlement = await _payable(client)
    for amount in ("10.00", "20.00", "30.00"):
        await _pay(client, headers, settlement, amount=amount)
    page = (await client.get("/v1/payments?limit=2&offset=0", headers=headers)).json()
    assert page["total"] == 3 and len(page["items"]) == 2
    assert page["limit"] == 2 and page["offset"] == 0
    last = (await client.get("/v1/payments?limit=2&offset=2", headers=headers)).json()
    assert len(last["items"]) == 1


async def test_payment_detail_is_404_for_unknown_id(client):
    headers, _center, _supplier, _settlement = await _payable(client)
    r = await client.get(f"/v1/payments/{uuid.uuid4()}", headers=headers)
    assert r.status_code == 404


# --- permissions -------------------------------------------------------------


async def test_payment_api_requires_authentication(client):
    assert (await client.get("/v1/payments")).status_code in (401, 403)


async def test_viewer_reads_but_cannot_pay(client):
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement)
    viewer = await _viewer(client, headers)
    assert (await client.get("/v1/payments", headers=viewer)).status_code == 200
    assert (await client.get("/v1/payments/balances", headers=viewer)).status_code == 200
    assert (await client.get(f"/v1/payments/{payment['id']}", headers=viewer)).status_code == 200
    for action, body in (
        ("submit", {}),
        ("execute", {}),
        ("retry", {}),
        ("cancel", {"reason": "no"}),
    ):
        r = await _action(client, viewer, payment["id"], action, body)
        assert r.status_code == 403, action
    r = await _create_payment(
        client, viewer, settlement["supplier_id"], [{"settlement_id": settlement["id"]}]
    )
    assert r.status_code == 403


async def test_user_without_payment_permission_is_forbidden(client):
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement)
    _, outsider = await register_and_login(client, "outsider@example.com")
    for method, path in (
        ("get", "/v1/payments"),
        ("get", f"/v1/payments/{payment['id']}"),
        ("get", "/v1/payments/balances"),
    ):
        r = await getattr(client, method)(path, headers=outsider)
        assert r.status_code == 403, path
    r = await client.post(
        f"/v1/payments/{payment['id']}/cancel", json={"reason": "x"}, headers=outsider
    )
    assert r.status_code == 403


async def test_all_payment_permissions_are_registered(client):
    from platform_core.modules.authz.permissions import PERMISSIONS

    for key in ("payment.read", "payment.manage", "payment.retry", "payment.cancel"):
        assert key in PERMISSIONS


# --- tenant isolation --------------------------------------------------------


async def test_payments_are_invisible_across_tenants(client):
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement)

    other_headers = await _second_tenant(client)
    page = (await client.get("/v1/payments", headers=other_headers)).json()
    assert page["total"] == 0
    r = await client.get(f"/v1/payments/{payment['id']}", headers=other_headers)
    assert r.status_code == 404  # never leak another tenant's existence
    r = await client.get(f"/v1/settlements/{settlement['id']}/balance", headers=other_headers)
    assert r.status_code == 404


async def test_another_tenant_cannot_act_on_a_payment(client):
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement)
    other_headers = await _second_tenant(client)
    for action, body in (("submit", {}), ("cancel", {"reason": "x"})):
        r = await _action(client, other_headers, payment["id"], action, body)
        assert r.status_code == 404, action
