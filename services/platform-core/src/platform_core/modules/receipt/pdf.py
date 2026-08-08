"""A real, dependency-free PDF writer for receipts (PROD-001).

RCP-001 shipped a placeholder that emitted a text file named `.pdf.txt` and
flagged itself `placeholder=True`. That was the right call at the time — the
scope wall forbade a PDF engine — but it means a dairy cannot hand a farmer
proof of payment, which is most of what a receipt is for.

**Why write the PDF rather than take a library.**

The obvious options were ReportLab (a large dependency for one page of text),
WeasyPrint (pulls Cairo/Pango system libraries) and a headless browser (a
browser, in the payment path, on a single-host village deployment). The work
order asks for no browser dependency without a compelling reason, and none of
these is compelling for what a receipt actually is: one page, one font, black
text on white, no images.

PDF 1.4 with the standard Type 1 fonts is a genuinely simple container format
— a header, a handful of objects, a cross-reference table and a trailer. The
whole writer is below and adds nothing to the dependency tree, which matters
for a platform that ships to places where `apt install` is a site visit.

**Determinism.** No creation timestamp is embedded and object order is fixed,
so rendering the same immutable receipt twice produces byte-identical output.
That is what lets RCP-001's "nothing is stored, any format is re-derivable"
rule stay true, and it makes the artifact checksummable for an audit.

**Encoding.** The standard fonts are single-byte (WinAnsi). Text outside that
range — a Devanagari supplier name, say — cannot be drawn with a base-14 font
and is transliterated to `?` rather than producing a corrupt file. That is a
real limitation, recorded in the divergence register: a market needing
non-Latin receipts needs an embedded TrueType font, which is a bigger change
than this one.
"""

from __future__ import annotations

from decimal import Decimal

#: Points. A4 — the format of every dairy office this platform targets.
PAGE_WIDTH = 595.28
PAGE_HEIGHT = 841.89
MARGIN = 56.0

# The base-14 fonts every conforming reader has built in, so nothing is
# embedded and the file stays a few kilobytes.
FONT_REGULAR = "Helvetica"
FONT_BOLD = "Helvetica-Bold"


def _escape(text: str) -> str:
    """Escape a PDF literal string.

    Backslash and both parentheses are structural inside `( ... )`, so an
    unescaped supplier name containing a bracket would corrupt the page
    stream. This is the injection boundary of the format.
    """
    out = []
    for char in text:
        if char in ("\\", "(", ")"):
            out.append("\\" + char)
        elif " " <= char <= "~":
            out.append(char)
        elif char in ("\n", "\r", "\t"):
            out.append(" ")
        else:
            # Outside WinAnsi's printable ASCII range there is no glyph in a
            # base-14 font. Substituting is honest; emitting the raw byte
            # would produce a file that opens and shows nonsense.
            out.append("?")
    return "".join(out)


class _Text:
    """Accumulates a page's content stream in drawing order."""

    def __init__(self) -> None:
        self._ops: list[str] = []

    def line(self, x: float, y: float, text: str, *, font: str = FONT_REGULAR, size: float = 10.0):
        self._ops.append(
            f"BT /{'F2' if font == FONT_BOLD else 'F1'} {size:.2f} Tf "
            f"1 0 0 1 {x:.2f} {y:.2f} Tm ({_escape(text)}) Tj ET"
        )
        return self

    def right(self, x: float, y: float, text: str, *, font: str = FONT_REGULAR, size: float = 10.0):
        """Right-align at x. Money in a column that does not line up is the
        difference between a receipt and a printout."""
        return self.line(x - _width(text, size), y, text, font=font, size=size)

    def rule(self, x0: float, y: float, x1: float, *, width: float = 0.6, grey: float = 0.75):
        self._ops.append(f"{grey:.2f} G {width:.2f} w {x0:.2f} {y:.2f} m {x1:.2f} {y:.2f} l S 0 G")
        return self

    def render(self) -> bytes:
        return "\n".join(self._ops).encode("latin-1", "replace")


#: Helvetica advance widths (1/1000 em) for printable ASCII, so right-aligned
#: columns are actually aligned. Approximate for the few glyphs a receipt never
#: uses; exact for digits, letters and punctuation, which are all it does use.
_WIDTHS = {
    **{chr(c): 556 for c in range(32, 127)},
    **{d: 556 for d in "0123456789"},
    " ": 278, "!": 278, '"': 355, "#": 556, "$": 556, "%": 889, "&": 667,
    "'": 191, "(": 333, ")": 333, "*": 389, "+": 584, ",": 278, "-": 333,
    ".": 278, "/": 278, ":": 278, ";": 278, "<": 584, "=": 584, ">": 584,
    "?": 556, "@": 1015, "[": 278, "\\": 278, "]": 278, "^": 469, "_": 556,
    "`": 333, "{": 334, "|": 260, "}": 334, "~": 584,
    "A": 667, "B": 667, "C": 722, "D": 722, "E": 667, "F": 611, "G": 778,
    "H": 722, "I": 278, "J": 500, "K": 667, "L": 556, "M": 833, "N": 722,
    "O": 778, "P": 667, "Q": 778, "R": 722, "S": 667, "T": 611, "U": 722,
    "V": 667, "W": 944, "X": 667, "Y": 667, "Z": 611,
    "a": 556, "b": 556, "c": 500, "d": 556, "e": 556, "f": 278, "g": 556,
    "h": 556, "i": 222, "j": 222, "k": 500, "l": 222, "m": 833, "n": 556,
    "o": 556, "p": 556, "q": 556, "r": 333, "s": 500, "t": 278, "u": 556,
    "v": 500, "w": 722, "x": 500, "y": 500, "z": 500,
}  # fmt: skip


def _width(text: str, size: float) -> float:
    return sum(_WIDTHS.get(c, 556) for c in text) * size / 1000.0


def _font_object(base_font: str) -> bytes:
    return (
        f"<< /Type /Font /Subtype /Type1 /BaseFont /{base_font} /Encoding /WinAnsiEncoding >>"
    ).encode("latin-1")


def build_pdf(content: _Text) -> bytes:
    """Assemble a one-page PDF 1.4 document.

    Five objects: catalog, page tree, page, content stream, and the two font
    dictionaries. The cross-reference table records each object's byte offset,
    which is why the body is built first and measured as it is written.
    """
    stream = content.render()
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH:.2f} {PAGE_HEIGHT:.2f}] "
            f"/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> /Contents 4 0 R >>"
        ).encode("latin-1"),
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        _font_object(FONT_REGULAR),
        _font_object(FONT_BOLD),
    ]

    out = bytearray(b"%PDF-1.4\n")
    # A binary comment marks the file as non-text for tools that sniff it.
    out += b"%\xe2\xe3\xcf\xd3\n"
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"

    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n"
    ).encode()
    return bytes(out)


def _rate(value: object) -> str:
    """A unit price keeps four decimals — it is a rate, not a total, and
    rounding it to cents hides the difference between 44.7291 and 44.7350."""
    if value in (None, ""):
        return "-"
    try:
        return f"{Decimal(str(value)):,.4f}"
    except (ArithmeticError, ValueError):  # pragma: no cover - defensive
        return str(value)


def _money(value: object) -> str:
    if value in (None, ""):
        return "-"
    try:
        return f"{Decimal(str(value)):,.2f}"
    except (ArithmeticError, ValueError):  # pragma: no cover - defensive
        return str(value)


def render_receipt_pdf(receipt: dict) -> bytes:
    """One printable page for one receipt.

    Laid out for the thing it is: a farmer checking that the amount matches
    what they were told, and an auditor matching a receipt number to a payment.
    Those two readings get the largest type on the page.
    """
    page = _Text()
    right_edge = PAGE_WIDTH - MARGIN
    y = PAGE_HEIGHT - MARGIN

    lines = receipt.get("lines", [])
    organization = str(receipt.get("organization_name") or "").strip()
    page.line(MARGIN, y, organization or "Lacteva", font=FONT_BOLD, size=16)
    page.right(right_edge, y, "PAYMENT RECEIPT", font=FONT_BOLD, size=12)
    y -= 16
    # The center is a per-line fact. Naming it in the header is only honest
    # when every settlement on the receipt came from the same one; otherwise
    # the column carries it and the header says nothing.
    centers = {str(line.get("center_name") or "").strip() for line in lines}
    centers.discard("")
    if len(centers) == 1:
        page.line(MARGIN, y, next(iter(centers)), size=9)
    elif len(centers) > 1:
        page.line(MARGIN, y, f"{len(centers)} collection centers", size=9)
    page.right(right_edge, y, f"No. {receipt.get('receipt_number', '')}", font=FONT_BOLD, size=10)
    y -= 12
    status = str(receipt.get("status", "")).upper()
    page.right(right_edge, y, f"{status} on {receipt.get('generated_at', '')}", size=8)

    y -= 18
    page.rule(MARGIN, y, right_edge)
    y -= 22

    # --- who and what -------------------------------------------------------
    page.line(MARGIN, y, "Supplier", font=FONT_BOLD, size=9)
    page.line(MARGIN + 130, y, str(receipt.get("supplier_name", "")), size=10)
    y -= 14
    page.line(MARGIN, y, "Supplier code", font=FONT_BOLD, size=9)
    page.line(MARGIN + 130, y, str(receipt.get("supplier_code", "")), size=10)
    y -= 14
    page.line(MARGIN, y, "Payment", font=FONT_BOLD, size=9)
    method = str(receipt.get("payment_method", "")).replace("_", " ").title()
    page.line(MARGIN + 130, y, f"{receipt.get('payment_number', '')} ({method})", size=10)
    y -= 14
    reference = receipt.get("payment_reference")
    if reference:
        page.line(MARGIN, y, "Reference", font=FONT_BOLD, size=9)
        page.line(MARGIN + 130, y, str(reference), size=10)
        y -= 14
    if receipt.get("payment_date"):
        page.line(MARGIN, y, "Paid on", font=FONT_BOLD, size=9)
        page.line(MARGIN + 130, y, str(receipt.get("payment_date")), size=10)
        y -= 14

    y -= 10
    currency = str(receipt.get("currency", ""))

    # --- settlement lines ---------------------------------------------------
    col_period = MARGIN + 150
    col_qty = MARGIN + 300
    col_rate = MARGIN + 380
    page.line(MARGIN, y, "Settlement", font=FONT_BOLD, size=9)
    page.line(col_period, y, "Period", font=FONT_BOLD, size=9)
    page.right(col_qty, y, "Quantity", font=FONT_BOLD, size=9)
    page.right(col_rate, y, "Avg rate", font=FONT_BOLD, size=9)
    page.right(right_edge, y, f"Paid ({currency})", font=FONT_BOLD, size=9)
    y -= 6
    page.rule(MARGIN, y, right_edge, width=0.4)
    y -= 14

    for line in lines:
        page.line(MARGIN, y, str(line.get("settlement_number", "")), size=9)
        period = f"{line.get('period_from') or ''} - {line.get('period_to') or ''}"
        page.line(col_period, y, period, size=8)
        if len(centers) > 1 and line.get("center_name"):
            page.line(MARGIN + 6, y - 9, str(line["center_name"]), size=7)
        quantity = line.get("quantity")
        page.right(
            col_qty,
            y,
            f"{quantity} {line.get('quantity_unit') or ''}".strip() if quantity else "-",
            size=9,
        )
        page.right(
            col_rate,
            y,
            _rate(line.get("average_rate")),
            size=9,
        )
        page.right(right_edge, y, _money(line.get("amount_paid")), size=9)
        y -= 13
        if y < MARGIN + 120:  # one page: the rest is summarised by the total
            page.line(MARGIN, y, "… further settlements omitted; see the JSON artifact", size=8)
            y -= 13
            break

    y -= 4
    page.rule(MARGIN, y, right_edge, width=0.4)
    y -= 18

    # --- money --------------------------------------------------------------
    for label, value in (
        ("Gross", receipt.get("gross_amount")),
        ("Adjustments", receipt.get("adjustments_amount")),
    ):
        page.right(col_rate, y, label, size=9)
        page.right(right_edge, y, _money(value), size=9)
        y -= 14

    page.rule(col_rate - 40, y + 4, right_edge, width=0.8, grey=0.2)
    y -= 14
    page.right(col_rate, y, "PAID", font=FONT_BOLD, size=13)
    page.right(
        right_edge, y, f"{_money(receipt.get('net_amount'))} {currency}", font=FONT_BOLD, size=13
    )

    # --- audit footer -------------------------------------------------------
    footer = MARGIN + 34
    page.rule(MARGIN, footer + 26, right_edge, width=0.4)
    page.line(MARGIN, footer + 12, f"Receipt id {receipt.get('id', '')}", size=7)
    page.line(MARGIN, footer, f"Payment id {receipt.get('payment_id', '')}", size=7)
    page.right(
        right_edge,
        footer,
        "Computer-generated; valid without signature.",
        size=7,
    )
    return build_pdf(page)
