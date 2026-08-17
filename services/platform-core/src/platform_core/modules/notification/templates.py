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

#: An OPTIONAL segment: `[[Quantity: {quantity} {unit}\n]]` (DEMO-028).
#:
#: The segment is rendered only when every variable inside it is present AND
#: non-empty; otherwise the whole segment disappears, brackets and all.
#:
#: This exists because of a real hazard. `render` treats a missing variable as
#: an ERROR — deliberately, because half a sentence on a farmer's settlement is
#: worse than no message. But a retry re-renders from the payload STORED on the
#: notification row, so adding a required variable to a template retroactively
#: breaks every notification already in the table: production held 17 retryable
#: `invoice_issued` rows whose payloads predate the new fields, and they would
#: have started failing on a template error instead of their real one.
#:
#: An optional segment lets a template gain a line without rewriting history.
#: Old payloads render exactly as they did; new ones carry the extra line. What
#: it does NOT do is weaken the guarantee — a variable outside a segment is
#: still required, and a segment is written so the message reads correctly with
#: it and without it.
_OPTIONAL_PATTERN = re.compile(r"\[\[(.*?)\]\]", re.DOTALL)


class TemplateNotFoundError(Exception):
    """No template for this (key, channel) in any language."""


class TemplateRenderError(Exception):
    """The template needs variables the caller did not supply."""


#: What a template is FOR, in business terms (DEMO-032 §6).
#:
#: One entry per template key, not per channel or language — the purpose of a
#: settlement slip does not change because it went by WhatsApp. Keyed
#: separately from the templates themselves so a new language cannot silently
#: acquire a different purpose.
#:
#: Only journeys the product ACTUALLY has appear here. There is no marketing
#: category, no reminder, no promotion: inventing an entry would be inventing a
#: business behaviour, and the registry is meant to be a true statement of what
#: this platform sends.
PURPOSES: dict[str, str] = {
    "settlement_finalized": "Tells a farmer their settlement is final and what they are owed",
    # DEMO-033: the fixed-parameter WhatsApp variants of the two business
    # journeys. Same purpose, stated per variant because the registry is keyed
    # by template and an operator submitting one for approval needs to read
    # what it is for without cross-referencing.
    "settlement_finalized_base": (
        "Tells a farmer their settlement is final and what they are owed (WhatsApp)"
    ),
    "settlement_finalized_with_quantity": (
        "Tells a farmer their settlement is final, including how much milk it covers (WhatsApp)"
    ),
    "invoice_issued_base": "Tells a customer their bill for a period is ready (WhatsApp)",
    "invoice_issued_with_quantity": (
        "Tells a customer their bill is ready, including how much was delivered (WhatsApp)"
    ),
    "invoice_issued_with_balance": (
        "Tells a customer their bill is ready, including an earlier unpaid balance (WhatsApp)"
    ),
    "invoice_issued_with_quantity_and_balance": (
        "Tells a customer their bill is ready, with quantity delivered and an "
        "earlier unpaid balance (WhatsApp)"
    ),
    "payment_completed": "Tells a farmer a settlement payment has been executed",
    "receipt_available": "Tells a farmer a payment receipt is available",
    "invoice_issued": "Tells a customer their bill for a period is ready",
    "customer_payment_recorded": "Tells a customer a payment against their account was recorded",
    "supplier_registered": "Welcomes a farmer and gives them their supplier code",
    "supplier_archived": "Tells a farmer their supplier account was closed",
    "milk_rejected": "Tells a farmer a collection was rejected, and why",
    "price_unavailable": "Tells an operator no rate could be resolved for a collection",
    "invitation": "Sends a new user their one-time invitation link",
    "invitation_accepted": "Confirms to an administrator that an invitation was accepted",
    "password_reset": "Sends a user a one-time password-reset link",
}

#: Templates that carry a business fact to a farmer or a customer, as opposed
#: to platform messages about accounts and access.
#:
#: The distinction is the one DEMO-025 already drew for tenant channel
#: selection, restated here because it is also the line a regulator draws
#: between "transactional/service" and everything else.
BUSINESS_PURPOSE_KEYS = frozenset(
    {
        "settlement_finalized",
        "settlement_finalized_base",
        "settlement_finalized_with_quantity",
        "invoice_issued_base",
        "invoice_issued_with_quantity",
        "invoice_issued_with_balance",
        "invoice_issued_with_quantity_and_balance",
        "payment_completed",
        "receipt_available",
        "invoice_issued",
        "customer_payment_recorded",
        "milk_rejected",
    }
)


@dataclass(frozen=True)
class Template:
    key: str
    channel: str
    language: str
    title: str
    body: str

    #: DEMO-032. Registry metadata, defaulted so no existing entry changed.
    #:
    #: `version` is the CONTENT version of this template. It is not a schema
    #: version and nothing branches on it: it exists because an approved
    #: WhatsApp template is approved as a specific wording, so changing the
    #: wording means re-approval, and an operator needs to be able to see that
    #: the text moved.
    version: int = 1
    #: Inactive means "still here so old messages can be re-rendered on retry,
    #: but not chosen for anything new". Nothing is inactive today; the field
    #: exists so retiring a wording does not mean deleting one.
    active: bool = True

    @property
    def purpose(self) -> str:
        """What this template is for, in business terms."""
        return PURPOSES.get(self.key, "")

    @property
    def variables(self) -> tuple[str, ...]:
        """The variables a caller MUST supply — optional segments excluded."""
        text = _strip_optional(self.title) + _strip_optional(self.body)
        return tuple(dict.fromkeys(_VARIABLE_PATTERN.findall(text)))

    @property
    def optional_variables(self) -> tuple[str, ...]:
        """Variables that appear only inside optional segments. Supplying one
        adds its line; omitting it removes the line and nothing else."""
        found: list[str] = []
        for text in (self.title, self.body):
            for segment in _OPTIONAL_PATTERN.findall(text):
                found.extend(_VARIABLE_PATTERN.findall(segment))
        required = set(self.variables)
        return tuple(dict.fromkeys(name for name in found if name not in required))


@dataclass(frozen=True)
class RenderedMessage:
    title: str
    body: str
    language: str


def _strip_optional(text: str) -> str:
    """The text with every optional segment removed."""
    return _OPTIONAL_PATTERN.sub("", text)


def _resolve_optional(text: str, values: dict) -> str:
    """Keep each optional segment only if all of its variables have a value."""

    def decide(match: re.Match) -> str:
        segment = match.group(1)
        names = _VARIABLE_PATTERN.findall(segment)
        if any(str(values.get(name, "")).strip() == "" for name in names):
            return ""
        return segment

    return _OPTIONAL_PATTERN.sub(decide, text)


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
        "{line_count} collection(s)[[, {quantity} {quantity_unit}]].",
    ),
    _t(
        "settlement_finalized",
        "sms",
        "sw",
        "Malipo {number} tayari",
        "Habari {name}, malipo {number} ya {period_from} hadi {period_to} yamekamilika. "
        "Jumla {gross_amount} {currency}, malipo halisi {net_amount} {currency}, "
        "mizigo {line_count}[[, {quantity} {quantity_unit}]].",
    ),
    _t(
        "settlement_finalized",
        "sms",
        "hi",
        "भुगतान {number} तैयार",
        "नमस्ते {name}, {period_from} से {period_to} तक का भुगतान {number} अंतिम रूप से तैयार है। "
        "कुल {gross_amount} {currency}, देय राशि {net_amount} {currency}, {line_count} संग्रह"
        "[[, {quantity} {quantity_unit}]]।",
    ),
    _t(
        "settlement_finalized",
        "sms",
        "ar",
        "تسوية {number} جاهزة",
        "مرحبا {name}، التسوية {number} من {period_from} إلى {period_to} مكتملة. "
        "الإجمالي {gross_amount} {currency}، الصافي المستحق {net_amount} {currency}، "
        "{line_count} عملية جمع[[، {quantity} {quantity_unit}]].",
    ),
    _t(
        "settlement_finalized",
        "email",
        "en",
        "Settlement {number} is ready",
        "Hello {name},\n\nSettlement {number} covering {period_from} to {period_to} "
        "has been finalised.\n\n"
        "Collections: {line_count}\n"
        "[[Quantity: {quantity} {quantity_unit}\n]]"
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
        "{amount} {currency}[[ for {quantity} {quantity_unit}]]. "
        "Please pay at your convenience.",
    ),
    _t(
        "invoice_issued",
        "sms",
        "hi",
        "बिल {number} तैयार",
        "नमस्ते {name}, {period_from} से {period_to} तक का आपका बिल {number} "
        "{amount} {currency} है[[ ({quantity} {quantity_unit})]]। कृपया भुगतान करें।",
    ),
    _t(
        "invoice_issued",
        "sms",
        "ar",
        "الفاتورة {number} جاهزة",
        "مرحبا {name}، فاتورتك {number} من {period_from} إلى {period_to} هي "
        "{amount} {currency}[[ ({quantity} {quantity_unit})]]. يرجى السداد.",
    ),
    _t(
        "invoice_issued",
        "sms",
        "sw",
        "Bili {number} tayari",
        "Habari {name}, bili yako {number} ya {period_from} hadi {period_to} ni "
        "{amount} {currency}[[ kwa {quantity} {quantity_unit}]]. Tafadhali lipa.",
    ),
    _t(
        "invoice_issued",
        "email",
        "en",
        "Your bill {number} is ready",
        "Hello {name},\n\nYour bill {number} covering {period_from} to {period_to} "
        "is {amount} {currency}.\n"
        "[[Delivered: {quantity} {quantity_unit}\n]]"
        "[[Brought forward: {previous_balance} {currency}\n]]"
        "\nThis is a summary of an invoice recorded in Lacteva.",
    ),
    # --- DEMO-028: the languages the catalog was missing -------------------
    #
    # A Kenyan dairy that chose WhatsApp for its bills got ENGLISH ones, while
    # the same dairy's SMS bills were in Swahili — the fallback is silent, so
    # nothing said so. Email was English-only for both journeys, which meant a
    # Hindi or Arabic dairy switching channel silently changed language too.
    #
    # A test now asserts that every tenant-SELECTABLE template offers the same
    # languages on every channel it supports, so this gap cannot reopen.
    _t(
        "invoice_issued",
        "email",
        "sw",
        "Bili yako {number} iko tayari",
        "Habari {name},\n\nBili yako {number} ya {period_from} hadi {period_to} "
        "ni {amount} {currency}.\n"
        "[[Imepokelewa: {quantity} {quantity_unit}\n]]"
        "[[Salio la awali: {previous_balance} {currency}\n]]"
        "\nHii ni muhtasari wa bili iliyorekodiwa katika Lacteva.",
    ),
    _t(
        "invoice_issued",
        "email",
        "hi",
        "आपका बिल {number} तैयार है",
        "नमस्ते {name},\n\n{period_from} से {period_to} तक का आपका बिल {number} "
        "{amount} {currency} है।\n"
        "[[वितरित: {quantity} {quantity_unit}\n]]"
        "[[पिछला शेष: {previous_balance} {currency}\n]]"
        "\nयह Lacteva में दर्ज एक बिल का सारांश है।",
    ),
    _t(
        "invoice_issued",
        "email",
        "ar",
        "فاتورتك {number} جاهزة",
        "مرحبا {name}،\n\nفاتورتك {number} من {period_from} إلى {period_to} "
        "هي {amount} {currency}.\n"
        "[[الكمية: {quantity} {quantity_unit}\n]]"
        "[[رصيد سابق: {previous_balance} {currency}\n]]"
        "\nهذا ملخص لفاتورة مسجلة في Lacteva.",
    ),
    _t(
        "settlement_finalized",
        "email",
        "sw",
        "Malipo {number} yako tayari",
        "Habari {name},\n\nMalipo {number} ya {period_from} hadi {period_to} "
        "yamekamilika.\n\n"
        "Mizigo: {line_count}\n"
        "[[Kiasi: {quantity} {quantity_unit}\n]]"
        "Jumla: {gross_amount} {currency}\n"
        "Malipo halisi: {net_amount} {currency}\n\n"
        "Huu ni muhtasari wa malipo yaliyorekodiwa katika Lacteva. Wasiliana "
        "na kituo chako cha ukusanyaji ikiwa kuna tatizo.",
    ),
    _t(
        "settlement_finalized",
        "email",
        "hi",
        "भुगतान {number} तैयार है",
        "नमस्ते {name},\n\n{period_from} से {period_to} तक का भुगतान {number} "
        "अंतिम रूप से तैयार है।\n\n"
        "संग्रह: {line_count}\n"
        "[[मात्रा: {quantity} {quantity_unit}\n]]"
        "कुल: {gross_amount} {currency}\n"
        "देय राशि: {net_amount} {currency}\n\n"
        "यह Lacteva में दर्ज एक भुगतान का सारांश है। कोई गड़बड़ी लगे तो अपने "
        "संग्रह केंद्र से संपर्क करें।",
    ),
    _t(
        "settlement_finalized",
        "email",
        "ar",
        "التسوية {number} جاهزة",
        "مرحبا {name}،\n\nالتسوية {number} من {period_from} إلى {period_to} "
        "مكتملة.\n\n"
        "عمليات الجمع: {line_count}\n"
        "[[الكمية: {quantity} {quantity_unit}\n]]"
        "الإجمالي: {gross_amount} {currency}\n"
        "الصافي المستحق: {net_amount} {currency}\n\n"
        "هذا ملخص لتسوية مسجلة في Lacteva. تواصل مع مركز الجمع إذا كان هناك خطأ.",
    ),
    # --- DEMO-033: fixed-parameter WhatsApp variants -----------------------
    #
    # An approved WhatsApp template has a FIXED parameter count and a fixed
    # order. Lacteva's optional segments do not — DEMO-032 found that this made
    # all 8 business WhatsApp templates unapprovable, and DEMO-028 added those
    # segments for a reason that has not gone away: a retry re-renders from a
    # payload that may predate a field.
    #
    # So the two designs stop sharing a template. SMS and email keep the
    # segments and behave exactly as before; WhatsApp gets one explicit variant
    # per real combination, each with a deterministic parameter list.
    #
    # **The wordings are not new.** Every variant body was generated by taking
    # the existing WhatsApp template and either inlining or removing each
    # optional segment — so the Hindi, Arabic and Swahili text is the text that
    # was already reviewed, not a translation invented here.
    #
    # Six variants, and only six, because two optional GROUPS exist:
    # `{quantity, quantity_unit}` on both journeys and `{previous_balance}` on
    # the invoice. Every one of the six is reachable — a settlement or invoice
    # with mixed units reports no quantity, a bill with nothing carried forward
    # reports no balance, and a notification stored before DEMO-028 has neither
    # when it is retried.
    _t(
        "invoice_issued_base",
        "whatsapp",
        "ar",
        "الفاتورة {number} جاهزة",
        "مرحبا {name}،\n\nفاتورتك *{number}* جاهزة.\n"
        "الفترة: من {period_from} إلى {period_to}\n"
        "المبلغ المستحق: *{amount} {currency}*\n\nشكرا لتعاملكم معنا.",
    ),
    _t(
        "invoice_issued_base",
        "whatsapp",
        "en",
        "Bill {number} ready",
        "Hello {name},\n\nYour bill *{number}* is ready.\n"
        "Period: {period_from} to {period_to}\n"
        "Amount due: *{amount} {currency}*\n\n"
        "Thank you for taking milk from us.",
    ),
    _t(
        "invoice_issued_base",
        "whatsapp",
        "hi",
        "बिल {number} तैयार",
        "नमस्ते {name},\n\nआपका बिल *{number}* तैयार है।\n"
        "अवधि: {period_from} से {period_to}\nदेय राशि: *{amount} {currency}*\n"
        "\nहमसे दूध लेने के लिए धन्यवाद।",
    ),
    _t(
        "invoice_issued_base",
        "whatsapp",
        "sw",
        "Bili {number} tayari",
        "Habari {name},\n\nBili yako *{number}* iko tayari.\n"
        "Kipindi: {period_from} hadi {period_to}\n"
        "Kiasi cha kulipa: *{amount} {currency}*\n\n"
        "Asante kwa kuchukua maziwa kwetu.",
    ),
    _t(
        "invoice_issued_with_balance",
        "whatsapp",
        "ar",
        "الفاتورة {number} جاهزة",
        "مرحبا {name}،\n\nفاتورتك *{number}* جاهزة.\n"
        "الفترة: من {period_from} إلى {period_to}\n"
        "رصيد سابق: {previous_balance} {currency}\n"
        "المبلغ المستحق: *{amount} {currency}*\n\nشكرا لتعاملكم معنا.",
    ),
    _t(
        "invoice_issued_with_balance",
        "whatsapp",
        "en",
        "Bill {number} ready",
        "Hello {name},\n\nYour bill *{number}* is ready.\n"
        "Period: {period_from} to {period_to}\n"
        "Brought forward: {previous_balance} {currency}\n"
        "Amount due: *{amount} {currency}*\n\n"
        "Thank you for taking milk from us.",
    ),
    _t(
        "invoice_issued_with_balance",
        "whatsapp",
        "hi",
        "बिल {number} तैयार",
        "नमस्ते {name},\n\nआपका बिल *{number}* तैयार है।\n"
        "अवधि: {period_from} से {period_to}\n"
        "पिछला शेष: {previous_balance} {currency}\n"
        "देय राशि: *{amount} {currency}*\n\nहमसे दूध लेने के लिए धन्यवाद।",
    ),
    _t(
        "invoice_issued_with_balance",
        "whatsapp",
        "sw",
        "Bili {number} tayari",
        "Habari {name},\n\nBili yako *{number}* iko tayari.\n"
        "Kipindi: {period_from} hadi {period_to}\n"
        "Salio la awali: {previous_balance} {currency}\n"
        "Kiasi cha kulipa: *{amount} {currency}*\n\n"
        "Asante kwa kuchukua maziwa kwetu.",
    ),
    _t(
        "invoice_issued_with_quantity",
        "whatsapp",
        "ar",
        "الفاتورة {number} جاهزة",
        "مرحبا {name}،\n\nفاتورتك *{number}* جاهزة.\n"
        "الفترة: من {period_from} إلى {period_to}\n"
        "الكمية: {quantity} {quantity_unit}\n"
        "المبلغ المستحق: *{amount} {currency}*\n\nشكرا لتعاملكم معنا.",
    ),
    _t(
        "invoice_issued_with_quantity",
        "whatsapp",
        "en",
        "Bill {number} ready",
        "Hello {name},\n\nYour bill *{number}* is ready.\n"
        "Period: {period_from} to {period_to}\n"
        "Delivered: {quantity} {quantity_unit}\n"
        "Amount due: *{amount} {currency}*\n\n"
        "Thank you for taking milk from us.",
    ),
    _t(
        "invoice_issued_with_quantity",
        "whatsapp",
        "hi",
        "बिल {number} तैयार",
        "नमस्ते {name},\n\nआपका बिल *{number}* तैयार है।\n"
        "अवधि: {period_from} से {period_to}\nवितरित: {quantity} {quantity_unit}"
        "\nदेय राशि: *{amount} {currency}*\n\nहमसे दूध लेने के लिए धन्यवाद।",
    ),
    _t(
        "invoice_issued_with_quantity",
        "whatsapp",
        "sw",
        "Bili {number} tayari",
        "Habari {name},\n\nBili yako *{number}* iko tayari.\n"
        "Kipindi: {period_from} hadi {period_to}\n"
        "Imepokelewa: {quantity} {quantity_unit}\n"
        "Kiasi cha kulipa: *{amount} {currency}*\n\n"
        "Asante kwa kuchukua maziwa kwetu.",
    ),
    _t(
        "invoice_issued_with_quantity_and_balance",
        "whatsapp",
        "ar",
        "الفاتورة {number} جاهزة",
        "مرحبا {name}،\n\nفاتورتك *{number}* جاهزة.\n"
        "الفترة: من {period_from} إلى {period_to}\n"
        "الكمية: {quantity} {quantity_unit}\n"
        "رصيد سابق: {previous_balance} {currency}\n"
        "المبلغ المستحق: *{amount} {currency}*\n\nشكرا لتعاملكم معنا.",
    ),
    _t(
        "invoice_issued_with_quantity_and_balance",
        "whatsapp",
        "en",
        "Bill {number} ready",
        "Hello {name},\n\nYour bill *{number}* is ready.\n"
        "Period: {period_from} to {period_to}\n"
        "Delivered: {quantity} {quantity_unit}\n"
        "Brought forward: {previous_balance} {currency}\n"
        "Amount due: *{amount} {currency}*\n\n"
        "Thank you for taking milk from us.",
    ),
    _t(
        "invoice_issued_with_quantity_and_balance",
        "whatsapp",
        "hi",
        "बिल {number} तैयार",
        "नमस्ते {name},\n\nआपका बिल *{number}* तैयार है।\n"
        "अवधि: {period_from} से {period_to}\nवितरित: {quantity} {quantity_unit}"
        "\nपिछला शेष: {previous_balance} {currency}\n"
        "देय राशि: *{amount} {currency}*\n\nहमसे दूध लेने के लिए धन्यवाद।",
    ),
    _t(
        "invoice_issued_with_quantity_and_balance",
        "whatsapp",
        "sw",
        "Bili {number} tayari",
        "Habari {name},\n\nBili yako *{number}* iko tayari.\n"
        "Kipindi: {period_from} hadi {period_to}\n"
        "Imepokelewa: {quantity} {quantity_unit}\n"
        "Salio la awali: {previous_balance} {currency}\n"
        "Kiasi cha kulipa: *{amount} {currency}*\n\n"
        "Asante kwa kuchukua maziwa kwetu.",
    ),
    _t(
        "settlement_finalized_base",
        "whatsapp",
        "ar",
        "تسوية {number} جاهزة",
        "مرحبا {name}،\n\nتسويتك *{number}* مكتملة.\n"
        "الفترة: من {period_from} إلى {period_to}\nعمليات الجمع: {line_count}\n"
        "الإجمالي: {gross_amount} {currency}\n"
        "الصافي المستحق: *{net_amount} {currency}*\n\n"
        "تواصل مع مركز الجمع إذا كان هناك خطأ.",
    ),
    _t(
        "settlement_finalized_base",
        "whatsapp",
        "en",
        "Settlement {number} ready",
        "Hello {name},\n\nYour settlement *{number}* is finalised.\n"
        "Period: {period_from} to {period_to}\nCollections: {line_count}\n"
        "Gross: {gross_amount} {currency}\n"
        "Net payable: *{net_amount} {currency}*\n\n"
        "Contact your collection centre if anything looks wrong.",
    ),
    _t(
        "settlement_finalized_base",
        "whatsapp",
        "hi",
        "भुगतान {number} तैयार",
        "नमस्ते {name},\n\nआपका भुगतान *{number}* अंतिम रूप से तैयार है।\n"
        "अवधि: {period_from} से {period_to}\nसंग्रह: {line_count}\n"
        "कुल: {gross_amount} {currency}\nदेय राशि: *{net_amount} {currency}*\n"
        "\nकोई गड़बड़ी लगे तो अपने संग्रह केंद्र से संपर्क करें।",
    ),
    _t(
        "settlement_finalized_base",
        "whatsapp",
        "sw",
        "Malipo {number} tayari",
        "Habari {name},\n\nMalipo yako *{number}* yamekamilika.\n"
        "Kipindi: {period_from} hadi {period_to}\nMizigo: {line_count}\n"
        "Jumla: {gross_amount} {currency}\n"
        "Malipo halisi: *{net_amount} {currency}*\n\n"
        "Wasiliana na kituo chako cha ukusanyaji ikiwa kuna tatizo.",
    ),
    _t(
        "settlement_finalized_with_quantity",
        "whatsapp",
        "ar",
        "تسوية {number} جاهزة",
        "مرحبا {name}،\n\nتسويتك *{number}* مكتملة.\n"
        "الفترة: من {period_from} إلى {period_to}\nعمليات الجمع: {line_count}\n"
        "الكمية: {quantity} {quantity_unit}\n"
        "الإجمالي: {gross_amount} {currency}\n"
        "الصافي المستحق: *{net_amount} {currency}*\n\n"
        "تواصل مع مركز الجمع إذا كان هناك خطأ.",
    ),
    _t(
        "settlement_finalized_with_quantity",
        "whatsapp",
        "en",
        "Settlement {number} ready",
        "Hello {name},\n\nYour settlement *{number}* is finalised.\n"
        "Period: {period_from} to {period_to}\nCollections: {line_count}\n"
        "Quantity: {quantity} {quantity_unit}\nGross: {gross_amount} {currency}"
        "\nNet payable: *{net_amount} {currency}*\n\n"
        "Contact your collection centre if anything looks wrong.",
    ),
    _t(
        "settlement_finalized_with_quantity",
        "whatsapp",
        "hi",
        "भुगतान {number} तैयार",
        "नमस्ते {name},\n\nआपका भुगतान *{number}* अंतिम रूप से तैयार है।\n"
        "अवधि: {period_from} से {period_to}\nसंग्रह: {line_count}\n"
        "मात्रा: {quantity} {quantity_unit}\nकुल: {gross_amount} {currency}\n"
        "देय राशि: *{net_amount} {currency}*\n\n"
        "कोई गड़बड़ी लगे तो अपने संग्रह केंद्र से संपर्क करें।",
    ),
    _t(
        "settlement_finalized_with_quantity",
        "whatsapp",
        "sw",
        "Malipo {number} tayari",
        "Habari {name},\n\nMalipo yako *{number}* yamekamilika.\n"
        "Kipindi: {period_from} hadi {period_to}\nMizigo: {line_count}\n"
        "Kiasi: {quantity} {quantity_unit}\nJumla: {gross_amount} {currency}\n"
        "Malipo halisi: *{net_amount} {currency}*\n\n"
        "Wasiliana na kituo chako cha ukusanyaji ikiwa kuna tatizo.",
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
    # DEMO-028. `push` is the DEFAULT channel for a bill and is not
    # tenant-selectable, so an Indian or Arabic dairy that configures nothing
    # was getting English pushes while every other channel offered its own
    # language. The default channel is exactly the one that must not be the
    # narrowest.
    _t(
        "invoice_issued",
        "push",
        "hi",
        "आपका बिल तैयार है",
        "{period} का बिल {number} तैयार है। देखने के लिए Lacteva खोलें।",
    ),
    _t(
        "invoice_issued",
        "push",
        "ar",
        "فاتورتك جاهزة",
        "الفاتورة {number} عن {period} جاهزة. افتح Lacteva لعرضها.",
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
    # DEMO-032 §8. An UNKNOWN variable is an error too, and it used to be
    # silently ignored.
    #
    # The failure that hides behind that: a consumer renames `net_amount` to
    # `amount`, the template still has `{net_amount}` — so the render fails
    # loudly, which is fine. But rename it the OTHER way, or add a figure the
    # template does not yet show, and nothing complains: the message goes to a
    # farmer looking complete and missing the number that was added for them.
    #
    # Known means "used by SOME template for this key", not "used by this one".
    #
    # The dispatch mapping is declarative and one builder feeds every channel:
    # `invoice_issued` supplies `period` for the push template and
    # `previous_balance` for the WhatsApp and email ones, and the SMS template
    # uses neither. Requiring each channel's exact set would have made that
    # deliberate superset an error — the first draft of this check did, and
    # three delivery tests said so immediately.
    #
    # What survives is the case §8 is actually about: a variable no template
    # anywhere displays, which is a rename or a typo, and which today reaches a
    # farmer as a message that looks complete and is missing a figure.
    #
    # `name` is exempt: the dispatcher fills it from the recipient directory
    # for templates that want it and passes it to those that do not.
    # Its own variables are always known — a template built outside the
    # registry (a test, a preview) can only be judged against itself.
    known = (
        variables_for(template.key)
        | set(template.variables)
        | set(template.optional_variables)
        | {"name"}
    )
    unknown = sorted(set(values) - known)
    if unknown:
        raise TemplateRenderError(
            f"template {template.key!r} was given variable(s) it does not use: "
            f"{', '.join(unknown)} — a value nobody displays is a value nobody sees"
        )

    def substitute(text: str) -> str:
        # Optional segments are resolved FIRST, so a variable that only ever
        # appears inside a dropped segment is never looked up.
        resolved = _resolve_optional(text, values)
        return _VARIABLE_PATTERN.sub(lambda match: str(values[match.group(1)]), resolved)

    return RenderedMessage(
        title=substitute(template.title),
        body=substitute(template.body),
        language=template.language,
    )


#: Which template key a journey uses on a FIXED-PARAMETER channel (DEMO-033).
#:
#: Keyed by the journey and by which optional GROUPS the data actually
#: supports. The groups are named rather than positional so adding one later is
#: a new entry rather than a re-ordering.
#:
#: This is the whole of §4's "business layer determines the variant": it reads
#: available data and picks a template. It contains no vendor, no provider
#: template id, and no channel-specific transport concern — a different
#: fixed-parameter channel would reuse it unchanged.
VARIANTS: dict[str, dict[frozenset[str], str]] = {
    "settlement_finalized": {
        frozenset(): "settlement_finalized_base",
        frozenset({"quantity"}): "settlement_finalized_with_quantity",
    },
    "invoice_issued": {
        frozenset(): "invoice_issued_base",
        frozenset({"quantity"}): "invoice_issued_with_quantity",
        frozenset({"balance"}): "invoice_issued_with_balance",
        frozenset({"quantity", "balance"}): "invoice_issued_with_quantity_and_balance",
    },
}

#: What each optional group needs in order to be considered present. A group is
#: present only when EVERY variable in it has a non-empty value — half a group
#: is not a group, and rendering half of one is the "half-supplied segment"
#: failure DEMO-028 already refused.
VARIANT_GROUPS: dict[str, tuple[str, ...]] = {
    "quantity": ("quantity", "quantity_unit"),
    "balance": ("previous_balance",),
}

#: Channels whose templates are approved with a fixed parameter list, so a
#: variant must be selected. A property of the CHANNEL, not of a vendor.
FIXED_PARAMETER_CHANNELS = ("whatsapp",)


def present_groups(variables: dict) -> frozenset[str]:
    """Which optional groups the data actually supports."""
    return frozenset(
        name
        for name, members in VARIANT_GROUPS.items()
        if all(str(variables.get(member, "") or "").strip() for member in members)
    )


def select_template_key(key: str, channel: str, variables: dict) -> str:
    """The template key to render, given the data (DEMO-033 §4).

    On a flexible channel this is the key unchanged — SMS and email keep their
    optional segments and behave exactly as they did.

    On a fixed-parameter channel it resolves to the variant whose parameter
    list the data exactly supports. A journey with no variants registered is
    returned unchanged, because most templates have no optional segments and
    need no variant.
    """
    if channel not in FIXED_PARAMETER_CHANNELS:
        return key
    variants = VARIANTS.get(key)
    if not variants:
        return key
    groups = present_groups(variables)
    chosen = variants.get(groups)
    if chosen is None:
        # Every subset a journey can produce must have a variant. Reaching here
        # means the data supports a combination nobody registered — refuse,
        # rather than silently sending a message missing a figure.
        raise TemplateNotFoundError(
            f"no {channel} variant of {key!r} for the available fields "
            f"{sorted(groups) or ['none']} — an approved template cannot vary"
        )
    return chosen


def assert_fixed_parameters(template: Template, variables: dict) -> None:
    """§5. A fixed-parameter template gets EXACTLY its parameters.

    Not a superset and not a subset: an approved template is approved as a
    parameter list, and a vendor rejects a message that does not match it.
    Dispatch legitimately carries a superset — one builder feeds every channel
    of a journey — so this is where the superset is narrowed and checked, and
    where a mismatch becomes an error instead of a silently dropped figure.
    """
    if template.channel not in FIXED_PARAMETER_CHANNELS:
        return
    if template.optional_variables:
        raise TemplateRenderError(
            f"template {template.key!r} is on a fixed-parameter channel and still "
            "has optional segments — an approved template cannot vary"
        )
    required = set(template.variables)
    supplied = {
        name for name, value in variables.items() if str(value or "").strip() or name in required
    }
    missing = sorted(required - supplied)
    if missing:
        raise TemplateRenderError(
            f"template {template.key!r} is missing parameter(s): {', '.join(missing)}"
        )


def fixed_parameters(template: Template, variables: dict) -> tuple[str, ...]:
    """The parameter values, in the template's declared order (DEMO-033).

    Positional and complete — what a `{{1}}, {{2}}` template API is handed.

    It refuses a missing variable itself rather than substituting an empty
    string. Dispatch already calls `assert_fixed_parameters` first, so this is
    defence in depth — but a blank `{{3}}` is a farmer reading a message with a
    hole where a figure belongs, and a safety that depends on the caller
    remembering to call something else is not a safety.
    """
    missing = sorted(name for name in template.variables if name not in variables)
    if missing:
        raise TemplateRenderError(
            f"template {template.key!r} cannot build a fixed parameter list: "
            f"missing {', '.join(missing)}"
        )
    return tuple(str(variables[name]) for name in template.variables)


def journey_family(key: str) -> set[str]:
    """Every template key belonging to the same journey as `key` (DEMO-033).

    A journey key plus its fixed-parameter variants — or, given a variant, the
    journey and its siblings. One dispatch builder feeds the whole family, so
    the family is the unit that decides which variables are legitimate.
    """
    for journey, variants in VARIANTS.items():
        if key == journey or key in variants.values():
            return {journey, *variants.values()}
    return {key}


def variables_for(key: str) -> set[str]:
    """Every variable any template in this journey can display (DEMO-032).

    Required and optional, across every channel, language AND variant. This is
    the set a dispatch builder may legitimately supply, because one builder
    feeds all of a journey's channels — `invoice_issued` supplies `period` for
    push and `previous_balance` for the variant that shows a carried balance,
    and the variant that shows neither is still fed by the same builder.
    """
    family = journey_family(key)
    names: set[str] = set()
    for template in TEMPLATES:
        if template.key in family:
            names.update(template.variables)
            names.update(template.optional_variables)
    return names


def catalog() -> list[Template]:
    """Every registered template, for the ops/template-preview API."""
    return sorted(TEMPLATES, key=lambda t: (t.key, t.channel, t.language))


def languages_for(key: str, channel: str) -> list[str]:
    return sorted(
        template.language
        for template in TEMPLATES
        if template.key == key and template.channel == channel
    )
