"""Receipt rendering abstraction (RCP-001).

A renderer turns the frozen receipt record into an artifact a human can read.
The shape deliberately mirrors the NOT-001 channel-provider abstraction — a
Protocol, named adapters, a registry, and configuration-driven selection —
because it solves the same problem: the platform owns the CONTENT and leaves
the delivery medium to an adapter.

The platform ships three renderers:

- ``json``  — the canonical machine artifact; the receipt as data.
- ``html``  — a self-contained printable document, no external assets.
- ``pdf``   — a PLACEHOLDER. It produces a deterministic stand-in document
  and does NOT integrate any PDF engine or external service (RCP-001 scope
  wall). A real implementation is a deployment concern that implements this
  same protocol; no vendor-specific code lives in the platform.

Rendering is a pure function of the receipt record. Nothing is stored: the
record is immutable, so any format can be re-derived at any time and will be
byte-identical. That is why there is no artifact table and no object-storage
dependency here.
"""

from dataclasses import dataclass
from html import escape
from typing import Protocol

import structlog

from platform_core.core.config import get_settings
from platform_core.core.errors import AppError

log = structlog.get_logger("receipt.render")


class RenderFormatError(AppError):
    """No renderer is registered for the requested format (business
    exception: the caller asked for something the platform cannot produce)."""

    status_code = 422
    code = "receipt_render_format_unsupported"


@dataclass(frozen=True)
class RenderedReceipt:
    """A rendered artifact plus what a transport needs to serve it."""

    format: str
    content_type: str
    filename: str
    #: `str` for text formats, `bytes` for binary ones (PROD-001). Starlette's
    #: Response accepts either, so a download needs no special case; the JSON
    #: render endpoint base64-encodes bytes and says so.
    body: str | bytes
    placeholder: bool = False  # True when no real engine produced this

    @property
    def is_binary(self) -> bool:
        return isinstance(self.body, bytes)


class ReceiptRenderer(Protocol):
    name: str
    format: str
    content_type: str

    def render(self, receipt: dict) -> RenderedReceipt:
        """Render the receipt view (a plain dict, so renderers stay free of
        ORM and transport concerns)."""
        ...


def _filename(receipt: dict, extension: str) -> str:
    return f"{receipt.get('receipt_number', 'receipt')}.{extension}"


class JsonReceiptRenderer:
    """The canonical artifact: the receipt exactly as the platform holds it."""

    name = "json"
    format = "json"
    content_type = "application/json"

    def render(self, receipt: dict) -> RenderedReceipt:
        import json

        return RenderedReceipt(
            format=self.format,
            content_type=self.content_type,
            filename=_filename(receipt, "json"),
            body=json.dumps(receipt, indent=2, sort_keys=True, default=str),
        )


class HtmlReceiptRenderer:
    """A self-contained printable receipt.

    No external stylesheet, font, or image: a receipt must render identically
    on a village printer with no connectivity.
    """

    name = "html"
    format = "html"
    content_type = "text/html; charset=utf-8"

    def render(self, receipt: dict) -> RenderedReceipt:
        currency = receipt.get("currency", "")
        rows = "".join(
            "<tr>"
            f"<td>{escape(str(line.get('settlement_number', '')))}</td>"
            f"<td>{escape(str(line.get('period_from') or ''))}"
            f" to {escape(str(line.get('period_to') or ''))}</td>"
            f"<td class='n'>{escape(str(line.get('gross_amount', '')))}</td>"
            f"<td class='n'>{escape(str(line.get('adjustments_amount', '')))}</td>"
            f"<td class='n'>{escape(str(line.get('amount_paid', '')))}</td>"
            "</tr>"
            for line in receipt.get("lines", [])
        )
        reference = receipt.get("payment_reference")
        reference_note = f"· ref {escape(str(reference))}" if reference else ""
        body = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Receipt {escape(str(receipt.get("receipt_number", "")))}</title>
<style>
 body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #111; }}
 h1 {{ font-size: 1.25rem; margin: 0 0 .25rem; }}
 .muted {{ color: #555; font-size: .875rem; }}
 table {{ border-collapse: collapse; width: 100%; margin: 1.25rem 0; }}
 th, td {{ border-bottom: 1px solid #ddd; padding: .5rem; text-align: left; }}
 td.n, th.n {{ text-align: right; }}
 .total {{ font-size: 1.125rem; font-weight: 600; }}
 .status {{ text-transform: uppercase; letter-spacing: .05em; font-size: .75rem; }}
</style></head><body>
<h1>Receipt {escape(str(receipt.get("receipt_number", "")))}</h1>
<p class="muted status">{escape(str(receipt.get("status", "")))}
 · generated {escape(str(receipt.get("generated_at", "")))}</p>
<p>
 <strong>{escape(str(receipt.get("supplier_name", "")))}</strong>
 ({escape(str(receipt.get("supplier_code", "")))})<br>
 Payment {escape(str(receipt.get("payment_number", "")))}
 · {escape(str(receipt.get("payment_method", "")).replace("_", " ").lower())}
 {reference_note}
</p>
<table>
 <thead><tr>
  <th>Settlement</th><th>Period</th>
  <th class="n">Gross</th><th class="n">Adjustments</th><th class="n">Paid</th>
 </tr></thead>
 <tbody>{rows}</tbody>
</table>
<p class="total">Paid: {escape(str(receipt.get("net_amount", "")))} {escape(str(currency))}</p>
<p class="muted">Payment id {escape(str(receipt.get("payment_id", "")))}
 · receipt id {escape(str(receipt.get("id", "")))}</p>
</body></html>"""
        return RenderedReceipt(
            format=self.format,
            content_type=self.content_type,
            filename=_filename(receipt, "html"),
            body=body,
        )


class BuiltinPdfRenderer:
    """A real, printable PDF (PROD-001).

    Replaces the RCP-001 placeholder. No PDF engine, no browser and no new
    dependency: `receipt/pdf.py` writes PDF 1.4 directly, which is a
    proportionate answer for one page of black text on white — see that
    module's header for why each of the alternatives was rejected.

    Output is deterministic (no embedded timestamp), so re-rendering an
    immutable receipt is byte-identical and the artifact can be checksummed
    for an audit without storing it.
    """

    name = "builtin-pdf"
    format = "pdf"
    content_type = "application/pdf"

    def render(self, receipt: dict) -> RenderedReceipt:
        from platform_core.modules.receipt.pdf import render_receipt_pdf

        return RenderedReceipt(
            format=self.format,
            content_type=self.content_type,
            filename=_filename(receipt, "pdf"),
            body=render_receipt_pdf(receipt),
        )


class PlaceholderPdfRenderer:
    """PDF placeholder — NO PDF engine and NO external service (scope wall).

    It emits a readable stand-in that names itself as a placeholder, so a
    portal download never silently hands someone a file pretending to be a
    PDF. Swapping in a real engine means registering another renderer for the
    `pdf` format; nothing else in the platform changes.
    """

    name = "placeholder-pdf"
    format = "pdf"
    content_type = "text/plain; charset=utf-8"

    def render(self, receipt: dict) -> RenderedReceipt:
        lines = receipt.get("lines", [])
        detail = "\n".join(
            f"  {line.get('settlement_number', ''):<14}"
            f"{line.get('amount_paid', ''):>14} {receipt.get('currency', '')}"
            for line in lines
        )
        body = (
            "LACTEVA RECEIPT — PDF PLACEHOLDER\n"
            "(no PDF engine is integrated; this is a stand-in artifact)\n\n"
            f"Receipt      {receipt.get('receipt_number', '')}\n"
            f"Status       {receipt.get('status', '')}\n"
            f"Supplier     {receipt.get('supplier_name', '')} "
            f"({receipt.get('supplier_code', '')})\n"
            f"Payment      {receipt.get('payment_number', '')} "
            f"({receipt.get('payment_method', '')})\n"
            f"Reference    {receipt.get('payment_reference') or '-'}\n"
            f"Generated    {receipt.get('generated_at', '')}\n\n"
            f"Settlements ({len(lines)}):\n{detail}\n\n"
            f"PAID         {receipt.get('net_amount', '')} {receipt.get('currency', '')}\n"
        )
        log.debug("receipt_pdf_placeholder", receipt=receipt.get("receipt_number"))
        return RenderedReceipt(
            format=self.format,
            content_type=self.content_type,
            filename=_filename(receipt, "pdf.txt"),
            body=body,
            placeholder=True,
        )


_RENDERERS: dict[str, ReceiptRenderer] = {}


def register_renderer(renderer: ReceiptRenderer) -> None:
    """Install a renderer for its format (deployment wiring; tests use it to
    inject recording or failing renderers)."""
    _RENDERERS[renderer.format] = renderer


def reset_renderers() -> None:
    _RENDERERS.clear()


def _defaults() -> dict[str, ReceiptRenderer]:
    settings = get_settings()
    pdf: ReceiptRenderer = (
        PlaceholderPdfRenderer()
        if settings.receipt_pdf_renderer == "placeholder"
        else BuiltinPdfRenderer()
    )
    return {"json": JsonReceiptRenderer(), "html": HtmlReceiptRenderer(), "pdf": pdf}


def get_renderer(fmt: str) -> ReceiptRenderer:
    fmt = (fmt or "json").lower()
    if fmt not in _RENDERERS:
        default = _defaults().get(fmt)
        if default is None:
            raise RenderFormatError(f"no renderer for format {fmt!r}")
        _RENDERERS[fmt] = default
    return _RENDERERS[fmt]


def available_formats() -> list[str]:
    return sorted({*_RENDERERS, *_defaults()})
