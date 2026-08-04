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
    _t(
        "settlement_finalized",
        "sms",
        "en",
        "Settlement {number} ready",
        "Hello {name}, settlement {number} is finalised: {net_amount} {currency} "
        "for {line_count} delivery(ies).",
    ),
    _t(
        "settlement_finalized",
        "sms",
        "sw",
        "Malipo {number} tayari",
        "Habari {name}, malipo {number} yamekamilika: {net_amount} {currency} "
        "kwa mizigo {line_count}.",
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
        "The invitation expires in {expires_days} days.",
    ),
    _t(
        "invitation_accepted",
        "email",
        "en",
        "Welcome to Lacteva",
        "Your account is active. You joined {organization} as {role}.",
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
