"""Can Lacteva reasonably attempt to contact this person? (DEMO-029)

**A derivation, not a directory.** The work order warns against a duplicate
contact store and the survey agreed: every fact this needs already exists —
`NotificationRecipient` for suppliers, `Customer.phone` for households, the
tenant's channel configuration, and the provider registry. Nothing here stores
a contact detail; it reads the ones the platform already keeps and answers one
question.

Three answers, and the third is the honest one that a lesser design would
collapse into the second:

    REACHABLE     there is an address of the kind this channel needs
    UNREACHABLE   there is not, and that is a fact — a missing phone number
    UNKNOWN       the platform cannot tell without asking someone else

**WhatsApp is always UNKNOWN at best.** Possessing a phone number does not
prove a WhatsApp account exists on it, no gateway here can be asked, and
reporting a household as reachable on WhatsApp because it has a phone would be
inventing a capability. That is §6's rule and it is the single most important
line in this file.

**This never blocks money.** Reachability is about communication and nothing
else: a farmer with no phone number is settled exactly as before, is paid
exactly as before, and appears in this report so an operator can do something
about it. Silence would be the failure — the point of counting the unreachable
is that somebody sees them.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.modules.notification.models import NotificationRecipient

#: The three answers. Deliberately not a new status vocabulary for messages —
#: this describes a RECIPIENT, not a notification, and nothing else in the
#: platform already says this.
REACHABLE = "reachable"
UNREACHABLE = "unreachable"
UNKNOWN = "unknown"

#: Why, in the work order's own words.
PHONE_MISSING = "phone_missing"
EMAIL_MISSING = "email_missing"
INVALID_PHONE = "invalid_phone"
CHANNEL_DISABLED = "channel_disabled"
NO_SUPPORTED_CHANNEL = "no_supported_channel"
WHATSAPP_UNKNOWN = "whatsapp_unknown"
PROVIDER_UNAVAILABLE = "provider_unavailable"
NOT_IN_DIRECTORY = "not_in_directory"

#: Deliberately conservative: it can say "this is certainly not a phone
#: number", and never "this number works".
#:
#: Digits, optionally a leading `+`, and the separators humans type. Between 7
#: and 15 digits — 15 is E.164's maximum and 7 is shorter than any national
#: number in a market this platform serves. Anything outside that was typed by
#: mistake; anything inside it may still be wrong, which is why the answer for
#: a well-formed number is REACHABLE and not "will arrive".
#: A leading `(` is allowed because people write `(020) 555-0134` and that is a
#: real number. Erring permissive is deliberate in this direction: a false
#: "invalid" ACCUSES a record of being wrong and sends an operator to fix
#: something that is fine, while a false "valid" simply lets the send fail
#: visibly in the notification history, where it is already handled.
_PHONE_SHAPE = re.compile(r"^[+(]?[0-9(][0-9 ()\-.]{5,20}$")


def looks_like_a_phone_number(value: str | None) -> bool:
    if not value or not value.strip():
        return False
    candidate = value.strip()
    if not _PHONE_SHAPE.match(candidate):
        return False
    digits = sum(character.isdigit() for character in candidate)
    return 7 <= digits <= 15


def looks_like_an_email(value: str | None) -> bool:
    """Shape only. Deliverability is not knowable without sending."""
    if not value or not value.strip():
        return False
    candidate = value.strip()
    if candidate.count("@") != 1:
        return False
    local, _, domain = candidate.partition("@")
    return bool(local) and "." in domain and not domain.startswith(".")


@dataclass(frozen=True)
class Reachability:
    """One recipient's answer."""

    subject_id: uuid.UUID
    subject_type: str
    name: str
    channel: str
    status: str
    reason: str | None = None
    #: The masked address, when there is one. Masked by the same convention
    #: the notification history uses — an operator needs to see WHICH number is
    #: on file without the report becoming a list of farmers' phone numbers.
    contact: str | None = None


def evaluate(
    *,
    channel: str,
    phone: str | None,
    email: str | None,
    provider_available: bool,
    subject_id: uuid.UUID,
    subject_type: str,
    name: str,
) -> Reachability:
    """The whole decision, as a pure function.

    Pure on purpose: it is the part worth testing exhaustively, and it has no
    session, no tenant and no I/O to arrange in order to do so.
    """
    from platform_core.modules.notification.providers import mask_phone

    def answer(status: str, reason: str | None, contact: str | None = None) -> Reachability:
        return Reachability(
            subject_id=subject_id,
            subject_type=subject_type,
            name=name,
            channel=channel,
            status=status,
            reason=reason,
            contact=contact,
        )

    if not provider_available:
        # The deployment cannot send on this channel at all. Not the
        # recipient's fault, and not something an operator fixes by editing a
        # phone number — so it is UNKNOWN with its own reason, never
        # UNREACHABLE.
        return answer(UNKNOWN, PROVIDER_UNAVAILABLE)

    if channel in ("sms", "whatsapp"):
        if not phone or not phone.strip():
            return answer(UNREACHABLE, PHONE_MISSING)
        if not looks_like_a_phone_number(phone):
            return answer(UNREACHABLE, INVALID_PHONE, mask_phone(phone))
        if channel == "whatsapp":
            # A phone number is not a WhatsApp account. Nothing in this
            # platform can check, so the honest answer is UNKNOWN — never YES.
            return answer(UNKNOWN, WHATSAPP_UNKNOWN, mask_phone(phone))
        return answer(REACHABLE, None, mask_phone(phone))

    if channel == "email":
        if not email or not email.strip():
            return answer(UNREACHABLE, EMAIL_MISSING)
        if not looks_like_an_email(email):
            return answer(UNREACHABLE, EMAIL_MISSING, email.strip()[:3] + "***")
        return answer(REACHABLE, None, email.strip()[:3] + "***")

    if channel == "push":
        # A push needs a registered device, which is a per-user fact this
        # report cannot establish for a subject that may have no login at all.
        return answer(UNKNOWN, NO_SUPPORTED_CHANNEL)

    return answer(UNKNOWN, NO_SUPPORTED_CHANNEL)


@dataclass(frozen=True)
class ReachabilitySummary:
    """What an operator sees before a communication run."""

    template_key: str
    channel: str
    total: int
    reachable: int
    unreachable: int
    unknown: int
    #: reason → count, so the portal can say "9 missing phone, 5 invalid".
    reasons: dict[str, int]
    #: Everyone who is NOT plainly reachable. **They are never silently
    #: skipped** — the whole purpose of the report is that these people are
    #: visible and identifiable.
    affected: list[Reachability]


class ReachabilityView(BaseModel):
    subject_id: uuid.UUID
    subject_type: str
    name: str
    channel: str
    status: str
    reason: str | None = None
    #: Masked. An operator needs to see WHICH number is on file; the report
    #: must not become a list of farmers' phone numbers.
    contact: str | None = None


class ReachabilitySummaryView(BaseModel):
    """The pre-communication report, as an operator reads it."""

    template_key: str
    channel: str
    total: int
    reachable: int
    unreachable: int
    unknown: int
    reasons: dict[str, int]
    #: Everyone not plainly reachable, named. The counts above are always
    #: complete; this list is capped, and `affected_truncated` says so rather
    #: than letting a long list look short.
    affected: list[ReachabilityView]
    affected_truncated: bool = False

    @classmethod
    def of(cls, summary: ReachabilitySummary) -> ReachabilitySummaryView:
        shown = len(summary.affected)
        return cls(
            template_key=summary.template_key,
            channel=summary.channel,
            total=summary.total,
            reachable=summary.reachable,
            unreachable=summary.unreachable,
            unknown=summary.unknown,
            reasons=summary.reasons,
            affected=[ReachabilityView(**vars(item)) for item in summary.affected],
            affected_truncated=shown < (summary.unreachable + summary.unknown),
        )


class ReachabilityService:
    """Reachability for one tenant, on the channel a template actually uses."""

    #: How many affected recipients to name. A summary is still a summary; the
    #: counts are always complete even when the list is capped, and the cap is
    #: reported so nothing looks smaller than it is.
    LIST_LIMIT = 200

    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def for_template(
        self, template_key: str, *, subject_type: str = "supplier", limit: int | None = None
    ) -> ReachabilitySummary:
        """Evaluate everyone this template would be sent to.

        The channel is resolved through the SAME function dispatch uses, so the
        report cannot describe a channel the message would not have gone on.
        """
        from platform_core.consumers.notification_dispatch import MAPPINGS
        from platform_core.modules.notification.service import resolve_channel

        default = _default_channel(MAPPINGS, template_key)
        channel = await resolve_channel(
            self._session, template_key, default, tenant_id=self._tenant_id
        )
        available = _provider_available(channel)

        results = [
            evaluate(
                channel=channel,
                phone=phone,
                email=email,
                provider_available=available,
                subject_id=subject_id,
                subject_type=subject_type,
                name=name,
            )
            for subject_id, name, phone, email in await self._contacts(subject_type)
        ]

        reasons: dict[str, int] = {}
        for result in results:
            if result.reason:
                reasons[result.reason] = reasons.get(result.reason, 0) + 1
        affected = [r for r in results if r.status != REACHABLE]
        cap = self.LIST_LIMIT if limit is None else max(0, limit)

        return ReachabilitySummary(
            template_key=template_key,
            channel=channel,
            total=len(results),
            reachable=sum(1 for r in results if r.status == REACHABLE),
            unreachable=sum(1 for r in results if r.status == UNREACHABLE),
            unknown=sum(1 for r in results if r.status == UNKNOWN),
            reasons=dict(sorted(reasons.items())),
            affected=affected[:cap],
        )

    async def _contacts(
        self, subject_type: str
    ) -> list[tuple[uuid.UUID, str, str | None, str | None]]:
        """Contact details from the records that already hold them.

        Suppliers come through the notification directory, which is the same
        place `_resolve_recipient` reads — so this report cannot disagree with
        what a send would actually do. Households come from `customer`, which
        is where a household's number lives and where the invoice event reads
        it from.
        """
        if subject_type == "customer":
            from platform_core.modules.customer.models import Customer

            rows = (
                await self._session.execute(
                    select(Customer.id, Customer.name, Customer.phone).where(
                        Customer.tenant_id == self._tenant_id,
                        Customer.status == "active",
                    )
                )
            ).all()
            # A household has no email anywhere in this platform. Reporting one
            # as email-unreachable is correct, and inventing a column to hold
            # an address nobody collects would not be.
            return [(row[0], row[1], row[2], None) for row in rows]

        rows = (
            await self._session.execute(
                select(
                    NotificationRecipient.subject_id,
                    NotificationRecipient.display_name,
                    NotificationRecipient.phone,
                    NotificationRecipient.email,
                ).where(
                    NotificationRecipient.tenant_id == self._tenant_id,
                    NotificationRecipient.subject_type == subject_type,
                    NotificationRecipient.active.is_(True),
                )
            )
        ).all()
        return [(row[0], row[1], row[2], row[3]) for row in rows]

    async def directory_size(self, subject_type: str = "supplier") -> int:
        return (
            await self._session.scalar(
                select(func.count())
                .select_from(NotificationRecipient)
                .where(
                    NotificationRecipient.tenant_id == self._tenant_id,
                    NotificationRecipient.subject_type == subject_type,
                )
            )
        ) or 0


def _default_channel(mappings, template_key: str) -> str:
    for mapping in mappings.values():
        if mapping.template_key == template_key:
            return mapping.channel
    return "sms"


def _provider_available(channel: str) -> bool:
    """Whether this deployment can send on this channel at all.

    A `disabled` provider is configured and refuses — which is a real answer
    and not an error, and the reason an operator sees is
    `provider_unavailable` rather than a list of blameless farmers.
    """
    from platform_core.modules.notification.providers import DisabledProvider, get_provider

    try:
        provider = get_provider(channel)
    except Exception:
        return False
    return not isinstance(provider, DisabledProvider)


__all__ = [
    "CHANNEL_DISABLED",
    "EMAIL_MISSING",
    "INVALID_PHONE",
    "NOT_IN_DIRECTORY",
    "NO_SUPPORTED_CHANNEL",
    "PHONE_MISSING",
    "PROVIDER_UNAVAILABLE",
    "REACHABLE",
    "UNKNOWN",
    "UNREACHABLE",
    "WHATSAPP_UNKNOWN",
    "Reachability",
    "ReachabilityService",
    "ReachabilitySummary",
    "ReachabilitySummaryView",
    "ReachabilityView",
    "evaluate",
    "looks_like_a_phone_number",
    "looks_like_an_email",
]
