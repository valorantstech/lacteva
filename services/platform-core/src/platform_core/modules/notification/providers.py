"""Channel provider abstraction (NOT-001).

A provider is the thing that actually hands a rendered message to a channel.
The platform ships ADAPTERS ONLY — a logging adapter (which delegates to the
existing `Notifier` port, preserving that abstraction) and a placeholder
adapter that accepts and records without side effects. Real gateways (market
SMS providers, transactional email) are deployment concerns that implement
this same protocol; no provider-specific code lives in the platform.

Selection is configuration (`LACTEVA_NOTIFICATION_SMS_PROVIDER`,
`LACTEVA_NOTIFICATION_EMAIL_PROVIDER`), and providers can be swapped at
runtime through `register_provider` — the seam deployments and tests use.
"""

import asyncio
import json
import smtplib
import uuid
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any, Protocol

import structlog

from platform_core.core import webhook_security
from platform_core.core.config import get_settings
from platform_core.infrastructure.notifications import Notification, get_notifier

log = structlog.get_logger("notification.provider")


class ProviderSendError(Exception):
    """Delivery failed and is worth trying again.

    The base class is RETRYABLE, which keeps every pre-MSG-001 raiser
    behaving exactly as it did. Permanence is the special case and has to be
    claimed explicitly — the safe default when a provider says something
    unfamiliar is to try again, not to give up on a farmer's message.
    """


class PermanentSendError(ProviderSendError):
    """Delivery failed and will fail identically forever (MSG-001).

    An invalid phone number, a rejected sender id, a bad credential, a
    malformed request. Retrying these costs money on every attempt, delays
    the queue behind them, and cannot succeed.

    Before MSG-001 the retry engine had no way to be told this: every failure
    was retried to exhaustion, so one mistyped number consumed five gateway
    calls and five backoff windows.
    """


@dataclass(frozen=True)
class OutboundMessage:
    channel: str
    recipient: str
    title: str
    body: str
    language: str
    template_key: str
    notification_id: uuid.UUID

    #: The template's variables, IN DECLARED ORDER, already substituted
    #: (DEMO-031).
    #:
    #: **This exists because WhatsApp cannot accept the message Lacteva
    #: renders.** The WhatsApp Business Platform requires a business-initiated
    #: message to name a pre-approved template and supply positional
    #: parameters, and permits free text only inside a 24-hour customer-service
    #: window. DEMO-025 wrote that limitation into `HttpWhatsAppProvider`'s own
    #: docstring and shipped the text-only path anyway — which works against a
    #: gateway that accepts text and fails against the actual platform.
    #:
    #: So the boundary now carries both: `body` for anything that takes text,
    #: and `parameters` for anything that takes a template. Nothing in the
    #: domain changed — the order comes from the template's own declaration,
    #: which `Template.variables` has always exposed — and no adapter is
    #: obliged to use either one.
    parameters: tuple[str, ...] = ()
    #: What the VENDOR calls this template, when a vendor requires a name of
    #: its own. Configuration, never a constant: an approved template name is
    #: issued per account and per market, and hard-coding one would put a
    #: vendor's registry into Lacteva's source.
    vendor_template: str | None = None

    @property
    def idempotency_key(self) -> str:
        """What the gateway should deduplicate on (MSG-001).

        The notification id, which is stable across every retry of this
        message — so a send that succeeded at the gateway but timed out on
        our side is recognised as a duplicate rather than delivered twice.
        The platform cannot prevent that on its own: only the gateway knows
        it already accepted the message.
        """
        return f"lacteva-{self.notification_id}"


@dataclass(frozen=True)
class DeliveryResult:
    """What a provider reports back (MSG-001).

    `send()` used to return a bare string, which was enough to write in the
    audit trail and not enough to operate: an operator asking "did it
    actually arrive?" had nothing to read, and a provider with a richer
    answer had nowhere to put it.
    """

    #: The gateway's own id. This is what a support conversation quotes.
    provider_message_id: str
    #: accepted | sent | delivered | unknown. Most gateways only ACCEPT
    #: synchronously and confirm delivery later over a webhook the platform
    #: does not yet receive — see MSG-001's technical debt.
    status: str = "accepted"
    #: Provider-specific fields worth keeping: cost, segment count, the
    #: gateway's own status string. Never credentials.
    metadata: dict[str, Any] = field(default_factory=dict)


ACCEPTED = "accepted"
DELIVERED = "delivered"
UNKNOWN = "unknown"

#: Re-exported from `core/webhook_security` so a receipt adapter has one import
#: rather than two. There is still exactly ONE definition — see DEMO-029.
SIGNATURE_HEADER = webhook_security.SIGNATURE_HEADER


class ReceiptVerificationError(Exception):
    """A delivery receipt did not verify, or could not be read (DEMO-029).

    Never leak which of those it was to the caller: an attacker probing the
    endpoint learns from the difference.
    """


@dataclass(frozen=True)
class DeliveryReceipt:
    """What a gateway says happened AFTER it accepted a message (DEMO-029).

    The gap this closes: `DeliveryResult` is what a gateway said when it TOOK
    the message, which is the only thing Lacteva has ever known. A receipt is
    what it says later, asynchronously, about whether the message arrived.

    `state` is the PLATFORM's vocabulary, not the vendor's — an adapter
    normalises `DELIVRD` / `delivered` / `2` / `success` into one of these, so
    the domain never grows a table of gateway synonyms. That normalisation is
    §4's "the provider adapter may normalize provider-specific statuses".
    """

    #: The gateway's own id for this notification of this event. The REPLAY
    #: key: recording it under a unique constraint is what makes a redelivered
    #: receipt do nothing at all.
    event_id: str
    #: The gateway's id for the MESSAGE, matched against
    #: `notification.provider_reference`. This is the only way a receipt finds
    #: its notification — never a tenant or a notification id from the payload.
    provider_reference: str
    #: `delivered` | `failed` | `unknown`. Deliberately not `sent`: a receipt
    #: reporting "sent" tells the platform nothing it did not already know, and
    #: treating it as progress would be inventing information.
    state: str
    #: Why, when the gateway says. Free text, truncated, never a payload dump.
    reason: str | None = None
    #: The gateway's own status string, kept verbatim for `provider_status`.
    provider_status: str | None = None


class ReceiptCapableProvider(Protocol):
    """A provider that can verify and read delivery receipts.

    **Structural and optional, on purpose.** Most gateways send delivery
    reports; some do not, and a platform that assumed they all did would be
    inventing provider capability — the thing every one of these work orders
    forbids. A provider without `parse_receipt` simply has no receipt endpoint,
    and the route answers 404.
    """

    name: str

    def parse_receipt(self, *, body: bytes, headers: dict[str, str]) -> DeliveryReceipt: ...


def supports_receipts(provider: object) -> bool:
    """Whether this provider can be sent delivery receipts at all."""
    return callable(getattr(provider, "parse_receipt", None))


def find_receipt_provider(name: str):
    """The receipt-capable provider called `name`, or None (DEMO-029).

    The registry is keyed by CHANNEL, because that is what a send needs. A
    delivery receipt arrives at a URL that names the PROVIDER, because a
    gateway knows what it is and not which of Lacteva's channels it serves —
    so this walks the channels and matches on the provider's own name.

    A channel whose provider cannot even be built (selected as `http` with no
    URL configured, say) is skipped rather than raised: one misconfigured
    channel must not stop receipts arriving for a working one.
    """
    for channel in ("sms", "whatsapp", "email", "push"):
        try:
            provider = get_provider(channel)
        except Exception as exc:
            log.debug("receipt_provider_skipped", channel=channel, error=type(exc).__name__)
            continue
        if getattr(provider, "name", None) == name and supports_receipts(provider):
            return provider
    return None


class ChannelProvider(Protocol):
    name: str

    async def send(self, message: OutboundMessage) -> DeliveryResult:
        """Deliver, or raise.

        Raise `PermanentSendError` when a retry cannot help and
        `ProviderSendError` when it can. Getting that distinction wrong is
        the difference between five wasted gateway calls and a message that
        never gets sent.
        """
        ...


def mask_phone(value: str) -> str:
    """A phone number, safe to log (MSG-001).

    `+254700123456` becomes `+2547****3456`: enough to correlate a log line
    with a support conversation, not enough to be a contact list. Applied
    everywhere a recipient is logged, because a log that carries every
    supplier's number is a copy of the directory with weaker access control
    than the database it came from.
    """
    if not value:
        return ""
    if "@" in value:  # an email address
        name, _, domain = value.partition("@")
        head = name[:1]
        return f"{head}{'*' * max(len(name) - 1, 1)}@{domain}"
    if len(value) <= 6:
        return "*" * len(value)
    return f"{value[:5]}{'*' * (len(value) - 9)}{value[-4:]}"


class LoggingProvider:
    """Delegates to the platform `Notifier` port (preserved abstraction) and
    logs the rendered message. The dev/test default."""

    def __init__(self, channel: str):
        self.name = f"logging-{channel}"
        self._channel = channel

    async def send(self, message: OutboundMessage) -> DeliveryResult:
        await get_notifier().send(
            Notification(
                id=message.notification_id,
                channel=self._channel,
                recipient=message.recipient,
                template_key=message.template_key,
                locale=message.language,
                payload={"title": message.title, "body": message.body},
            )
        )
        log.info(
            "notification_dispatched",
            channel=self._channel,
            template=message.template_key,
            recipient=mask_phone(message.recipient),
            language=message.language,
        )
        return DeliveryResult(
            provider_message_id=f"{self.name}:{message.notification_id}", status=ACCEPTED
        )


class PlaceholderProvider:
    """Accepts and records without any side effect — the stand-in until a
    market gateway is configured. Deliveries are marked sent so the pipeline
    is exercised end to end; nothing leaves the platform."""

    def __init__(self, channel: str):
        self.name = f"placeholder-{channel}"
        self._channel = channel

    async def send(self, message: OutboundMessage) -> DeliveryResult:
        log.debug(
            "notification_placeholder",
            channel=self._channel,
            template=message.template_key,
            recipient=mask_phone(message.recipient),
        )
        return DeliveryResult(provider_message_id=f"{self.name}:{uuid.uuid4()}", status=ACCEPTED)


class ReceiptTestProvider(LoggingProvider):
    """**TEST ONLY.** A provider that also accepts delivery receipts (DEMO-029).

    It sends nothing anywhere — `LoggingProvider` writes a log line — and it
    exists so the whole receipt path can be EXECUTED rather than described:
    accepted, delivered, failed, duplicate callback, out-of-order callback and
    timeout, all deterministically.

    It is not registered by configuration and cannot be selected by a
    deployment; a test installs it with `register_provider`. Nothing it reports
    is a real external message, and the portal has no way to show one as if it
    were.
    """

    def __init__(self, channel: str = "sms") -> None:
        super().__init__(channel)
        self.name = "receipt-test"

    def sign(self, body: bytes) -> str:
        """The signature this provider would send — used by tests to forge a
        LEGITIMATE delivery, and by omission an illegitimate one."""
        from platform_core.core import webhook_security
        from platform_core.core.config import get_settings

        return webhook_security.sign(get_settings().notification_receipt_secret, body)

    def receipt_body(
        self, *, event_id: str, reference: str, status: str, reason: str | None = None
    ) -> bytes:
        return json.dumps(
            {"event_id": event_id, "reference": reference, "status": status, "reason": reason},
            sort_keys=True,
        ).encode()

    def parse_receipt(self, *, body: bytes, headers: dict[str, str]) -> DeliveryReceipt:
        return _parse_documented_receipt(body, headers)


class SandboxGatewayProvider:
    """**SANDBOX.** A gateway shaped like a real one, that reaches nobody.

    This is DEMO-031's answer to "cross the vendor boundary safely" without a
    contract, an account or a credential. It is not a stub that returns
    success: it enforces the constraints a real business-messaging platform
    enforces, so the parts of Lacteva that must satisfy them are actually
    exercised rather than assumed.

    What it insists on, and why each one is real:

    * **A template name for WhatsApp.** The WhatsApp Business Platform will not
      accept a business-initiated free-text message; it requires a pre-approved
      template. An adapter with no `vendor_template` configured is refused
      PERMANENTLY here, because that is what the real platform does and a retry
      cannot fix a template that was never approved.
    * **Positional parameters.** It sends `parameters`, not `body`, on the
      WhatsApp channel — the shape a template message actually takes.
    * **A recipient that looks like one.** A malformed number is a permanent
      failure, not a retryable one.
    * **Deterministic, addressable outcomes.** The recipient's last digit
      selects accepted / temporary failure / permanent failure, so the retry
      classification and the receipt path can both be driven without a clock or
      a random source.

    It is registered only under the `sandbox` provider name and refuses to run
    in `production` messaging mode, so it cannot become the thing a real
    deployment sends through by accident.

    **No message leaves this process.** Nothing here opens a socket.
    """

    #: Last digit of the recipient → what the "gateway" does. Deterministic so
    #: a test can address an outcome without patching anything.
    _OUTCOMES = {"7": "temporary", "8": "permanent"}

    def __init__(self, channel: str = "sms") -> None:
        self.name = f"sandbox-{channel}"
        self._channel = channel
        self.sent: list[OutboundMessage] = []

    async def send(self, message: OutboundMessage) -> DeliveryResult:
        if get_settings().messaging_mode == "production":
            # A sandbox in production is a platform that thinks it is talking
            # to farmers and is not. Worse than failing.
            raise PermanentSendError(
                "the sandbox gateway must not run in production messaging mode"
            )

        recipient = (message.recipient or "").strip()
        digits = [c for c in recipient if c.isdigit()]
        if len(digits) < 7:
            raise PermanentSendError(
                f"sandbox gateway: implausible recipient {mask_phone(recipient)}"
            )

        if self._channel == "whatsapp":
            if not message.vendor_template:
                raise PermanentSendError(
                    "sandbox gateway: WhatsApp requires an approved template name — set "
                    "LACTEVA_NOTIFICATION_VENDOR_TEMPLATES for "
                    f"{message.template_key}.{self._channel}"
                )
            if not message.parameters:
                raise PermanentSendError("sandbox gateway: a template message needs parameters")

        outcome = self._OUTCOMES.get(digits[-1], "accepted")
        if outcome == "temporary":
            raise ProviderSendError("sandbox gateway: temporary upstream failure")
        if outcome == "permanent":
            raise PermanentSendError("sandbox gateway: recipient rejected by the carrier")

        self.sent.append(message)
        log.info(
            "sandbox_gateway_accepted",
            channel=self._channel,
            template=message.template_key,
            vendor_template=message.vendor_template,
            recipient=mask_phone(recipient),
            parameters=len(message.parameters),
        )
        return DeliveryResult(
            provider_message_id=f"sbx-{message.notification_id}",
            status=ACCEPTED,
            metadata={"sandbox": True, "channel": self._channel},
        )

    # --- receipts, through DEMO-029's boundary ------------------------------

    def sign(self, body: bytes) -> str:
        return webhook_security.sign(get_settings().notification_receipt_secret, body)

    def receipt_body(
        self, *, event_id: str, reference: str, status: str, reason: str | None = None
    ) -> bytes:
        return json.dumps(
            {"event_id": event_id, "reference": reference, "status": status, "reason": reason},
            sort_keys=True,
        ).encode()

    def parse_receipt(self, *, body: bytes, headers: dict[str, str]) -> DeliveryReceipt:
        """The SAME documented contract and the SAME verification as every
        other receipt-capable adapter — DEMO-029's boundary, reused."""
        return _parse_documented_receipt(body, headers)


class DryRunProvider:
    """Renders and logs a real message without sending it (MSG-001).

    The difference from `PlaceholderProvider` is intent, and it matters
    operationally: placeholder means "no gateway is configured yet", dry-run
    means "a gateway IS configured and we are deliberately not using it".
    Staging runs in dry-run against production-shaped configuration, so a
    credential or sender-id mistake surfaces before it reaches a farmer.
    """

    def __init__(self, channel: str):
        self.name = f"dry-run-{channel}"
        self._channel = channel

    async def send(self, message: OutboundMessage) -> DeliveryResult:
        log.info(
            "sms_dry_run",
            channel=self._channel,
            template=message.template_key,
            recipient=mask_phone(message.recipient),
            characters=len(message.body),
            segments=_segments(message.body),
        )
        return DeliveryResult(
            provider_message_id=f"{self.name}:{message.notification_id}",
            status=ACCEPTED,
            metadata={"dry_run": True, "segments": _segments(message.body)},
        )


class DisabledProvider:
    """Refuses to send, permanently (MSG-001).

    For a market that is not live, or a suspended gateway. `PermanentSendError`
    rather than silent success on purpose: a notification marked sent that
    was never sent is a lie the platform would then repeat to an operator
    asking why a supplier was not told.
    """

    def __init__(self, channel: str):
        self.name = f"disabled-{channel}"
        self._channel = channel

    async def send(self, message: OutboundMessage) -> DeliveryResult:
        raise PermanentSendError(f"{self._channel} delivery is disabled by configuration")


def _segments(body: str) -> int:
    """SMS segment count — GSM-7 is 160 characters, 153 when concatenated;
    anything outside that alphabet forces UCS-2 at 70/67. Logged because
    segments are what a gateway bills, and a template that quietly crosses a
    boundary doubles the cost of every message it sends."""
    gsm = body.isascii()
    single, multi = (160, 153) if gsm else (70, 67)
    if len(body) <= single:
        return 1
    return -(-len(body) // multi)


class MessagingModeError(PermanentSendError):
    """The platform is not permitted to talk to a real gateway right now.

    A PERMANENT failure, deliberately: retrying will not change the mode, and a
    retry loop against a refusal is just a slower refusal. It surfaces in the
    notification history as a failed message with a reason an operator can act
    on — which is the point. Silently succeeding, or silently discarding, are
    the two outcomes this exists to prevent.
    """


def assert_may_reach_the_network(provider_name: str) -> None:
    """Refuse a real network call unless the deployment asked for one (DEMO-031).

    `test` is the DEFAULT, so a deployment that configures a gateway and says
    nothing else sends nothing. Reaching a real recipient requires choosing
    `sandbox` or `production` out loud.
    """
    mode = get_settings().messaging_mode
    if mode == "test":
        raise MessagingModeError(
            f"{provider_name} may not contact a gateway: LACTEVA_MESSAGING_MODE is 'test'. "
            "Set 'sandbox' or 'production' to allow it."
        )


class HttpSmsProvider:
    """A generic HTTP SMS gateway (MSG-001).

    **Vendor-neutral by construction.** The platform must not depend on one
    market's gateway — dairy markets differ by country and the same
    deployment may change provider without changing code. So this speaks a
    small, documented JSON contract configured entirely by environment, and
    classifies outcomes by HTTP STATUS, which every gateway agrees on even
    when their payloads do not.

    A gateway whose shape does not fit implements `ChannelProvider` and is
    installed with `register_provider` — that seam already existed and this
    class does not replace it.

    Classification, and the reasoning behind each:

    | Status | Verdict | Why |
    | --- | --- | --- |
    | 2xx | accepted | |
    | 400, 404, 422 | **permanent** | Malformed request or unknown number — identical on retry |
    | 401, 403 | **permanent** | A credential problem is fixed by an operator, not by waiting |
    | 408, 425, 429 | retry | Timeout or throttle; the backoff is exactly right |
    | 5xx | retry | The gateway's problem, not the message's |
    | timeout / network | retry | We cannot know whether it arrived, so we
      assume it did not — the idempotency key stops the double send |
    | unparseable body | accepted, `status=unknown` | A 2xx we cannot read is
      still a 2xx; failing it would resend a message the gateway took |
    """

    #: A retry cannot change the outcome, so do not spend a gateway call on it.
    PERMANENT_STATUSES = frozenset({400, 401, 402, 403, 404, 405, 409, 415, 422})

    def parse_receipt(self, *, body: bytes, headers: dict[str, str]) -> "DeliveryReceipt":
        """DEMO-029. Reads Lacteva's documented delivery-report contract."""
        return _parse_documented_receipt(body, headers)

    def __init__(self, channel: str = "sms") -> None:
        self.name = "http-sms"
        self._channel = channel
        settings = get_settings()
        self._url = settings.sms_api_url
        self._api_key = settings.sms_api_key
        self._sender = settings.sms_sender_id
        self._timeout = settings.sms_timeout_seconds
        if not self._url:
            raise ValueError("LACTEVA_SMS_API_URL must be set when the sms provider is 'http'")

    async def send(self, message: OutboundMessage) -> DeliveryResult:
        import httpx

        # DEMO-031: the mode gate, before anything leaves the process.
        assert_may_reach_the_network(self.name)

        payload = {
            "to": message.recipient,
            "from": self._sender,
            "text": message.body,
            # The gateway deduplicates on this. Stable across every retry, so
            # a send that succeeded but timed out on our side is recognised
            # rather than delivered twice — the one double-send the platform
            # cannot prevent by itself.
            "client_reference": message.idempotency_key,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Idempotency-Key": message.idempotency_key,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(self._url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            # We do not know whether it arrived. Assume it did not and retry;
            # the idempotency key is what makes that safe.
            raise ProviderSendError(f"gateway timeout after {self._timeout}s") from exc
        except httpx.HTTPError as exc:
            raise ProviderSendError(f"gateway unreachable: {type(exc).__name__}") from exc

        if response.status_code in self.PERMANENT_STATUSES:
            raise PermanentSendError(
                f"gateway rejected the message ({response.status_code}): "
                f"{_safe_detail(response.text)}"
            )
        if response.status_code >= 400:
            raise ProviderSendError(
                f"gateway error {response.status_code}: {_safe_detail(response.text)}"
            )

        try:
            body = response.json()
        except ValueError:
            # A 2xx we cannot parse is still a 2xx. Treating it as a failure
            # would resend a message the gateway has already accepted.
            log.warning("sms_unparseable_response", status=response.status_code)
            return DeliveryResult(
                provider_message_id=message.idempotency_key,
                status=UNKNOWN,
                metadata={"unparseable": True, "http_status": response.status_code},
            )
        if not isinstance(body, dict):
            log.warning("sms_unexpected_response_shape", status=response.status_code)
            return DeliveryResult(
                provider_message_id=message.idempotency_key,
                status=UNKNOWN,
                metadata={"http_status": response.status_code},
            )

        return DeliveryResult(
            provider_message_id=str(
                body.get("message_id") or body.get("id") or message.idempotency_key
            ),
            status=str(body.get("status") or ACCEPTED),
            metadata={
                "http_status": response.status_code,
                "segments": _segments(message.body),
                # Whatever the gateway says about cost, which is the number an
                # operator reconciles against an invoice.
                **{k: body[k] for k in ("cost", "currency", "parts") if k in body},
            },
        )


def _parse_documented_receipt(body: bytes, headers: dict[str, str]) -> DeliveryReceipt:
    """Lacteva's own documented delivery-report contract (DEMO-029).

    `HttpSmsProvider` already speaks "a small, documented JSON contract
    configured entirely by environment" for SENDING. This is the same idea for
    the report coming back, and it is deliberately Lacteva's contract rather
    than any vendor's — inventing a named gateway's DLR format would be
    inventing a capability nobody contracted.

        POST /v1/notifications/receipts/<provider>
        X-Lacteva-Signature: <hex hmac-sha256 of the raw body>
        {"event_id": "...", "reference": "...", "status": "delivered",
         "reason": "..."}

    A gateway whose reports differ implements `parse_receipt` on its own
    adapter and is installed with `register_provider` — the same seam that has
    always existed for `send`.
    """
    from platform_core.core import webhook_security
    from platform_core.core.config import get_settings

    secret = get_settings().notification_receipt_secret
    if not webhook_security.verify(secret, body, webhook_security.header_value(headers)):
        raise ReceiptVerificationError("signature mismatch")
    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise ReceiptVerificationError("unparseable body") from exc

    event_id = str(payload.get("event_id") or "").strip()
    reference = str(payload.get("reference") or "").strip()
    raw_status = str(payload.get("status") or "").strip()
    if not event_id or not reference or not raw_status:
        raise ReceiptVerificationError("incomplete receipt")

    return DeliveryReceipt(
        event_id=event_id,
        provider_reference=reference,
        state=normalise_receipt_status(raw_status),
        reason=_safe_detail(str(payload.get("reason") or "")) or None,
        provider_status=raw_status[:20],
    )


#: Gateway words that mean the same thing (DEMO-029).
#:
#: Every SMS gateway has its own spelling of "it arrived" — SMPP says
#: `DELIVRD`, most REST APIs say `delivered`, some say `2`. Normalising here is
#: what keeps the domain free of vendor synonyms. Anything unrecognised is
#: `unknown`, never a guess: a status this platform cannot read must not
#: advance a farmer's message to delivered.
_RECEIPT_STATUSES: dict[str, str] = {
    "delivered": DELIVERED,
    "delivrd": DELIVERED,
    "success": DELIVERED,
    "ok": DELIVERED,
    "failed": "failed",
    "undeliv": "failed",
    "undelivered": "failed",
    "rejected": "failed",
    "expired": "failed",
    "error": "failed",
}


def normalise_receipt_status(raw: str) -> str:
    """A gateway's word in Lacteva's vocabulary. `unknown` when unrecognised."""
    return _RECEIPT_STATUSES.get((raw or "").strip().lower(), UNKNOWN)


class HttpWhatsAppProvider(HttpSmsProvider):
    """WhatsApp over the same generic HTTP contract (DEMO-025).

    **A subclass rather than a copy, and that is the whole design decision.**
    Every business-messaging gateway that offers WhatsApp — and in most
    markets it is the same vendor that sells the SMS route — exposes it as
    another endpoint taking a recipient, a body and an idempotency key. The
    classification table above is about HTTP status codes, which do not become
    different because the message travels over a different network.

    So WhatsApp differs in exactly three ways, all of them configuration: its
    own URL, its own credential, and its own sender identity. Anything a
    vendor does that this contract cannot express — template approval ids,
    interactive buttons, media — belongs in a `ChannelProvider` of its own,
    installed through `register_provider`. That seam is why this class is
    allowed to be small.

    **What this is NOT.** It is not the WhatsApp Business API's own protocol,
    and it does not attempt template registration or session-window rules. A
    deployment pointing this at a gateway is responsible for having whatever
    pre-approved template the destination market requires; Lacteva sends text
    and records what came back.
    """

    def __init__(self, channel: str = "whatsapp") -> None:
        self.name = "http-whatsapp"
        self._channel = channel
        settings = get_settings()
        self._url = settings.whatsapp_api_url
        self._api_key = settings.whatsapp_api_key
        self._sender = settings.whatsapp_sender_id
        self._timeout = settings.whatsapp_timeout_seconds
        if not self._url:
            raise ValueError(
                "LACTEVA_WHATSAPP_API_URL must be set when the whatsapp provider is 'http'"
            )


class SmtpEmailProvider:
    """The production email transport (PROD-001).

    **Why SMTP rather than a vendor SDK.** Every transactional email service —
    SES, SendGrid, Postmark, Mailgun, and a cooperative's own relay — speaks
    SMTP, so one adapter reaches all of them with no vendor dependency and no
    lock-in, and a market whose regulator requires mail to stay on national
    infrastructure is served by the same code path. A vendor API adapter, if
    one is ever wanted for the analytics, implements this same protocol and
    changes nothing else.

    **Why a thread rather than an async SMTP library.** `smtplib` is stdlib and
    blocking; the alternative is another dependency in the delivery path. The
    send runs in `asyncio.to_thread`, so the consumer loop is never blocked and
    the platform gains no new supply-chain surface for a protocol that has not
    changed in twenty years.

    **Failure classification is the part that matters.** MSG-001's finding was
    that retrying an unretryable failure costs a real gateway call and a
    backoff window each time, and never succeeds. SMTP states this precisely:
    5xx is permanent, 4xx is transient, and the exception hierarchy separates a
    refused recipient from a refused connection.
    """

    name = "smtp-email"

    def __init__(self, channel: str = "email"):
        self._channel = channel

    def _settings(self):
        return get_settings()

    async def send(self, message: OutboundMessage) -> DeliveryResult:
        # DEMO-031: the mode gate, before anything leaves the process.
        assert_may_reach_the_network(self.name)

        settings = self._settings()
        if not settings.smtp_host:
            # A misconfiguration, not a bad address: this fails identically for
            # every message until someone changes the configuration.
            raise PermanentSendError("LACTEVA_SMTP_HOST is not configured")

        sender = settings.smtp_from_address or settings.smtp_username
        if not sender:
            raise PermanentSendError("no envelope sender (LACTEVA_SMTP_FROM_ADDRESS)")

        mail = EmailMessage()
        mail["Subject"] = message.title
        mail["From"] = formataddr((settings.smtp_from_name, sender))
        mail["To"] = message.recipient
        # Stable across every retry of this notification, so a receiving MTA
        # that deduplicates on Message-ID recognises a resend of a message the
        # gateway already accepted but whose response we lost. The platform
        # cannot make SMTP idempotent by itself; this is the part it can do.
        #
        # Built by hand rather than with `email.utils.make_msgid`, which mixes
        # in a timestamp and random bytes — that produced a NEW id on every
        # attempt and defeated the entire purpose. Caught by a test asserting
        # two sends of one message share an id.
        _local, _, domain = sender.partition("@")
        mail["Message-ID"] = f"<{message.idempotency_key}@{domain or 'lacteva.local'}>"
        mail["Auto-Submitted"] = "auto-generated"  # RFC 3834: never auto-reply
        mail["Content-Language"] = message.language
        mail.set_content(message.body)

        try:
            await asyncio.to_thread(self._deliver, mail, sender, message.recipient, settings)
        except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused) as exc:
            raise PermanentSendError(f"address refused: {_safe_detail(str(exc))}") from exc
        except (smtplib.SMTPAuthenticationError, smtplib.SMTPNotSupportedError) as exc:
            # A credential or capability problem. Every subsequent message
            # fails the same way; retrying is pure cost.
            raise PermanentSendError(
                f"smtp rejected the session: {_safe_detail(str(exc))}"
            ) from exc
        except smtplib.SMTPResponseException as exc:
            detail = _safe_detail(str(exc))
            if 500 <= int(exc.smtp_code or 0) < 600:
                raise PermanentSendError(f"smtp {exc.smtp_code}: {detail}") from exc
            raise ProviderSendError(f"smtp {exc.smtp_code}: {detail}") from exc
        except (OSError, smtplib.SMTPException) as exc:
            # Connection refused, DNS failure, TLS failure, timeout, server
            # disconnect. All genuinely transient — the base class retries.
            raise ProviderSendError(f"smtp transport failure: {_safe_detail(str(exc))}") from exc

        log.info(
            "email_sent",
            provider=self.name,
            template=message.template_key,
            recipient=mask_phone(message.recipient),
            language=message.language,
            host=settings.smtp_host,
        )
        return DeliveryResult(
            provider_message_id=mail["Message-ID"],
            status=ACCEPTED,
            metadata={"host": settings.smtp_host, "security": settings.smtp_security},
        )

    def _deliver(self, mail: EmailMessage, sender: str, recipient: str, settings) -> None:
        """The blocking half, run in a worker thread."""
        timeout = settings.smtp_timeout_seconds
        if settings.smtp_security == "ssl":
            client: smtplib.SMTP = smtplib.SMTP_SSL(
                settings.smtp_host, settings.smtp_port, timeout=timeout
            )
        else:
            client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=timeout)
        try:
            client.ehlo()
            if settings.smtp_security == "starttls":
                client.starttls()
                client.ehlo()
            if settings.smtp_username:
                client.login(settings.smtp_username, settings.smtp_password)
            client.send_message(mail, from_addr=sender, to_addrs=[recipient])
        finally:
            try:
                client.quit()
            except smtplib.SMTPException:  # pragma: no cover - the send already happened
                client.close()


class HttpPushProvider:
    """A generic HTTP push gateway (DEMO-012 §10).

    Deliberately the same shape as `HttpSmsProvider`, and for the same
    reason: the platform must not depend on one vendor. FCM, APNs, a
    self-hosted relay and an operator's own gateway all differ in payload and
    agree on HTTP status, so the contract here is a small documented JSON
    body configured entirely from the environment, and the classification is
    by status. A vendor SDK adapter implements `ChannelProvider` and is
    installed with `register_provider` — that seam is why no SDK is imported.

    Two things differ from SMS, both because of what a push token IS:

    * `410 Gone` and `404` mean the token is DEAD — the app was uninstalled
      or the token rotated. That is permanent, and it is also the platform's
      cue to stop holding a token that can never be delivered to again, which
      the service does on `PermanentSendError`.
    * The recipient is never logged. A token is capability-like: whoever
      holds it can push to that handset.

    **This adapter has never delivered a real push.** It is exercised against
    a stub gateway in `tests/test_push_delivery.py`, which proves the
    contract, the classification and the idempotency key — not that any
    particular vendor accepts it. `LACTEVA_NOTIFICATION_PUSH_PROVIDER`
    therefore defaults to `disabled`, so a deployment that has not made the
    vendor decision fails visibly rather than marking pushes delivered.
    """

    PERMANENT_STATUSES = frozenset({400, 401, 402, 403, 404, 405, 409, 410, 415, 422})

    #: A dead token, as opposed to a rejected message. The distinction is the
    #: whole reason this provider is not just the SMS one with a new name.
    GONE_STATUSES = frozenset({404, 410})

    def __init__(self, channel: str = "push") -> None:
        self.name = "http-push"
        self._channel = channel
        settings = get_settings()
        self._url = settings.push_api_url
        self._api_key = settings.push_api_key
        self._timeout = settings.push_timeout_seconds
        if not self._url:
            raise ValueError("LACTEVA_PUSH_API_URL must be set when the push provider is 'http'")

    async def send(self, message: OutboundMessage) -> DeliveryResult:
        # DEMO-031: the mode gate, before anything leaves the process.
        assert_may_reach_the_network(self.name)

        import httpx

        payload = {
            "token": message.recipient,
            "title": message.title or "Lacteva",
            "body": message.body,
            # What the app opens when the notification is tapped. The phone
            # is told WHICH record, never the record's contents: a lock
            # screen is a public surface and a balance is not.
            "data": {
                "template": message.template_key,
                "notification_id": str(message.notification_id),
            },
            "client_reference": message.idempotency_key,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Idempotency-Key": message.idempotency_key,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(self._url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderSendError(f"push gateway timeout after {self._timeout}s") from exc
        except httpx.HTTPError as exc:
            raise ProviderSendError(f"push gateway unreachable: {type(exc).__name__}") from exc

        if response.status_code in self.GONE_STATUSES:
            raise PermanentSendError(f"push token is no longer registered ({response.status_code})")
        if response.status_code in self.PERMANENT_STATUSES:
            raise PermanentSendError(
                f"push gateway rejected the message ({response.status_code}): "
                f"{_safe_detail(response.text)}"
            )
        if response.status_code >= 400:
            raise ProviderSendError(
                f"push gateway error {response.status_code}: {_safe_detail(response.text)}"
            )

        try:
            body = response.json()
        except ValueError:
            log.warning("push_unparseable_response", status=response.status_code)
            return DeliveryResult(
                provider_message_id=message.idempotency_key,
                status=UNKNOWN,
                metadata={"unparseable": True, "http_status": response.status_code},
            )
        if not isinstance(body, dict):
            log.warning("push_unexpected_response_shape", status=response.status_code)
            return DeliveryResult(
                provider_message_id=message.idempotency_key,
                status=UNKNOWN,
                metadata={"http_status": response.status_code},
            )

        # Note what is absent: the token. Not in the log line, not in the
        # metadata that `NotificationView` exposes to an operator.
        log.info(
            "push_sent",
            provider=self.name,
            template=message.template_key,
            language=message.language,
        )
        return DeliveryResult(
            provider_message_id=str(
                body.get("message_id") or body.get("id") or message.idempotency_key
            ),
            status=str(body.get("status") or ACCEPTED),
            metadata={"http_status": response.status_code},
        )


def _safe_detail(text: str) -> str:
    """A gateway error, trimmed and free of anything worth stealing.

    Error bodies echo the request often enough that a raw copy can carry the
    phone number, and occasionally the credential.
    """
    return (text or "")[:200].replace("\n", " ")


_PROVIDERS: dict[str, ChannelProvider] = {}


def register_provider(channel: str, provider: ChannelProvider) -> None:
    """Install a provider for a channel (deployment wiring; tests use it to
    inject failing or recording adapters)."""
    _PROVIDERS[channel] = provider


def reset_providers() -> None:
    _PROVIDERS.clear()


def get_provider(channel: str) -> ChannelProvider:
    if channel not in _PROVIDERS:
        settings = get_settings()
        configured = {
            "sms": settings.notification_sms_provider,
            "email": settings.notification_email_provider,
            "push": settings.notification_push_provider,
            "whatsapp": settings.notification_whatsapp_provider,
        }.get(channel, "logging")
        _PROVIDERS[channel] = _build(channel, configured)
    return _PROVIDERS[channel]


#: Configuration key holding the VENDOR's own name for one of our templates:
#: `notification.vendor_template.settlement_finalized.whatsapp` (DEMO-031).
#:
#: A WhatsApp template name is issued per business account and per market after
#: approval; it is not a property of the message and it is certainly not a
#: constant in this repository. A deployment that has one sets it; an adapter
#: that needs one and finds none refuses rather than guessing.
VENDOR_TEMPLATE_PREFIX = "notification.vendor_template."


def vendor_template_key(template_key: str, channel: str) -> str:
    return f"{VENDOR_TEMPLATE_PREFIX}{template_key}.{channel}"


def vendor_template_for(template_key: str, channel: str) -> str | None:
    """The vendor's name for this template, from process configuration.

    Read from settings rather than the tenant config store: an approved
    template belongs to the ACCOUNT Lacteva holds with a gateway, which is a
    deployment fact, not something a dairy chooses. Absent is the normal case
    and is not an error here — the adapter decides whether it can proceed.
    """
    mapping = get_settings().notification_vendor_templates
    return mapping.get(f"{template_key}.{channel}") or None


def _http_builder(channel: str):
    """Which HTTP provider a channel means. One mapping, not a chain of
    conditionals that grows a branch per channel."""
    return {
        "push": HttpPushProvider,
        "whatsapp": HttpWhatsAppProvider,
    }.get(channel, HttpSmsProvider)


def _build(channel: str, configured: str) -> ChannelProvider:
    """Configuration to provider. One place, so a typo is a startup failure
    rather than a message that quietly goes nowhere."""
    builders = {
        "logging": LoggingProvider,
        "placeholder": PlaceholderProvider,
        "dry_run": DryRunProvider,
        "disabled": DisabledProvider,
        "http": _http_builder(channel),
        "sandbox": SandboxGatewayProvider,
        "smtp": SmtpEmailProvider,
    }
    builder = builders.get(configured)
    if builder is None:
        raise ValueError(
            f"unknown {channel} provider {configured!r} — expected one of {sorted(builders)}"
        )
    return builder(channel)
