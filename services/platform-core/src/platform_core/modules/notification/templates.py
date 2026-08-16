"""Notification template registry and renderer (NOT-001).

Every outbound message is rendered from a template — there are NO hardcoded
messages anywhere in the platform. A template is identified by
(key, channel, language) and declares its title, body, and the variables it
requires. Language resolution falls back to the platform default, so a
market pack can ship one locale at a time without breaking delivery.

Templates are platform data declared in code today; per-tenant overrides are
recorded technical debt (see the NOT-001 report), and the shape here — a
registry keyed by (key, channel, language) — is what an override table would
populate.
"""

import re
from dataclasses import dataclass

DEFAULT_LANGUAGE = "en"
CHANNELS = ("sms", "email")

_VARIABLE_PATTERN = re.compile(r"\{(\w+)\}")


class TemplateNotFoundError(Exception):
    """No template for this (key, channel) in any language."""


class TemplateRenderError(Exception):
    """The template needs variables the caller did not supply."""


@dataclass(frozen=True)
class Template:
    key: str
    channel: str
    language: str
    title: str
    body: str

    @property
    def variables(self) -> tuple[str, ...]:
        found = _VARIABLE_PATTERN.findall(self.title) + _VARIABLE_PATTERN.findall(self.body)
        return tuple(dict.fromkeys(found))  # declared order, de-duplicated


@dataclass(frozen=True)
class RenderedMessage:
    title: str
    body: str
    language: str


def _t(key: str, channel: str, language: str, title: str, body: str) -> Template:
    return Template(key=key, channel=channel, language=language, title=title, body=body)


# The catalog. Keys are stable identifiers referenced by event mappings.
TEMPLATES: tuple[Template, ...] = (
    _t(
        "supplier_registered",
        "sms",
        "en",
        "Welcome to {organization}",
        "Hello {name}, you are registered as supplier {code}. "
        "Bring your card or QR code to the collection center.",
    ),
    _t(
        "supplier_registered",
        "sms",
        "sw",
        "Karibu {organization}",
        "Habari {name}, umesajiliwa kama mzalishaji {code}. "
        "Lete kadi au msimbo wako wa QR kwenye kituo cha ukusanyaji.",
    ),
    _t(
        "supplier_archived",
        "sms",
        "en",
        "Supplier account closed",
        "Hello {name}, your supplier account {code} has been closed. "
        "Contact your collection center if this is unexpected.",
    ),
    # --- Farmer settlement slip (DEMO-025) ---------------------------------
    #
    # The slip is a REPRESENTATION of a settlement that already exists. Every
    # figure below is read from the finalized settlement — nothing here
    # computes money. `{period_from}`/`{period_to}` are BUSINESS dates carried
    # on the event for exactly this reason.
    #
    # `{gross_amount}` and `{net_amount}` are both shown even though they are
    # equal today: the deduction engine is still a placeholder, and a slip
    # that showed only one number would have to change shape the day
    # deductions arrive. Showing both now means the farmer's slip does not
    # change its meaning later.
    _t(
        "settlement_finalized",
        "sms",
        "en",
        "Settlement {number} ready",
        "Hello {name}, settlement {number} for {period_from} to {period_to} is finalised. "
        "Gross {gross_amount} {currency}, net payable {net_amount} {currency}, "
        "{line_count} collection(s).",
    ),
    _t(
        "settlement_finalized",
        "sms",
        "sw",
        "Malipo {number} tayari",
        "Habari {name}, malipo {number} ya {period_from} hadi {period_to} yamekamilika. "
        "Jumla {gross_amount} {currency}, malipo halisi {net_amount} {currency}, "
        "mizigo {line_count}.",
    ),
    _t(
        "settlement_finalized",
        "sms",
        "hi",
        "भुगतान {number} तैयार",
        "नमस्ते {name}, {period_from} से {period_to} तक का भुगतान {number} अंतिम रूप से तैयार है। "
        "कुल {gross_amount} {currency}, देय राशि {net_amount} {currency}, {line_count} संग्रह।",
    ),
    _t(
        "settlement_finalized",
        "sms",
        "ar",
        "تسوية {number} جاهزة",
        "مرحبا {name}، التسوية {number} من {period_from} إلى {period_to} مكتملة. "
        "الإجمالي {gross_amount} {currency}، الصافي المستحق {net_amount} {currency}، "
        "{line_count} عملية جمع.",
    ),
    _t(
        "settlement_finalized",
        "whatsapp",
        "en",
        "Settlement {number} ready",
        "Hello {name},\n\nYour settlement *{number}* is finalised.\n"
        "Period: {period_from} to {period_to}\n"
        "Collections: {line_count}\n"
        "Gross: {gross_amount} {currency}\n"
        "Net payable: *{net_amount} {currency}*\n\n"
        "Contact your collection centre if anything looks wrong.",
    ),
    _t(
        "settlement_finalized",
        "whatsapp",
        "sw",
        "Malipo {number} tayari",
        "Habari {name},\n\nMalipo yako *{number}* yamekamilika.\n"
        "Kipindi: {period_from} hadi {period_to}\n"
        "Mizigo: {line_count}\n"
        "Jumla: {gross_amount} {currency}\n"
        "Malipo halisi: *{net_amount} {currency}*\n\n"
        "Wasiliana na kituo chako cha ukusanyaji ikiwa kuna tatizo.",
    ),
    _t(
        "settlement_finalized",
        "whatsapp",
        "hi",
        "भुगतान {number} तैयार",
        "नमस्ते {name},\n\nआपका भुगतान *{number}* अंतिम रूप से तैयार है।\n"
        "अवधि: {period_from} से {period_to}\n"
        "संग्रह: {line_count}\n"
        "कुल: {gross_amount} {currency}\n"
        "देय राशि: *{net_amount} {currency}*\n\n"
        "कोई गड़बड़ी लगे तो अपने संग्रह केंद्र से संपर्क करें।",
    ),
    _t(
        "settlement_finalized",
        "whatsapp",
        "ar",
        "تسوية {number} جاهزة",
        "مرحبا {name}،\n\nتسويتك *{number}* مكتملة.\n"
        "الفترة: من {period_from} إلى {period_to}\n"
        "عمليات الجمع: {line_count}\n"
        "الإجمالي: {gross_amount} {currency}\n"
        "الصافي المستحق: *{net_amount} {currency}*\n\n"
        "تواصل مع مركز الجمع إذا كان هناك خطأ.",
    ),
    _t(
        "settlement_finalized",
        "email",
        "en",
        "Settlement {number} is ready",
        "Hello {name},\n\nSettlement {number} covering {period_from} to {period_to} "
        "has been finalised.\n\n"
        "Collections: {line_count}\n"
        "Gross amount: {gross_amount} {currency}\n"
        "Net payable: {net_amount} {currency}\n\n"
        "This is a summary of a settlement recorded in Lacteva. Contact your "
        "collection centre if anything looks wrong.",
    ),
    _t(
        "payment_completed",
        "sms",
        "en",
        "Payment sent",
        "Hello {name}, {amount} {currency} has been paid for settlement {number}. "
        "Reference {reference}.",
    ),
    _t(
        "receipt_available",
        "sms",
        "en",
        "Receipt {number}",
        "Hello {name}, receipt {number} for {amount} {currency} is ready. "
        "Keep this reference for your records.",
    ),
    _t(
        "receipt_available",
        "sms",
        "sw",
        "Risiti {number}",
        "Habari {name}, risiti {number} ya {amount} {currency} iko tayari. Hifadhi kumbukumbu hii.",
    ),
    _t(
        "milk_rejected",
        "sms",
        "en",
        "Delivery not accepted",
        "Hello {name}, your delivery on {date} was not accepted. Reason: {reason}. "
        "Please speak to the collection center operator.",
    ),
    _t(
        "price_unavailable",
        "sms",
        "en",
        "Pricing pending",
        "Hello {name}, your delivery on {date} was recorded but pricing is pending. "
        "The amount will follow once rates are published.",
    ),
    _t(
        "password_reset",
        "email",
        "en",
        "Reset your Lacteva password",
        "A password reset was requested for your account. "
        "The link expires in {expires_hours} hours. "
        "If you did not request this, ignore this message.",
    ),
    _t(
        "invitation",
        "email",
        "en",
        "You have been invited to Lacteva",
        "You have been invited to join {organization} as {role}. "
        "Use this code to complete your registration: {invite_token}. "
        "The invitation expires in {expires_days} days. "
        "Do not share this code with anyone, including the person who invited you.",
    ),
    _t(
        "invitation_accepted",
        "email",
        "en",
        "Welcome to Lacteva",
        "Your account is active. You joined {organization} as {role}.",
    ),
    # DEMO-012 §10 — the two things a household wants its phone to tell it.
    #
    # NO AMOUNT in either body, deliberately. A push notification is rendered
    # on a lock screen, which is a public surface: the phone on a table shows
    # what a household owes to whoever walks past. The figure is one tap away
    # in the app, behind the sign-in, where it is also the platform's own
    # figure rather than a copy of it that can go stale between the event and
    # the reading.
    # --- Customer invoice (DEMO-025) ---------------------------------------
    #
    # The push variants below predate this milestone and are kept: a household
    # with the app installed should still get a push. What DEMO-025 adds is
    # the ability to reach a household that has NO app, which is most of them
    # — over SMS, WhatsApp or email.
    #
    # `{period_from}`/`{period_to}` are the invoice's own business dates. The
    # push templates keep `{period}` for compatibility and the consumer now
    # builds it from those dates rather than from a UTC timestamp slice.
    _t(
        "invoice_issued",
        "sms",
        "en",
        "Bill {number} ready",
        "Hello {name}, your bill {number} for {period_from} to {period_to} is "
        "{amount} {currency}. Please pay at your convenience.",
    ),
    _t(
        "invoice_issued",
        "sms",
        "hi",
        "बिल {number} तैयार",
        "नमस्ते {name}, {period_from} से {period_to} तक का आपका बिल {number} "
        "{amount} {currency} है। कृपया भुगतान करें।",
    ),
    _t(
        "invoice_issued",
        "sms",
        "ar",
        "الفاتورة {number} جاهزة",
        "مرحبا {name}، فاتورتك {number} من {period_from} إلى {period_to} هي "
        "{amount} {currency}. يرجى السداد.",
    ),
    _t(
        "invoice_issued",
        "sms",
        "sw",
        "Bili {number} tayari",
        "Habari {name}, bili yako {number} ya {period_from} hadi {period_to} ni "
        "{amount} {currency}. Tafadhali lipa.",
    ),
    _t(
        "invoice_issued",
        "whatsapp",
        "en",
        "Bill {number} ready",
        "Hello {name},\n\nYour bill *{number}* is ready.\n"
        "Period: {period_from} to {period_to}\n"
        "Amount due: *{amount} {currency}*\n\n"
        "Thank you for taking milk from us.",
    ),
    _t(
        "invoice_issued",
        "whatsapp",
        "hi",
        "बिल {number} तैयार",
        "नमस्ते {name},\n\nआपका बिल *{number}* तैयार है।\n"
        "अवधि: {period_from} से {period_to}\n"
        "देय राशि: *{amount} {currency}*\n\n"
        "हमसे दूध लेने के लिए धन्यवाद।",
    ),
    _t(
        "invoice_issued",
        "whatsapp",
        "ar",
        "الفاتورة {number} جاهزة",
        "مرحبا {name}،\n\nفاتورتك *{number}* جاهزة.\n"
        "الفترة: من {period_from} إلى {period_to}\n"
        "المبلغ المستحق: *{amount} {currency}*\n\n"
        "شكرا لتعاملكم معنا.",
    ),
    _t(
        "invoice_issued",
        "email",
        "en",
        "Your bill {number} is ready",
        "Hello {name},\n\nYour bill {number} covering {period_from} to {period_to} "
        "is {amount} {currency}.\n\n"
        "This is a summary of an invoice recorded in Lacteva.",
    ),
    _t(
        "invoice_issued",
        "push",
        "en",
        "Your bill is ready",
        "Bill {number} for {period} is ready. Open Lacteva to see it.",
    ),
    _t(
        "invoice_issued",
        "push",
        "sw",
        "Bili yako iko tayari",
        "Bili {number} ya {period} iko tayari. Fungua Lacteva kuiona.",
    ),
    _t(
        "customer_payment_recorded",
        "push",
        "en",
        "Payment received",
        "We have recorded your payment {number}. Thank you.",
    ),
    _t(
        "customer_payment_recorded",
        "push",
        "sw",
        "Malipo yamepokelewa",
        "Tumepokea malipo yako {number}. Asante.",
    ),
)

_REGISTRY: dict[tuple[str, str, str], Template] = {
    (template.key, template.channel, template.language): template for template in TEMPLATES
}


def get_template(key: str, channel: str, language: str | None = None) -> Template:
    """Resolve (key, channel, language) with fallback to the default language."""
    language = (language or DEFAULT_LANGUAGE).lower()
    template = _REGISTRY.get((key, channel, language))
    if template is None:
        template = _REGISTRY.get((key, channel, DEFAULT_LANGUAGE))
    if template is None:
        raise TemplateNotFoundError(f"no template for {key!r} on channel {channel!r}")
    return template


def render(template: Template, variables: dict) -> RenderedMessage:
    """Substitute `{variable}` placeholders. Missing variables are an error —
    never a half-rendered message delivered to a farmer."""
    values = {key: value for key, value in variables.items() if value is not None}
    missing = [name for name in template.variables if name not in values]
    if missing:
        raise TemplateRenderError(
            f"template {template.key!r} is missing variable(s): {', '.join(sorted(missing))}"
        )

    def substitute(text: str) -> str:
        return _VARIABLE_PATTERN.sub(lambda match: str(values[match.group(1)]), text)

    return RenderedMessage(
        title=substitute(template.title),
        body=substitute(template.body),
        language=template.language,
    )


def catalog() -> list[Template]:
    """Every registered template, for the ops/template-preview API."""
    return sorted(TEMPLATES, key=lambda t: (t.key, t.channel, t.language))


def languages_for(key: str, channel: str) -> list[str]:
    return sorted(
        template.language
        for template in TEMPLATES
        if template.key == key and template.channel == channel
    )
