"""Dependency injection wiring (FastAPI dependencies).

Composition root for request-scoped services: routers depend on these
providers, never construct services or touch the session directly.
"""

import uuid
from dataclasses import dataclass
from typing import Annotated

import jwt as pyjwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.backup.service import BackupService
from platform_core.core.db import get_session
from platform_core.core.errors import ForbiddenError, UnauthorizedError
from platform_core.core.i18n import set_locale
from platform_core.core.metrics import AUTH_FAILURES, AUTHZ_DENIALS, JWT_VERIFICATION_FAILURES
from platform_core.core.rls import platform_factory
from platform_core.core.security import decode_token
from platform_core.core.tenancy import (
    get_current_tenant,
    set_current_customer,
    set_current_tenant,
)
from platform_core.infrastructure.events import EventBus, get_event_bus
from platform_core.infrastructure.storage import get_object_storage
from platform_core.modules.audit.service import AuditService
from platform_core.modules.auth.models import AuthSession
from platform_core.modules.auth.service import AuthService
from platform_core.modules.authz.service import AuthzService, PermissionEngine
from platform_core.modules.billing.service import BillingService
from platform_core.modules.business_calendar.service import BusinessCalendarService
from platform_core.modules.collection_center.service import CollectionCenterService
from platform_core.modules.configuration.service import ConfigurationService
from platform_core.modules.customer.service import CustomerService
from platform_core.modules.delivery.service import DeliveryService
from platform_core.modules.event_relay.consumers import ConsumerRunner
from platform_core.modules.event_relay.projections import ProjectionRebuilder
from platform_core.modules.event_relay.service import OutboxEventBus, RelayService
from platform_core.modules.identity.models import User
from platform_core.modules.identity.service import IdentityService
from platform_core.modules.milk_collection.service import MilkCollectionService
from platform_core.modules.notification.service import NotificationService
from platform_core.modules.operational_readiness.service import OperationalReadinessService
from platform_core.modules.organization.service import (
    InvitationService,
    MembershipService,
    OrganizationService,
    StructureService,
)
from platform_core.modules.payment.service import PaymentService
from platform_core.modules.pricing.calculator import PricingCalculationService
from platform_core.modules.pricing.matrix import PricingMatrixService
from platform_core.modules.pricing.resolution import PricingResolutionService
from platform_core.modules.pricing.service import RateCardService
from platform_core.modules.receipt.service import ReceiptService
from platform_core.modules.reporting.service import ReportingService
from platform_core.modules.settlement.service import SettlementService
from platform_core.modules.supplier.service import SupplierService
from platform_core.modules.sync.service import SyncService

Session = Annotated[AsyncSession, Depends(get_session)]


def get_outbox_bus(session: Session) -> EventBus:
    """The transactional bus (SPRINT-008A): publishes land in event_outbox
    inside the caller's transaction; the relay delivers to the transport."""
    return OutboxEventBus(session, get_event_bus())


Bus = Annotated[EventBus, Depends(get_outbox_bus)]


def get_relay_service(session: Session) -> RelayService:
    return RelayService(session, get_event_bus())


def get_consumer_runner() -> ConsumerRunner:
    # Own session factory: consumers run isolated per-event transactions.
    # MT-001: the consumer ops API reports on every tenant's events; it is
    # guarded by `relay.manage`, not by a tenant. Handing it a request-scoped
    # session would show an operator an empty platform.
    return ConsumerRunner(platform_factory("ops API: consumer administration"))


def get_backup_service() -> "BackupService":
    from platform_core.core.backup.service import BackupService

    # Own session factory: backup and verification runs are platform
    # operations spanning every tenant, not request-scoped work.
    return BackupService(platform_factory("ops API: backup administration"))


def get_projection_rebuilder() -> ProjectionRebuilder:
    # Own session factory: replay commits per batch, independent of requests.
    return ProjectionRebuilder(platform_factory("ops API: projection administration"))


_bearer = HTTPBearer(auto_error=False)


def get_audit_service(session: Session) -> AuditService:
    return AuditService(session)


Audit = Annotated[AuditService, Depends(get_audit_service)]


def get_identity_service(session: Session, bus: Bus, audit: Audit) -> IdentityService:
    return IdentityService(session, bus, audit)


Identity = Annotated[IdentityService, Depends(get_identity_service)]


def get_membership_service(session: Session) -> MembershipService:
    return MembershipService(session)


def get_auth_service(session: Session, identity: Identity, audit: Audit, bus: Bus) -> AuthService:
    return AuthService(session, identity, MembershipService(session), audit, bus)


def get_structure_service(session: Session, bus: Bus, audit: Audit) -> StructureService:
    return StructureService(session, bus, audit)


def get_invitation_service(session: Session, bus: Bus, audit: Audit) -> InvitationService:
    return InvitationService(session, bus, audit)


def get_organization_service(session: Session, bus: Bus, audit: Audit) -> OrganizationService:
    return OrganizationService(session, bus, audit)


def get_authz_service(session: Session, audit: Audit) -> AuthzService:
    return AuthzService(session, audit)


def get_permission_engine(session: Session) -> PermissionEngine:
    return PermissionEngine(session)


def get_configuration_service(session: Session, audit: Audit) -> ConfigurationService:
    return ConfigurationService(session, audit)


def get_collection_center_service(
    session: Session, bus: Bus, audit: Audit
) -> CollectionCenterService:
    return CollectionCenterService(session, bus, audit)


def get_readiness_service(session: Session, bus: Bus, audit: Audit) -> OperationalReadinessService:
    return OperationalReadinessService(session, bus, audit)


def get_supplier_service(session: Session, bus: Bus, audit: Audit) -> SupplierService:
    return SupplierService(session, bus, audit, get_object_storage())


def get_rate_card_service(session: Session, bus: Bus, audit: Audit) -> RateCardService:
    return RateCardService(session, bus, audit)


def get_pricing_matrix_service(session: Session, bus: Bus, audit: Audit) -> PricingMatrixService:
    return PricingMatrixService(session, bus, audit)


def get_pricing_resolution_service(session: Session) -> PricingResolutionService:
    # Read-side only: no bus, no audit — resolution mutates nothing.
    return PricingResolutionService(session)


def get_pricing_calculation_service(
    session: Session, bus: Bus, audit: Audit
) -> PricingCalculationService:
    return PricingCalculationService(session, bus, ConfigurationService(session, audit))


def get_notification_service(session: Session) -> NotificationService:
    """The dispatcher. Business modules never receive this — notifications
    originate only from durable events (BR-0016)."""
    return NotificationService(session)


def get_reporting_service(session: Session) -> ReportingService:
    # Read-only: no bus, no audit — reports mutate nothing.
    return ReportingService(session)


def get_payment_service(session: Session, bus: Bus, audit: Audit) -> PaymentService:
    return PaymentService(session, bus, audit)


def get_receipt_service(session: Session, bus: Bus, audit: Audit) -> ReceiptService:
    return ReceiptService(session, bus, audit)


def get_customer_service(session: Session, audit: Audit) -> CustomerService:
    return CustomerService(session, audit)


def get_delivery_service(session: Session, bus: Bus, audit: Audit) -> DeliveryService:
    return DeliveryService(session, bus, audit)


def get_billing_service(session: Session, bus: Bus, audit: Audit) -> BillingService:
    return BillingService(session, bus, audit)


def get_settlement_service(session: Session, bus: Bus, audit: Audit) -> SettlementService:
    return SettlementService(session, bus, audit, RelayService(session, get_event_bus()))


def get_milk_collection_service(session: Session, bus: Bus, audit: Audit) -> MilkCollectionService:
    # MVP-001: the transaction engine invokes the Pricing Platform at the
    # pricing step (resolution -> calculator), composed here — no module
    # reaches into another's internals.
    return MilkCollectionService(
        session,
        bus,
        audit,
        OperationalReadinessService(session, bus, audit),
        PricingResolutionService(session),
        PricingCalculationService(session, bus, ConfigurationService(session, audit)),
    )


def get_sync_service(session: Session, bus: Bus, audit: Audit) -> SyncService:
    """OFF-001: sync replays device operations through the SAME collection
    service the online API uses — offline is a transport, not a second
    implementation."""
    return SyncService(session, get_milk_collection_service(session, bus, audit))


@dataclass(frozen=True)
class Principal:
    user: User
    tenant_id: uuid.UUID | None
    session_id: uuid.UUID
    #: DEMO-012 — set when this login speaks for ONE customer (the mobile
    #: customer experience). None for every staff account.
    customer_id: uuid.UUID | None = None

    @property
    def is_customer(self) -> bool:
        return self.customer_id is not None

    @property
    def id(self) -> uuid.UUID:
        return self.user.id


async def get_current_principal(
    session: Session,
    identity: Identity,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    if credentials is None:
        raise UnauthorizedError()
    try:
        payload = decode_token(credentials.credentials, expected_type="access")
        session_id = uuid.UUID(payload["sid"])
    except (pyjwt.InvalidTokenError, KeyError, ValueError) as exc:
        # `reason` is a bounded vocabulary — never the exception message,
        # which would be unbounded label cardinality (see core/metrics.py).
        JWT_VERIFICATION_FAILURES.labels(type(exc).__name__).inc()
        AUTH_FAILURES.labels("invalid_token").inc()
        raise UnauthorizedError() from exc
    # SEC-002: bind BEFORE the first read, not after.
    #
    # `auth_session` and `user_account` are themselves tenant-owned. The
    # session was bound from the X-Tenant-ID header — which a client is not
    # obliged to send — so under RLS a tenant-scoped session row was invisible
    # to the very request that owned it, and every authenticated call without
    # that header failed as 401. The token is signed and self-contained, so
    # its tenant claim is authoritative before any row is read; binding here
    # closes the window without trusting anything the caller can forge.
    token_tenant = uuid.UUID(payload["tenant_id"]) if payload.get("tenant_id") else None
    if token_tenant is not None:
        from platform_core.core.rls import rebind_tenant

        await rebind_tenant(session, token_tenant)

    # Access tokens die with their session: logout/reset revokes immediately.
    # TODO(M2): cache active-session lookups in Redis (one DB hit per request now).
    auth_session = await session.get(AuthSession, session_id)
    from platform_core.core.db import as_utc, utcnow

    if (
        auth_session is None
        or auth_session.revoked_at is not None
        or as_utc(auth_session.expires_at) < utcnow()
    ):
        AUTH_FAILURES.labels("session_revoked_or_expired").inc()
        raise UnauthorizedError()
    user = await identity.get_user(uuid.UUID(payload["sub"]))
    if not user.is_active:
        AUTH_FAILURES.labels("user_inactive").inc()
        raise UnauthorizedError()

    # DEMO-008: membership is checked on EVERY request, not only at login.
    #
    # `AuthService.login` already refused a suspended member, and `refresh`
    # already refused a deactivated user — but neither re-checked membership
    # afterwards. Suspending someone therefore did nothing until their access
    # token expired, and their refresh token kept minting new ones: the
    # suspension was a note in a table rather than a revocation.
    #
    # This is the same guarantee `user.is_active` above already has, applied
    # to the other half of the relationship. A missing membership row still
    # counts as active — platform principals have none, and so do users
    # created before memberships were backfilled; that rule lives in
    # `MembershipService.is_active_member` and is deliberately not duplicated
    # here.
    if token_tenant is not None:
        if not await MembershipService(session).is_active_member(user.id, token_tenant):
            AUTH_FAILURES.labels("membership_inactive").inc()
            raise UnauthorizedError()
        # Tenant-scoped tokens are authoritative — the header cannot override.
        # The binding already happened above, before the first read; this
        # keeps the context variable and the binding in agreement.
        set_current_tenant(token_tenant)
        principal_tenant = token_tenant
    else:
        # Platform-level principals may act inside a tenant via X-Tenant-ID
        # (bootstrap/administration path, permission-guarded per route).
        principal_tenant = get_current_tenant()

    # DEMO-012: bind the customer scope from the ACCOUNT, never the request.
    #
    # A customer-facing login is limited to one customer's rows. That limit is
    # a property of the account — set when the account is created — so it is
    # read here from the user row rather than accepted from a header, a claim
    # or a query parameter. There is deliberately no way for a client to ask
    # for a different scope, or to ask for none.
    #
    # Staff accounts have NULL and are unaffected: the narrowing only ever
    # removes rows, so a scope that fails to apply cannot widen access.
    set_current_customer(user.customer_id)
    # DEMO-013 §5: the person's OWN language wins, and it is read from their
    # row rather than from a header — `Accept-Language` is a device setting,
    # and a phone left in the wrong language must not decide what a dairy's
    # staff read. The middleware's negotiation from the header stands only for
    # requests that never authenticate.
    if user.locale:
        set_locale(user.locale)
    return Principal(
        user=user,
        tenant_id=principal_tenant,
        session_id=session_id,
        customer_id=user.customer_id,
    )


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]


def get_business_calendar_service(
    session: Session, principal: CurrentPrincipal
) -> BusinessCalendarService:
    """DEMO-020. Scoped to the caller's own organization at construction.

    The tenant comes from the authenticated principal rather than from a path
    or a body, so there is no request in which a caller can name someone
    else's organization — the service simply has no way to be pointed at one.
    """
    if principal.tenant_id is None:
        raise ForbiddenError("this endpoint requires an organization context")
    return BusinessCalendarService(session, principal.tenant_id)


def require_center_access(param: str = "center_id"):
    """Route guard: the principal may act at the centre named by `param`.

    DEMO-008 §7. Organization-wide principals pass unchanged; a centre-scoped
    one is refused any centre outside its grant.

    The refusal is **403, not 404** — and that is a deliberate departure from
    the cross-tenant rule. Another organization's centre must not be shown to
    exist, because its existence is itself private. A centre in your OWN
    organization is not a secret from you: you can see it on the centres list,
    your colleagues work there, and pretending it does not exist would send an
    operator hunting for a typo instead of telling them the truth, which is
    that they are not assigned to it.
    """

    async def guard(
        request: Request,
        principal: CurrentPrincipal,
        engine: Annotated[PermissionEngine, Depends(get_permission_engine)],
        session: Session,
    ) -> Principal:
        raw = request.path_params.get(param) or request.query_params.get(param)
        if raw is None:
            return principal
        try:
            center_id = uuid.UUID(str(raw))
        except ValueError:
            return principal  # malformed — the route's own validation answers
        scope = await engine.center_scope(principal.id, principal.tenant_id)
        if scope is None or center_id in scope:
            return principal

        from platform_core.core.security_audit import PERMISSION_DENIED, record_security_event

        await record_security_event(
            session,
            action=PERMISSION_DENIED,
            subject=f"center:{center_id}",
            actor_id=principal.id,
            detail={
                "reason": "center_out_of_scope",
                "tenant_id": str(principal.tenant_id) if principal.tenant_id else None,
            },
        )
        await session.commit()
        AUTHZ_DENIALS.labels("center.scope").inc()
        raise ForbiddenError("this centre is outside your assigned scope")

    return guard


def require_permission(permission: str):
    """Route guard: Depends(require_permission('audit.read'))."""

    async def guard(
        principal: CurrentPrincipal,
        engine: Annotated[PermissionEngine, Depends(get_permission_engine)],
        session: Session,
    ) -> Principal:
        if not await engine.check(principal.id, principal.tenant_id, permission):
            # SEC-001: a denial is a security event. Privilege-escalation
            # attempts are invisible unless the refusals are recorded.
            from platform_core.core.security_audit import PERMISSION_DENIED, record_security_event

            await record_security_event(
                session,
                action=PERMISSION_DENIED,
                subject=permission,
                actor_id=principal.id,
                detail={"tenant_id": str(principal.tenant_id) if principal.tenant_id else None},
            )
            await session.commit()
            AUTHZ_DENIALS.labels(permission).inc()
            raise ForbiddenError(permission)
        return principal

    return guard
