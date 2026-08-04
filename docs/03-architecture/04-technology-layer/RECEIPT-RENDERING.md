---
id: RECEIPT-RENDERING
title: Receipt Rendering
type: reference
status: Approved
version: "1.0"
owner: Engineering
created: 2026-08-05
last-updated: 2026-08-05
related: [BR-REGISTER, NOTIFICATION-ENGINE, CLAUDE-CONTEXT]
baseline: ARCH-BASELINE-V1
---

# Receipt Rendering

How Lacteva turns an immutable receipt record into an artifact a farmer can hold. Established by RCP-001.

**The guarantee (BR-0020):** a receipt is generated only from a completed payment, and its content never changes. Rendering therefore has an unusual property — it is a **pure function of frozen data**, so the same receipt renders byte-identically forever.

## 1. Why nothing is stored

The obvious design stores a generated PDF and serves the file. That design has three problems this platform cannot accept:

| Problem | Consequence |
| --- | --- |
| The stored file is a second source of truth | It can drift from the record, and then which one is the receipt? |
| Storage becomes a dependency of issuance | An object-store outage would block receipts, and dev-lite would need MinIO |
| A new format means a backfill | Adding HTML later would leave older receipts format-poor |

Because the record is immutable, re-deriving is *free of risk* — the input cannot have changed. So the engine renders on demand and stores no artifact. Adding a format is a registration, not a migration.

## 2. The abstraction

The shape deliberately mirrors the NOT-001 [channel-provider abstraction](NOTIFICATION-ENGINE.md): a Protocol, named adapters, a registry, and configuration-driven selection. Both solve the same problem — the platform owns the *content* and leaves the medium to an adapter.

```
ReceiptService.render(receipt_id, format)
      └─ builds a plain dict from the frozen record   (no ORM leaks out)
             │
             ▼
      get_renderer(format)      registry, falling back to platform defaults
             │
             ▼
      renderer.render(dict) -> RenderedReceipt(format, content_type, filename, body, placeholder)
```

Renderers receive a plain dict, never an ORM object, so they carry no persistence or transport concerns and are trivially testable.

## 3. The shipped renderers

| Format | Renderer | Real? | Notes |
| --- | --- | --- | --- |
| `json` | `JsonReceiptRenderer` | yes | The canonical machine artifact — the receipt as data |
| `html` | `HtmlReceiptRenderer` | yes | Self-contained: no external stylesheet, font, image, or script |
| `pdf` | `PlaceholderPdfRenderer` | **no** | Deterministic stand-in; announces itself as a placeholder |

The HTML renderer's self-containment is a field requirement, not a preference: a village collection center prints without connectivity, so a receipt that fetches anything is a receipt that fails.

**No PDF engine is integrated.** The placeholder emits readable text that names itself as a placeholder, and `RenderedReceipt.placeholder` is `True` so every surface can say so — the portal shows a badge, the mobile app shows a card. A download must never hand someone a file quietly pretending to be a real PDF.

## 4. Swapping in a real engine

A deployment registers its own renderer for the format:

```python
register_renderer(MyPdfRenderer())   # format = "pdf"
```

Nothing else in the platform changes: no service, no route, no schema. The same seam is what tests use to inject recording or failing renderers.

## 5. Serving

| Endpoint | Purpose |
| --- | --- |
| `GET /v1/receipts/{id}/render?format=` | Preview — the artifact as data (body + content type), for portal and mobile |
| `GET /v1/receipts/{id}/download?format=` | The artifact as a file, with `Content-Disposition` |

An unsupported format is a **422** business exception (`receipt_render_format_unsupported`), not a 500 — asking for a format the platform cannot produce is a caller mistake, not a server fault.

Note for clients: the download endpoint is bearer-authenticated, so a plain `<a href>` cannot carry the token. The portal renders through the API client and saves a blob locally; the mobile app copies the artifact and says so.

## 6. Known limits

- **No real PDF.** The one that matters. A print-quality artifact needs an engine (WeasyPrint, wkhtmltopdf, a service) registered as a renderer.
- **No branding or localisation.** Templates are code, English, and carry no tenant logo — the same debt the notification engine records for its message templates.
- **No signature or QR verification.** A receipt cannot yet be validated offline the way a supplier QR identity can.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-05 | Engineering | Established by RCP-001. |
