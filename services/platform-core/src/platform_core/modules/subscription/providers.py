"""The payment provider boundary (DEMO-027).

**Lacteva is not becoming a payment processor.** The whole of this file exists
to keep one sentence true:

    the business layer knows that a payment was confirmed;
    it does not know who confirmed it.

So the domain speaks in `CheckoutRequest`, `PaymentOutcome` and `WebhookEvent`,
and a provider adapter is the only code that has ever heard of a vendor. The
shape is copied deliberately from `modules/notification/providers.py` — a
Protocol, a registry, and one `_build` mapping configuration to an adapter —
because a second shape for the same idea is how two boundaries drift apart.

**There is no vendor adapter here, and that is the honest state.** No payment
provider has been selected for Lacteva's own billing; the M-Pesa strings
elsewhere in this tree are the DAIRY paying its farmers, which is a different
concern in a different module. Inventing an adapter for a gateway nobody has
contracted would mean inventing credentials, and a provider that cannot be
executed is not evidence of anything. What exists instead:

    DisabledPaymentProvider  the default, and the only correct production
                             posture today — it refuses, loudly, so a
                             deployment cannot quietly accept money it has
                             no way to take
    TestPaymentProvider      TEST ONLY, deterministic, refused outright in
                             production by settings validation

When a provider is chosen, it is one class implementing `PaymentProvider` and
one line in `_build`. Nothing in the domain moves.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

from platform_core.core import webhook_security
from platform_core.core.config import get_settings

#: The header a provider signature is read from. A real adapter uses whatever
#: its vendor documents; this constant belongs to the test provider and to the
#: default contract, not to the domain.
#:
#: DEMO-029 moved the signature ARITHMETIC to `core/webhook_security.py` so the
#: delivery-receipt webhook uses the same one rather than a second copy. Nothing
#: here changed behaviour — this module now imports what it used to inline.
SIGNATURE_HEADER = webhook_security.SIGNATURE_HEADER


# --- failures -----------------------------------------------------------------


class PaymentProviderError(Exception):
    """Base for everything a provider can fail with."""


class PaymentProviderUnavailable(PaymentProviderError):
    """No provider is configured, or the configured one refuses to act.

    Raised by `DisabledPaymentProvider` for every operation. It is a REFUSAL,
    not an outage: a deployment with no contracted gateway must fail visibly at
    the moment somebody tries to pay, rather than record an intent that can
    never be completed.
    """


class PaymentProviderTimeout(PaymentProviderError):
    """The provider did not answer in time — retryable, state UNKNOWN.

    Distinct from a failure on purpose. A timeout means the payment may well
    have succeeded, so the caller must not mark it failed; it must ask again.
    """


class WebhookVerificationError(PaymentProviderError):
    """A webhook did not carry a valid signature, or could not be parsed.

    Never leak which of those it was to the caller: an attacker probing the
    endpoint learns from the difference.
    """


# --- the language the domain speaks -------------------------------------------


@dataclass(frozen=True)
class CheckoutRequest:
    """Everything a provider needs to open a checkout, and nothing else.

    Note what is absent: no tenant id, no user, no email, no organization
    address. A checkout needs an amount, a currency and OUR reference; the rest
    is the platform's business and does not need to leave it.
    """

    #: Our own payment id, stringified. Doubles as the idempotency key at the
    #: provider, which is what makes a retried checkout safe on their side too.
    reference: str
    amount: Decimal
    currency: str
    #: Human-readable only — what the payer sees on a hosted checkout page.
    description: str


@dataclass(frozen=True)
class CheckoutSession:
    """What the provider gives back: an id to track, and where to send the payer."""

    provider_reference: str
    checkout_url: str | None = None
    #: Whatever the provider needs echoed back by a client SDK. Opaque, and
    #: never anything secret — this crosses to the browser.
    public_parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PaymentOutcome:
    """A provider's verdict on one payment.

    `state` is deliberately the platform's vocabulary, not the vendor's: an
    adapter translates `captured`/`paid`/`settled`/`COMPLETE` into one of these
    four, so the domain never grows a table of vendor synonyms.
    """

    #: `pending` | `succeeded` | `failed` | `cancelled`
    state: str
    provider_reference: str
    #: What the provider says was actually charged. The platform compares this
    #: with what it asked for and refuses a mismatch — see `billing.py`.
    amount: Decimal | None = None
    currency: str | None = None
    failure_code: str | None = None
    failure_message: str | None = None
    #: Present only when the provider is managing a recurring subscription.
    external_customer_id: str | None = None
    external_subscription_id: str | None = None


@dataclass(frozen=True)
class WebhookEvent:
    """One verified provider notification.

    `event_id` is the replay key and the reason webhooks are safe here: the
    platform records it under a unique constraint, so the second delivery of
    the same event does nothing at all. A provider that does not supply a
    stable event id must have one derived by its adapter (a digest of the raw
    body is the usual answer) — the domain requires that it exists.
    """

    event_id: str
    #: `payment.succeeded` | `payment.failed` | `payment.cancelled` |
    #: `renewal.succeeded` | `renewal.failed`
    kind: str
    outcome: PaymentOutcome


class PaymentProvider(Protocol):
    """The entire vendor surface. Four methods, and no vendor in any name."""

    name: str

    def create_checkout(self, request: CheckoutRequest) -> CheckoutSession: ...

    def verify(self, provider_reference: str) -> PaymentOutcome:
        """Ask the provider what actually happened. **Authoritative.**

        The platform calls this rather than believing a browser, and calls it
        again when confirming a webhook, because a signature proves who sent a
        message and not what is true.
        """
        ...

    def parse_webhook(self, *, body: bytes, headers: dict[str, str]) -> WebhookEvent:
        """Verify the signature and translate. Raises `WebhookVerificationError`."""
        ...


# --- providers ----------------------------------------------------------------


class DisabledPaymentProvider:
    """Refuses everything. The default, and correct until a gateway is contracted.

    A `NullProvider` that silently succeeded would be the single most dangerous
    class in this repository: it would activate subscriptions for money nobody
    ever paid. So it refuses, and the refusal is what the tests assert.
    """

    def __init__(self, name: str = "disabled") -> None:
        self.name = name

    def create_checkout(self, request: CheckoutRequest) -> CheckoutSession:
        raise PaymentProviderUnavailable(
            "no payment provider is configured for this deployment — "
            "subscriptions are activated by the Lacteva team"
        )

    def verify(self, provider_reference: str) -> PaymentOutcome:
        raise PaymentProviderUnavailable("no payment provider is configured")

    def parse_webhook(self, *, body: bytes, headers: dict[str, str]) -> WebhookEvent:
        raise PaymentProviderUnavailable("no payment provider is configured")


class TestPaymentProvider:
    """**TEST ONLY.** A deterministic provider that takes no money.

    It exists so the whole path — checkout, verification, webhook, activation,
    replay, concurrency — can be *executed* rather than described, which is the
    standing rule in this repository. It is refused outright in production by
    `Settings` validation, because a fake gateway reachable in production is
    indistinguishable from free software.

    Determinism comes from the reference, not from a clock or a random source:
    the scenario is whatever `scenario` says, and every call with the same
    input gives the same answer, so a concurrency test can race eight callers
    and still assert an exact final state.
    """

    #: What the next payment does. Tests set it; nothing else may.
    scenario: str

    def __init__(self, name: str = "test", scenario: str = "success") -> None:
        self.name = name
        self.scenario = scenario
        #: References this provider has been asked to verify, in order. Lets a
        #: test assert that the platform re-verified rather than trusting a
        #: payload it was handed.
        self.verifications: list[str] = []

    # -- checkout --------------------------------------------------------------

    def create_checkout(self, request: CheckoutRequest) -> CheckoutSession:
        if self.scenario == "checkout_timeout":
            raise PaymentProviderTimeout("test provider: checkout timed out")
        return CheckoutSession(
            provider_reference=f"test_{request.reference}",
            checkout_url=f"https://payments.test.invalid/checkout/{request.reference}",
            public_parameters={"provider": self.name, "amount": str(request.amount)},
        )

    # -- verification ----------------------------------------------------------

    def verify(self, provider_reference: str) -> PaymentOutcome:
        self.verifications.append(provider_reference)
        if self.scenario == "timeout":
            raise PaymentProviderTimeout("test provider: verification timed out")
        state = self._state()
        paid = state == "succeeded"
        declined = state == "failed"
        return PaymentOutcome(
            state=state,
            provider_reference=provider_reference,
            amount=self._amount,
            currency=self._currency,
            failure_code="test_declined" if declined else None,
            failure_message="the test provider was asked to decline" if declined else None,
            external_customer_id=f"cus_{provider_reference}" if paid else None,
            external_subscription_id=f"sub_{provider_reference}" if paid else None,
        )

    #: Set by `record_intent` so `verify` can answer with the amount the
    #: platform actually asked for. A test that wants a MISMATCH overrides it.
    _amount: Decimal | None = None
    _currency: str | None = None

    def record_intent(self, amount: Decimal, currency: str) -> None:
        """Tell the fake what it is supposed to have charged."""
        self._amount = amount
        self._currency = currency

    def _state(self) -> str:
        return {
            "success": "succeeded",
            "failed": "failed",
            "cancelled": "cancelled",
            "pending": "pending",
        }.get(self.scenario, "succeeded")

    # -- webhooks --------------------------------------------------------------

    def sign(self, body: bytes) -> str:
        """The signature this provider would send. Used by tests to forge a
        LEGITIMATE delivery — and, by omission, an illegitimate one."""
        return webhook_security.sign(_webhook_secret(), body)

    def webhook_body(
        self,
        *,
        event_id: str,
        kind: str,
        provider_reference: str,
        amount: Decimal | None = None,
        currency: str | None = None,
        state: str | None = None,
    ) -> bytes:
        """Build a delivery exactly as this provider would send it."""
        return json.dumps(
            {
                "event_id": event_id,
                "kind": kind,
                "reference": provider_reference,
                "amount": None if amount is None else str(amount),
                "currency": currency,
                "state": state,
            },
            sort_keys=True,
        ).encode()

    def parse_webhook(self, *, body: bytes, headers: dict[str, str]) -> WebhookEvent:
        supplied = webhook_security.header_value(headers)
        # Constant time, in one place: see `core/webhook_security.compare`.
        if not webhook_security.verify(_webhook_secret(), body, supplied):
            raise WebhookVerificationError("signature mismatch")
        try:
            payload = json.loads(body)
        except ValueError as exc:  # pragma: no cover - defensive
            raise WebhookVerificationError("unparseable body") from exc

        event_id = payload.get("event_id")
        kind = payload.get("kind")
        reference = payload.get("reference")
        if not event_id or not kind or not reference:
            raise WebhookVerificationError("incomplete event")

        state = payload.get("state") or ("succeeded" if kind.endswith(".succeeded") else "failed")
        amount = payload.get("amount")
        return WebhookEvent(
            event_id=str(event_id),
            kind=str(kind),
            outcome=PaymentOutcome(
                state=str(state),
                provider_reference=str(reference),
                amount=None if amount is None else Decimal(str(amount)),
                currency=payload.get("currency"),
            ),
        )


# --- the registry -------------------------------------------------------------


_PROVIDERS: dict[str, PaymentProvider] = {}


def register_payment_provider(name: str, provider: PaymentProvider) -> None:
    """Install a provider (deployment wiring; tests inject fakes here)."""
    _PROVIDERS[name] = provider


def reset_payment_providers() -> None:
    _PROVIDERS.clear()


def get_payment_provider(name: str | None = None) -> PaymentProvider:
    """The provider this deployment uses, built once and cached.

    `name` is for the webhook route, which is addressed per provider so that
    two gateways can run side by side during a migration. It is validated
    against configuration — an unknown name is not built, so the endpoint
    cannot be used to instantiate anything a deployment did not choose.
    """
    settings = get_settings()
    configured = settings.subscription_payment_provider
    resolved = name or configured
    if resolved not in _PROVIDERS:
        if name is not None and name != configured:
            raise PaymentProviderUnavailable(f"unknown payment provider: {name}")
        _PROVIDERS[resolved] = _build(configured)
    return _PROVIDERS[resolved]


def _build(configured: str) -> PaymentProvider:
    """Configuration to provider. One place, so a typo fails startup rather
    than one payment at a time."""
    builders: dict[str, Any] = {
        "disabled": DisabledPaymentProvider,
        "test": TestPaymentProvider,
    }
    builder = builders.get(configured)
    if builder is None:
        raise ValueError(
            f"unknown payment provider {configured!r} — expected one of {sorted(builders)}"
        )
    return builder(configured)


def _webhook_secret() -> str:
    return get_settings().subscription_payment_webhook_secret


__all__ = [
    "SIGNATURE_HEADER",
    "CheckoutRequest",
    "CheckoutSession",
    "DisabledPaymentProvider",
    "PaymentOutcome",
    "PaymentProvider",
    "PaymentProviderError",
    "PaymentProviderTimeout",
    "PaymentProviderUnavailable",
    "TestPaymentProvider",
    "WebhookEvent",
    "WebhookVerificationError",
    "get_payment_provider",
    "register_payment_provider",
    "reset_payment_providers",
]
