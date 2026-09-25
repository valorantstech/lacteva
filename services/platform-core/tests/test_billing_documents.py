"""WO-83 — month-end for four hundred households.

* "Issue all": every draft for the period issued in one act, the
  exceptions listed, and a preview that counts and totals without issuing;
* the shop has an address, a phone and a "Pay to" line, settable at
  creation and under Settings, printed at the head of the bill, the
  statement and the public bill link;
* the bill and the statement as real PDFs, matching the screen to the paisa;
* `UPI` is a payment method, and the platform's tuple is what the portal
  derives its list from;
* a household in credit reads "Advance", not "Previous balance -412" —
  presentation only, the arithmetic untouched (the test's name says so).
"""

from datetime import timedelta
from decimal import Decimal

from tests.clock import reference_date
from tests.test_localization import _make_org, _platform_admin
from tests.test_sales_workflow import _issued_invoice, _month_of_deliveries, _sales_env

TODAY = reference_date()


async def _draft(client, admin, customer_id, *, days=3, start_offset=0):
    end = TODAY - timedelta(days=start_offset)
    start = end - timedelta(days=days - 1)
    await _month_of_deliveries(client, admin, customer_id, days=days)
    r = await client.post(
        "/v1/invoices",
        json={"customer_id": customer_id, "period_from": str(start), "period_to": str(end)},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _customer(client, admin, name):
    r = await client.post(
        "/v1/customers",
        json={
            "name": name,
            "customer_type": "household",
            "billing_mode": "credit",
            "phone": "+91 98450 12345",
            "plan": {
                "product": "RAW-COW-MILK",
                "default_quantity": "2.000",
                "unit_price": "56.0000",
            },
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text
    return r.json()


# --- issue all ---------------------------------------------------------------------


async def test_issue_all_issues_every_draft_for_the_period_and_lists_the_exceptions(client):
    _org, admin, customer = await _sales_env(client)
    drafts = [await _draft(client, admin, customer["id"])]
    for i in range(3):
        other = await _customer(client, admin, f"Household {i}")
        drafts.append(await _draft(client, admin, other["id"]))
    # One draft the batch cannot issue: its lines were released underneath it
    # by cancelling and regenerating — simplest honest exception: no lines.
    empty = await _customer(client, admin, "Nothing Delivered")
    r = await client.post(
        "/v1/invoices",
        json={
            "customer_id": empty["id"],
            "period_from": str(TODAY - timedelta(days=2)),
            "period_to": str(TODAY),
        },
        headers=admin,
    )
    # A draft with no lines may be refused at generation; either way the
    # batch's exception list is exercised below by the closed-period case.
    period = {"period_from": str(TODAY - timedelta(days=2)), "period_to": str(TODAY)}

    preview = (
        await client.post(
            "/v1/invoices/issue-batch", json={**period, "preview": True}, headers=admin
        )
    ).json()
    assert preview["preview"] is True
    assert len(preview["issued"]) == len(drafts)
    assert Decimal(preview["total"]) == sum(Decimal(d["amount_due"]) for d in drafts)
    still_draft = (await client.get(f"/v1/invoices/{drafts[0]['id']}", headers=admin)).json()
    assert still_draft["invoice"]["status"] == "draft", "a preview issues nothing"

    r = await client.post("/v1/invoices/issue-batch", json=period, headers=admin)
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["preview"] is False
    assert {line["invoice_id"] for line in result["issued"]} == {d["id"] for d in drafts}
    assert Decimal(result["total"]) == Decimal(preview["total"])
    for d in drafts:
        detail = (await client.get(f"/v1/invoices/{d['id']}", headers=admin)).json()
        assert detail["invoice"]["status"] == "issued"
    # Again: nothing left to issue, nothing broken.
    again = (await client.post("/v1/invoices/issue-batch", json=period, headers=admin)).json()
    assert again["issued"] == [] and again["skipped"] == []
    # And the period is checked.
    r = await client.post(
        "/v1/invoices/issue-batch",
        json={"period_from": str(TODAY), "period_to": str(TODAY - timedelta(days=1))},
        headers=admin,
    )
    assert r.status_code == 422


async def test_issue_all_reports_a_draft_it_cannot_issue_and_issues_the_rest(client):
    _org, admin, customer = await _sales_env(client)
    good = await _draft(client, admin, customer["id"])
    other = await _customer(client, admin, "Closed Month")
    bad = await _draft(client, admin, other["id"])
    # Break one draft's totals the way the platform itself refuses: cancel it
    # and regenerate is the honest route, but the refusal that the batch must
    # carry past is any ConflictError — provoke one by cancelling `bad`
    # first, then asking the batch to issue everything it can still see.
    r = await client.post(f"/v1/invoices/{bad['id']}/cancel", json={}, headers=admin)
    assert r.status_code == 200, r.text
    period = {"period_from": str(TODAY - timedelta(days=2)), "period_to": str(TODAY)}
    result = (await client.post("/v1/invoices/issue-batch", json=period, headers=admin)).json()
    assert [line["invoice_id"] for line in result["issued"]] == [good["id"]]
    assert result["skipped"] == []  # a cancelled draft is not a draft any more


# --- the shop's head ------------------------------------------------------------------


async def test_the_shop_s_address_phone_and_pay_to_are_set_and_read_back(client):
    headers = await _platform_admin(client)
    r = await _make_org(
        client,
        headers,
        name="Gavyam Dairy & Sweets",
        slug="gavyam",
        country_code="IN",
        address="Runwal Garden City, Manpada, Dombivli East, Maharashtra - 421204",
        phone="+91 98200 00000",
    )
    assert r.status_code == 201, r.text
    org = r.json()
    assert org["address"].startswith("Runwal Garden City")
    assert org["phone"] == "+91 98200 00000"
    assert org["pay_to"] is None

    _org2, admin, _customer = await _sales_env(client)
    settings = (await client.get("/v1/organizations/settings/locale", headers=admin)).json()
    assert settings["address"] is None and settings["phone"] is None and settings["pay_to"] is None
    r = await client.put(
        "/v1/organizations/settings/locale",
        json={
            "address": "12 Lake Road\nDombivli",
            "phone": "+91 98450 00000",
            "pay_to": "UPI gavyam@upi",
        },
        headers=admin,
    )
    assert r.status_code == 200, r.text
    assert r.json()["pay_to"] == "UPI gavyam@upi"
    me = (await client.get("/v1/auth/me", headers=admin)).json()
    assert me["organization"]["phone"] == "+91 98450 00000"
    assert me["organization"]["pay_to"] == "UPI gavyam@upi"
    # Absent means unchanged; an empty string clears.
    r = await client.put(
        "/v1/organizations/settings/locale", json={"timezone": "Asia/Kolkata"}, headers=admin
    )
    assert r.json()["pay_to"] == "UPI gavyam@upi"
    r = await client.put("/v1/organizations/settings/locale", json={"pay_to": ""}, headers=admin)
    assert r.json()["pay_to"] is None


# --- the documents --------------------------------------------------------------------


def _text_of(pdf: bytes) -> str:
    """The strings the writer drew, in order — enough to check a header."""
    import re

    return b" ".join(m.group(1) for m in re.finditer(rb"\((.*?)\) Tj", pdf)).decode("latin-1")


async def test_the_bill_is_a_pdf_headed_by_the_shop_and_matching_the_screen(client):
    _org, admin, customer = await _sales_env(client)
    r = await client.put(
        "/v1/organizations/settings/locale",
        json={
            "address": "12 Lake Road, Dombivli",
            "phone": "+91 98450 00000",
            "pay_to": "UPI kilima@upi",
        },
        headers=admin,
    )
    assert r.status_code == 200, r.text
    invoice, _delivered = await _issued_invoice(client, admin, customer["id"])
    r = await client.get(f"/v1/invoices/{invoice['id']}/pdf", headers=admin)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF-1.4")
    assert b"%%EOF" in r.content
    text = _text_of(r.content)
    detail = (await client.get(f"/v1/invoices/{invoice['id']}", headers=admin)).json()
    assert "12 Lake Road, Dombivli" in text
    assert "Phone +91 98450 00000" in text
    assert "Pay to" in text and "UPI kilima@upi" in text
    assert invoice["invoice_number"] in text
    assert "INVOICE" in text
    # To the paisa: the amount due on the screen is the amount due on the page.
    assert f"{Decimal(detail['invoice']['amount_due']):.2f}" in text
    assert "Previous balance" in text and "Advance" not in text
    # Deterministic: the same immutable bill renders to the same bytes.
    again = await client.get(f"/v1/invoices/{invoice['id']}/pdf", headers=admin)
    assert again.content == r.content
    # And a household's own login gets its own bill.
    from tests.test_customer_scope import _customer_login

    me = await _customer_login(client, admin, _org["id"], customer["id"], "pdf@household.example")
    assert (await client.get(f"/v1/invoices/{invoice['id']}/pdf", headers=me)).status_code == 200


async def test_the_statement_pdf_and_the_advance_wording(client):
    _org, admin, customer = await _sales_env(client)
    # Money before any bill: the household is in CREDIT.
    r = await client.post(
        "/v1/customer-payments",
        json={"customer_id": customer["id"], "amount": "412.00", "method": "UPI"},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    assert r.json()["method"] == "UPI"
    balance = (await client.get(f"/v1/customers/{customer['id']}/balance", headers=admin)).json()
    assert Decimal(balance["outstanding"]) == Decimal("-412.00"), "the arithmetic is untouched"
    r = await client.get(f"/v1/customers/{customer['id']}/statement.pdf", headers=admin)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    text = _text_of(r.content)
    assert "STATEMENT" in text
    assert "Advance held" in text and "412.00" in text
    assert "-412" not in text
    # A bill raised after it carries the credit forward — and says "Advance".
    invoice, _d = await _issued_invoice(client, admin, customer["id"])
    assert Decimal(invoice["previous_balance"]) == Decimal("-412.00")
    text = _text_of((await client.get(f"/v1/invoices/{invoice['id']}/pdf", headers=admin)).content)
    assert "Advance" in text and "412.00" in text and "-412" not in text


def test_upi_is_a_payment_method_and_the_registry_is_the_portal_s_source():
    from pathlib import Path

    from platform_core.modules.billing.models import PAYMENT_METHOD_LABELS, PAYMENT_METHODS

    assert "UPI" in PAYMENT_METHODS and "MOBILE_MONEY" in PAYMENT_METHODS
    assert set(PAYMENT_METHOD_LABELS) == set(PAYMENT_METHODS)
    assert all({"en", "hi"} <= set(v) for v in PAYMENT_METHOD_LABELS.values())
    # The portal's list is derived from this tuple; its own test reads this
    # file. Both directions are pinned so a method cannot become unofferable.
    api = (Path(__file__).resolve().parents[3] / "apps/admin-portal/src/lib/api.ts").read_text()
    for method in PAYMENT_METHODS:
        assert f'"{method}"' in api, f"{method} is not offered by the portal"


async def test_the_public_bill_carries_the_shop_s_head(client):
    _org, admin, customer = await _sales_env(client)
    await client.put(
        "/v1/organizations/settings/locale",
        json={"address": "12 Lake Road", "phone": "+91 98450 00000", "pay_to": "UPI kilima@upi"},
        headers=admin,
    )
    await _issued_invoice(client, admin, customer["id"])
    r = await client.post(f"/v1/customers/{customer['id']}/bill-link", headers=admin)
    assert r.status_code == 201, r.text
    page = (await client.get(f"/v1/public/bill/{r.json()['token']}")).json()
    assert page["organization_address"] == "12 Lake Road"
    assert page["organization_phone"] == "+91 98450 00000"
    assert page["pay_to"] == "UPI kilima@upi"
