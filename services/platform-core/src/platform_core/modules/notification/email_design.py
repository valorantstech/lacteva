"""What an email LOOKS like, decided from what it means (WO-105 · LACTEVA-NOTIFY-003).

The owner, on receiving the first real invitation: "in all emails add lacteva
logo and design it properly, currently mails are so basic."

The templates stay the single source of the WORDS — plain text, four
languages, what SMS and WhatsApp send. This module gives each email a little
STRUCTURE the HTML wrapper in `providers._html_document` renders: which
variable is the action (a button, with the raw link beneath as the
fallback), which is the code (a labelled box), which figures make a bill's
summary table and its amount due, who the email is from (the tenant, with
its phone, address and pay-to line), and why the reader received it. Nothing
here is markup, and nothing here is a second copy of a sentence a translator
wrote.

`preview_samples()` is the one set of sample values the committed previews,
their screenshots and the snapshot tests all render from.
"""

from __future__ import annotations

# ruff: noqa: E501
# (the label catalog is prose in four languages; wrapping it helps nobody)
from dataclasses import dataclass, field

#: The logo, as an email can carry it: a PNG at 2x with an opaque white
#: background, served by the marketing site at a VERSIONED path — a new
#: version is a new filename, never an overwrite, because mail clients and
#: Gmail's image proxy cache aggressively. Rendered by
#: tools/email-preview/render_logo.js from the brand's own lockup.
LOGO_URL = "https://lacteva.com/email/lacteva-logo-v1@2x.png"
LOGO_WIDTH = 180
LOGO_HEIGHT = 44
TAGLINE = "Smart Dairy. Stronger Tomorrow."

#: Brand colours from the design system's tokens (tools/brand/mark.json), not
#: new ones. The header is WHITE: the logo's navy wordmark is designed for a
#: light ground and vanished on the old green band, so the green moved to the
#: accent rule, the button and the footer.
DAIRY = "#1B5E20"
RULE_GREEN = "#428B19"
MILK = "#FDFBF4"
INK = "#1A1C19"
MUTED = "#5B6159"
RULE = "#DCE5DA"
NAVY = "#022551"


@dataclass(frozen=True)
class Sender:
    """Who the email is from, as the reader should understand it."""

    name: str
    phone: str | None = None
    address: str | None = None
    pay_to: str | None = None
    is_platform: bool = False

    @property
    def contact_line(self) -> str:
        parts = [self.name, *(p for p in (self.phone, self.address) if p)]
        return " · ".join(parts)


PLATFORM_SENDER = Sender(name="Lacteva", is_platform=True)

#: The one-time values that travel as `secret_variables` — the code, and the
#: link that carries it. Named here so a preview knows which placeholders to
#: treat as the action and the code.
EMAIL_SECRET_VARIABLES = frozenset(
    {"invite_link", "invite_token", "reset_link", "reset_token", "change_link", "change_token"}
)


@dataclass(frozen=True)
class EmailAction:
    label: str
    url: str


@dataclass(frozen=True)
class EmailParts:
    sender: Sender
    #: Why this person received the email — the footer's second line.
    why: str
    action: EmailAction | None = None
    code_label: str | None = None
    code: str | None = None
    #: A bill's or settlement's figures, label → value, in reading order.
    summary: tuple[tuple[str, str], ...] = ()
    #: The one figure that matters most, set large: ("Amount due", "1,240.00 INR").
    amount: tuple[str, str] | None = None
    #: The shop's "Pay to" line (WO-83 §2a), for bills only.
    pay_to: str | None = None
    #: The template this was built for — the wrapper keys nothing on it, but
    #: a preview file is named by it.
    template_key: str = ""
    labels: dict[str, str] = field(default_factory=dict)


# --- the words the wrapper adds (labels, not sentences) --------------------

_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "join": "Join {organization}",
        "choose_password": "Choose a new password",
        "confirm_email": "Confirm your new email",
        "view_bill": "View your bill",
        "your_code": "Your code",
        "invitation_code": "Invitation code",
        "reset_code": "Password reset code",
        "change_code": "Email change code",
        "fallback": "If the button does not work, copy this link:",
        "bill": "Bill",
        "settlement": "Settlement",
        "slip": "Slip",
        "period": "Period",
        "date": "Date",
        "milk_delivered": "Milk delivered",
        "quantity": "Quantity",
        "collections": "Collections",
        "brought_forward": "Brought forward",
        "gross": "Gross amount",
        "fat_snf": "Fat / SNF",
        "rate": "Rate",
        "amount_due": "Amount due",
        "net_payable": "Net payable",
        "amount": "Amount",
        "pay_to": "Pay to",
        "why_invitation": "You received this email because you were invited to join {organization} on Lacteva.",
        "why_reset": "You received this email because a password reset was requested for your account in {organization}.",
        "why_change": "You received this email because somebody asked to make this address the login for an account in {organization}.",
        "why_notice": "You received this email because a change to your login was requested in {organization}.",
        "why_accepted": "You received this email because your account in {organization} was activated.",
        "why_bill": "{organization} uses Lacteva to send your bills.",
        "why_settlement": "{organization} uses Lacteva to record and pay for the milk you deliver.",
        "why_collection": "{organization} uses Lacteva to record the milk you deliver.",
        "why_default": "You received this email from {organization} through Lacteva.",
        "automated": "This is an automated message — please do not reply.",
        "questions": "Questions? Contact {contact}.",
    },
    "hi": {
        "join": "{organization} से जुड़ें",
        "choose_password": "नया पासवर्ड चुनें",
        "confirm_email": "अपना नया ईमेल पुष्टि करें",
        "view_bill": "अपना बिल देखें",
        "your_code": "आपका कोड",
        "invitation_code": "आमंत्रण कोड",
        "reset_code": "पासवर्ड रीसेट कोड",
        "change_code": "ईमेल परिवर्तन कोड",
        "fallback": "यदि बटन काम न करे, तो यह लिंक कॉपी करें:",
        "bill": "बिल",
        "settlement": "निपटान",
        "slip": "पर्ची",
        "period": "अवधि",
        "date": "तारीख",
        "milk_delivered": "दिया गया दूध",
        "quantity": "मात्रा",
        "collections": "संग्रह",
        "brought_forward": "पिछला बकाया",
        "gross": "कुल राशि",
        "fat_snf": "फैट / एसएनएफ",
        "rate": "दर",
        "amount_due": "देय राशि",
        "net_payable": "शुद्ध देय",
        "amount": "राशि",
        "pay_to": "भुगतान करें",
        "why_invitation": "आपको यह ईमेल इसलिए मिला क्योंकि आपको Lacteva पर {organization} से जुड़ने के लिए आमंत्रित किया गया।",
        "why_reset": "आपको यह ईमेल इसलिए मिला क्योंकि {organization} में आपके खाते के लिए पासवर्ड रीसेट का अनुरोध किया गया।",
        "why_change": "आपको यह ईमेल इसलिए मिला क्योंकि किसी ने {organization} के एक खाते का लॉगिन इस पते पर बदलने को कहा।",
        "why_notice": "आपको यह ईमेल इसलिए मिला क्योंकि {organization} में आपके लॉगिन में बदलाव का अनुरोध किया गया।",
        "why_accepted": "आपको यह ईमेल इसलिए मिला क्योंकि {organization} में आपका खाता सक्रिय हुआ।",
        "why_bill": "{organization} आपके बिल भेजने के लिए Lacteva का उपयोग करता है।",
        "why_settlement": "{organization} आपके दूध का हिसाब और भुगतान Lacteva से करता है।",
        "why_collection": "{organization} आपके दिए गए दूध का रिकॉर्ड Lacteva में रखता है।",
        "why_default": "यह ईमेल आपको {organization} से Lacteva के माध्यम से मिला।",
        "automated": "यह एक स्वचालित संदेश है — कृपया उत्तर न दें।",
        "questions": "प्रश्न? {contact} से संपर्क करें।",
    },
    "sw": {
        "join": "Jiunge na {organization}",
        "choose_password": "Chagua nenosiri jipya",
        "confirm_email": "Thibitisha barua pepe yako mpya",
        "view_bill": "Tazama bili yako",
        "your_code": "Msimbo wako",
        "invitation_code": "Msimbo wa mwaliko",
        "reset_code": "Msimbo wa kuweka upya nenosiri",
        "change_code": "Msimbo wa kubadili barua pepe",
        "fallback": "Kama kitufe hakifanyi kazi, nakili kiungo hiki:",
        "bill": "Bili",
        "settlement": "Malipo",
        "slip": "Stakabadhi",
        "period": "Kipindi",
        "date": "Tarehe",
        "milk_delivered": "Maziwa yaliyowasilishwa",
        "quantity": "Kiasi",
        "collections": "Makusanyo",
        "brought_forward": "Salio la awali",
        "gross": "Jumla kuu",
        "fat_snf": "Mafuta / SNF",
        "rate": "Kiwango",
        "amount_due": "Kiasi kinachodaiwa",
        "net_payable": "Kinacholipwa",
        "amount": "Kiasi",
        "pay_to": "Lipa kwa",
        "why_invitation": "Umepokea barua pepe hii kwa sababu ulialikwa kujiunga na {organization} kwenye Lacteva.",
        "why_reset": "Umepokea barua pepe hii kwa sababu kuweka upya nenosiri kuliombwa kwa akaunti yako katika {organization}.",
        "why_change": "Umepokea barua pepe hii kwa sababu mtu aliomba anwani hii iwe ya kuingia kwa akaunti katika {organization}.",
        "why_notice": "Umepokea barua pepe hii kwa sababu mabadiliko ya kuingia kwako yaliombwa katika {organization}.",
        "why_accepted": "Umepokea barua pepe hii kwa sababu akaunti yako katika {organization} imewashwa.",
        "why_bill": "{organization} hutumia Lacteva kukutumia bili zako.",
        "why_settlement": "{organization} hutumia Lacteva kurekodi na kulipia maziwa unayowasilisha.",
        "why_collection": "{organization} hutumia Lacteva kurekodi maziwa unayowasilisha.",
        "why_default": "Umepokea barua pepe hii kutoka {organization} kupitia Lacteva.",
        "automated": "Huu ni ujumbe wa kiotomatiki — tafadhali usijibu.",
        "questions": "Maswali? Wasiliana na {contact}.",
    },
    "ar": {
        "join": "انضم إلى {organization}",
        "choose_password": "اختر كلمة مرور جديدة",
        "confirm_email": "أكّد بريدك الإلكتروني الجديد",
        "view_bill": "اعرض فاتورتك",
        "your_code": "رمزك",
        "invitation_code": "رمز الدعوة",
        "reset_code": "رمز إعادة تعيين كلمة المرور",
        "change_code": "رمز تغيير البريد الإلكتروني",
        "fallback": "إذا لم يعمل الزر، انسخ هذا الرابط:",
        "bill": "الفاتورة",
        "settlement": "التسوية",
        "slip": "الإيصال",
        "period": "الفترة",
        "date": "التاريخ",
        "milk_delivered": "الحليب الموصَّل",
        "quantity": "الكمية",
        "collections": "عمليات التجميع",
        "brought_forward": "الرصيد السابق",
        "gross": "المبلغ الإجمالي",
        "fat_snf": "الدهون / SNF",
        "rate": "السعر",
        "amount_due": "المبلغ المستحق",
        "net_payable": "صافي المستحق",
        "amount": "المبلغ",
        "pay_to": "ادفع إلى",
        "why_invitation": "وصلتك هذه الرسالة لأنك دُعيت للانضمام إلى {organization} على Lacteva.",
        "why_reset": "وصلتك هذه الرسالة لأن إعادة تعيين كلمة المرور طُلبت لحسابك في {organization}.",
        "why_change": "وصلتك هذه الرسالة لأن أحدًا طلب جعل هذا العنوان بريد الدخول لحساب في {organization}.",
        "why_notice": "وصلتك هذه الرسالة لأن تغييرًا في بيانات دخولك طُلب في {organization}.",
        "why_accepted": "وصلتك هذه الرسالة لأن حسابك في {organization} قد فُعّل.",
        "why_bill": "يستخدم {organization} Lacteva لإرسال فواتيرك.",
        "why_settlement": "يستخدم {organization} Lacteva لتسجيل الحليب الذي توصّله والدفع مقابله.",
        "why_collection": "يستخدم {organization} Lacteva لتسجيل الحليب الذي توصّله.",
        "why_default": "وصلتك هذه الرسالة من {organization} عبر Lacteva.",
        "automated": "هذه رسالة آلية — يرجى عدم الرد.",
        "questions": "أسئلة؟ تواصل مع {contact}.",
    },
}


def labels_for(language: str) -> dict[str, str]:
    base = language.split("-")[0].lower()
    return {**_LABELS["en"], **_LABELS.get(base, {})}


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def _money(amount, currency) -> str:
    amount, currency = _text(amount), _text(currency)
    return f"{amount} {currency}".strip()


def email_parts(
    template_key: str,
    language: str,
    variables: dict,
    secrets: dict,
    sender: Sender,
) -> EmailParts:
    """The structure of one email, from its template key and its values.

    `variables` are the template's ordinary values (already what the text
    part shows), `secrets` the one-time values that never reach storage —
    the code, and the link that carries it. Missing optional figures make
    no row: "Brought forward: 0.00" is noise, and the builders already omit
    it (DEMO-028)."""
    L = labels_for(language)
    values = {**variables, **secrets}
    organization = _text(values.get("organization")) or sender.name

    def why(key: str) -> str:
        return L[key].format(organization=organization or sender.name)

    if template_key == "invitation":
        return EmailParts(
            sender=sender,
            why=why("why_invitation"),
            action=EmailAction(
                L["join"].format(organization=organization), _text(values.get("invite_link"))
            )
            if values.get("invite_link")
            else None,
            code_label=L["invitation_code"],
            code=_text(values.get("invite_token")) or None,
            template_key=template_key,
            labels=L,
        )
    if template_key == "password_reset":
        return EmailParts(
            sender=sender,
            why=why("why_reset"),
            action=EmailAction(L["choose_password"], _text(values.get("reset_link")))
            if values.get("reset_link")
            else None,
            code_label=L["reset_code"],
            code=_text(values.get("reset_token")) or None,
            template_key=template_key,
            labels=L,
        )
    if template_key == "email_change_confirm":
        return EmailParts(
            sender=sender,
            why=why("why_change"),
            action=EmailAction(L["confirm_email"], _text(values.get("change_link")))
            if values.get("change_link")
            else None,
            code_label=L["change_code"],
            code=_text(values.get("change_token")) or None,
            template_key=template_key,
            labels=L,
        )
    if template_key == "email_change_notice":
        return EmailParts(sender=sender, why=why("why_notice"), template_key=template_key, labels=L)
    if template_key == "invitation_accepted":
        return EmailParts(
            sender=sender, why=why("why_accepted"), template_key=template_key, labels=L
        )

    if template_key == "invoice_issued":
        rows = [
            (L["bill"], _text(values.get("number"))),
            (L["period"], _period(values)),
        ]
        if _text(values.get("quantity")):
            rows.append(
                (
                    L["milk_delivered"],
                    f"{_text(values.get('quantity'))} {_text(values.get('quantity_unit'))}".strip(),
                )
            )
        if _text(values.get("previous_balance")):
            rows.append(
                (
                    L["brought_forward"],
                    _money(values.get("previous_balance"), values.get("currency")),
                )
            )
        return EmailParts(
            sender=sender,
            why=L["why_bill"].format(organization=sender.name),
            action=EmailAction(L["view_bill"], _text(values.get("bill_link")))
            if values.get("bill_link")
            else None,
            summary=tuple((k, v) for k, v in rows if v),
            amount=(L["amount_due"], _money(values.get("amount"), values.get("currency"))),
            pay_to=sender.pay_to,
            template_key=template_key,
            labels=L,
        )
    if template_key == "settlement_finalized":
        rows = [
            (L["settlement"], _text(values.get("number"))),
            (L["period"], _period(values)),
            (L["collections"], _text(values.get("line_count"))),
        ]
        if _text(values.get("quantity")):
            rows.append(
                (
                    L["quantity"],
                    f"{_text(values.get('quantity'))} {_text(values.get('quantity_unit'))}".strip(),
                )
            )
        rows.append((L["gross"], _money(values.get("gross_amount"), values.get("currency"))))
        return EmailParts(
            sender=sender,
            why=L["why_settlement"].format(organization=sender.name),
            summary=tuple((k, v) for k, v in rows if v),
            amount=(L["net_payable"], _money(values.get("net_amount"), values.get("currency"))),
            template_key=template_key,
            labels=L,
        )
    if template_key == "collection_completed":
        rows = [
            (L["slip"], _text(values.get("slip_number"))),
            (L["date"], _text(values.get("date"))),
            (
                L["quantity"],
                f"{_text(values.get('quantity'))} {_text(values.get('quantity_unit'))}".strip(),
            ),
            (L["fat_snf"], f"{_text(values.get('fat'))} / {_text(values.get('snf'))}"),
            (
                L["rate"],
                f"{_text(values.get('unit_price'))} / {_text(values.get('quantity_unit'))}".strip(),
            ),
        ]
        return EmailParts(
            sender=sender,
            why=L["why_collection"].format(organization=sender.name),
            summary=tuple((k, v) for k, v in rows if v and v.strip(" /")),
            amount=(L["amount"], _money(values.get("gross_amount"), values.get("currency"))),
            template_key=template_key,
            labels=L,
        )
    return EmailParts(
        sender=sender,
        why=L["why_default"].format(organization=sender.name),
        template_key=template_key,
        labels=L,
    )


def _period(values: dict) -> str:
    a, b = _text(values.get("period_from")), _text(values.get("period_to"))
    return f"{a} \u2013 {b}" if a and b else a or b


# --- the samples every preview renders from ---------------------------------

SAMPLE_SENDER = Sender(
    name="Patel Dairy Shop and Sweets",
    phone="+91 98765 43210",
    address="Station Road, Jawala Bazar, Maharashtra",
    pay_to="UPI: pateldairy@upi · Bank: Patel Dairy, a/c 001234, IFSC ABCD0001234",
)

_SAMPLE_LINK = "https://app.lacteva.com/{page}#code=Wc1T3hnQx8Lm2ZpVr7YbNd4KfJ9sTa0uEgHiOlPq-mvUg"
_SAMPLE_CODE = "Wc1T3hnQx8Lm2ZpVr7YbNd4KfJ9sTa0uEgHiOlPq-mvUg"


def preview_samples(template_key: str) -> tuple[dict, dict]:
    """(variables, secrets) that make a realistic preview of `template_key`.
    One source, so the committed HTML, the screenshots and the snapshot test
    all show the same email."""
    common = {
        "organization": SAMPLE_SENDER.name,
        "portal_url": "https://app.lacteva.com",
        "name": "Sarwari Patel",
    }
    if template_key == "invitation":
        return {**common, "role": "owner", "expires_days": 7}, {
            "invite_link": _SAMPLE_LINK.format(page="accept-invitation"),
            "invite_token": _SAMPLE_CODE,
        }
    if template_key == "password_reset":
        return {**common, "expires_hours": 2}, {
            "reset_link": _SAMPLE_LINK.format(page="reset-password"),
            "reset_token": _SAMPLE_CODE,
        }
    if template_key == "email_change_confirm":
        return {**common, "expires_hours": 24}, {
            "change_link": _SAMPLE_LINK.format(page="confirm-email"),
            "change_token": _SAMPLE_CODE,
        }
    if template_key == "email_change_notice":
        return {**common, "new_email": "sarwari.new@example.com", "expires_hours": 24}, {}
    if template_key == "invitation_accepted":
        return {**common, "role": "owner"}, {}
    if template_key == "invoice_issued":
        return {
            **common,
            "number": "INV-2026-0091",
            "period_from": "2026-09-01",
            "period_to": "2026-09-30",
            "amount": "1,860.00",
            "currency": "INR",
            "quantity": "62.0",
            "quantity_unit": "L",
            "previous_balance": "240.00",
        }, {}
    if template_key == "settlement_finalized":
        return {
            **common,
            "name": "Ramesh Pawar",
            "number": "STL-2026-0042",
            "period_from": "2026-09-16",
            "period_to": "2026-09-30",
            "line_count": 29,
            "quantity": "412.5",
            "quantity_unit": "L",
            "gross_amount": "18,562.50",
            "currency": "INR",
            "net_amount": "17,900.00",
        }, {}
    if template_key == "collection_completed":
        return {
            **common,
            "name": "Ramesh Pawar",
            "slip_number": "SLP-20260926-017",
            "date": "2026-09-26",
            "quantity": "14.2",
            "quantity_unit": "L",
            "fat": "4.1",
            "snf": "8.6",
            "unit_price": "45.00",
            "currency": "INR",
            "gross_amount": "639.00",
        }, {}
    return common, {}
