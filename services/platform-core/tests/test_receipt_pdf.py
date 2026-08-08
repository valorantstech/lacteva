"""Printable PDF receipts (PROD-001).

RCP-001 shipped a placeholder renderer that emitted a text file named
`.pdf.txt`. QR-0007 recorded that as a gap in feature completeness: a dairy
that hands farmers proof of payment could not.

These tests check the file is a real PDF rather than bytes that begin with
`%PDF` — the structure has to resolve, the content has to be present, and the
escaping boundary has to hold.
"""

import re
import uuid
from decimal import Decimal

import pytest

from platform_core.modules.receipt.pdf import build_pdf, render_receipt_pdf


def _receipt(**overrides) -> dict:
    receipt = {
        "id": str(uuid.uuid4()),
        "receipt_number": "RCP-A1B2C3",
        "status": "generated",
        "organization_name": "Nakuru Dairy Cooperative Society",
        "supplier_name": "Grace Njeri",
        "supplier_code": "S-004821",
        "payment_id": str(uuid.uuid4()),
        "payment_number": "PAY-77AA10",
        "payment_reference": "QGH7X2LM90",
        "payment_method": "MOBILE_MONEY",
        "payment_date": "2026-08-05",
        "currency": "KES",
        "gross_amount": "18450.75",
        "adjustments_amount": "-320.25",
        "net_amount": "18130.50",
        "generated_at": "2026-08-05T09:14:22Z",
        "lines": [
            {
                "settlement_number": "STL-9F3D21",
                "center_name": "Njoro Collection Center",
                "period_from": "2026-07-01",
                "period_to": "2026-07-31",
                "quantity": "412.500",
                "quantity_unit": "kg",
                "average_rate": "44.7291",
                "amount_paid": "18130.50",
                "gross_amount": "18450.75",
                "adjustments_amount": "-320.25",
            }
        ],
    }
    receipt.update(overrides)
    return receipt


def _xref_resolves(pdf: bytes) -> int:
    """Every cross-reference offset must land on its object header.

    This is what separates a real PDF from bytes that merely start with the
    right magic: a reader seeks by these offsets, so if they are wrong the file
    opens as corrupt no matter how correct the text inside is.
    """
    marker = re.search(rb"startxref\s+(\d+)", pdf)
    assert marker, "no startxref"
    start = int(marker.group(1))
    assert pdf[start : start + 4] == b"xref", "startxref does not point at the table"
    entries = re.findall(rb"^(\d{10}) (\d{5}) n\s*$", pdf[start:], re.M)
    assert entries, "no in-use xref entries"
    for index, (offset, _generation) in enumerate(entries, start=1):
        at = int(offset)
        assert re.match(rb"%d 0 obj" % index, pdf[at : at + 20]), (
            f"xref entry {index} points at {pdf[at : at + 20]!r}"
        )
    return len(entries)


def test_the_output_is_a_structurally_valid_pdf():
    pdf = render_receipt_pdf(_receipt())
    assert pdf.startswith(b"%PDF-1.4")
    assert pdf.rstrip().endswith(b"%%EOF")
    assert _xref_resolves(pdf) >= 5
    assert b"/Type /Page" in pdf and b"/MediaBox" in pdf


def test_every_required_field_appears_in_the_document():
    """The fields a farmer checks and an auditor reconciles."""
    receipt = _receipt()
    pdf = render_receipt_pdf(receipt)
    for expected in (
        receipt["organization_name"],
        receipt["supplier_name"],
        receipt["supplier_code"],
        receipt["receipt_number"],
        receipt["payment_number"],
        receipt["payment_reference"],
        "Njoro Collection Center",
        "STL-9F3D21",
        "412.500 kg",
        "44.7291",  # the RATE keeps four decimals — it is not a total
        "18,130.50",
        "KES",
    ):
        assert expected.encode("latin-1") in pdf, f"{expected!r} is missing from the receipt"


def test_rendering_is_deterministic():
    """No embedded timestamp: the same immutable receipt renders byte-identically,
    which is what lets the artifact be checksummed without being stored."""
    receipt = _receipt()
    assert render_receipt_pdf(receipt) == render_receipt_pdf(receipt)


def test_a_supplier_name_cannot_break_the_content_stream():
    """The injection boundary of the format.

    Parentheses and backslashes delimit PDF literal strings. An unescaped
    supplier name containing one would corrupt the page — and supplier names
    are user input.
    """
    pdf = render_receipt_pdf(_receipt(supplier_name="Jane (Wanjiku) \\ O'Brien"))
    assert b"(Jane \\(Wanjiku\\) \\\\ O'Brien)" in pdf
    _xref_resolves(pdf)


def test_text_outside_the_font_is_substituted_rather_than_corrupting_the_file():
    """A base-14 font has no Devanagari glyph. Substituting is a documented
    limitation; emitting the raw bytes would produce a file that opens and
    shows nonsense."""
    pdf = render_receipt_pdf(_receipt(supplier_name="सुनीता देवी"))
    _xref_resolves(pdf)
    assert b"%PDF" in pdf


@pytest.mark.parametrize(
    "receipt",
    [
        {},  # nothing at all
        {"lines": []},  # a payment with no settlements
        {"net_amount": None, "gross_amount": None},
        {"lines": [{"settlement_number": "STL-1", "amount_paid": None}]},
    ],
)
def test_missing_data_renders_a_valid_document_rather_than_raising(receipt):
    """A receipt generated before PROD-001 has no quantity, rate or center.

    Those rows are absent, not invented — but the document must still open.
    Raising here would make an OLD receipt undownloadable, which is a worse
    outcome than a receipt with fewer columns filled in.
    """
    pdf = render_receipt_pdf(receipt)
    _xref_resolves(pdf)


def test_many_settlements_stay_on_one_page():
    """A supplier paid for a year of periods must not produce a document whose
    content runs off the bottom of the page."""
    lines = [
        {
            "settlement_number": f"STL-{n:06d}",
            "period_from": "2026-01-01",
            "period_to": "2026-01-31",
            "quantity": "100.000",
            "quantity_unit": "kg",
            "average_rate": "44.0000",
            "amount_paid": "4400.00",
        }
        for n in range(60)
    ]
    pdf = render_receipt_pdf(_receipt(lines=lines))
    _xref_resolves(pdf)
    assert b"further settlements omitted" in pdf


def test_an_empty_document_still_builds():
    from platform_core.modules.receipt.pdf import _Text

    _xref_resolves(build_pdf(_Text()))


# --- through the service seam -----------------------------------------------


def test_the_pdf_renderer_is_the_default_and_is_not_a_placeholder():
    from platform_core.modules.receipt.rendering import get_renderer, reset_renderers

    reset_renderers()
    try:
        renderer = get_renderer("pdf")
        assert renderer.name == "builtin-pdf"
        assert renderer.content_type == "application/pdf"
        rendered = renderer.render(_receipt())
        assert rendered.is_binary
        assert rendered.placeholder is False
        assert rendered.filename.endswith(".pdf") and not rendered.filename.endswith(".pdf.txt")
    finally:
        reset_renderers()


async def test_the_render_endpoint_base64_encodes_the_pdf_and_says_so(client):
    """The render view is JSON, so a binary artifact has to be encoded — and
    the client must not have to infer that from the content type."""
    import base64

    from tests.test_receipts import _receipted

    headers, _center, _supplier, _settlement, _payment, receipt = await _receipted(client)
    response = await client.get(f"/v1/receipts/{receipt['id']}/render?format=pdf", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["encoding"] == "base64"
    assert body["content_type"] == "application/pdf"
    assert base64.b64decode(body["body"]).startswith(b"%PDF-1.4")
    assert body["placeholder"] is False


async def test_downloading_a_receipt_serves_real_pdf_bytes(client):
    from tests.test_receipts import _receipted

    headers, _center, _supplier, _settlement, _payment, receipt = await _receipted(client)
    response = await client.get(
        f"/v1/receipts/{receipt['id']}/download?format=pdf", headers=headers
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-1.4")
    _xref_resolves(response.content)


async def test_a_receipt_carries_the_dairy_center_and_quantity(client):
    """PROD-001 enriched `payment.completed.v1` so the receipt can say what the
    money was FOR. Proven end to end rather than by unit-testing the payload."""
    from tests.test_receipts import _receipted

    headers, _center, _supplier, _settlement, _payment, receipt = await _receipted(client)
    detail = (await client.get(f"/v1/receipts/{receipt['id']}", headers=headers)).json()
    rendered = (
        await client.get(f"/v1/receipts/{receipt['id']}/render?format=json", headers=headers)
    ).json()
    import json

    payload = json.loads(rendered["body"])
    assert payload["organization_name"], "the issuing dairy is missing from the receipt"
    assert payload["lines"], "the receipt has no settlement lines"
    line = payload["lines"][0]
    assert line["quantity"] is not None, "quantity did not reach the receipt"
    assert Decimal(line["quantity"]) > 0
    assert line["average_rate"] is not None, "the rate did not reach the receipt"
    assert detail["receipt"]["receipt_number"]
