"""A total may never wear the wrong currency (WO-61 · LACTEVA-BACKEND-007).

WHAT THE OWNER SAW. Signed into a demo dairy, the settlements page listed
four settlements of 3,600.00 + 450.00 + 450.00 + 5,647.50 **KES** and headed
them with a "Finalized value" tile reading their exact sum, 10,147.50,
labelled **INR**. Same tenant, same page, same money, two currencies. For a
platform whose whole claim is exact money, a total in the wrong currency is
worse than no total.

WHY IT COULD HAPPEN. `SettlementSummary.finalized_net_total` was a bare
`Decimal`: the platform summed money and did not say what money it was. A
client that must render a number it has no denomination for has exactly one
place left to look — the organization — and the organization's currency is
not a property of the rows. It agrees with them right up until it doesn't.

THE RULE THESE HOLD DOWN. **An aggregate carries the currency of the rows it
sums, or it does not go out.** Not the organization's, not a default, not the
client's guess. Where a tenant genuinely holds more than one currency the
answer is a figure per currency and never one number, because adding shillings
to rupees is not an arithmetic problem, it is a category error.
"""

import pytest

pytestmark = pytest.mark.asyncio


async def _make_the_organization_say_rupees(org_id: str) -> None:
    """Point the organization's money at INR, leaving its rows alone.

    This is not hypothetical: `Phoenix Demo Dairy` on the live host is exactly
    this shape — an Indian tenant seeded before DEMO-013 removed the hardcoded
    `"KES"` default, so its four settlements are stored in shillings while its
    organization row correctly says rupees. The data is legacy; the lie the
    page told about it was current.
    """
    import uuid as _uuid

    from sqlalchemy import update

    from platform_core.core.db import get_session_factory
    from platform_core.modules.organization.models import Organization

    async with get_session_factory()() as session:
        await session.execute(
            update(Organization)
            .where(Organization.id == _uuid.UUID(org_id))
            .values(country_code="IN", currency_code="INR")
        )
        await session.commit()


async def test_a_settlement_total_is_labelled_by_its_rows_not_by_the_organization(client):
    """The owner's screenshot, as an assertion.

    The organization says INR. The settlements say KES. The total may say only
    one thing, and it is not the organization's.
    """
    from tests.test_message_delivery import _settlement_env

    headers, _supplier, settlement = await _settlement_env(client)
    finalized = await client.post(f"/v1/settlements/{settlement['id']}/finalize", headers=headers)
    assert finalized.status_code == 200, finalized.text
    assert finalized.json()["currency"] == "KES"
    net = finalized.json()["net_amount"]

    me = (await client.get("/v1/auth/me", headers=headers)).json()
    await _make_the_organization_say_rupees(me["organization"]["id"])
    after = (await client.get("/v1/auth/me", headers=headers)).json()
    assert after["organization"]["currency_code"] == "INR", "the fixture did not take"

    report = (await client.get("/v1/reports/settlements", headers=headers)).json()
    assert report["finalized_by_currency"] == {"KES": net}, (
        "the finalized total is not denominated by the settlements it sums — a client "
        f"can only guess, and it guesses the organization: {report}"
    )
    assert "INR" not in report["finalized_by_currency"]
    # And the per-status row says what money it is in, for the same reason.
    finalized_row = next(r for r in report["by_status"] if r["status"] == "finalized")
    assert finalized_row["currency"] == "KES"


async def test_a_payment_total_is_labelled_by_its_rows(client):
    """The same rule on the money going out."""
    from tests.test_message_delivery import _settlement_env

    headers, _supplier, _settlement = await _settlement_env(client)
    me = (await client.get("/v1/auth/me", headers=headers)).json()
    await _make_the_organization_say_rupees(me["organization"]["id"])

    report = (await client.get("/v1/reports/payments", headers=headers)).json()
    for field in ("completed_by_currency", "outstanding_by_currency", "failed_by_currency"):
        assert field in report, f"{field} missing — a payment total with no denomination"
        assert "INR" not in report[field], (
            "a payment total is being denominated from the organization rather than "
            f"from the payments: {report[field]}"
        )


@pytest.mark.filterwarnings("ignore::pytest.PytestWarning")
async def test_no_reporting_total_goes_out_without_its_currency():
    """The structural guard, so the next aggregate cannot repeat this.

    Every money field on a reporting DTO must either be keyed BY currency, or
    sit beside a `currency` field on the same model. A bare `Decimal` total is
    a number a client has to denominate for itself, and the only thing it has
    to hand is the organization — which is how a Kenyan total came to be
    labelled in rupees.
    """
    import inspect

    from platform_core.modules.reporting import service as reporting

    #: Money by name. `Decimal` alone is not the test — a quantity is a
    #: Decimal too, and litres have no currency.
    MONEY = ("amount", "total", "payable", "net", "gross", "balance", "outstanding", "value")
    #: Models whose money is a single row's own, carried beside it.
    exempt_with_currency_field = set()

    offenders: list[str] = []
    for name, model in vars(reporting).items():
        if not (inspect.isclass(model) and hasattr(model, "model_fields")):
            continue
        fields = model.model_fields
        has_currency = "currency" in fields
        for field_name, field in fields.items():
            annotation = str(field.annotation)
            if "Decimal" not in annotation:
                continue
            if "dict" in annotation.lower():
                continue  # keyed BY currency — the shape this rule asks for
            if not any(word in field_name for word in MONEY):
                continue
            if has_currency:
                exempt_with_currency_field.add(name)
                continue
            offenders.append(f"{name}.{field_name}")
    assert not offenders, (
        "money aggregated without a currency — each of these forces a client to "
        f"denominate a total for itself: {sorted(offenders)}"
    )
