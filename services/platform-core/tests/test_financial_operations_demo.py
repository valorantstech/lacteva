"""Settlement and payment operations, executed (DEMO-006).

The admin portal decides which lifecycle buttons to show by mirroring the
guards in `SettlementService` and `PaymentService`. A mirror is a claim, and a
claim about a guard is worth nothing until the guard is made to *refuse*. So
every test here drives the real API and asserts a refusal:

* a finalized settlement rejects **every** mutation — collect, calculate,
  cancel, add-line, remove-line. That is what the portal's empty lifecycle bar
  asserts visually, proved here as five separate 409s;
* `settlement.finalize` is a permission the API declares separately from
  `settlement.manage`, and a manager who lacks it is refused;
* a processing payment cannot be cancelled — the portal hides that button for
  exactly this reason, and the truthful sequence is fail-then-cancel;
* neither a settlement nor a payment is reachable, readable or actionable from
  another tenant, which returns 404 rather than 403 so that the existence of a
  row is never leaked.
"""

import uuid
from decimal import Decimal

from tests.conftest import invite
from tests.test_payments import (
    _action,
    _pay,
    _payable,
    _second_tenant,
)
from tests.test_settlements import (
    _add_calculation,
    _calculation_id,
    _settlement_env,
)


async def _post(client, headers, settlement_id, action, body=None):
    return await client.post(
        f"/v1/settlements/{settlement_id}/{action}",
        json=body if body is not None else {},
        headers=headers,
    )


async def _finalized(client):
    """A settlement with one line, calculated and finalized."""
    headers, center, supplier, settlement = await _settlement_env(client)
    calc_id = await _calculation_id(client, headers, center["id"], quantity=20.0)
    assert (await _add_calculation(client, headers, settlement["id"], calc_id)).status_code == 201
    assert (await _post(client, headers, settlement["id"], "calculate")).status_code == 200
    r = await _post(client, headers, settlement["id"], "finalize")
    assert r.status_code == 200, r.text
    return headers, center, supplier, r.json()


async def _user_with(client, admin_headers, *permission_keys, email, role_name):
    """A user in the SAME tenant holding exactly `permission_keys`."""
    me = (await client.get("/v1/auth/me", headers=admin_headers)).json()
    tenant_id = me["tenant_id"]
    r = await client.post(
        "/v1/authz/roles",
        json={"name": role_name, "permission_keys": list(permission_keys)},
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    _inv, inv_token = await invite(client, admin_headers, email=email, role_name=role_name)
    r = await client.post(
        "/v1/invitations/accept",
        json={"token": inv_token, "password": "operator-password-1", "full_name": "Operator"},
    )
    assert r.status_code in (200, 201), r.text
    pair = (
        await client.post(
            "/v1/auth/token",
            json={"email": email, "password": "operator-password-1", "tenant_id": tenant_id},
        )
    ).json()
    return {"Authorization": f"Bearer {pair['access_token']}"}


# --- immutability: what the portal's empty lifecycle bar means ----------------


async def test_finalized_settlement_refuses_every_mutation(client):
    """BR-0010, executed. The portal shows no lifecycle button on a finalized
    settlement; here is the platform refusing each of them in turn."""
    headers, center, _supplier, settlement = await _finalized(client)
    sid = settlement["id"]

    for action, body in (
        ("collect", {}),
        ("calculate", {}),
        ("finalize", {}),
        ("cancel", {"reason": "changed my mind"}),
    ):
        r = await _post(client, headers, sid, action, body)
        assert r.status_code == 409, f"{action} -> {r.status_code} {r.text}"

    # Adding a line, and removing one, are refused for the same reason.
    calc_id = await _calculation_id(client, headers, center["id"], quantity=5.0)
    r = await _add_calculation(client, headers, sid, calc_id)
    assert r.status_code == 409, r.text

    lines = (await client.get(f"/v1/settlements/{sid}", headers=headers)).json()["lines"]
    r = await client.delete(f"/v1/settlements/{sid}/lines/{lines[0]['id']}", headers=headers)
    assert r.status_code == 409, r.text

    # And nothing moved.
    after = (await client.get(f"/v1/settlements/{sid}", headers=headers)).json()["settlement"]
    assert after["status"] == "finalized"
    assert Decimal(str(after["net_amount"])) == Decimal(str(settlement["net_amount"]))
    assert after["line_count"] == settlement["line_count"]


async def test_finalize_is_refused_from_draft_and_from_an_empty_settlement(client):
    """The portal offers Finalize only from `calculated` with at least one
    line. Both halves of that condition are the platform's, not the portal's."""
    headers, center, _supplier, settlement = await _settlement_env(client)
    sid = settlement["id"]

    # draft, no lines
    assert (await _post(client, headers, sid, "finalize")).status_code == 409
    # calculated, still no lines
    assert (await _post(client, headers, sid, "calculate")).status_code == 200
    r = await _post(client, headers, sid, "finalize")
    assert r.status_code == 409
    assert "no lines" in r.json()["extra"]

    # a line drops it back to draft — finalize is refused again until recalculated
    calc_id = await _calculation_id(client, headers, center["id"], quantity=8.0)
    assert (await _add_calculation(client, headers, sid, calc_id)).status_code == 201
    assert (await client.get(f"/v1/settlements/{sid}", headers=headers)).json()["settlement"][
        "status"
    ] == "draft"
    assert (await _post(client, headers, sid, "finalize")).status_code == 409


# --- authorization: finalize is its own permission ----------------------------


async def test_manager_without_finalize_permission_is_refused(client):
    """`settlement.finalize` is declared separately from `settlement.manage`
    precisely so that freezing money can be a different job. A user with manage
    can calculate; the same user cannot finalize."""
    headers, center, _supplier, settlement = await _settlement_env(client)
    calc_id = await _calculation_id(client, headers, center["id"], quantity=12.0)
    assert (await _add_calculation(client, headers, settlement["id"], calc_id)).status_code == 201

    operator = await _user_with(
        client,
        headers,
        "settlement.read",
        "settlement.manage",
        email="settler@kilima.example",
        role_name="settlement-operator",
    )

    # Allowed: read and calculate.
    assert (await client.get("/v1/settlements", headers=operator)).status_code == 200
    assert (await _post(client, operator, settlement["id"], "calculate")).status_code == 200
    # Refused: finalize.
    assert (await _post(client, operator, settlement["id"], "finalize")).status_code == 403

    # The settlement is still calculated — the refusal changed nothing.
    body = (await client.get(f"/v1/settlements/{settlement['id']}", headers=headers)).json()
    assert body["settlement"]["status"] == "calculated"


async def test_finalize_permission_alone_is_enough_to_finalize(client):
    """The mirror image: a user holding read + finalize may freeze it, and
    that is the whole point of the split."""
    headers, center, _supplier, settlement = await _settlement_env(client)
    calc_id = await _calculation_id(client, headers, center["id"], quantity=12.0)
    assert (await _add_calculation(client, headers, settlement["id"], calc_id)).status_code == 201
    assert (await _post(client, headers, settlement["id"], "calculate")).status_code == 200

    approver = await _user_with(
        client,
        headers,
        "settlement.read",
        "settlement.finalize",
        email="approver@kilima.example",
        role_name="settlement-approver",
    )
    r = await _post(client, approver, settlement["id"], "finalize")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "finalized"
    # ...but that user still cannot open a new period.
    assert (await _post(client, approver, settlement["id"], "collect")).status_code == 403


# --- tenant isolation ---------------------------------------------------------


async def test_settlements_are_invisible_and_inert_across_tenants(client):
    headers, _center, _supplier, settlement = await _finalized(client)
    sid = settlement["id"]
    other = await _second_tenant(client)

    page = (await client.get("/v1/settlements", headers=other)).json()
    assert page["total"] == 0
    # 404, never 403: another tenant's row does not exist as far as this
    # organization is concerned.
    assert (await client.get(f"/v1/settlements/{sid}", headers=other)).status_code == 404
    for action, body in (
        ("collect", {}),
        ("calculate", {}),
        ("finalize", {}),
        ("cancel", {"reason": "x"}),
    ):
        r = await _post(client, other, sid, action, body)
        assert r.status_code == 404, f"{action} -> {r.status_code}"

    r = await client.post(
        f"/v1/settlements/{sid}/calculations",
        json={"calculation_id": str(uuid.uuid4())},
        headers=other,
    )
    assert r.status_code == 404

    # And the owning tenant is untouched.
    assert (await client.get(f"/v1/settlements/{sid}", headers=headers)).status_code == 200


async def test_a_payment_cannot_be_reached_from_another_tenant(client):
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement)
    other = await _second_tenant(client)

    assert (await client.get("/v1/payments", headers=other)).json()["total"] == 0
    assert (await client.get(f"/v1/payments/{payment['id']}", headers=other)).status_code == 404
    for action, body in (
        ("submit", {}),
        ("execute", {}),
        ("complete", {}),
        ("fail", {"reason": "x"}),
        ("cancel", {"reason": "x"}),
    ):
        r = await _action(client, other, payment["id"], action, body)
        assert r.status_code == 404, f"{action} -> {r.status_code}"

    # Still a draft in its own tenant.
    body = (await client.get(f"/v1/payments/{payment['id']}", headers=headers)).json()
    assert body["payment"]["status"] == "draft"


# --- the payment failure path, as the portal drives it ------------------------


async def test_processing_payment_refuses_cancellation_but_accepts_failure(client):
    """The portal hides `Cancel` while a payment is processing and says why.
    This is that rule, executed: cancel is refused, fail is accepted, and the
    reason the operator typed is what the platform stores."""
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement)
    pid = payment["id"]

    assert (await _action(client, headers, pid, "submit")).status_code == 200
    r = await _action(client, headers, pid, "execute", {"provider": "mpesa-b2c"})
    assert r.status_code == 200, r.text

    r = await _action(client, headers, pid, "cancel", {"reason": "too late"})
    assert r.status_code == 409
    assert "record the failure first" in r.json()["extra"]

    reason = "provider rejected: invalid account 254700000001"
    r = await _action(client, headers, pid, "fail", {"reason": reason})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "failed"
    assert r.json()["failure_reason"] == reason

    detail = (await client.get(f"/v1/payments/{pid}", headers=headers)).json()
    assert detail["attempts"][-1]["status"] == "failed"
    assert detail["attempts"][-1]["failure_reason"] == reason

    # The money is released: the settlement is payable again.
    balance = (
        await client.get(f"/v1/settlements/{settlement['id']}/balance", headers=headers)
    ).json()
    assert Decimal(balance["outstanding"]) == Decimal(balance["payable"])

    # And now cancelling IS permitted — the truthful sequence.
    r = await _action(client, headers, pid, "cancel", {"reason": "abandoned"})
    assert r.status_code == 200, r.text


async def test_a_retry_opens_a_new_attempt_and_keeps_the_failed_one(client):
    """BR-0019: attempts are never reused. The portal's attempt history is
    therefore an audit trail, and this is what it is a trail of."""
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement)
    pid = payment["id"]

    await _action(client, headers, pid, "submit")
    await _action(client, headers, pid, "execute", {"provider": "mpesa-b2c"})
    await _action(client, headers, pid, "fail", {"reason": "network timeout"})

    r = await _action(client, headers, pid, "retry", {"provider": "mpesa-b2c"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "processing"
    # The retry cleared the payment-level reason, but not the attempt's.
    assert r.json()["failure_reason"] is None

    detail = (await client.get(f"/v1/payments/{pid}", headers=headers)).json()
    attempts = detail["attempts"]
    assert [a["attempt_number"] for a in attempts] == [1, 2]
    assert attempts[0]["status"] == "failed"
    assert attempts[0]["failure_reason"] == "network timeout"
    assert attempts[1]["status"] == "processing"


async def test_completed_payment_refuses_every_further_operation(client):
    """The portal offers no operation on a completed payment. Here is why."""
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement)
    pid = payment["id"]
    await _action(client, headers, pid, "submit")
    await _action(client, headers, pid, "execute")
    r = await _action(client, headers, pid, "complete", {"reference": "BNK-9"})
    assert r.status_code == 200, r.text

    for action, body in (
        ("submit", {}),
        ("execute", {}),
        ("retry", {}),
        ("complete", {}),
        ("fail", {"reason": "x"}),
        ("cancel", {"reason": "x"}),
    ):
        r = await _action(client, headers, pid, action, body)
        assert r.status_code == 409, f"{action} -> {r.status_code} {r.text}"

    body = (await client.get(f"/v1/payments/{pid}", headers=headers)).json()
    assert body["payment"]["status"] == "completed"
    assert body["totals_match_lines"] is True
