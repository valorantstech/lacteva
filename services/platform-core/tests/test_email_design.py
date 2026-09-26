"""Every email wears the brand and is designed (WO-105 · LACTEVA-NOTIFY-003).

The owner, on the first real invitation: "in all emails add lacteva logo and
design it properly, currently mails are so basic." What is pinned here is
the structure every email now has — the logo header, the button, the code
box, the bill's table with its amount due and pay-to block, the footer — and
the PROOF: every email template renders to a committed HTML file and two
committed screenshots, so a reviewer sees the email in the diff, and a change
to the wrapper that was not re-rendered fails here.

Regenerate after a deliberate change:
    .venv/bin/python ../../tools/email-preview/render_previews.py
    node ../../tools/email-preview/screenshot.js
"""

import pathlib
import re
import struct
import uuid

from platform_core.modules.notification import email_design
from platform_core.modules.notification.email_design import (
    LOGO_HEIGHT,
    LOGO_URL,
    LOGO_WIDTH,
    SAMPLE_SENDER,
    TAGLINE,
    Sender,
    email_parts,
    preview_samples,
)
from platform_core.modules.notification.providers import OutboundMessage, email_html
from platform_core.modules.notification.templates import TEMPLATES, render
from tests.test_org_structure import _tenant_admin

REPO = pathlib.Path(__file__).resolve().parents[3]
PREVIEWS = REPO / "services/platform-core/src/platform_core/modules/notification/previews"
EMAIL_TEMPLATES = [t for t in TEMPLATES if t.channel == "email"]


def _rendered(template, sender=SAMPLE_SENDER):
    variables, secrets = preview_samples(template.key)
    known = set(template.variables) | set(template.optional_variables)
    message = render(template, {k: v for k, v in {**variables, **secrets}.items() if k in known})
    outbound = OutboundMessage(
        channel="email",
        recipient="preview@example.invalid",
        title=message.title,
        body=message.body,
        language=template.language,
        template_key=template.key,
        notification_id=uuid.UUID(int=0),
        highlight=next(iter(secrets.values())) if len(secrets) == 1 else None,
        presentation=email_parts(template.key, template.language, variables, secrets, sender),
    )
    return message, email_html(outbound)


def test_there_are_email_templates_to_design():
    assert len(EMAIL_TEMPLATES) >= 15
    assert {t.key for t in EMAIL_TEMPLATES} >= {
        "invitation",
        "password_reset",
        "email_change_confirm",
        "invoice_issued",
        "settlement_finalized",
        "collection_completed",
    }


def test_every_email_wears_the_logo_header_and_the_footer():
    """One image — the logo, by absolute versioned URL with explicit size and
    alt text — on a WHITE header with the green accent rule; the tagline, why
    the reader got it, who to contact and "do not reply" in the footer; 16px
    body text; lang and dir from the language."""
    for template in EMAIL_TEMPLATES:
        _message, html = _rendered(template)
        assert html.count("<img") == 1, template.key
        assert (
            f'<img src="{LOGO_URL}" width="{LOGO_WIDTH}" height="{LOGO_HEIGHT}" alt="Lacteva"'
            in html
        )
        assert "data:image" not in html and "cid:" not in html
        assert "background:#FFFFFF;padding:22px 28px 18px;border-bottom:3px solid #428B19" in html
        assert "font-size:16px;line-height:1.6" in html, "16px body text"
        assert TAGLINE in html
        assert (
            "please do not reply" in html
            or "يرجى عدم الرد" in html
            or "उत्तर न दें" in html
            or "usijibu" in html
        )
        assert SAMPLE_SENDER.name in html and SAMPLE_SENDER.phone in html
        lang = template.language
        assert f'<html lang="{lang}" dir="{"rtl" if lang == "ar" else "ltr"}">' in html
        assert "<script" not in html and "<svg" not in html


def test_the_action_is_a_button_with_the_link_beneath_and_the_code_is_a_box():
    for key, label, page in (
        ("invitation", "Join Patel Dairy Shop and Sweets", "accept-invitation"),
        ("password_reset", "Choose a new password", "reset-password"),
        ("email_change_confirm", "Confirm your new email", "confirm-email"),
    ):
        template = next(t for t in EMAIL_TEMPLATES if t.key == key and t.language == "en")
        message, html = _rendered(template)
        _vars, secrets = preview_samples(key)
        link = next(v for k, v in secrets.items() if k.endswith("_link"))
        code = next(v for k, v in secrets.items() if k.endswith("_token"))
        # The button: a padded anchor with the VML fallback for Outlook, and
        # the raw URL beneath it in small type.
        assert f'<a href="{link}" style="display:inline-block;padding:13px 26px' in html, key
        assert f">{label}</a>" in html, key
        assert "<v:roundrect" in html and "<!--[if mso]>" in html
        assert "If the button does not work, copy this link:" in html
        assert page in link
        # The code box: labelled, monospace, letter-spaced, nothing touching it.
        assert re.search(rf"unicode-bidi:embed;\">\s*{re.escape(code)}</div>", html), key
        assert "letter-spacing:.06em" in html and "monospace" in html
        # The text part still carries the link and the code on their own lines.
        assert re.search(rf"^{re.escape(link)}$", message.body, re.M), key
        assert re.search(rf"^{re.escape(code)}$", message.body, re.M), key
        # No raw URL as a paragraph — the button replaced the sentence: the
        # link appears as the VML href, the anchor's href, and the fallback's
        # href and its visible text. Nowhere else.
        assert html.count(link) == 4, (key, html.count(link))


def test_bills_render_as_a_summary_table_with_the_amount_due_and_the_pay_to_block():
    template = next(t for t in EMAIL_TEMPLATES if t.key == "invoice_issued" and t.language == "en")
    _message, html = _rendered(template)
    for label, value in (
        ("Bill", "INV-2026-0091"),
        ("Period", "2026-09-01 \u2013 2026-09-30"),
        ("Milk delivered", "62.0 L"),
        ("Brought forward", "240.00 INR"),
    ):
        assert re.search(rf">{re.escape(label)}</td>.*?>{re.escape(value)}</td>", html), label
    # The amount due, large, right-aligned, tabular figures.
    assert re.search(r">Amount due</td>.*?font-size:26px.*?>1,860\.00 INR</td>", html, re.S)
    assert "tabular-nums" in html
    # The shop's "Pay to" block (WO-83 §2a).
    assert ">PAY TO<" not in html  # the label is set in CSS caps, not shouted in the source
    assert ">Pay to</div>" in html and SAMPLE_SENDER.pay_to in html
    # The figure lines of the text are the table's rows here, not a paragraph.
    assert "Delivered: 62.0 L" not in html and "Brought forward: 240.00 INR" not in html
    assert "Patel Dairy Shop and Sweets uses Lacteva to send your bills." in html
    # The "View your bill" button appears only when the event carries a link.
    assert "View your bill" not in html


def test_a_bill_with_a_link_gets_the_view_your_bill_button():
    variables, _ = preview_samples("invoice_issued")
    parts = email_parts(
        "invoice_issued",
        "en",
        {**variables, "bill_link": "https://app.lacteva.com/bill/abc"},
        {},
        SAMPLE_SENDER,
    )
    assert parts.action is not None
    assert parts.action.label == "View your bill"
    assert parts.action.url == "https://app.lacteva.com/bill/abc"


def test_settlements_and_collections_render_their_figures_as_a_table():
    settlement = next(
        t for t in EMAIL_TEMPLATES if t.key == "settlement_finalized" and t.language == "en"
    )
    _m, html = _rendered(settlement)
    assert re.search(r">Net payable</td>.*?>17,900\.00 INR</td>", html, re.S)
    assert re.search(r">Collections</td>.*?>29</td>", html, re.S)
    assert "Collections: 29" not in html
    collection = next(
        t for t in EMAIL_TEMPLATES if t.key == "collection_completed" and t.language == "en"
    )
    _m, html = _rendered(collection)
    assert re.search(r">Fat / SNF</td>.*?>4\.1 / 8\.6</td>", html, re.S)
    assert re.search(r">Amount</td>.*?>639\.00 INR</td>", html, re.S)


def test_labels_follow_the_language_and_arabic_is_right_to_left():
    ar = next(t for t in EMAIL_TEMPLATES if t.key == "settlement_finalized" and t.language == "ar")
    _m, html = _rendered(ar)
    assert '<html lang="ar" dir="rtl">' in html
    assert ">صافي المستحق</td>" in html
    # Figures stay LTR inside an RTL page.
    assert 'align="right" dir="ltr"' in html
    hi = next(t for t in EMAIL_TEMPLATES if t.key == "collection_completed" and t.language == "hi")
    _m, html = _rendered(hi)
    assert ">फैट / एसएनएफ</td>" in html
    assert "कृपया उत्तर न दें" in html


def test_a_platform_email_says_lacteva_and_names_no_tenant():
    template = next(t for t in EMAIL_TEMPLATES if t.key == "password_reset" and t.language == "en")
    _m, html = _rendered(template, sender=email_design.PLATFORM_SENDER)
    assert "Questions? Contact" not in html
    assert SAMPLE_SENDER.phone not in html
    assert TAGLINE in html and "please do not reply" in html


def test_a_tenant_name_with_markup_is_text_in_the_footer_and_the_button():
    hostile = Sender(
        name='<script>alert(1)</script> & "Sons"', phone="<b>1</b>", pay_to="<img src=x>"
    )
    template = next(t for t in EMAIL_TEMPLATES if t.key == "invoice_issued" and t.language == "en")
    _m, html = _rendered(template, sender=hostile)
    assert "<script>" not in html and "<img src=x>" not in html and "<b>1</b>" not in html
    assert "&lt;script&gt;" in html and html.count("<img") == 1


def test_every_email_template_has_a_committed_preview_and_two_screenshots():
    """The proof a reviewer SEES: the HTML as it would be sent, photographed
    at 600px and 375px, next to the templates. Regenerate after a deliberate
    change (see the module docstring); a wrapper change without it fails."""
    for template in EMAIL_TEMPLATES:
        stem = f"{template.key}.{template.language}"
        _m, html = _rendered(template)
        committed = PREVIEWS / f"{stem}.html"
        assert committed.exists(), f"missing preview {stem}.html — run render_previews.py"
        assert committed.read_text() == html, f"{stem}.html is stale — run render_previews.py"
        for width in (600, 375):
            shot = PREVIEWS / f"{stem}.{width}.png"
            assert shot.exists(), f"missing screenshot {shot.name} — run screenshot.js"
            data = shot.read_bytes()
            assert data[:8] == b"\x89PNG\r\n\x1a\n"
            w, _h = struct.unpack(">II", data[16:24])
            assert w == width, (shot.name, w)


def test_the_logo_asset_is_committed_at_the_versioned_path_at_2x():
    """The URL the emails carry is served by the marketing site from its
    public folder; the PNG is 2x the display size with a white background
    baked in (dark mode cannot invert what is not transparent)."""
    path = REPO / "apps/marketing-site/public" / LOGO_URL.replace("https://lacteva.com/", "")
    assert path.exists(), path
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    w, h = struct.unpack(">II", data[16:24])
    assert (w, h) == (LOGO_WIDTH * 2, LOGO_HEIGHT * 2), (w, h)
    # Colour type 2 (RGB) or 6 (RGBA); either way the renderer painted white
    # behind the mark — `omitBackground: false` — so no alpha is relied on.
    assert data[25] in (2, 6)


async def test_the_preview_endpoint_returns_the_email_page_for_this_tenant(client):
    """The owner can look at what customers receive without sending one: the
    preview carries the HTML, rendered with THIS organisation's name in the
    footer, and only for the email channel."""
    org, admin = await _tenant_admin(client)
    r = await client.post(
        "/v1/notification-templates/invoice_issued/preview",
        json={
            "channel": "email",
            "language": "en",
            "variables": {"amount": "1,860.00", "currency": "INR"},
        },
        headers=admin,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["html"] and body["html"].startswith("<!doctype html>")
    assert LOGO_URL in body["html"]
    assert org["name"] in body["html"]
    assert "1,860.00 INR" in body["html"]
    r = await client.post(
        "/v1/notification-templates/invoice_issued/preview",
        json={"channel": "sms", "language": "en", "variables": {}},
        headers=admin,
    )
    assert r.status_code == 200 and r.json()["html"] is None
