"""The bill and the statement as documents (WO-83 §2).

Rendered with the receipt's own PDF writer — one page, one font, black on
white, no dependency — and its conventions: the organisation's name, address
and phone at the head, the number and period on the right, the figures the
household checks in the largest type. Deterministic, like the receipt: the
same immutable invoice renders to the same bytes forever.

Nothing is computed here. Every figure comes from `InvoiceDetailView` or
`CustomerStatement`, which the platform already computed and stored; a
document that did its own arithmetic could disagree with the screen.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from platform_core.modules.receipt.pdf import (
    FONT_BOLD,
    FONT_REGULAR,
    MARGIN,
    PAGE_HEIGHT,
    PAGE_WIDTH,
    _money,
    _Text,
    build_pdf,
)

RIGHT = PAGE_WIDTH - MARGIN
#: Below this the page is full; the renderer starts another.
FOOT = MARGIN + 40


class _Document:
    """A multi-page writer over the receipt's single-page primitives."""

    def __init__(self, head: dict[str, Any], title: str, subtitle: str) -> None:
        self._head = head
        self._title = title
        self._subtitle = subtitle
        self.pages: list[_Text] = []
        self.page: _Text = _Text()
        self.y = PAGE_HEIGHT - MARGIN
        self._start()

    def _start(self) -> None:
        self.page = _Text()
        self.pages.append(self.page)
        self.y = PAGE_HEIGHT - MARGIN
        organisation = str(self._head.get("organization_name") or "").strip() or "Lacteva"
        self.page.line(MARGIN, self.y, organisation, font=FONT_BOLD, size=16)
        self.page.right(RIGHT, self.y, self._title, font=FONT_BOLD, size=12)
        self.y -= 14
        for part in _address_lines(self._head):
            self.page.line(MARGIN, self.y, part, size=9)
            self.y -= 11
        self.page.right(RIGHT, self.y + 11, self._subtitle, size=9)
        self.y -= 8
        self.page.rule(MARGIN, self.y, RIGHT)
        self.y -= 18

    def need(self, height: float) -> None:
        if self.y - height < FOOT:
            self.page.line(MARGIN, FOOT - 14, "continued overleaf", size=8)
            self._start()

    def line(self, x: float, text: str, *, font: str = FONT_REGULAR, size: float = 10.0) -> None:
        self.page.line(x, self.y, text, font=font, size=size)

    def right(self, x: float, text: str, *, font: str = FONT_REGULAR, size: float = 10.0) -> None:
        self.page.right(x, self.y, text, font=font, size=size)

    def rule(self) -> None:
        self.page.rule(MARGIN, self.y, RIGHT)

    def down(self, step: float) -> None:
        self.y -= step

    def render(self) -> bytes:
        # Every page is finished with the same primitives the receipt uses;
        # the receipt writer handles ONE page, so a document of several is
        # concatenated by rendering each page through it.
        if len(self.pages) == 1:
            return build_pdf(self.pages[0])
        return _concatenate(self.pages)


def _address_lines(head: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    address = str(head.get("organization_address") or "").strip()
    if address:
        lines.extend(part.strip() for part in address.replace("\r", "").split("\n") if part.strip())
    phone = str(head.get("organization_phone") or "").strip()
    if phone:
        lines.append(f"Phone {phone}")
    return lines


def _concatenate(pages: list[_Text]) -> bytes:
    """Several single pages as one file. The receipt writer's format is PDF
    1.4 with fixed object order; a multi-page file is the same objects with
    one Pages node — built here from the pages' content streams."""
    streams = [page.render() for page in pages]
    objects: list[bytes] = []
    # 1 catalog, 2 pages, 3 font regular, 4 font bold, then (page, stream) pairs.
    n = len(streams)
    kids = " ".join(f"{5 + 2 * i} 0 R" for i in range(n)).encode()
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"<< /Type /Pages /Kids [" + kids + b"] /Count " + str(n).encode() + b" >>")
    objects.append(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    )
    objects.append(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"
    )
    for stream in streams:
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595.28 841.89] "
            b"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents "
            + str(len(objects) + 2).encode()
            + b" 0 R >>"
        )
        objects.append(
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        )
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(out)


# --- the bill ----------------------------------------------------------------------


def render_invoice_pdf(
    detail: dict[str, Any], head: dict[str, Any], customer: dict[str, Any]
) -> bytes:
    """One household's bill. `detail` is `InvoiceDetailView` as a dict,
    `head` the organisation's name/address/phone/pay_to, `customer` its
    name/code/address."""
    invoice = detail["invoice"]
    doc = _Document(
        head,
        "INVOICE",
        f"No. {invoice.get('invoice_number', '')} · {invoice.get('period_from', '')} to "
        f"{invoice.get('period_to', '')}",
    )
    status = str(invoice.get("status", "")).upper()
    doc.line(MARGIN, "Bill to", font=FONT_BOLD, size=9)
    doc.line(MARGIN + 110, str(customer.get("name", "")), size=10)
    doc.right(RIGHT, status, font=FONT_BOLD, size=9)
    doc.down(13)
    doc.line(MARGIN, "Customer code", font=FONT_BOLD, size=9)
    doc.line(MARGIN + 110, str(customer.get("code", "")), size=10)
    doc.down(13)
    address = str(customer.get("address") or "").strip()
    if address:
        doc.line(MARGIN, "Address", font=FONT_BOLD, size=9)
        doc.line(MARGIN + 110, address, size=10)
        doc.down(13)
    doc.down(8)
    doc.rule()
    doc.down(16)

    # --- lines -------------------------------------------------------------
    doc.line(MARGIN, "Date", font=FONT_BOLD, size=8)
    doc.line(MARGIN + 60, "Item", font=FONT_BOLD, size=8)
    doc.right(MARGIN + 300, "Qty", font=FONT_BOLD, size=8)
    doc.right(MARGIN + 380, "Rate", font=FONT_BOLD, size=8)
    doc.right(RIGHT, "Amount", font=FONT_BOLD, size=8)
    doc.down(4)
    doc.rule()
    doc.down(13)
    for line in detail.get("lines", []):
        doc.need(13)
        kind = "item" if line.get("line_kind") == "item" else f"milk · {line.get('slot', '')}"
        name = str(line.get("product_name") or line.get("product", ""))
        doc.line(MARGIN, str(line.get("delivery_date", "")), size=8)
        doc.line(MARGIN + 60, f"{name} ({kind})"[:48], size=8)
        doc.right(
            MARGIN + 300, f"{_qty(line.get('quantity'))} {line.get('quantity_unit', '')}", size=8
        )
        rate = _rate(line.get("unit_price"))
        if line.get("price_source") == "override":
            rate += " *"
        doc.right(MARGIN + 380, rate, size=8)
        doc.right(RIGHT, _money(line.get("amount")), size=8)
        doc.down(12)
    if any(line.get("price_source") == "override" for line in detail.get("lines", [])):
        doc.need(12)
        doc.line(MARGIN, "* a rate agreed for that day, other than the standing order's", size=7)
        doc.down(12)
    doc.down(4)
    doc.rule()
    doc.down(16)

    # --- totals ------------------------------------------------------------
    currency = str(invoice.get("currency", ""))
    for label, value, bold in (
        ("Subtotal", invoice.get("subtotal"), False),
        ("Adjustments", invoice.get("adjustments"), False),
        (
            _carried_label(invoice.get("previous_balance")),
            _carried_value(invoice.get("previous_balance")),
            False,
        ),
        ("Total", invoice.get("total"), False),
        ("Amount due", invoice.get("amount_due"), True),
        ("Paid", detail.get("paid"), False),
        ("Outstanding", detail.get("outstanding"), True),
    ):
        doc.need(14)
        doc.right(
            MARGIN + 380, label, font=FONT_BOLD if bold else FONT_REGULAR, size=10 if bold else 9
        )
        doc.right(
            RIGHT,
            f"{_money(value)} {currency}",
            font=FONT_BOLD if bold else FONT_REGULAR,
            size=11 if bold else 9,
        )
        doc.down(14)
    doc.down(6)
    _pay_to(doc, head)
    return doc.render()


# --- the statement ------------------------------------------------------------------


def render_statement_pdf(
    statement: dict[str, Any], head: dict[str, Any], customer: dict[str, Any]
) -> bytes:
    """A household's ledger for a window: opening, every bill and payment,
    closing — `CustomerStatement` as a dict."""
    doc = _Document(
        head,
        "STATEMENT",
        f"{statement.get('date_from', '')} to {statement.get('date_to', '')}",
    )
    currency = str(statement.get("currency", ""))
    doc.line(MARGIN, "Customer", font=FONT_BOLD, size=9)
    doc.line(MARGIN + 110, f"{customer.get('name', '')} ({statement.get('code', '')})", size=10)
    doc.down(13)
    address = str(customer.get("address") or "").strip()
    if address:
        doc.line(MARGIN, "Address", font=FONT_BOLD, size=9)
        doc.line(MARGIN + 110, address, size=10)
        doc.down(13)
    doc.down(8)
    doc.rule()
    doc.down(16)
    doc.line(MARGIN, "Date", font=FONT_BOLD, size=8)
    doc.line(MARGIN + 60, "Entry", font=FONT_BOLD, size=8)
    doc.right(MARGIN + 300, "Billed", font=FONT_BOLD, size=8)
    doc.right(MARGIN + 380, "Paid", font=FONT_BOLD, size=8)
    doc.right(RIGHT, "Balance", font=FONT_BOLD, size=8)
    doc.down(4)
    doc.rule()
    doc.down(13)
    opening = statement.get("opening_balance")
    doc.line(MARGIN + 60, _carried_label(opening), font=FONT_BOLD, size=8)
    doc.right(RIGHT, _balance(opening), font=FONT_BOLD, size=8)
    doc.down(12)
    for entry in statement.get("entries", []):
        doc.need(13)
        kind = "Payment" if entry.get("kind") == "payment" else "Invoice"
        label = f"{kind} {entry.get('reference', '')}"
        receipt = entry.get("receipt_number")
        if receipt:
            label += f" · receipt {receipt}"
        doc.line(MARGIN, str(entry.get("entry_date", "")), size=8)
        doc.line(MARGIN + 60, label[:48], size=8)
        doc.right(
            MARGIN + 300, _money(entry.get("debit")) if _nonzero(entry.get("debit")) else "", size=8
        )
        doc.right(
            MARGIN + 380,
            _money(entry.get("credit")) if _nonzero(entry.get("credit")) else "",
            size=8,
        )
        doc.right(RIGHT, _balance(entry.get("balance")), size=8)
        doc.down(12)
    doc.down(4)
    doc.rule()
    doc.down(16)
    closing = statement.get("closing_balance")
    for label, value, bold in (
        ("Billed in this period", statement.get("billed"), False),
        ("Paid in this period", statement.get("paid"), False),
        (_carried_label(closing, closing=True), _carried_value(closing), True),
    ):
        doc.need(14)
        doc.right(
            MARGIN + 380, label, font=FONT_BOLD if bold else FONT_REGULAR, size=10 if bold else 9
        )
        doc.right(
            RIGHT,
            f"{_money(value)} {currency}",
            font=FONT_BOLD if bold else FONT_REGULAR,
            size=11 if bold else 9,
        )
        doc.down(14)
    doc.down(6)
    _pay_to(doc, head)
    return doc.render()


# --- helpers -------------------------------------------------------------------------


def _pay_to(doc: _Document, head: dict[str, Any]) -> None:
    pay_to = str(head.get("pay_to") or "").strip()
    if not pay_to:
        return
    doc.need(30)
    doc.rule()
    doc.down(14)
    doc.line(MARGIN, "Pay to", font=FONT_BOLD, size=9)
    doc.line(MARGIN + 110, pay_to[:90], size=10)
    doc.down(12)


def _qty(value: object) -> str:
    try:
        return format(Decimal(str(value)).normalize(), "f")
    except Exception:  # pragma: no cover - defensive
        return str(value or "")


def _rate(value: object) -> str:
    try:
        return format(Decimal(str(value)).quantize(Decimal("0.01")), "f")
    except Exception:  # pragma: no cover - defensive
        return str(value or "")


def _nonzero(value: object) -> bool:
    try:
        return Decimal(str(value)) != 0
    except Exception:  # pragma: no cover - defensive
        return False


def _balance(value: object) -> str:
    """A running balance in credit reads `412.00 CR`, never `-412.00` — the
    way a ledger book writes it (WO-83 §5, presentation only)."""
    try:
        d = Decimal(str(value))
    except Exception:  # pragma: no cover - defensive
        return str(value or "")
    return f"{_money(-d)} CR" if d < 0 else _money(d)


def _carried_label(value: object, *, closing: bool = False) -> str:
    """WO-83 §5: a household in CREDIT reads "Advance", not "Previous
    balance -412". Presentation only; the arithmetic is untouched."""
    try:
        negative = Decimal(str(value)) < 0
    except Exception:  # pragma: no cover - defensive
        negative = False
    if closing:
        return "Advance held" if negative else "Balance due"
    return "Advance" if negative else "Previous balance"


def _carried_value(value: object) -> object:
    try:
        d = Decimal(str(value))
        return -d if d < 0 else d
    except Exception:  # pragma: no cover - defensive
        return value
