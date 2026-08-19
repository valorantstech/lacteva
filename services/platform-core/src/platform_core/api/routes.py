"""API routers for all platform modules (OpenAPI-tagged, /v1 prefix)."""

import uuid
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from platform_core.api import deps
from platform_core.api.deps import (
    CurrentPrincipal,
    Principal,
    get_business_calendar_service,
    require_center_access,
    require_permission,
)
from platform_core.api.idempotent_route import IdempotentRoute, idempotency_guard
from platform_core.api.transactional_route import TransactionalRoute
from platform_core.core import alerts, health, rate_limit, security_audit
from platform_core.core.backup.service import (
    BackupRunView,
    BackupStatusView,
    ClassificationView,
)
from platform_core.core.business_time import business_today, month_bounds
from platform_core.core.db import as_utc
from platform_core.core.errors import (
    AppError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from platform_core.core.http_security import client_ip
from platform_core.core.keys import get_key_registry
from platform_core.core.locales import country_choices, currency_symbol, language_choices
from platform_core.core.org_context import tenant_timezone
from platform_core.core.security_audit import record_security_event
from platform_core.core.tenancy import require_current_tenant
from platform_core.core.tenant_lifecycle import TenantLifecycleService
from platform_core.modules.audit.service import AuditPage
from platform_core.modules.auth.service import AuthService, LoginCommand, TokenPair
from platform_core.modules.authz.permissions import PERMISSIONS
from platform_core.modules.authz.service import AuthzService, PermissionEngine
from platform_core.modules.billing.service import (
    BillingService,
    CustomerBalanceView,
    CustomerPaymentDetailView,
    CustomerPaymentPage,
    CustomerPaymentView,
    CustomerStatement,
    GenerateInvoiceCommand,
    InvoiceDetailView,
    InvoicePage,
    InvoiceView,
    RecordCustomerPaymentCommand,
)
from platform_core.modules.business_calendar.service import (
    BusinessCalendarService,
    CalendarDayInput,
    CalendarDayView,
    CalendarView,
    FinancialPeriodInput,
    FinancialPeriodView,
    centre_exception_is_working,
    resolve_working_day,
)
from platform_core.modules.collection_center.service import (
    CalendarEntryInput,
    CalendarEntryView,
    CenterDetailView,
    CenterPage,
    CenterView,
    CollectionCenterService,
    CreateCenterCommand,
    OperatingWindowInput,
    OperatingWindowView,
    UpdateCenterCommand,
)
from platform_core.modules.configuration.service import ConfigurationService
from platform_core.modules.customer.service import (
    CreateCustomerCommand,
    CustomerDetailView,
    CustomerImportRowResult,
    CustomerPage,
    CustomerService,
    CustomerView,
    DeliveryPlanInput,
    DeliveryPlanView,
    PausePlanCommand,
    UpdateCustomerCommand,
)
from platform_core.modules.delivery.export import filename as export_filename
from platform_core.modules.delivery.export import to_csv
from platform_core.modules.delivery.generation import GenerationResult
from platform_core.modules.delivery.service import (
    AmendDeliveryCommand,
    DeliveryPage,
    DeliveryReport,
    DeliveryService,
    DeliveryView,
    GenerationRunView,
    RecordDeliveryCommand,
    RouteMembership,
)
from platform_core.modules.event_relay.consumers import (
    ConsumerRunner,
    ConsumersHealth,
    ConsumerStatus,
    ExecutionView,
)
from platform_core.modules.event_relay.projections import (
    ProjectionRebuilder,
    ProjectionStatus,
    RebuildResult,
    ResetResult,
    VerificationResult,
)
from platform_core.modules.event_relay.service import (
    DeadLetterView,
    OutboxEventView,
    RelayService,
    RelayStats,
)
from platform_core.modules.identity.schemas import RegisterUserCommand, UserView
from platform_core.modules.identity.service import IdentityService
from platform_core.modules.logistics.service import (
    DriverInput,
    DriverUserLink,
    DriverView,
    LogisticsService,
    RouteDetailView,
    RouteInput,
    RouteStopsInput,
    RouteView,
    RunAssignment,
    RunGenerationView,
    RunInput,
    RunStatusInput,
    RunStopView,
    RunView,
    StopOutcomeInput,
    VehicleInput,
    VehicleView,
    route_memberships,
)
from platform_core.modules.milk_collection.service import (
    IdentifySupplierCommand,
    MilkCollectionService,
    MilkInfoCommand,
    QualityCommand,
    RejectCommand,
    SessionPage,
    SessionView,
    SlipView,
    TransactionEventView,
    TransactionPage,
    TransactionView,
    WeightCommand,
)
from platform_core.modules.notification import receipts as receipt_processing
from platform_core.modules.notification.providers import ReceiptVerificationError
from platform_core.modules.notification.reachability import (
    ReachabilityService,
    ReachabilitySummaryView,
)
from platform_core.modules.notification.receipts import UnknownReceiptProvider
from platform_core.modules.notification.service import (
    ApprovalCommand,
    ApprovalView,
    MessagingPosture,
    NotificationPage,
    NotificationService,
    NotificationStats,
    NotificationView,
    PushDeviceView,
    RegisterPushDeviceCommand,
    RenderedPreview,
    TemplateRegistryView,
    TemplateView,
)
from platform_core.modules.operational_readiness.models import DEVICE_CATEGORIES
from platform_core.modules.operational_readiness.service import (
    READINESS_RULES,
    DeviceDetailView,
    DevicePage,
    DeviceView,
    OperationalReadinessService,
    OperatorView,
    ReadinessResult,
    RegisterDeviceCommand,
)
from platform_core.modules.organization.service import (
    BranchView,
    CreateOrganizationCommand,
    InvitationService,
    LocaleSettingsView,
    MembershipService,
    OrganizationService,
    OrganizationView,
    StructureService,
    UpdateLocaleSettingsCommand,
    WorkspaceView,
)
from platform_core.modules.payment.service import (
    BalancePage,
    CancelPaymentCommand,
    CompletePaymentCommand,
    CreatePaymentCommand,
    ExecutePaymentCommand,
    FailPaymentCommand,
    PaymentDetailView,
    PaymentPage,
    PaymentService,
    PaymentView,
    SettlementBalanceView,
)
from platform_core.modules.pricing.calculator import (
    CalculationRequest,
    CalculationResult,
    PricingCalculationService,
)
from platform_core.modules.pricing.matrix import (
    CreateMatrixCommand,
    DimensionInput,
    DimensionView,
    MatrixDetailView,
    MatrixPage,
    MatrixView,
    PricingMatrixService,
    RowInput,
    RowView,
    UpdateMatrixCommand,
)
from platform_core.modules.pricing.resolution import (
    PricingResolutionService,
    ResolutionQuery,
    ResolutionResult,
)
from platform_core.modules.pricing.service import (
    AssignProductCommand,
    CreateRateCardCommand,
    RateCardDetailView,
    RateCardInput,
    RateCardPage,
    RateCardService,
    RateCardView,
)
from platform_core.modules.receipt.service import (
    ReceiptDetailView,
    ReceiptPage,
    ReceiptService,
    ReceiptView,
    RenderedReceiptView,
)
from platform_core.modules.reporting.service import (
    CollectionChain,
    CollectionTrend,
    DailyCollectionSummary,
    DashboardSummary,
    OperationalStatusPage,
    PaymentSummary,
    PricingSummary,
    RateBandRow,
    ReceivablesPage,
    ReportingService,
    SalesSummary,
    SettlementSummary,
    SummaryPage,
)
from platform_core.modules.settlement.service import (
    AddCalculationCommand,
    CreateSettlementCommand,
    SettlementDetailView,
    SettlementLineView,
    SettlementPage,
    SettlementService,
    SettlementView,
)
from platform_core.modules.subscription import webhooks as webhook_processing
from platform_core.modules.subscription.billing import (
    QuoteView,
    SubscriptionBillingService,
    SubscriptionPaymentView,
)
from platform_core.modules.subscription.providers import (
    PaymentProviderUnavailable,
    WebhookVerificationError,
)
from platform_core.modules.subscription.service import (
    EntitlementView,
    SubscriptionService,
    SubscriptionView,
)
from platform_core.modules.supplier.service import (
    AddBankAccountCommand,
    BankAccountView,
    CreateSupplierCommand,
    DocumentView,
    ImportRowResult,
    SupplierDetailView,
    SupplierPage,
    SupplierProfileInput,
    SupplierService,
    SupplierView,
    UploadDocumentCommand,
    qr_payload_for,
)
from platform_core.modules.sync.service import (
    SyncBatchInput,
    SyncBatchResult,
    SyncOperationPage,
    SyncOperationView,
    SyncService,
    SyncStatsView,
)

# IDM-001: one line covers all 177 operations, and a new endpoint is covered
# by existing. The guard reserves the key inside the request's transaction;
# the route class records the response into the same one.
router = APIRouter(
    prefix="/v1",
    route_class=IdempotentRoute,
    dependencies=[Depends(idempotency_guard)],
)

# --- Public key discovery (SEC-001) -----------------------------------------
# Unauthenticated by design: the JWKS document is public key material, and a
# resource server must be able to fetch it without already holding a token.
wellknown = APIRouter(tags=["security"], route_class=IdempotentRoute)


@wellknown.get("/.well-known/jwks.json")
async def jwks() -> dict:
    """Public keys for verifying platform tokens (RFC 7517).

    Only ACTIVE keys appear: a retired or expired key must never be presented
    as trustworthy. Rotation is therefore visible here first — a new kid shows
    up before any token carries it."""
    return get_key_registry().jwks()


security_router = APIRouter(prefix="/_security", tags=["security"], route_class=IdempotentRoute)
SecurityAdmin = Annotated[Principal, Depends(require_permission("platform.security.manage"))]


@security_router.get("/keys")
async def list_signing_keys(_: SecurityAdmin) -> list[dict]:
    """Registry status for operators — kid, window, and which key signs.
    Private material is never returned, by construction."""
    return get_key_registry().describe()


# --- Authentication -------------------------------------------------------
auth = APIRouter(prefix="/auth", tags=["auth"], route_class=IdempotentRoute)


@auth.post("/register", response_model=UserView, status_code=201)
async def register(
    cmd: RegisterUserCommand,
    identity: Annotated[IdentityService, Depends(deps.get_identity_service)],
) -> Any:
    """Public self-registration (platform-level user, no tenant).

    TODO(M1): org-scoped users join via invitation flow; this endpoint then
    gains rate limiting + email verification before production exposure.
    """
    return await identity.register_user(cmd, tenant_id=None)


@auth.post("/token", response_model=TokenPair)
async def login(
    cmd: LoginCommand,
    request: Request,
    service: Annotated[AuthService, Depends(deps.get_auth_service)],
    session: deps.Session,
) -> TokenPair:
    """Rate limited per-IP AND per-identifier: one host hammering many
    accounts (credential stuffing) and many hosts hammering one account
    (distributed brute force) are different attacks and neither is caught by
    a purely per-IP budget."""
    ip = client_ip(request)
    await rate_limit.enforce(rate_limit.LOGIN, ip=ip, user=None, endpoint="login")
    await rate_limit.enforce(
        rate_limit.LOGIN_PER_USER,
        ip=ip,
        user=cmd.email.lower(),
        # MT-001: an email is unique per tenant, not globally. Without this,
        # one tenant's failed logins spend another tenant's budget for the
        # same address.
        tenant=str(cmd.tenant_id) if cmd.tenant_id else None,
        endpoint="login",
    )
    try:
        pair = await service.login(cmd)
    except AppError:
        # A failed login is a security event whether or not the account
        # exists — and the response still must not reveal which.
        await record_security_event(
            session,
            action=security_audit.LOGIN_FAILED,
            subject=cmd.email.lower(),
            detail={"ip": ip},
        )
        await session.commit()
        raise
    await record_security_event(
        session,
        action=security_audit.LOGIN_SUCCEEDED,
        subject=cmd.email.lower(),
        detail={"ip": ip},
    )
    return pair


class RefreshRequest(BaseModel):
    refresh_token: str


@auth.post("/refresh", response_model=TokenPair)
async def refresh(
    body: RefreshRequest,
    request: Request,
    service: Annotated[AuthService, Depends(deps.get_auth_service)],
    session: deps.Session,
) -> TokenPair:
    ip = client_ip(request)
    await rate_limit.enforce(rate_limit.REFRESH, ip=ip, user=None, endpoint="refresh")
    pair = await service.refresh(body.refresh_token)
    await record_security_event(
        session, action=security_audit.TOKEN_REFRESHED, subject="refresh", detail={"ip": ip}
    )
    return pair


@auth.post("/logout", status_code=204)
async def logout(
    principal: CurrentPrincipal,
    service: Annotated[AuthService, Depends(deps.get_auth_service)],
    session: deps.Session,
) -> None:
    await service.logout(principal.session_id, actor_id=principal.id)
    await record_security_event(
        session,
        action=security_audit.LOGOUT,
        subject=str(principal.session_id),
        actor_id=principal.id,
    )


class PasswordResetRequest(BaseModel):
    email: str
    tenant_id: uuid.UUID | None = None


@auth.post("/password-reset/request", status_code=202)
async def request_password_reset(
    body: PasswordResetRequest,
    request: Request,
    service: Annotated[AuthService, Depends(deps.get_auth_service)],
    session: deps.Session,
) -> dict:
    """Always 202 — never reveals whether the account exists. Delivery via
    the notification channel (logging adapter until M2)."""
    ip = client_ip(request)
    await rate_limit.enforce(rate_limit.PASSWORD_RESET, ip=ip, user=None, endpoint="password-reset")
    await service.request_password_reset(body.email, body.tenant_id)
    await record_security_event(
        session,
        action=security_audit.PASSWORD_RESET_REQUESTED,
        subject=body.email.lower(),
        detail={"ip": ip},
    )
    return {"status": "accepted"}


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(min_length=10, max_length=128)


@auth.post("/password-reset/confirm", status_code=204)
async def confirm_password_reset(
    body: PasswordResetConfirm,
    request: Request,
    service: Annotated[AuthService, Depends(deps.get_auth_service)],
    session: deps.Session,
) -> None:
    await rate_limit.enforce(
        rate_limit.PASSWORD_RESET, ip=client_ip(request), user=None, endpoint="password-reset"
    )
    await service.confirm_password_reset(body.token, body.new_password)
    await record_security_event(
        session, action=security_audit.PASSWORD_RESET_COMPLETED, subject="reset-confirm"
    )


class MeOrganization(BaseModel):
    """The organization, INCLUDING its locale context (DEMO-013).

    Carried on `/v1/auth/me` deliberately: every client — the portal, the
    mobile app, anything later — needs the currency to render money, the
    timezone to render a date, and the language list to offer a choice. Any
    client holding its own copy of those would be a second answer to a
    question the platform has already answered, and the two would disagree the
    first time a dairy changed one.

    It also means the mobile app caches localization with the session it
    already caches (§13), rather than needing a separate call it cannot make
    offline.
    """

    id: uuid.UUID
    name: str
    slug: str
    country_code: str
    currency_code: str
    currency_symbol: str
    timezone: str
    default_language: str
    supported_languages: list[str]
    languages: list[dict]


class MeMembership(BaseModel):
    status: str
    joined_at: datetime


class MeRole(BaseModel):
    name: str
    description: str
    #: The centre this particular grant is limited to, or null for the whole
    #: organization. The same role can be held at different scopes.
    center_id: uuid.UUID | None


class MeView(BaseModel):
    """The authorization context the portal renders from (DEMO-008 §13).

    It carries what the caller needs to decide what to SHOW, and nothing that
    would help anybody log in as them: no password hash, no session id, no
    token, no refresh material. `UserView` has never included the hash and
    still does not.

    Everything here is derived from the database at request time — the same
    resolution `require_permission` uses — so the portal cannot come to believe
    in a permission the backend would refuse.
    """

    user: UserView
    tenant_id: uuid.UUID | None
    organization: MeOrganization | None
    membership: MeMembership | None
    roles: list[MeRole]
    #: Centres this principal may act at; null means the whole organization.
    center_scope: list[uuid.UUID] | None
    permissions: list[str]
    #: DEMO-012 — the customer this login speaks for, or null for staff.
    #:
    #: A client needs it to decide WHICH EXPERIENCE to open; it is not a
    #: security control here. The platform narrows every sales query to this
    #: customer server-side (`core/tenancy.enforce_customer_scope`), so a
    #: client that ignored this field would still be shown nothing else.
    customer_id: uuid.UUID | None = None


class SetLanguageRequest(BaseModel):
    """A BCP-47 tag the organization has enabled."""

    language: str = Field(min_length=2, max_length=16)


@auth.put("/me/language", response_model=UserView)
async def set_my_language(
    body: SetLanguageRequest,
    principal: CurrentPrincipal,
    identity: deps.Identity,
) -> Any:
    """Choose your own language (DEMO-013 §5).

    Any authenticated principal may change their OWN language and nobody
    else's — the user id comes from the token, never from the body. It needs
    no permission: a language is a personal preference, and gating it behind
    an administrative grant would mean a collection operator had to file a
    ticket to read their own screen in Hindi.

    The organization still decides which languages exist; the service refuses
    anything outside `supported_languages` with a 403.
    """
    return await identity.set_language(principal.id, body.language)


class SetTimezoneRequest(BaseModel):
    """An IANA zone, or null for the organization's."""

    timezone: str | None = Field(default=None, max_length=64)


@auth.put("/me/timezone", response_model=UserView)
async def set_my_timezone(
    body: SetTimezoneRequest,
    principal: CurrentPrincipal,
    identity: deps.Identity,
) -> Any:
    """Choose the clock you read timestamps in (DEMO-014 §4).

    Display only, and needs no permission for the same reason a language does
    not: it changes nothing for anybody else. It cannot move a business date —
    reports, billing periods and delivery days are measured on the
    ORGANIZATION's clock, which this does not touch.
    """
    return await identity.set_timezone(principal.id, body.timezone)


@auth.get("/me", response_model=MeView)
async def me(
    principal: CurrentPrincipal,
    engine: Annotated[PermissionEngine, Depends(deps.get_permission_engine)],
    session: deps.Session,
) -> MeView:
    from platform_core.modules.authz.models import Role, UserRole
    from platform_core.modules.organization.models import Membership, Organization

    perms = await engine.effective_permissions(principal.id, principal.tenant_id)

    organization = None
    membership = None
    if principal.tenant_id is not None:
        org = await session.get(Organization, principal.tenant_id)
        if org is not None:
            organization = MeOrganization(
                id=org.id,
                name=org.name,
                slug=org.slug,
                country_code=org.country_code,
                currency_code=org.currency_code,
                currency_symbol=currency_symbol(org.currency_code),
                timezone=org.timezone,
                default_language=org.default_locale,
                supported_languages=list(org.supported_languages or ["en"]),
                languages=language_choices(list(org.supported_languages or ["en"])),
            )
        row = await session.scalar(
            select(Membership).where(
                Membership.tenant_id == principal.tenant_id,
                Membership.user_id == principal.id,
            )
        )
        if row is not None:
            membership = MeMembership(status=row.status, joined_at=as_utc(row.joined_at))

    granted = (
        await session.execute(
            select(Role, UserRole.center_id)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(
                UserRole.user_id == principal.id,
                (UserRole.tenant_id == principal.tenant_id) | (UserRole.tenant_id.is_(None)),
            )
            .order_by(Role.name)
        )
    ).all()
    scope = await engine.center_scope(principal.id, principal.tenant_id)

    return MeView(
        user=UserView.model_validate(principal.user),
        tenant_id=principal.tenant_id,
        organization=organization,
        membership=membership,
        roles=[
            MeRole(name=role.name, description=role.description, center_id=center_id)
            for role, center_id in granted
        ],
        center_scope=sorted(scope) if scope is not None else None,
        permissions=sorted(perms),
        customer_id=principal.customer_id,
    )


# --- Identity -------------------------------------------------------------
identity_router = APIRouter(prefix="/identity", tags=["identity"], route_class=IdempotentRoute)


@identity_router.get("/users/{user_id}", response_model=UserView)
async def get_user(
    user_id: uuid.UUID,
    identity: Annotated[IdentityService, Depends(deps.get_identity_service)],
    _: Annotated[Principal, Depends(require_permission("identity.user.read"))],
) -> Any:
    return await identity.get_user(user_id)


class UserActiveRequest(BaseModel):
    """SEC-003 / F-02. A desired end state, not a verb, so the same request
    twice is the same answer twice — an administrator disabling an account
    twice has not made a mistake worth a 409."""

    is_active: bool
    #: Free-text note for the access review that reads this later. Recorded in
    #: the audit entry; never used to make a decision.
    reason: str | None = Field(default=None, max_length=200)


@identity_router.post("/users/{user_id}/status", response_model=UserView)
async def set_user_status(
    user_id: uuid.UUID,
    body: UserActiveRequest,
    auth_service: Annotated[AuthService, Depends(deps.get_auth_service)],
    principal: Annotated[Principal, Depends(require_permission("identity.user.manage"))],
) -> Any:
    """Deactivate or reactivate a user, and settle their live sessions.

    Goes through the AUTH service rather than identity directly: deactivating
    a user without revoking their refresh tokens leaves them able to mint
    fresh access tokens from a session nobody re-checked.
    """
    return await auth_service.set_user_active(
        user_id,
        active=body.is_active,
        actor_id=principal.id,
        tenant_id=principal.tenant_id,
    )


# --- Organizations --------------------------------------------------------
org_router = APIRouter(prefix="/organizations", tags=["organizations"], route_class=IdempotentRoute)


@org_router.post("", response_model=OrganizationView, status_code=201)
async def create_organization(
    cmd: CreateOrganizationCommand,
    service: Annotated[OrganizationService, Depends(deps.get_organization_service)],
    principal: Annotated[Principal, Depends(require_permission("organization.manage"))],
) -> Any:
    return await service.create_organization(cmd, actor_id=principal.id)


@org_router.get("/{org_id}", response_model=OrganizationView)
async def get_organization(
    org_id: uuid.UUID,
    service: Annotated[OrganizationService, Depends(deps.get_organization_service)],
    _: Annotated[Principal, Depends(require_permission("organization.read"))],
) -> Any:
    return await service.get_organization(org_id)


# --- Organization locale settings (DEMO-013 §2, §12) -------------------------
#
# Guarded by the permissions DEMO-008 already registered: `organization.read`
# to see the settings, `organization.manage` to change them. No new
# authorization mechanism — the whole point of a registry is that a new screen
# is a new grant, not a new gate.


@org_router.get("/settings/locale", response_model=LocaleSettingsView)
async def get_locale_settings(
    service: Annotated[OrganizationService, Depends(deps.get_organization_service)],
    _: Annotated[Principal, Depends(require_permission("organization.read"))],
) -> Any:
    """This organization's country, currency, timezone and languages."""
    return await service.locale_settings()


@org_router.put("/settings/locale", response_model=LocaleSettingsView)
async def update_locale_settings(
    cmd: UpdateLocaleSettingsCommand,
    service: Annotated[OrganizationService, Depends(deps.get_organization_service)],
    principal: Annotated[Principal, Depends(require_permission("organization.settings.manage"))],
) -> Any:
    """Change the money, the clock or the languages. Country is not settable
    here — see `UpdateLocaleSettingsCommand`."""
    return await service.update_locale_settings(cmd, actor_id=principal.id)


# --- Locale reference data ---------------------------------------------------


locale_router = APIRouter(prefix="/locales", tags=["locales"], route_class=TransactionalRoute)


@locale_router.get("/countries")
async def list_countries(_: CurrentPrincipal) -> Any:
    """What each country implies, for an onboarding form to propose from.

    Served rather than shipped so the portal and the mobile app offer the same
    countries without either holding a copy that can drift. Authenticated
    because it is not public information about this deployment, and free of
    anything tenant-specific.
    """
    return {"countries": country_choices()}


# --- Subscription, trial and entitlement (DEMO-026) ------------------------
#
# Read is a tenant-administrator act; CHANGE is a Lacteva-operator one. Until a
# payment provider exists, the only truthful way for an organization to become
# `active` is for somebody at Lacteva to say so — so `manage` sits behind its
# own permission that no tenant role holds.
#
# Nothing here accepts a status from the caller. There is no endpoint that
# takes `status`, which is how "the client cannot forge a subscription state"
# is guaranteed rather than validated.
subscription_router = APIRouter(
    prefix="/organization", tags=["subscription"], route_class=TransactionalRoute
)


class ActivateSubscriptionRequest(BaseModel):
    plan_code: str
    subscribed_centres: int
    period_end: date | None = None


@subscription_router.get(
    "/subscription",
    dependencies=[Depends(require_permission("organization.subscription.read"))],
)
async def read_subscription(
    service: Annotated[SubscriptionService, Depends(deps.get_subscription_service)],
) -> SubscriptionView:
    """This organization's plan, trial dates and commercial standing."""
    return await service.view()


@subscription_router.get(
    "/entitlement",
    dependencies=[Depends(require_permission("organization.subscription.read"))],
)
async def read_entitlement(
    service: Annotated[SubscriptionService, Depends(deps.get_subscription_service)],
) -> EntitlementView:
    """What the organization may commercially do, and how many centres it uses."""
    return await service.entitlement_view()


@subscription_router.post(
    "/subscription/activate",
    dependencies=[Depends(require_permission("organization.subscription.manage"))],
)
async def activate_subscription(
    service: Annotated[SubscriptionService, Depends(deps.get_subscription_service)],
    body: ActivateSubscriptionRequest,
) -> SubscriptionView:
    """Put this organization onto a paid plan. **No money moves.**"""
    return await service.activate(
        plan_code=body.plan_code,
        subscribed_centres=body.subscribed_centres,
        period_end=body.period_end,
    )


@subscription_router.post(
    "/subscription/cancel",
    dependencies=[Depends(require_permission("organization.subscription.manage"))],
)
async def cancel_subscription(
    service: Annotated[SubscriptionService, Depends(deps.get_subscription_service)],
) -> SubscriptionView:
    return await service.cancel()


# --- Subscription payment (DEMO-027) --------------------------------------
#
# What a client may send is deliberately tiny: a plan code and a number of
# collection centres. No amount, no currency, no status, no payment id, no
# provider reference. Everything else is the server's, because every one of
# those fields is a way to pay less than the price or to become active without
# paying at all.


class CheckoutRequestBody(BaseModel):
    plan_code: str
    #: Collection centres to subscribe for. The ONLY number a customer chooses.
    subscribed_centres: int


@subscription_router.get(
    "/subscription/quote",
    dependencies=[Depends(require_permission("organization.subscription.read"))],
)
async def quote_subscription(
    billing: Annotated[SubscriptionBillingService, Depends(deps.get_subscription_billing_service)],
    plan_code: str,
    subscribed_centres: int,
) -> QuoteView:
    """What a subscription would cost. Calculated here, never sent by a client."""
    return await billing.quote(plan_code=plan_code, quantity=subscribed_centres)


@subscription_router.post(
    "/subscription/checkout",
    dependencies=[Depends(require_permission("organization.subscription.pay"))],
)
async def start_subscription_checkout(
    billing: Annotated[SubscriptionBillingService, Depends(deps.get_subscription_billing_service)],
    body: CheckoutRequestBody,
) -> SubscriptionPaymentView:
    """Open a checkout with the configured provider.

    Refuses plainly when no gateway is contracted or no price is published —
    both are things an administrator can act on, and neither improves by being
    retried.
    """
    return await billing.start_checkout(plan_code=body.plan_code, quantity=body.subscribed_centres)


@subscription_router.post(
    "/subscription/checkout/refresh",
    dependencies=[Depends(require_permission("organization.subscription.pay"))],
)
async def refresh_subscription_checkout(
    billing: Annotated[SubscriptionBillingService, Depends(deps.get_subscription_billing_service)],
) -> SubscriptionPaymentView:
    """Ask the PROVIDER what happened to the open payment.

    Takes no arguments on purpose. A browser returning from a hosted checkout
    is a hint that something may have changed, not evidence of what — so the
    most it can say is "look again". It cannot name a payment, an amount or a
    status.
    """
    return await billing.refresh_open_payment()


@subscription_router.post(
    "/subscription/checkout/cancel",
    dependencies=[Depends(require_permission("organization.subscription.pay"))],
)
async def cancel_subscription_checkout(
    billing: Annotated[SubscriptionBillingService, Depends(deps.get_subscription_billing_service)],
) -> SubscriptionPaymentView:
    return await billing.cancel_open_payment()


@subscription_router.get(
    "/subscription/payments",
    dependencies=[Depends(require_permission("organization.subscription.read"))],
)
async def list_subscription_payments(
    billing: Annotated[SubscriptionBillingService, Depends(deps.get_subscription_billing_service)],
) -> list[SubscriptionPaymentView]:
    """This organization's own subscription payments. Never anyone else's."""
    return await billing.history()


# --- The provider webhook (DEMO-027) --------------------------------------
#
# Its own router with NO idempotency route class and NO authentication
# dependency, both deliberately.
#
# Not `IdempotentRoute`, because that keys on a client-supplied
# `Idempotency-Key` header and a payment gateway sends its own event id
# instead — de-duplication belongs on that id, in the database, where a replay
# cannot slip past a header nobody sent.
#
# Not authenticated, because a gateway has no Lacteva account. What replaces
# authentication is a signature over the raw body, checked in constant time
# against a secret that exists only in deployment configuration.
webhook_router = APIRouter(
    prefix="/payments", tags=["subscription"], route_class=TransactionalRoute
)


@webhook_router.post("/webhooks/{provider}", status_code=200)
async def receive_payment_webhook(provider: str, request: Request) -> dict[str, str]:
    """Accept one provider notification.

    Returns 200 for anything it has correctly handled — INCLUDING a replay and
    an unknown reference. That is deliberate: a gateway reads a non-2xx as
    "retry", and asking it to redeliver an event that was already applied, or
    one about a payment this platform has never heard of, achieves nothing and
    eventually pages somebody.

    401 and 404 say only that the request was refused, never which check
    refused it.
    """
    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    try:
        result = await webhook_processing.process_webhook(
            provider_name=provider, body=body, headers=headers
        )
    except WebhookVerificationError as exc:
        raise UnauthorizedError("webhook rejected") from exc
    except PaymentProviderUnavailable as exc:
        raise NotFoundError("unknown payment provider") from exc
    return {"outcome": result.outcome}


# --- Business calendar and financial periods (DEMO-020) -------------------
#
# Only what a caller can actually act on. The business-date MACHINERY is not
# exposed — no endpoint converts an arbitrary instant, and none accepts a
# timezone, because a client that could name the zone could name the wrong one
# and the whole point is that the organization's clock is not negotiable.
calendar_router = APIRouter(
    prefix="/organization", tags=["business-calendar"], route_class=TransactionalRoute
)


@calendar_router.get(
    "/calendar", dependencies=[Depends(require_permission("organization.calendar.read"))]
)
async def organization_calendar(
    service: Annotated[BusinessCalendarService, Depends(get_business_calendar_service)],
    centers: Annotated[CollectionCenterService, Depends(deps.get_collection_center_service)],
    center_id: uuid.UUID | None = None,
) -> CalendarView:
    """What day it is for this dairy, and which month and period that falls in.

    With `center_id`, the centre's own exception overrides the organization's
    for that day (DEMO-021 §2). The two services are composed HERE, in the
    composition root, so neither reads the other's tables: the centre service
    is asked for the centre's opinion, the calendar service for the
    organization's, and `resolve_working_day` decides between them.

    A user's display timezone is not a parameter of any of it.
    """
    view = await service.overview()
    if center_id is None:
        return view
    kind = await centers.calendar_exception(center_id, view.business_date)
    centre_opinion = None if kind is None else centre_exception_is_working(kind)
    return view.model_copy(
        update={
            "is_working_day": resolve_working_day(
                organization=await service.organization_exception(view.business_date),
                centre=centre_opinion,
            )
        }
    )


@calendar_router.get(
    "/calendar/days", dependencies=[Depends(require_permission("organization.calendar.read"))]
)
async def list_calendar_days(
    service: Annotated[BusinessCalendarService, Depends(get_business_calendar_service)],
    date_from: date,
    date_to: date,
) -> list[CalendarDayView]:
    return await service.calendar_days(date_from, date_to)


@calendar_router.put(
    "/calendar/days", dependencies=[Depends(require_permission("organization.calendar.manage"))]
)
async def set_calendar_day(
    service: Annotated[BusinessCalendarService, Depends(get_business_calendar_service)],
    principal: CurrentPrincipal,
    payload: CalendarDayInput,
) -> CalendarDayView:
    """PUT, not POST: a day either is or is not an exception, and saying so
    twice must mean the same as saying it once."""
    return await service.set_calendar_day(payload, actor_id=principal.id)


@calendar_router.delete(
    "/calendar/days/{day}",
    status_code=204,
    dependencies=[Depends(require_permission("organization.calendar.manage"))],
)
async def remove_calendar_day(
    service: Annotated[BusinessCalendarService, Depends(get_business_calendar_service)],
    day: date,
) -> None:
    await service.remove_calendar_day(day)


@calendar_router.get(
    "/financial-periods",
    dependencies=[Depends(require_permission("organization.calendar.read"))],
)
async def list_financial_periods(
    service: Annotated[BusinessCalendarService, Depends(get_business_calendar_service)],
) -> list[FinancialPeriodView]:
    return await service.periods()


@calendar_router.post(
    "/financial-periods",
    status_code=201,
    dependencies=[Depends(require_permission("organization.period.manage"))],
)
async def open_financial_period(
    service: Annotated[BusinessCalendarService, Depends(get_business_calendar_service)],
    principal: CurrentPrincipal,
    payload: FinancialPeriodInput,
) -> FinancialPeriodView:
    return await service.open_period(payload, actor_id=principal.id)


@calendar_router.post(
    "/financial-periods/{period_id}/close",
    dependencies=[Depends(require_permission("organization.period.manage"))],
)
async def close_financial_period(
    service: Annotated[BusinessCalendarService, Depends(get_business_calendar_service)],
    principal: CurrentPrincipal,
    period_id: uuid.UUID,
) -> FinancialPeriodView:
    return await service.close_period(period_id, actor_id=principal.id)


@calendar_router.post(
    "/financial-periods/{period_id}/reopen",
    dependencies=[Depends(require_permission("organization.period.manage"))],
)
async def reopen_financial_period(
    service: Annotated[BusinessCalendarService, Depends(get_business_calendar_service)],
    principal: CurrentPrincipal,
    period_id: uuid.UUID,
) -> FinancialPeriodView:
    return await service.reopen_period(period_id, actor_id=principal.id)


# --- Organization structure (workspaces, branches) ------------------------
structure_router = APIRouter(tags=["organization-structure"], route_class=IdempotentRoute)


class CreateWorkspaceRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,78}[a-z0-9]$")


@structure_router.post("/workspaces", response_model=WorkspaceView, status_code=201)
async def create_workspace(
    body: CreateWorkspaceRequest,
    service: Annotated[StructureService, Depends(deps.get_structure_service)],
    principal: Annotated[Principal, Depends(require_permission("organization.structure.manage"))],
) -> Any:
    return await service.create_workspace(name=body.name, slug=body.slug, actor_id=principal.id)


@structure_router.get("/workspaces", response_model=list[WorkspaceView])
async def list_workspaces(
    service: Annotated[StructureService, Depends(deps.get_structure_service)],
    _: Annotated[Principal, Depends(require_permission("organization.structure.read"))],
) -> Any:
    return await service.list_workspaces()


class CreateBranchRequest(BaseModel):
    workspace_id: uuid.UUID
    name: str = Field(min_length=2, max_length=200)
    code: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}$")


@structure_router.post("/branches", response_model=BranchView, status_code=201)
async def create_branch(
    body: CreateBranchRequest,
    service: Annotated[StructureService, Depends(deps.get_structure_service)],
    principal: Annotated[Principal, Depends(require_permission("organization.structure.manage"))],
) -> Any:
    return await service.create_branch(
        workspace_id=body.workspace_id, name=body.name, code=body.code, actor_id=principal.id
    )


@structure_router.get("/branches", response_model=list[BranchView])
async def list_branches(
    service: Annotated[StructureService, Depends(deps.get_structure_service)],
    _: Annotated[Principal, Depends(require_permission("organization.structure.read"))],
) -> Any:
    return await service.list_branches()


# --- Members & invitations -------------------------------------------------
member_router = APIRouter(tags=["members"], route_class=IdempotentRoute)


class MemberStatusRequest(BaseModel):
    """An end state, not a verb — the same convention `UserActiveRequest`
    uses, so suspending an already-suspended member is not a 409."""

    status: str


@member_router.post("/members/{user_id}/status")
async def set_member_status(
    user_id: uuid.UUID,
    body: MemberStatusRequest,
    service: Annotated[MembershipService, Depends(deps.get_membership_service)],
    audit: Annotated[deps.AuditService, Depends(deps.get_audit_service)],
    session: deps.Session,
    principal: Annotated[Principal, Depends(require_permission("organization.member.manage"))],
) -> dict:
    """Suspend or reinstate a member (DEMO-008 §2, §14).

    A suspension takes effect on the member's NEXT request, not when their
    token expires — `get_current_principal` re-checks membership on every call.
    """
    membership = await service.set_status(user_id, body.status, actor_id=principal.id)
    await audit.record(
        action="organization.member.status_changed",
        resource_type="membership",
        resource_id=membership.id,
        actor_id=principal.id,
        detail={"user_id": str(user_id), "status": membership.status},
    )
    await session.commit()
    return {"user_id": str(user_id), "status": membership.status}


@member_router.get("/members")
async def list_members(
    service: Annotated[MembershipService, Depends(deps.get_membership_service)],
    session: deps.Session,
    principal: Annotated[Principal, Depends(require_permission("organization.member.read"))],
) -> list[dict]:
    """The organization's people, with what each of them may do.

    DEMO-008 §9: the roles come from the same `user_role` rows the permission
    engine reads, so the administration screen and the enforcement cannot
    disagree about who holds what. Two grouped queries for the whole list, not
    one per member.
    """
    from platform_core.modules.authz.models import Role, UserRole

    members = await service.list_members()
    user_ids = [m.user_id for m in members]
    by_user: dict[uuid.UUID, list[dict]] = {}
    if user_ids:
        for user_id, name, center_id in (
            await session.execute(
                select(UserRole.user_id, Role.name, UserRole.center_id)
                .join(Role, Role.id == UserRole.role_id)
                .where(
                    UserRole.user_id.in_(user_ids),
                    (UserRole.tenant_id == principal.tenant_id) | (UserRole.tenant_id.is_(None)),
                )
                .order_by(Role.name)
            )
        ).all():
            by_user.setdefault(user_id, []).append(
                {"name": name, "center_id": str(center_id) if center_id else None}
            )
    return [
        {
            "user_id": str(m.user_id),
            "status": m.status,
            "joined_at": m.joined_at.isoformat(),
            "roles": by_user.get(m.user_id, []),
        }
        for m in await service.list_members()
    ]


class InviteRequest(BaseModel):
    email: str
    role_name: str = "tenant-viewer"


@member_router.post("/invitations", status_code=201)
async def create_invitation(
    body: InviteRequest,
    service: Annotated[InvitationService, Depends(deps.get_invitation_service)],
    principal: Annotated[Principal, Depends(require_permission("organization.member.manage"))],
) -> dict:
    invitation, _raw_token = await service.invite(
        email=body.email, role_name=body.role_name, actor_id=principal.id
    )
    # SEC-003 / F-04: the raw token is NOT returned. It used to be, "until
    # real delivery lands" — which meant whoever issued the invitation could
    # accept it themselves and create an account under the invitee's email,
    # in the invitee's tenant, with the role they were being offered. The
    # token now reaches the invitee through the notification channel and
    # nowhere else. Everything below is non-secret metadata.
    return {
        "id": str(invitation.id),
        "email": invitation.email,
        "role_name": invitation.role_name,
        "status": "pending",
        "expires_at": invitation.expires_at.isoformat(),
    }


class AcceptInvitationRequest(BaseModel):
    token: str
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)


@member_router.post("/invitations/accept", response_model=UserView, status_code=201)
async def accept_invitation(
    body: AcceptInvitationRequest,
    request: Request,
    service: Annotated[InvitationService, Depends(deps.get_invitation_service)],
    identity: Annotated[IdentityService, Depends(deps.get_identity_service)],
    authz: Annotated[AuthzService, Depends(deps.get_authz_service)],
    membership: Annotated[MembershipService, Depends(deps.get_membership_service)],
) -> Any:
    """Public: how invited people join their organization."""
    await rate_limit.enforce(
        rate_limit.INVITATION_ACCEPT,
        ip=client_ip(request),
        user=None,
        endpoint="invitation-accept",
    )
    return await service.accept(
        token=body.token,
        password=body.password,
        full_name=body.full_name,
        identity=identity,
        authz=authz,
        membership=membership,
    )


# --- Collection centers (facility management only) -------------------------
center_router = APIRouter(
    prefix="/collection-centers", tags=["collection-centers"], route_class=IdempotentRoute
)
CenterManage = Annotated[Principal, Depends(require_permission("collection.center.manage"))]
CenterRead = Annotated[Principal, Depends(require_permission("collection.center.read"))]
CenterSvc = Annotated[CollectionCenterService, Depends(deps.get_collection_center_service)]


@center_router.post("", response_model=CenterView, status_code=201)
async def create_center(cmd: CreateCenterCommand, service: CenterSvc, p: CenterManage) -> Any:
    return await service.create(cmd, actor_id=p.id)


@center_router.get("", response_model=CenterPage)
async def list_centers(
    service: CenterSvc,
    p: CenterRead,
    engine: Annotated[PermissionEngine, Depends(deps.get_permission_engine)],
    q: str | None = None,
    status: str | None = None,
    branch_id: uuid.UUID | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> CenterPage:
    return await service.list_page(
        q=q,
        status=status,
        branch_id=branch_id,
        center_scope=await engine.center_scope(p.id, p.tenant_id),
        limit=limit,
        offset=offset,
    )


@center_router.get(
    "/{center_id}",
    response_model=CenterDetailView,
    dependencies=[Depends(require_center_access())],
)
async def get_center_detail(
    center_id: uuid.UUID, service: CenterSvc, _: CenterRead
) -> CenterDetailView:
    return await service.detail(center_id)


@center_router.put("/{center_id}", response_model=CenterView)
async def update_center(
    center_id: uuid.UUID, cmd: UpdateCenterCommand, service: CenterSvc, p: CenterManage
) -> Any:
    return await service.update(center_id, cmd, actor_id=p.id)


class SetStatusRequest(BaseModel):
    status: str


@center_router.post("/{center_id}/status", response_model=CenterView)
async def set_center_status(
    center_id: uuid.UUID, body: SetStatusRequest, service: CenterSvc, p: CenterManage
) -> Any:
    return await service.set_status(center_id, body.status, actor_id=p.id)


class SetConfigCenterRequest(BaseModel):
    settings: dict[str, Any]


@center_router.put("/{center_id}/config")
async def set_center_config(
    center_id: uuid.UUID, body: SetConfigCenterRequest, service: CenterSvc, p: CenterManage
) -> dict:
    settings = await service.set_config(center_id, body.settings, actor_id=p.id)
    return {"settings": settings}


class SetHoursRequest(BaseModel):
    windows: list[OperatingWindowInput]


@center_router.put("/{center_id}/operating-hours", response_model=list[OperatingWindowView])
async def set_center_hours(
    center_id: uuid.UUID, body: SetHoursRequest, service: CenterSvc, p: CenterManage
) -> Any:
    return await service.set_operating_hours(center_id, body.windows, actor_id=p.id)


@center_router.post("/{center_id}/calendar", response_model=CalendarEntryView, status_code=201)
async def add_center_calendar_entry(
    center_id: uuid.UUID, entry: CalendarEntryInput, service: CenterSvc, p: CenterManage
) -> Any:
    return await service.add_calendar_entry(center_id, entry, actor_id=p.id)


@center_router.delete("/{center_id}/calendar/{entry_id}", status_code=204)
async def remove_center_calendar_entry(
    center_id: uuid.UUID, entry_id: uuid.UUID, service: CenterSvc, p: CenterManage
) -> None:
    await service.remove_calendar_entry(center_id, entry_id, actor_id=p.id)


# --- Operational readiness (devices, operators, readiness engine) ----------
ops_router = APIRouter(tags=["operational-readiness"], route_class=IdempotentRoute)
DeviceManage = Annotated[Principal, Depends(require_permission("operations.device.manage"))]
DeviceRead = Annotated[Principal, Depends(require_permission("operations.device.read"))]
ReadinessRead = Annotated[Principal, Depends(require_permission("operations.readiness.read"))]
OpsSvc = Annotated[OperationalReadinessService, Depends(deps.get_readiness_service)]


@ops_router.get("/device-categories")
async def list_device_categories(_: DeviceRead) -> dict[str, dict]:
    return DEVICE_CATEGORIES


@ops_router.post("/devices", response_model=DeviceView, status_code=201)
async def register_device(cmd: RegisterDeviceCommand, service: OpsSvc, p: DeviceManage) -> Any:
    return await service.register_device(cmd, actor_id=p.id)


@ops_router.get("/devices", response_model=DevicePage)
async def list_devices(
    service: OpsSvc,
    _: DeviceRead,
    center_id: uuid.UUID | None = None,
    category: str | None = None,
    status: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> DevicePage:
    return await service.list_devices(
        center_id=center_id, category=category, status=status, limit=limit, offset=offset
    )


@ops_router.get("/devices/{device_id}", response_model=DeviceDetailView)
async def get_device_detail(
    device_id: uuid.UUID, service: OpsSvc, _: DeviceRead
) -> DeviceDetailView:
    return await service.device_detail(device_id)


class AssignDeviceRequest(BaseModel):
    center_id: uuid.UUID


@ops_router.post("/devices/{device_id}/assign", response_model=DeviceView)
async def assign_device(
    device_id: uuid.UUID, body: AssignDeviceRequest, service: OpsSvc, p: DeviceManage
) -> Any:
    return await service.assign_device(device_id, body.center_id, actor_id=p.id)


class DeviceStatusRequest(BaseModel):
    status: str


@ops_router.post("/devices/{device_id}/status", response_model=DeviceView)
async def set_device_status(
    device_id: uuid.UUID, body: DeviceStatusRequest, service: OpsSvc, p: DeviceManage
) -> Any:
    return await service.set_device_status(device_id, body.status, actor_id=p.id)


class HealthReportRequest(BaseModel):
    state: str
    note: str = ""


@ops_router.post("/devices/{device_id}/health", status_code=201)
async def report_device_health(
    device_id: uuid.UUID, body: HealthReportRequest, service: OpsSvc, p: DeviceManage
) -> dict:
    report = await service.report_health(device_id, body.state, body.note, actor_id=p.id)
    return {"id": str(report.id), "state": report.state}


class AssignOperatorRequest(BaseModel):
    user_id: uuid.UUID
    role_label: str = "operator"


@ops_router.post(
    "/collection-centers/{center_id}/operators",
    status_code=201,
    dependencies=[Depends(require_center_access())],
)
async def assign_operator(
    center_id: uuid.UUID, body: AssignOperatorRequest, service: OpsSvc, p: DeviceManage
) -> dict:
    a = await service.assign_operator(center_id, body.user_id, body.role_label, actor_id=p.id)
    return {"user_id": str(a.user_id), "role_label": a.role_label}


@ops_router.get(
    "/collection-centers/{center_id}/operators",
    response_model=list[OperatorView],
    dependencies=[Depends(require_center_access())],
)
async def list_operators(center_id: uuid.UUID, service: OpsSvc, _: DeviceRead) -> Any:
    return await service.list_operators(center_id)


@ops_router.delete("/collection-centers/{center_id}/operators/{user_id}", status_code=204)
async def remove_operator(
    center_id: uuid.UUID, user_id: uuid.UUID, service: OpsSvc, p: DeviceManage
) -> None:
    await service.remove_operator(center_id, user_id, actor_id=p.id)


@ops_router.get("/readiness/rules")
async def list_readiness_rules(_: ReadinessRead) -> dict[str, dict]:
    return READINESS_RULES


@ops_router.get(
    "/collection-centers/{center_id}/readiness",
    response_model=ReadinessResult,
    dependencies=[Depends(require_center_access())],
)
async def evaluate_center_readiness(
    center_id: uuid.UUID, service: OpsSvc, _: ReadinessRead
) -> ReadinessResult:
    """The Operational Status API: evaluates the center now, on demand."""
    return await service.evaluate_readiness(center_id)


# --- Suppliers -------------------------------------------------------------
supplier_router = APIRouter(prefix="/suppliers", tags=["suppliers"], route_class=IdempotentRoute)
SupplierManage = Annotated[Principal, Depends(require_permission("supplier.manage"))]
SupplierRead = Annotated[Principal, Depends(require_permission("supplier.read"))]
SupplierSvc = Annotated[SupplierService, Depends(deps.get_supplier_service)]


@supplier_router.post("", response_model=SupplierView, status_code=201)
async def create_supplier(
    cmd: CreateSupplierCommand, service: SupplierSvc, p: SupplierManage
) -> Any:
    supplier = await service.create(cmd, actor_id=p.id)
    return (await service.detail(supplier.id)).supplier


@supplier_router.get("", response_model=SupplierPage)
async def search_suppliers(
    service: SupplierSvc,
    _: SupplierRead,
    q: str | None = None,
    status: str | None = None,
    center_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    # P1-PORTAL-SCALE-001: `?ids=…&ids=…` — batch display-name resolution for
    # exactly the rows a page shows. Bounded at one page of the cap; a foreign
    # tenant's id matches nothing (the tenant filter narrows first).
    ids: Annotated[list[uuid.UUID] | None, Query(max_length=100)] = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> SupplierPage:
    return await service.search(
        q=q,
        status=status,
        center_id=center_id,
        branch_id=branch_id,
        ids=ids,
        limit=limit,
        offset=offset,
    )


@supplier_router.get("/{supplier_id}", response_model=SupplierDetailView)
async def get_supplier_detail(
    supplier_id: uuid.UUID, service: SupplierSvc, _: SupplierRead
) -> SupplierDetailView:
    return await service.detail(supplier_id)


@supplier_router.put("/{supplier_id}", response_model=SupplierProfileInput)
async def update_supplier_profile(
    supplier_id: uuid.UUID, cmd: SupplierProfileInput, service: SupplierSvc, p: SupplierManage
) -> Any:
    profile = await service.update_profile(supplier_id, cmd, actor_id=p.id)
    return SupplierProfileInput(
        full_name=profile.full_name,
        phone=profile.phone,
        national_id=profile.national_id,
        village=profile.village,
        locale=profile.locale,
        extra=profile.extra,
    )


class RepairContactRequest(BaseModel):
    """The smallest thing an operator acting on a reachability report sends.

    A PATCH body rather than a whole profile: making somebody resend
    `national_id` and `village` to fix a phone number is how a forgotten field
    silently blanks a record.
    """

    phone: str = Field(default="", max_length=30)
    locale: str | None = Field(default=None, max_length=8)
    #: Why. Free text, stored on the audit entry and nowhere else.
    reason: str | None = Field(default=None, max_length=200)


@supplier_router.patch("/{supplier_id}/contact", response_model=SupplierProfileInput)
async def repair_supplier_contact(
    supplier_id: uuid.UUID, body: RepairContactRequest, service: SupplierSvc, p: SupplierManage
) -> Any:
    """Repair how a farmer is reached (DEMO-030).

    Behind the same `supplier.manage` permission as every other change to a
    supplier — a contact detail is part of the supplier record, and inventing a
    narrower permission for it would mean a role that can change a farmer's
    phone number but not their name.
    """
    profile = await service.repair_contact(
        supplier_id,
        phone=body.phone,
        locale=body.locale,
        reason=body.reason,
        actor_id=p.id,
    )
    return SupplierProfileInput(
        full_name=profile.full_name,
        phone=profile.phone,
        national_id=profile.national_id,
        village=profile.village,
        locale=profile.locale,
        extra=profile.extra,
    )


class SupplierStatusRequest(BaseModel):
    status: str


@supplier_router.post("/{supplier_id}/status", response_model=SupplierView)
async def set_supplier_status(
    supplier_id: uuid.UUID, body: SupplierStatusRequest, service: SupplierSvc, p: SupplierManage
) -> Any:
    await service.set_status(supplier_id, body.status, actor_id=p.id)
    return (await service.detail(supplier_id)).supplier


class AssignSupplierCenterRequest(BaseModel):
    center_id: uuid.UUID


@supplier_router.post("/{supplier_id}/centers", status_code=201)
async def assign_supplier_center(
    supplier_id: uuid.UUID,
    body: AssignSupplierCenterRequest,
    service: SupplierSvc,
    p: SupplierManage,
) -> dict:
    a = await service.assign_center(supplier_id, body.center_id, actor_id=p.id)
    return {"supplier_id": str(a.supplier_id), "center_id": str(a.center_id)}


@supplier_router.delete("/{supplier_id}/centers/{center_id}", status_code=204)
async def unassign_supplier_center(
    supplier_id: uuid.UUID, center_id: uuid.UUID, service: SupplierSvc, p: SupplierManage
) -> None:
    await service.unassign_center(supplier_id, center_id, actor_id=p.id)


class AssignSupplierBranchRequest(BaseModel):
    branch_id: uuid.UUID


@supplier_router.post("/{supplier_id}/branch", response_model=SupplierView)
async def assign_supplier_branch(
    supplier_id: uuid.UUID,
    body: AssignSupplierBranchRequest,
    service: SupplierSvc,
    p: SupplierManage,
) -> Any:
    await service.set_branch(supplier_id, body.branch_id, actor_id=p.id)
    return (await service.detail(supplier_id)).supplier


@supplier_router.post(
    "/{supplier_id}/bank-accounts", response_model=BankAccountView, status_code=201
)
async def add_supplier_bank_account(
    supplier_id: uuid.UUID, cmd: AddBankAccountCommand, service: SupplierSvc, p: SupplierManage
) -> Any:
    account = await service.add_bank_account(supplier_id, cmd, actor_id=p.id)
    accounts = await service.list_bank_accounts(supplier_id)
    return next(a for a in accounts if a.id == account.id)


@supplier_router.get("/{supplier_id}/bank-accounts", response_model=list[BankAccountView])
async def list_supplier_bank_accounts(
    supplier_id: uuid.UUID, service: SupplierSvc, _: SupplierRead
) -> Any:
    return await service.list_bank_accounts(supplier_id)


@supplier_router.post("/{supplier_id}/documents", response_model=DocumentView, status_code=201)
async def add_supplier_document(
    supplier_id: uuid.UUID, cmd: UploadDocumentCommand, service: SupplierSvc, p: SupplierManage
) -> Any:
    return await service.add_document(supplier_id, cmd, actor_id=p.id)


@supplier_router.get("/{supplier_id}/documents", response_model=list[DocumentView])
async def list_supplier_documents(
    supplier_id: uuid.UUID, service: SupplierSvc, _: SupplierRead
) -> Any:
    return await service.list_documents(supplier_id)


@supplier_router.get("/{supplier_id}/documents/{document_id}/url")
async def get_supplier_document_url(
    supplier_id: uuid.UUID, document_id: uuid.UUID, service: SupplierSvc, _: SupplierRead
) -> dict:
    return {"url": await service.document_url(supplier_id, document_id)}


@supplier_router.get("/{supplier_id}/qr")
async def get_supplier_qr(supplier_id: uuid.UUID, service: SupplierSvc, _: SupplierRead) -> dict:
    supplier = await service.get(supplier_id)
    return {"payload": qr_payload_for(supplier.id), "code": supplier.code}


class ResolveQrRequest(BaseModel):
    payload: str


@supplier_router.post("/qr/resolve", response_model=SupplierView)
async def resolve_supplier_qr(body: ResolveQrRequest, service: SupplierSvc, _: SupplierRead) -> Any:
    supplier = await service.resolve_qr(body.payload)
    return (await service.detail(supplier.id)).supplier


class ImportRequest(BaseModel):
    # Loose dicts by design: each row is validated individually in the service
    # so a single malformed row yields a per-row error, not a 422 batch failure.
    rows: list[dict[str, Any]]


@supplier_router.post("/import", response_model=list[ImportRowResult])
async def import_suppliers(body: ImportRequest, service: SupplierSvc, p: SupplierManage) -> Any:
    return await service.import_rows(body.rows, actor_id=p.id)


# --- Milk collection (sessions + transaction engine) ------------------------
milk_router = APIRouter(tags=["milk-collection"], route_class=IdempotentRoute)
SessionManage = Annotated[Principal, Depends(require_permission("collection.session.manage"))]
TxRecord = Annotated[Principal, Depends(require_permission("collection.transaction.record"))]
TxRead = Annotated[Principal, Depends(require_permission("collection.transaction.read"))]
MilkSvc = Annotated[MilkCollectionService, Depends(deps.get_milk_collection_service)]


class OpenSessionRequest(BaseModel):
    center_id: uuid.UUID
    label: str = ""


@milk_router.post("/collection-sessions", response_model=SessionView, status_code=201)
async def open_collection_session(
    body: OpenSessionRequest,
    service: MilkSvc,
    p: SessionManage,
    engine: Annotated[PermissionEngine, Depends(deps.get_permission_engine)],
) -> Any:
    """Open a session at a centre.

    The centre arrives in the BODY here, not the path, so the scope is checked
    in the handler rather than by `require_center_access`. Opening a session is
    the moment a person starts working at a centre — letting a centre-scoped
    operator open one somewhere else would make every collection recorded in
    that session out of scope too.
    """
    scope = await engine.center_scope(p.id, p.tenant_id)
    if scope is not None and body.center_id not in scope:
        raise ForbiddenError("this centre is outside your assigned scope")
    return await service.open_session(body.center_id, body.label, actor_id=p.id)


@milk_router.post("/collection-sessions/{session_id}/close", response_model=SessionView)
async def close_collection_session(
    session_id: uuid.UUID, service: MilkSvc, p: SessionManage
) -> Any:
    return await service.close_session(session_id, actor_id=p.id)


@milk_router.get("/collection-sessions", response_model=SessionPage)
async def list_collection_sessions(
    service: MilkSvc,
    _: TxRead,
    center_id: uuid.UUID | None = None,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Any:
    """Collection sessions, newest first.

    API-001: paginated. Sessions accumulate for the life of the tenant and
    were previously returned in full.
    """
    return await service.list_sessions(
        center_id=center_id, status=status, limit=limit, offset=offset
    )


class CreateTransactionRequest(BaseModel):
    session_id: uuid.UUID


@milk_router.post("/milk-transactions", response_model=TransactionView, status_code=201)
async def create_milk_transaction(
    body: CreateTransactionRequest, service: MilkSvc, p: TxRecord
) -> Any:
    return await service.create_transaction(body.session_id, actor_id=p.id)


@milk_router.post("/milk-transactions/{tx_id}/identify", response_model=TransactionView)
async def identify_transaction_supplier(
    tx_id: uuid.UUID, cmd: IdentifySupplierCommand, service: MilkSvc, p: TxRecord
) -> Any:
    return await service.identify_supplier(tx_id, cmd, actor_id=p.id)


@milk_router.post("/milk-transactions/{tx_id}/milk", response_model=TransactionView)
async def receive_transaction_milk(
    tx_id: uuid.UUID, cmd: MilkInfoCommand, service: MilkSvc, p: TxRecord
) -> Any:
    return await service.receive_milk(tx_id, cmd, actor_id=p.id)


@milk_router.post("/milk-transactions/{tx_id}/weight", response_model=TransactionView)
async def capture_transaction_weight(
    tx_id: uuid.UUID, cmd: WeightCommand, service: MilkSvc, p: TxRecord
) -> Any:
    return await service.capture_weight(tx_id, cmd, actor_id=p.id)


@milk_router.post("/milk-transactions/{tx_id}/quality", response_model=TransactionView)
async def capture_transaction_quality(
    tx_id: uuid.UUID, cmd: QualityCommand, service: MilkSvc, p: TxRecord
) -> Any:
    return await service.capture_quality(tx_id, cmd, actor_id=p.id)


@milk_router.post("/milk-transactions/{tx_id}/accept", response_model=TransactionView)
async def accept_transaction(tx_id: uuid.UUID, service: MilkSvc, p: TxRecord) -> Any:
    return await service.accept(tx_id, actor_id=p.id)


@milk_router.post("/milk-transactions/{tx_id}/reject", response_model=TransactionView)
async def reject_transaction(
    tx_id: uuid.UUID, cmd: RejectCommand, service: MilkSvc, p: TxRecord
) -> Any:
    return await service.reject(tx_id, cmd, actor_id=p.id)


@milk_router.post("/milk-transactions/{tx_id}/complete", response_model=TransactionView)
async def complete_transaction(tx_id: uuid.UUID, service: MilkSvc, p: TxRecord) -> Any:
    return await service.complete(tx_id, actor_id=p.id)


class CancelTransactionRequest(BaseModel):
    reason: str = ""


@milk_router.post("/milk-transactions/{tx_id}/cancel", response_model=TransactionView)
async def cancel_transaction(
    tx_id: uuid.UUID, body: CancelTransactionRequest, service: MilkSvc, p: TxRecord
) -> Any:
    return await service.cancel(tx_id, body.reason, actor_id=p.id)


@milk_router.get("/milk-transactions", response_model=TransactionPage)
async def list_milk_transactions(
    service: MilkSvc,
    p: TxRead,
    engine: Annotated[PermissionEngine, Depends(deps.get_permission_engine)],
    session_id: uuid.UUID | None = None,
    center_id: uuid.UUID | None = None,
    supplier_id: uuid.UUID | None = None,
    state: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> TransactionPage:
    return await service.list_transactions(
        session_id=session_id,
        center_id=center_id,
        supplier_id=supplier_id,
        state=state,
        date_from=date_from,
        date_to=date_to,
        center_scope=await engine.center_scope(p.id, p.tenant_id),
        limit=limit,
        offset=offset,
    )


@milk_router.get("/milk-transactions/{tx_id}", response_model=TransactionView)
async def get_milk_transaction(tx_id: uuid.UUID, service: MilkSvc, _: TxRead) -> Any:
    return await service.get_tx_view(tx_id)


@milk_router.get("/milk-transactions/{tx_id}/events", response_model=list[TransactionEventView])
async def get_milk_transaction_events(tx_id: uuid.UUID, service: MilkSvc, _: TxRead) -> Any:
    return await service.list_events(tx_id)


@milk_router.get("/milk-transactions/{tx_id}/slip", response_model=SlipView)
async def get_milk_transaction_slip(tx_id: uuid.UUID, service: MilkSvc, _: TxRead) -> Any:
    """P0-BIZ-003: the collection slip (parchi) for a completed transaction."""
    return await service.slip(tx_id)


# --- Pricing (Rate Card Foundation — lifecycle only, no calculations) -------
pricing_router = APIRouter(prefix="/rate-cards", tags=["pricing"], route_class=IdempotentRoute)
RateCardManage = Annotated[Principal, Depends(require_permission("pricing.ratecard.manage"))]
RateCardApprove = Annotated[Principal, Depends(require_permission("pricing.ratecard.approve"))]
RateCardRead = Annotated[Principal, Depends(require_permission("pricing.ratecard.read"))]
RateCardSvc = Annotated[RateCardService, Depends(deps.get_rate_card_service)]


@pricing_router.post("", response_model=RateCardView, status_code=201)
async def create_rate_card(
    cmd: CreateRateCardCommand, service: RateCardSvc, p: RateCardManage
) -> Any:
    return await service.create(cmd, actor_id=p.id)


@pricing_router.get("", response_model=RateCardPage)
async def search_rate_cards(
    service: RateCardSvc,
    _: RateCardRead,
    q: str | None = None,
    status: str | None = None,
    currency: str | None = None,
    center_id: uuid.UUID | None = None,
    product_code: str | None = None,
    active_on: date | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> RateCardPage:
    return await service.search(
        q=q,
        status=status,
        currency=currency,
        center_id=center_id,
        product_code=product_code,
        active_on=active_on,
        limit=limit,
        offset=offset,
    )


@pricing_router.get("/{card_id}", response_model=RateCardDetailView)
async def get_rate_card_detail(
    card_id: uuid.UUID, service: RateCardSvc, _: RateCardRead
) -> RateCardDetailView:
    return await service.detail(card_id)


@pricing_router.put("/{card_id}", response_model=RateCardView)
async def update_rate_card_draft(
    card_id: uuid.UUID, cmd: RateCardInput, service: RateCardSvc, p: RateCardManage
) -> Any:
    return await service.update_draft(card_id, cmd, actor_id=p.id)


@pricing_router.post("/{card_id}/submit", response_model=RateCardView)
async def submit_rate_card(card_id: uuid.UUID, service: RateCardSvc, p: RateCardManage) -> Any:
    return await service.submit_for_review(card_id, actor_id=p.id)


@pricing_router.post("/{card_id}/approve", response_model=RateCardView)
async def approve_rate_card(card_id: uuid.UUID, service: RateCardSvc, p: RateCardApprove) -> Any:
    return await service.approve(card_id, actor_id=p.id)


@pricing_router.post("/{card_id}/publish", response_model=RateCardView)
async def publish_rate_card(card_id: uuid.UUID, service: RateCardSvc, p: RateCardApprove) -> Any:
    return await service.publish(card_id, actor_id=p.id)


@pricing_router.post("/{card_id}/archive", response_model=RateCardView)
async def archive_rate_card(card_id: uuid.UUID, service: RateCardSvc, p: RateCardManage) -> Any:
    return await service.archive(card_id, actor_id=p.id)


@pricing_router.post("/{card_id}/versions", response_model=RateCardView, status_code=201)
async def create_rate_card_version(
    card_id: uuid.UUID, service: RateCardSvc, p: RateCardManage
) -> Any:
    return await service.new_version(card_id, actor_id=p.id)


class AssignRateCardCenterRequest(BaseModel):
    center_id: uuid.UUID


@pricing_router.post("/{card_id}/centers", status_code=201)
async def assign_rate_card_center(
    card_id: uuid.UUID,
    body: AssignRateCardCenterRequest,
    service: RateCardSvc,
    p: RateCardManage,
) -> dict:
    a = await service.assign_center(card_id, body.center_id, actor_id=p.id)
    return {"rate_card_id": str(a.rate_card_id), "center_id": str(a.center_id)}


@pricing_router.delete("/{card_id}/centers/{center_id}", status_code=204)
async def unassign_rate_card_center(
    card_id: uuid.UUID, center_id: uuid.UUID, service: RateCardSvc, p: RateCardManage
) -> None:
    await service.unassign_center(card_id, center_id, actor_id=p.id)


@pricing_router.post("/{card_id}/products", status_code=201)
async def assign_rate_card_product(
    card_id: uuid.UUID, cmd: AssignProductCommand, service: RateCardSvc, p: RateCardManage
) -> dict:
    a = await service.assign_product(card_id, cmd, actor_id=p.id)
    return {"rate_card_id": str(a.rate_card_id), "product_code": a.product_code}


@pricing_router.delete("/{card_id}/products/{product_code}", status_code=204)
async def unassign_rate_card_product(
    card_id: uuid.UUID, product_code: str, service: RateCardSvc, p: RateCardManage
) -> None:
    await service.unassign_product(card_id, product_code, actor_id=p.id)


# --- Pricing matrices (pricing DATA only — no calculation, Increment-002) ---
matrix_router = APIRouter(tags=["pricing"], route_class=IdempotentRoute)
MatrixSvc = Annotated[PricingMatrixService, Depends(deps.get_pricing_matrix_service)]


@matrix_router.get("/quality-dimensions", response_model=list[DimensionView])
async def list_quality_dimensions(service: MatrixSvc, _: RateCardRead) -> Any:
    """Configurable dimensions (FAT, SNF, …) — seeded per tenant on first use."""
    return await service.list_dimensions()


@matrix_router.post("/quality-dimensions", response_model=DimensionView, status_code=201)
async def create_quality_dimension(
    cmd: DimensionInput, service: MatrixSvc, p: RateCardManage
) -> Any:
    return await service.create_dimension(cmd, actor_id=p.id)


@matrix_router.post("/pricing-matrices", response_model=MatrixView, status_code=201)
async def create_pricing_matrix(
    cmd: CreateMatrixCommand, service: MatrixSvc, p: RateCardManage
) -> Any:
    matrix = await service.create_matrix(cmd, actor_id=p.id)
    return (await service.detail(matrix.id)).matrix


@matrix_router.get("/pricing-matrices", response_model=MatrixPage)
async def search_pricing_matrices(
    service: MatrixSvc,
    _: RateCardRead,
    q: str | None = None,
    rate_card_id: uuid.UUID | None = None,
    product_code: str | None = None,
    dimension_code: str | None = None,
    status: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> MatrixPage:
    return await service.search(
        q=q,
        rate_card_id=rate_card_id,
        product_code=product_code,
        dimension_code=dimension_code,
        status=status,
        limit=limit,
        offset=offset,
    )


@matrix_router.get("/pricing-matrices/{matrix_id}", response_model=MatrixDetailView)
async def get_pricing_matrix_detail(
    matrix_id: uuid.UUID, service: MatrixSvc, _: RateCardRead
) -> MatrixDetailView:
    return await service.detail(matrix_id)


@matrix_router.put("/pricing-matrices/{matrix_id}", response_model=MatrixView)
async def update_pricing_matrix(
    matrix_id: uuid.UUID, cmd: UpdateMatrixCommand, service: MatrixSvc, p: RateCardManage
) -> Any:
    matrix = await service.update_matrix(matrix_id, cmd, actor_id=p.id)
    return (await service.detail(matrix.id)).matrix


@matrix_router.delete("/pricing-matrices/{matrix_id}", status_code=204)
async def delete_pricing_matrix(
    matrix_id: uuid.UUID, service: MatrixSvc, p: RateCardManage
) -> None:
    await service.delete_matrix(matrix_id, actor_id=p.id)


@matrix_router.post("/pricing-matrices/{matrix_id}/rows", response_model=RowView, status_code=201)
async def create_pricing_matrix_row(
    matrix_id: uuid.UUID, cmd: RowInput, service: MatrixSvc, p: RateCardManage
) -> Any:
    return await service.add_row(matrix_id, cmd, actor_id=p.id)


@matrix_router.put("/pricing-matrices/{matrix_id}/rows/{row_id}", response_model=RowView)
async def update_pricing_matrix_row(
    matrix_id: uuid.UUID,
    row_id: uuid.UUID,
    cmd: RowInput,
    service: MatrixSvc,
    p: RateCardManage,
) -> Any:
    return await service.update_row(matrix_id, row_id, cmd, actor_id=p.id)


@matrix_router.delete("/pricing-matrices/{matrix_id}/rows/{row_id}", status_code=204)
async def delete_pricing_matrix_row(
    matrix_id: uuid.UUID, row_id: uuid.UUID, service: MatrixSvc, p: RateCardManage
) -> None:
    await service.delete_row(matrix_id, row_id, actor_id=p.id)


# --- Pricing resolution (read-side selection only — PRC-003) ----------------
ResolutionSvc = Annotated[PricingResolutionService, Depends(deps.get_pricing_resolution_service)]


@matrix_router.post("/pricing/resolve", response_model=ResolutionResult)
async def resolve_pricing(q: ResolutionQuery, service: ResolutionSvc, _: RateCardRead) -> Any:
    """Select the ONE pricing-matrix band applying to (center, product, date,
    dimension, reading). 422 with {stage, reason, inputs} when nothing
    matches; 409 when pricing data is ambiguous. Calculates nothing."""
    return await service.resolve(q)


CalcSvc = Annotated[PricingCalculationService, Depends(deps.get_pricing_calculation_service)]


@matrix_router.post("/pricing/calculate", response_model=CalculationResult)
async def calculate_pricing(req: CalculationRequest, service: CalcSvc, p: RateCardRead) -> Any:
    """Gross = unit price x quantity for a previously RESOLVED band (send the
    row_id from /pricing/resolve — prices are never client-supplied).
    Decimal arithmetic, explicit rounding policy, full trace (BR-0005/6/7).
    Emits pricing.calculated.v1. No bonuses/penalties/taxes (PRC-005+)."""
    return await service.calculate(req, actor_id=p.id)


# --- Settlements (payable amounts — lifecycle only, no payment, SET-001) ----
settlement_router = APIRouter(
    prefix="/settlements", tags=["settlement"], route_class=IdempotentRoute
)
SettlementManage = Annotated[Principal, Depends(require_permission("settlement.manage"))]
SettlementFinalize = Annotated[Principal, Depends(require_permission("settlement.finalize"))]
SettlementRead = Annotated[Principal, Depends(require_permission("settlement.read"))]
SettlementSvc = Annotated[SettlementService, Depends(deps.get_settlement_service)]


@settlement_router.post("", response_model=SettlementView, status_code=201)
async def create_settlement(
    cmd: CreateSettlementCommand, service: SettlementSvc, p: SettlementManage
) -> Any:
    settlement = await service.create(cmd, actor_id=p.id)
    return (await service.detail(settlement.id)).settlement


@settlement_router.get("", response_model=SettlementPage)
async def search_settlements(
    service: SettlementSvc,
    _: SettlementRead,
    q: str | None = None,
    supplier_id: uuid.UUID | None = None,
    center_id: uuid.UUID | None = None,
    status: str | None = None,
    overlapping_on: date | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> SettlementPage:
    return await service.search(
        q=q,
        supplier_id=supplier_id,
        center_id=center_id,
        status=status,
        overlapping_on=overlapping_on,
        limit=limit,
        offset=offset,
    )


@settlement_router.get("/{settlement_id}", response_model=SettlementDetailView)
async def get_settlement_detail(
    settlement_id: uuid.UUID, service: SettlementSvc, _: SettlementRead
) -> SettlementDetailView:
    return await service.detail(settlement_id)


@settlement_router.post(
    "/{settlement_id}/calculations", response_model=SettlementLineView, status_code=201
)
async def add_settlement_calculation(
    settlement_id: uuid.UUID,
    cmd: AddCalculationCommand,
    service: SettlementSvc,
    p: SettlementManage,
) -> Any:
    return await service.add_calculation(settlement_id, cmd, actor_id=p.id)


class AddTransactionRequest(BaseModel):
    transaction_id: uuid.UUID


@settlement_router.post(
    "/{settlement_id}/transactions", response_model=SettlementLineView, status_code=201
)
async def add_settlement_transaction(
    settlement_id: uuid.UUID,
    body: AddTransactionRequest,
    service: SettlementSvc,
    p: SettlementManage,
) -> Any:
    """MVP-001: settle a completed milk transaction by id (uses its own
    verified pricing calculation)."""
    return await service.add_transaction(settlement_id, body.transaction_id, actor_id=p.id)


@settlement_router.post("/{settlement_id}/collect")
async def collect_settlement_period(
    settlement_id: uuid.UUID, service: SettlementSvc, p: SettlementManage
) -> dict:
    """MVP-001: bulk-add every eligible milk transaction of the supplier,
    center, and period. Idempotent — already-settled transactions are skipped."""
    return await service.collect_period(settlement_id, actor_id=p.id)


@settlement_router.delete("/{settlement_id}/lines/{line_id}", status_code=204)
async def remove_settlement_line(
    settlement_id: uuid.UUID, line_id: uuid.UUID, service: SettlementSvc, p: SettlementManage
) -> None:
    await service.remove_line(settlement_id, line_id, actor_id=p.id)


@settlement_router.post("/{settlement_id}/calculate", response_model=SettlementView)
async def calculate_settlement_totals(
    settlement_id: uuid.UUID, service: SettlementSvc, p: SettlementManage
) -> Any:
    settlement = await service.calculate_totals(settlement_id, actor_id=p.id)
    return (await service.detail(settlement.id)).settlement


@settlement_router.post("/{settlement_id}/finalize", response_model=SettlementView)
async def finalize_settlement(
    settlement_id: uuid.UUID, service: SettlementSvc, p: SettlementFinalize
) -> Any:
    settlement = await service.finalize(settlement_id, actor_id=p.id)
    return (await service.detail(settlement.id)).settlement


class CancelSettlementRequest(BaseModel):
    reason: str = Field(default="", max_length=300)


@settlement_router.post("/{settlement_id}/cancel", response_model=SettlementView)
async def cancel_settlement(
    settlement_id: uuid.UUID,
    body: CancelSettlementRequest,
    service: SettlementSvc,
    p: SettlementManage,
) -> Any:
    settlement = await service.cancel(settlement_id, body.reason, actor_id=p.id)
    return (await service.detail(settlement.id)).settlement


# --- Payments (execution against finalized settlements — PAY-001) -----------
payment_router = APIRouter(tags=["payment"], route_class=IdempotentRoute)
PaymentRead = Annotated[Principal, Depends(require_permission("payment.read"))]
PaymentManage = Annotated[Principal, Depends(require_permission("payment.manage"))]
PaymentRetry = Annotated[Principal, Depends(require_permission("payment.retry"))]
PaymentCancel = Annotated[Principal, Depends(require_permission("payment.cancel"))]
PaymentSvc = Annotated[PaymentService, Depends(deps.get_payment_service)]


@payment_router.post("/payments", response_model=PaymentView, status_code=201)
async def create_payment(
    cmd: CreatePaymentCommand,
    service: PaymentSvc,
    p: PaymentManage,
    idempotency_key: Annotated[
        str | None,
        Header(
            alias="Idempotency-Key",
            max_length=80,
            description=(
                "Retry-safe creation. Re-sending the same key returns the payment "
                "the first request created instead of paying twice. Equivalent to "
                "the `idempotency_key` body field; the header is the conventional "
                "spelling and is preferred."
            ),
        ),
    ] = None,
) -> Any:
    """Create a payment against one or more finalized settlements of one
    supplier. Omit an allocation amount to pay the full outstanding balance;
    supply one for a partial payment.

    **Retry safety (API-001).** Paying twice is the worst outcome this endpoint
    has, and a mobile client on a village connection cannot tell a lost
    response from a lost request. Send an `Idempotency-Key` header: a repeat
    returns the original payment, unchanged, with the same status code.
    """
    # The header wins when both are present: it is the transport-level
    # statement of intent, and a proxy that retries will resend it verbatim.
    if idempotency_key:
        cmd = cmd.model_copy(update={"idempotency_key": idempotency_key})
    payment = await service.create(cmd, actor_id=p.id)
    return (await service.detail(payment.id)).payment


@payment_router.get("/payments", response_model=PaymentPage)
async def search_payments(
    service: PaymentSvc,
    _: PaymentRead,
    q: str | None = None,
    supplier_id: uuid.UUID | None = None,
    settlement_id: uuid.UUID | None = None,
    status: str | None = None,
    method: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PaymentPage:
    """Payment history: search number/reference, filter by supplier, the
    settlement paid, status, or method."""
    return await service.search(
        q=q,
        supplier_id=supplier_id,
        settlement_id=settlement_id,
        status=status,
        method=method,
        limit=limit,
        offset=offset,
    )


@payment_router.get("/payments/balances", response_model=BalancePage)
async def list_outstanding_balances(
    service: PaymentSvc,
    _: PaymentRead,
    supplier_id: uuid.UUID | None = None,
    outstanding_only: bool = True,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> BalancePage:
    """The settlement selector: finalized settlements with what is still owed."""
    return await service.balances(
        supplier_id=supplier_id, outstanding_only=outstanding_only, limit=limit, offset=offset
    )


@payment_router.get("/settlements/{settlement_id}/balance", response_model=SettlementBalanceView)
async def get_settlement_balance(
    settlement_id: uuid.UUID, service: PaymentSvc, _: PaymentRead
) -> SettlementBalanceView:
    """Outstanding balance of one settlement (payable - live allocations)."""
    return await service.balance(settlement_id)


@payment_router.get("/payments/{payment_id}", response_model=PaymentDetailView)
async def get_payment_detail(
    payment_id: uuid.UUID, service: PaymentSvc, _: PaymentRead
) -> PaymentDetailView:
    return await service.detail(payment_id)


@payment_router.post("/payments/{payment_id}/submit", response_model=PaymentView)
async def submit_payment(payment_id: uuid.UUID, service: PaymentSvc, p: PaymentManage) -> Any:
    """draft -> pending: approved for execution."""
    await service.submit(payment_id, actor_id=p.id)
    return (await service.detail(payment_id)).payment


@payment_router.post("/payments/{payment_id}/execute", response_model=PaymentView)
async def execute_payment(
    payment_id: uuid.UUID,
    cmd: ExecutePaymentCommand,
    service: PaymentSvc,
    p: PaymentManage,
) -> Any:
    """pending -> processing, opening a new attempt."""
    await service.execute(payment_id, cmd, actor_id=p.id)
    return (await service.detail(payment_id)).payment


@payment_router.post("/payments/{payment_id}/retry", response_model=PaymentView)
async def retry_payment(
    payment_id: uuid.UUID,
    cmd: ExecutePaymentCommand,
    service: PaymentSvc,
    p: PaymentRetry,
) -> Any:
    """failed -> processing with a NEW attempt (attempts are never reused)."""
    await service.retry(payment_id, cmd, actor_id=p.id)
    return (await service.detail(payment_id)).payment


@payment_router.post("/payments/{payment_id}/complete", response_model=PaymentView)
async def complete_payment(
    payment_id: uuid.UUID,
    cmd: CompletePaymentCommand,
    service: PaymentSvc,
    p: PaymentManage,
) -> Any:
    """processing -> completed. Permanent: emits payment.completed.v1."""
    await service.complete(payment_id, cmd, actor_id=p.id)
    return (await service.detail(payment_id)).payment


@payment_router.post("/payments/{payment_id}/fail", response_model=PaymentView)
async def fail_payment(
    payment_id: uuid.UUID,
    cmd: FailPaymentCommand,
    service: PaymentSvc,
    p: PaymentManage,
) -> Any:
    """processing -> failed. Retryable; releases the allocation."""
    await service.fail(payment_id, cmd, actor_id=p.id)
    return (await service.detail(payment_id)).payment


@payment_router.post("/payments/{payment_id}/cancel", response_model=PaymentView)
async def cancel_payment(
    payment_id: uuid.UUID,
    cmd: CancelPaymentCommand,
    service: PaymentSvc,
    p: PaymentCancel,
) -> Any:
    """Terminal. Not permitted while processing — record the failure first."""
    await service.cancel(payment_id, cmd, actor_id=p.id)
    return (await service.detail(payment_id)).payment


# --- Notifications (delivery history & operations — NOT-001) ----------------
# --- Delivery receipts (DEMO-029) -----------------------------------------
#
# Its own router with NO idempotency route class and NO authentication, for
# exactly the reasons DEMO-027's payment webhook has neither.
#
# Not `IdempotentRoute`: that keys on a client-supplied `Idempotency-Key`
# header, and a messaging gateway sends its own event id instead —
# de-duplication belongs on that id, in the database, where a replay cannot
# slip past a header nobody sent.
#
# Not authenticated: a gateway has no Lacteva account. What replaces
# authentication is a constant-time HMAC over the raw body, checked by the SAME
# `core/webhook_security` the payment webhook uses.
delivery_receipt_router = APIRouter(
    prefix="/notifications", tags=["notifications"], route_class=TransactionalRoute
)


@delivery_receipt_router.post("/receipts/{provider}", status_code=200)
async def receive_delivery_receipt(provider: str, request: Request) -> dict[str, str]:
    """Accept one provider delivery report.

    Returns 200 for everything it correctly handled — including a replay, an
    unknown reference, and a report that deliberately changed nothing. A
    gateway reads a non-2xx as "retry", and asking it to redeliver a report
    already applied achieves nothing and eventually pages somebody.

    401 and 404 say only that the request was refused, never which check
    refused it.
    """
    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    try:
        result = await receipt_processing.process_receipt(
            provider_name=provider, body=body, headers=headers
        )
    except ReceiptVerificationError as exc:
        raise UnauthorizedError("receipt rejected") from exc
    except UnknownReceiptProvider as exc:
        raise NotFoundError("unknown provider") from exc
    return {"outcome": result.outcome}


notification_router = APIRouter(tags=["notifications"], route_class=IdempotentRoute)
NotificationRead = Annotated[Principal, Depends(require_permission("notification.read"))]
NotificationManage = Annotated[Principal, Depends(require_permission("notification.manage"))]
NotificationSvc = Annotated[NotificationService, Depends(deps.get_notification_service)]


@notification_router.get(
    "/notification-templates/registry",
    dependencies=[Depends(require_permission("notification.read"))],
)
async def read_template_registry(service: NotificationSvc) -> TemplateRegistryView:
    """Every template Lacteva can send, and whether a provider knows it.

    **Read-only.** A template is code — reviewed, tested, shipped, and
    re-renderable months later for a retry. A database-editable message that a
    farmer receives about their money is a change nobody reviewed, and an
    approved WhatsApp wording that has silently diverged from the one a vendor
    approved.

    Process-wide rather than per-tenant, because the templates are. What is
    per-tenant is the channel a dairy chose, which lives in the configuration
    store behind RLS and is not exposed here.
    """
    return await service.registry_with_approvals()


@notification_router.post(
    "/notification-templates/approval",
    dependencies=[Depends(require_permission("notification.template.approve"))],
)
async def record_template_approval(
    service: NotificationSvc,
    audit: deps.Audit,
    principal: deps.CurrentPrincipal,
    body: ApprovalCommand,
) -> ApprovalView:
    """Record what an EXTERNAL provider or regulator decided (DEMO-033).

    **This does not approve anything.** It writes down that somebody outside
    Lacteva decided something, and who wrote it down. Behind a platform-admin
    permission that no tenant role holds — the messaging account is Lacteva's,
    so a dairy recording an approval would be asserting something about
    somebody else's account.

    The template must exist in that channel and language: an approval for
    something Lacteva cannot send is a note about nothing.
    """
    return await service.record_approval(body, actor_id=principal.id, audit=audit)


@notification_router.get(
    "/notifications/messaging-posture",
    dependencies=[Depends(require_permission("notification.read"))],
)
async def read_messaging_posture() -> MessagingPosture:
    """Whether this deployment can send, and on which channels (DEMO-031).

    **Never a credential and never a URL.** Three yes/no answers per channel —
    configured, permitted to send, able to report delivery — which is what an
    operator asking "did it go?" actually needs and leaks nothing.

    It is deployment-wide rather than per-tenant because the gateway is shared;
    what IS per-tenant is the channel choice, which lives in the configuration
    store behind RLS.
    """
    return NotificationService.posture()


@notification_router.get(
    "/notifications/reachability",
    dependencies=[Depends(require_permission("notification.read"))],
)
async def read_reachability(
    service: Annotated[ReachabilityService, Depends(deps.get_reachability_service)],
    template_key: str = "settlement_finalized",
    subject_type: str = "supplier",
) -> ReachabilitySummaryView:
    """Who can be reached before a communication run, and who cannot.

    **This blocks nothing.** A farmer with no phone number is still settled and
    still paid; the point of counting them is that somebody can see them and do
    something about it, instead of a message quietly going nowhere.
    """
    summary = await service.for_template(template_key, subject_type=subject_type)
    return ReachabilitySummaryView.of(summary)


@notification_router.get(
    "/notifications/reachability/settlement-period",
    dependencies=[Depends(require_permission("notification.read"))],
)
async def read_settlement_period_reachability(
    service: Annotated[ReachabilityService, Depends(deps.get_reachability_service)],
    settlements: Annotated[SettlementService, Depends(deps.get_settlement_service)],
    session: deps.Session,
    period_from: date | None = None,
    period_to: date | None = None,
) -> ReachabilitySummaryView:
    """Who can be reached about the settlements in a period (DEMO-030).

    **The dates default on the ORGANIZATION's calendar, not the server's.** An
    operator in Bengaluru asking "this month" at 00:30 local must be answered
    about their month, and `business_today` is the only thing that knows which
    that is — `date.today()` here would silently give an Indian dairy the
    previous month for five and a half hours every night.

    It still blocks nothing: this reports, and settlement proceeds regardless.
    """
    # `tenant_timezone` is the platform's own way to ask whose clock this is —
    # the same one the calendar and the scheduler use.
    today = business_today(await tenant_timezone(session))
    if period_from is None or period_to is None:
        default_from, default_to = month_bounds(today)
        period_from = period_from or default_from
        period_to = period_to or default_to
    if period_from > period_to:
        raise ValidationError("period_from must not be after period_to")
    # Composition, in the composition layer: the SETTLEMENT module answers who
    # it is settling, and the NOTIFICATION module answers whether they can be
    # reached. Neither queries the other's tables.
    subject_ids = await settlements.supplier_ids_in_period(period_from, period_to)
    summary = await service.for_subjects(subject_ids, template_key="settlement_finalized")
    return ReachabilitySummaryView.of(summary)


@notification_router.get("/notifications", response_model=NotificationPage)
async def search_notifications(
    service: NotificationSvc,
    _: NotificationRead,
    q: str | None = None,
    status: str | None = None,
    channel: str | None = None,
    template_key: str | None = None,
    event_id: uuid.UUID | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> NotificationPage:
    """Delivery history: search by recipient/text, filter by status (sent |
    failed | dead | pending), channel, template, or originating event."""
    return await service.search(
        q=q,
        status=status,
        channel=channel,
        template_key=template_key,
        event_id=event_id,
        limit=limit,
        offset=offset,
    )


@notification_router.get("/notifications/stats", response_model=NotificationStats)
async def notification_stats(service: NotificationSvc, _: NotificationRead) -> NotificationStats:
    return await service.stats()


@notification_router.get("/notification-templates", response_model=list[TemplateView])
async def list_notification_templates(service: NotificationSvc, _: NotificationRead) -> Any:
    """The template registry — every message the platform can send."""
    return service.templates()


class TemplatePreviewRequest(BaseModel):
    channel: str = "sms"
    language: str | None = None
    variables: dict = {}


@notification_router.post("/notification-templates/{key}/preview", response_model=RenderedPreview)
async def preview_notification_template(
    key: str,
    body: TemplatePreviewRequest,
    request: Request,
    service: NotificationSvc,
    p: NotificationRead,
) -> RenderedPreview:
    """Render a template with supplied (or placeholder) variables."""
    await rate_limit.enforce(
        rate_limit.NOTIFICATION_PREVIEW,
        ip=client_ip(request),
        user=str(p.id),
        endpoint="notification-preview",
    )
    return service.preview(key, body.channel, body.language, body.variables)


@notification_router.get("/notifications/{notification_id}", response_model=NotificationView)
async def get_notification(
    notification_id: uuid.UUID, service: NotificationSvc, _: NotificationRead
) -> Any:
    return await service.get(notification_id)


@notification_router.post("/notifications/{notification_id}/retry", response_model=NotificationView)
async def retry_notification(
    notification_id: uuid.UUID, service: NotificationSvc, _: NotificationManage
) -> Any:
    """Retry a failed or dead notification now (bypasses the backoff wait)."""
    return await service.retry(notification_id)


@notification_router.post("/notifications/retry-pending")
async def retry_pending_notifications(service: NotificationSvc, _: NotificationManage) -> dict:
    """Run the due-retry sweep immediately (the background loop does this)."""
    return await service.retry_pending()


# --- Push devices (DEMO-012 §10) ---------------------------------------------
#
# Deliberately NOT behind `notification.manage`. A phone registers ITSELF, for
# the person holding it, so the grant that matters is "you are signed in" —
# requiring an administrative permission would mean no field user could ever
# be reached. The user id comes from the authenticated principal and is never
# read from the body: a client that could name the user it registers for could
# redirect another person's notifications to its own handset.


@notification_router.post("/notification-devices", response_model=PushDeviceView, status_code=201)
async def register_notification_device(
    command: RegisterPushDeviceCommand,
    service: NotificationSvc,
    principal: CurrentPrincipal,
) -> Any:
    """Register (or refresh) this handset for push. Idempotent by token."""
    return await service.register_device(principal.id, command, customer_id=principal.customer_id)


@notification_router.get("/notification-devices", response_model=list[PushDeviceView])
async def list_notification_devices(service: NotificationSvc, principal: CurrentPrincipal) -> Any:
    """This principal's own devices — never anybody else's, and never with the
    token."""
    return await service.list_devices(principal.id)


@notification_router.delete("/notification-devices/{device_id}", status_code=204)
async def revoke_notification_device(
    device_id: uuid.UUID, service: NotificationSvc, principal: CurrentPrincipal
) -> None:
    """Sign-out, or a handset the user no longer has."""
    await service.revoke_device(principal.id, device_id)


# --- Receipts (immutable proof of payment — RCP-001) -------------------------
receipt_router = APIRouter(prefix="/receipts", tags=["receipt"], route_class=IdempotentRoute)
ReceiptRead = Annotated[Principal, Depends(require_permission("receipt.read"))]
ReceiptManage = Annotated[Principal, Depends(require_permission("receipt.manage"))]
ReceiptDownload = Annotated[Principal, Depends(require_permission("receipt.download"))]
ReceiptSvc = Annotated[ReceiptService, Depends(deps.get_receipt_service)]


@receipt_router.get("", response_model=ReceiptPage)
async def search_receipts(
    service: ReceiptSvc,
    _: ReceiptRead,
    q: str | None = None,
    supplier_id: uuid.UUID | None = None,
    payment_id: uuid.UUID | None = None,
    status: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ReceiptPage:
    """Receipt history: search number/payment/supplier/reference, filter by
    status (generated | delivered | archived). Archived receipts stay listed —
    nothing is ever removed."""
    return await service.search(
        q=q,
        supplier_id=supplier_id,
        payment_id=payment_id,
        status=status,
        limit=limit,
        offset=offset,
    )


@receipt_router.get("/{receipt_id}", response_model=ReceiptDetailView)
async def get_receipt_detail(
    receipt_id: uuid.UUID, service: ReceiptSvc, _: ReceiptRead
) -> ReceiptDetailView:
    return await service.detail(receipt_id)


@receipt_router.get("/{receipt_id}/render", response_model=RenderedReceiptView)
async def render_receipt(
    receipt_id: uuid.UUID,
    service: ReceiptSvc,
    _: ReceiptRead,
    format: str = "json",
) -> RenderedReceiptView:
    """Preview: the rendered artifact as data (body + content type), for
    portal and mobile previews. PDF is a placeholder renderer."""
    return await service.render(receipt_id, format)


@receipt_router.get("/{receipt_id}/download")
async def download_receipt(
    receipt_id: uuid.UUID,
    service: ReceiptSvc,
    _: ReceiptDownload,
    format: str = "pdf",
) -> Response:
    """Serve the artifact as a file. Rendering is a pure derivation of an
    immutable record, so a download is reproducible forever."""
    _receipt, rendered = await service.render_artifact(receipt_id, format)
    return Response(
        content=rendered.body,
        media_type=rendered.content_type,
        headers={"Content-Disposition": f'attachment; filename="{rendered.filename}"'},
    )


@receipt_router.post("/{receipt_id}/deliver", response_model=ReceiptView)
async def deliver_receipt(receipt_id: uuid.UUID, service: ReceiptSvc, p: ReceiptManage) -> Any:
    """Record that the artifact reached the payee."""
    await service.deliver(receipt_id, actor_id=p.id)
    return (await service.detail(receipt_id)).receipt


@receipt_router.post("/{receipt_id}/archive", response_model=ReceiptView)
async def archive_receipt(receipt_id: uuid.UUID, service: ReceiptSvc, p: ReceiptManage) -> Any:
    """Terminal, but still queryable — a receipt is never deleted."""
    await service.archive(receipt_id, actor_id=p.id)
    return (await service.detail(receipt_id)).receipt


# --- Offline sync (device replay + read-only monitor — OFF-001) --------------
sync_router = APIRouter(prefix="/sync", tags=["sync"], route_class=IdempotentRoute)
# Replay reuses the ONLINE permission: offline never bypasses authorization.
SyncPush = Annotated[Principal, Depends(require_permission("collection.transaction.record"))]
SyncRead = Annotated[Principal, Depends(require_permission("sync.read"))]
SyncSvc = Annotated[SyncService, Depends(deps.get_sync_service)]


@sync_router.post("/collection", response_model=SyncBatchResult)
async def push_collection_batch(
    batch: SyncBatchInput, service: SyncSvc, p: SyncPush
) -> SyncBatchResult:
    """Replay a batch of operations captured offline.

    Each operation carries a client-generated `operation_id` (the idempotency
    key) so a lost acknowledgement re-sends safely, and optional
    `client_reference`/`target_ref` local ids so work created offline can be
    referred to before the server has ever seen it. Every operation is applied
    through the online collection service — the batch never bypasses a rule.
    Per-operation results carry structured conflicts; a partial batch is a
    normal outcome, not an error."""
    return await service.push(batch, actor_id=p.id)


@sync_router.get("/operations", response_model=SyncOperationPage)
async def list_sync_operations(
    service: SyncSvc,
    _: SyncRead,
    status: str | None = None,
    kind: str | None = None,
    device_id: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> SyncOperationPage:
    """Sync monitor: what devices have replayed, and how it went."""
    return await service.search(
        status=status, kind=kind, device_id=device_id, limit=limit, offset=offset
    )


@sync_router.get("/stats", response_model=SyncStatsView)
async def sync_stats(service: SyncSvc, _: SyncRead) -> SyncStatsView:
    """Totals by status and kind, per-device activity, last sync time."""
    return await service.stats()


@sync_router.post("/operations/{operation_id}/retry", response_model=SyncOperationView)
async def retry_sync_operation(
    operation_id: uuid.UUID, service: SyncSvc, p: SyncPush
) -> SyncOperationView:
    """Re-apply a FAILED operation from its stored payload. Conflicts are not
    retryable — they need a human decision — and applied operations never
    run twice."""
    return await service.retry(operation_id, actor_id=p.id)


# --- Operations: health, alerts, overview (OBS-001) --------------------------
ops_observability_router = APIRouter(
    prefix="/_ops", tags=["operations"], route_class=IdempotentRoute
)
OpsRead = Annotated[Principal, Depends(require_permission("platform.relay.manage"))]


class ComponentHealthView(BaseModel):
    name: str
    status: str
    detail: str
    data: dict
    duration_ms: float


class PlatformHealthView(BaseModel):
    status: str
    ready: bool
    checked_at: str
    components: list[ComponentHealthView]


class AlertView(BaseModel):
    name: str
    severity: str
    summary: str
    action: str
    runbook: str
    detail: str


class OverviewView(BaseModel):
    """One call that answers 'is the platform well, and if not, what do I do?'"""

    status: str
    ready: bool
    checked_at: str
    components: dict[str, str]
    alerts: list[AlertView]
    counts: dict[str, int]


def _health_view(snapshot) -> PlatformHealthView:
    return PlatformHealthView(
        status=snapshot.status,
        ready=snapshot.ready,
        checked_at=snapshot.checked_at,
        components=[
            ComponentHealthView(
                name=c.name,
                status=c.status,
                detail=c.detail,
                data=c.data,
                duration_ms=c.duration_ms,
            )
            for c in snapshot.components
        ],
    )


@ops_observability_router.get("/health", response_model=PlatformHealthView)
async def platform_health(_: OpsRead) -> PlatformHealthView:
    """Per-component health on the four-level scale. Unlike `/health/ready`,
    this says WHICH component is unwell and how."""
    return _health_view(await health.evaluate())


@ops_observability_router.get("/alerts", response_model=list[AlertView])
async def firing_alerts(_: OpsRead) -> list[AlertView]:
    """Alerts currently firing, worst first. Each carries the action to take —
    an alert without one is a notification."""
    snapshot = await health.evaluate()
    return [AlertView(**vars(alert)) for alert in alerts.evaluate(snapshot)]


@ops_observability_router.get("/alert-rules", response_model=list[dict])
async def alert_rules(_: OpsRead) -> list[dict]:
    """Every rule the platform can fire — the same definitions that drive the
    exported Prometheus rules, so the two cannot disagree."""
    return [
        {
            "name": rule.name,
            "severity": rule.severity,
            "summary": rule.summary,
            "action": rule.action,
            "runbook": rule.runbook,
        }
        for rule in alerts.RULES
    ]


@ops_observability_router.get("/backups/status", response_model=BackupStatusView)
async def backup_status(_: OpsRead) -> BackupStatusView:
    """Are we protected right now? Answered from the platform itself, not from
    a cron log on a host a disaster may have taken with it."""
    return await deps.get_backup_service().status()


@ops_observability_router.get("/backups", response_model=list[BackupRunView])
async def backup_history(
    _: OpsRead, kind: str | None = None, limit: int = Query(20, ge=1, le=100)
) -> Any:
    """Every backup, restore, and verification the platform has recorded."""
    return await deps.get_backup_service().history(kind=kind, limit=limit)


@ops_observability_router.get("/backups/classification", response_model=list[ClassificationView])
async def backup_classification(_: OpsRead) -> Any:
    """What is captured, what is rebuilt, and why — the decision behind the
    backup, visible rather than buried in a script."""
    return deps.get_backup_service().classification()


@ops_observability_router.post("/backups/verify-integrity", response_model=BackupRunView)
async def verify_integrity(_: OpsRead, deep: bool = False) -> Any:
    """Check the LIVE database against the platform's own business rules.

    Useful after a restore and useful on a schedule: silent corruption nobody
    checks for is corruption a farmer discovers. `deep` additionally rebuilds
    every projection from the event log and compares.

    NOTE: there is deliberately no restore endpoint. Restoring over live data
    is the most destructive operation the platform can perform, and it belongs
    to the CLI where it cannot be reached by a misrouted request.
    """
    service = deps.get_backup_service()
    run = await service.verify_integrity(deep=deep)
    return service._view(run)


@ops_observability_router.get("/overview", response_model=OverviewView)
async def system_overview(_: OpsRead) -> OverviewView:
    """The single screen an operator opens first."""
    snapshot = await health.evaluate()
    firing = alerts.evaluate(snapshot)
    return OverviewView(
        status=snapshot.status,
        ready=snapshot.ready,
        checked_at=snapshot.checked_at,
        components={c.name: c.status for c in snapshot.components},
        alerts=[AlertView(**vars(alert)) for alert in firing],
        counts={
            "critical": sum(1 for a in firing if a.severity == alerts.CRITICAL),
            "warning": sum(1 for a in firing if a.severity == alerts.WARNING),
            "info": sum(1 for a in firing if a.severity == alerts.INFO),
        },
    )


# --- Reports (read-only operational summaries — REP-001) --------------------
report_router = APIRouter(prefix="/reports", tags=["reporting"], route_class=IdempotentRoute)
ReportRead = Annotated[Principal, Depends(require_permission("reporting.read"))]
ReportSvc = Annotated[ReportingService, Depends(deps.get_reporting_service)]


@report_router.get("/collection/daily", response_model=DailyCollectionSummary)
async def report_daily_collection(
    service: ReportSvc,
    _: ReportRead,
    date_from: date | None = None,
    date_to: date | None = None,
    center_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    supplier_id: uuid.UUID | None = None,
) -> DailyCollectionSummary:
    """Answers: milk collected, payable amount, accepted/rejected counts,
    weighted average FAT/SNF — defaults to today."""
    return await service.daily_summary(
        date_from=date_from,
        date_to=date_to,
        center_id=center_id,
        branch_id=branch_id,
        supplier_id=supplier_id,
    )


@report_router.get("/collection/by-center", response_model=SummaryPage)
async def report_collection_by_center(
    service: ReportSvc,
    _: ReportRead,
    date_from: date | None = None,
    date_to: date | None = None,
    branch_id: uuid.UUID | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> SummaryPage:
    """Per-center collection totals, ordered by milk collected (desc)."""
    return await service.center_summary(
        date_from=date_from, date_to=date_to, branch_id=branch_id, limit=limit, offset=offset
    )


@report_router.get("/collection/by-supplier", response_model=SummaryPage)
async def report_collection_by_supplier(
    service: ReportSvc,
    _: ReportRead,
    date_from: date | None = None,
    date_to: date | None = None,
    center_id: uuid.UUID | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> SummaryPage:
    """Per-supplier collection totals, ordered by milk supplied (desc)."""
    return await service.supplier_summary(
        date_from=date_from, date_to=date_to, center_id=center_id, limit=limit, offset=offset
    )


@report_router.get("/settlements", response_model=SettlementSummary)
async def report_settlements(
    service: ReportSvc,
    _: ReportRead,
    date_from: date | None = None,
    date_to: date | None = None,
    supplier_id: uuid.UUID | None = None,
    center_id: uuid.UUID | None = None,
) -> SettlementSummary:
    return await service.settlement_summary(
        date_from=date_from, date_to=date_to, supplier_id=supplier_id, center_id=center_id
    )


# DEMO-002 — the dashboard's own aggregates.
#
# Every one of these answers a question the portal would otherwise have had to
# answer by pulling rows into a browser and adding them up. They are read-only,
# tenant-scoped through the same principal as every other route, and each is a
# fixed number of grouped queries.


@report_router.get("/dashboard", response_model=DashboardSummary)
async def report_dashboard(
    service: ReportSvc,
    _: ReportRead,
    date_from: date | None = None,
    date_to: date | None = None,
) -> DashboardSummary:
    """One round trip for the KPI block: collection, settlements, payments,
    sales, rate distribution, active counts and what needs attention."""
    return await service.dashboard(date_from=date_from, date_to=date_to)


# DEMO-010 — the sales side of the same block. Both are `reporting.read`,
# because a report is a report; what a role may SEE is decided by the
# permission registry, never by which module the numbers came from.


@report_router.get("/sales/summary", response_model=SalesSummary)
async def report_sales_summary(
    service: ReportSvc,
    _: ReportRead,
    date_from: date | None = None,
    date_to: date | None = None,
) -> SalesSummary:
    """Milk delivered and what it was worth, plus the receivable balance:
    invoiced, received, still owed, and what is delivered but unbilled."""
    return await service.sales_summary(date_from=date_from, date_to=date_to)


@report_router.get("/receivables", response_model=ReceivablesPage)
async def report_receivables(
    service: ReportSvc,
    _: ReportRead,
    q: str | None = None,
    owing_only: bool = True,
    limit: int = 20,
    offset: int = 0,
) -> ReceivablesPage:
    """Who owes money, worst first.

    Paginated and ordered in SQL, with `total_outstanding` computed across
    every match rather than the page — a page total would understate the debt
    of any dairy with more households than fit on one screen.
    """
    return await service.receivables(q=q, owing_only=owing_only, limit=limit, offset=offset)


@report_router.get("/collection/{transaction_id}/chain", response_model=CollectionChain)
async def report_collection_chain(
    transaction_id: uuid.UUID,
    service: ReportSvc,
    _: ReportRead,
) -> CollectionChain:
    """Where one collection's money went: settlement, payment, receipt.

    Each stage is null until it happens, which is what a timeline needs — a
    priced-but-unsettled collection must not look like an unpriced one.
    """
    return await service.collection_chain(transaction_id)


@report_router.get("/collection/operational-status", response_model=OperationalStatusPage)
async def report_operational_status(
    service: ReportSvc,
    _: ReportRead,
    transaction_ids: Annotated[
        list[uuid.UUID],
        Query(
            min_length=1,
            max_length=100,
            description=(
                "Repeated transaction id — one page's worth. Bounded at 100 so "
                "the query stays a fixed cost."
            ),
        ),
    ],
) -> OperationalStatusPage:
    """Settlement, payment, receipt and last activity for a PAGE of collections.

    DEMO-007: the operational transaction list needs these four facts per row.
    `/collection/{id}/chain` answers them one row at a time, which on a
    fifty-row page is fifty round trips — so this asks the same question in
    bulk and answers it in a fixed number of queries.

    Ids that do not exist, or belong to another organization, come back with
    every field null rather than as an error: absence is the honest answer,
    and a 404 here would confirm which ids exist.
    """
    return await service.operational_status(transaction_ids)


@report_router.get("/payments", response_model=PaymentSummary)
async def report_payments(
    service: ReportSvc,
    _: ReportRead,
    date_from: date | None = None,
    date_to: date | None = None,
    supplier_id: uuid.UUID | None = None,
) -> PaymentSummary:
    """Counts and money by payment status (DEMO-001 recorded this as missing)."""
    return await service.payment_summary(
        date_from=date_from, date_to=date_to, supplier_id=supplier_id
    )


@report_router.get("/collection/trend", response_model=CollectionTrend)
async def report_collection_trend(
    service: ReportSvc,
    _: ReportRead,
    date_from: date | None = None,
    date_to: date | None = None,
    center_id: uuid.UUID | None = None,
    supplier_id: uuid.UUID | None = None,
) -> CollectionTrend:
    """Quantity and value per day, with empty days present as zeroes."""
    return await service.collection_trend(
        date_from=date_from, date_to=date_to, center_id=center_id, supplier_id=supplier_id
    )


@report_router.get("/collection/by-rate", response_model=list[RateBandRow])
async def report_collection_by_rate(
    service: ReportSvc,
    _: ReportRead,
    date_from: date | None = None,
    date_to: date | None = None,
    center_id: uuid.UUID | None = None,
) -> list[RateBandRow]:
    """What was bought at each resolved unit price — the quality-band effect,
    read back off the transactions that were actually paid."""
    return await service.rate_distribution(
        date_from=date_from, date_to=date_to, center_id=center_id
    )


@report_router.get("/pricing", response_model=PricingSummary)
async def report_pricing(
    service: ReportSvc,
    _: ReportRead,
    date_from: date | None = None,
    date_to: date | None = None,
    center_id: uuid.UUID | None = None,
) -> PricingSummary:
    return await service.pricing_summary(date_from=date_from, date_to=date_to, center_id=center_id)


# --- Event relay (internal platform operations) -----------------------------
relay_router = APIRouter(prefix="/_relay", tags=["event-relay"], route_class=IdempotentRoute)
RelayOps = Annotated[Principal, Depends(require_permission("platform.relay.manage"))]
RelaySvc = Annotated[RelayService, Depends(deps.get_relay_service)]


@relay_router.get("/status", response_model=RelayStats)
async def relay_status(service: RelaySvc, _: RelayOps) -> RelayStats:
    return await service.stats()


@relay_router.get("/events", response_model=list[OutboxEventView])
async def relay_events(
    service: RelaySvc,
    _: RelayOps,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=200),
) -> Any:
    return await service.list_events(status=status, limit=limit)


@relay_router.get("/dead-letters", response_model=list[DeadLetterView])
async def relay_dead_letters(
    service: RelaySvc, _: RelayOps, limit: int = Query(50, ge=1, le=200)
) -> Any:
    return await service.list_dead_letters(limit=limit)


@relay_router.post("/dead-letters/{dead_letter_id}/replay", response_model=OutboxEventView)
async def relay_replay_dead_letter(
    dead_letter_id: uuid.UUID, service: RelaySvc, _: RelayOps
) -> Any:
    return await service.replay_dead_letter(dead_letter_id)


@relay_router.post("/events/{event_id}/retry", response_model=OutboxEventView)
async def relay_retry_event(event_id: uuid.UUID, service: RelaySvc, _: RelayOps) -> Any:
    return await service.retry_event(event_id)


@relay_router.post("/events/{event_id}/replay", response_model=OutboxEventView)
async def relay_replay_event(event_id: uuid.UUID, service: RelaySvc, _: RelayOps) -> Any:
    return await service.replay_delivered(event_id)


@relay_router.post("/dispatch")
async def relay_dispatch_now(service: RelaySvc, _: RelayOps) -> dict:
    delivered = await service.dispatch_pending()
    return {"delivered": delivered}


# --- Consumer framework operations (SPRINT-008B) ----------------------------
consumers_router = APIRouter(
    prefix="/_consumers", tags=["event-consumers"], route_class=IdempotentRoute
)
ConsumerRun = Annotated[ConsumerRunner, Depends(deps.get_consumer_runner)]


@consumers_router.get("/status", response_model=ConsumersHealth)
async def consumers_health(runner: ConsumerRun, _: RelayOps) -> ConsumersHealth:
    """Per-consumer health: lag behind the log head, execution counts, dead
    letters. Overall degraded when anything is dead or badly lagging."""
    return await runner.health()


@consumers_router.post("/run")
async def consumers_run_now(runner: ConsumerRun, _: RelayOps) -> dict:
    return await runner.run_once()


@consumers_router.get("/executions", response_model=list[ExecutionView])
async def consumer_executions(
    runner: ConsumerRun,
    _: RelayOps,
    consumer: str | None = None,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=200),
) -> Any:
    return await runner.list_executions(consumer_name=consumer, status=status, limit=limit)


@consumers_router.get("/dead-letters", response_model=list[ExecutionView])
async def consumer_dead_letters(
    runner: ConsumerRun,
    _: RelayOps,
    consumer: str | None = None,
    limit: int = Query(50, ge=1, le=200),
) -> Any:
    return await runner.list_executions(consumer_name=consumer, status="dead", limit=limit)


@consumers_router.post("/{name}/pause", response_model=ConsumerStatus)
async def pause_consumer(name: str, runner: ConsumerRun, _: RelayOps) -> Any:
    """Stop a consumer without losing its place. The cursor stays put, so
    resuming continues from exactly where it stopped."""
    return await runner.set_enabled(name, False)


@consumers_router.post("/{name}/resume", response_model=ConsumerStatus)
async def resume_consumer(name: str, runner: ConsumerRun, _: RelayOps) -> Any:
    """Resume a paused consumer. It works through the backlog from its cursor."""
    return await runner.set_enabled(name, True)


@consumers_router.post("/executions/{execution_id}/replay", response_model=ExecutionView)
async def replay_consumer_execution(
    execution_id: uuid.UUID, request: Request, runner: ConsumerRun, p: RelayOps
) -> Any:
    await rate_limit.enforce(
        rate_limit.CONSUMER_REPLAY,
        ip=client_ip(request),
        user=str(p.id),
        endpoint="consumer-replay",
    )
    return await runner.replay_execution(execution_id)


# --- Projection lifecycle operations (PLT-001) ------------------------------
projections_router = APIRouter(
    prefix="/_projections", tags=["projections"], route_class=IdempotentRoute
)
Rebuilder = Annotated[ProjectionRebuilder, Depends(deps.get_projection_rebuilder)]


@projections_router.get("", response_model=list[ProjectionStatus])
async def list_projections(rebuilder: Rebuilder, _: RelayOps) -> Any:
    """Registry: every discovered projection with its version, derived
    position, processed/pending counts, row counts, rebuild story, health."""
    return await rebuilder.status_all()


@projections_router.post("/rebuild-all", response_model=list[RebuildResult])
async def rebuild_all_projections(
    request: Request,
    rebuilder: Rebuilder,
    p: RelayOps,
    dry_run: bool = False,
    batch_size: int = 500,
) -> Any:
    """Rebuild every projection in declared replay order."""
    await rate_limit.enforce(
        rate_limit.PROJECTION_REBUILD,
        ip=client_ip(request),
        user=str(p.id),
        endpoint="projection-rebuild",
    )
    return await rebuilder.rebuild_all(dry_run=dry_run, batch_size=batch_size)


@projections_router.get("/{name}", response_model=ProjectionStatus)
async def get_projection_status(name: str, rebuilder: Rebuilder, _: RelayOps) -> Any:
    return await rebuilder.status(name)


@projections_router.post("/{name}/rebuild", response_model=RebuildResult)
async def rebuild_projection(
    name: str,
    request: Request,
    rebuilder: Rebuilder,
    p: RelayOps,
    dry_run: bool = False,
    batch_size: int = 500,
) -> Any:
    """Replay the event log into this projection. `dry_run=true` reports the
    work and an ETA without touching data."""
    await rate_limit.enforce(
        rate_limit.PROJECTION_REBUILD,
        ip=client_ip(request),
        user=str(p.id),
        endpoint="projection-rebuild",
    )
    return await rebuilder.rebuild(name, dry_run=dry_run, batch_size=batch_size)


@projections_router.post("/{name}/cancel", response_model=ProjectionStatus)
async def cancel_projection_rebuild(name: str, rebuilder: Rebuilder, _: RelayOps) -> Any:
    """Stop a running rebuild after its current batch."""
    return await rebuilder.cancel(name)


@projections_router.post("/{name}/verify", response_model=VerificationResult)
async def verify_projection(
    name: str, rebuilder: Rebuilder, _: RelayOps, deep: bool = False
) -> Any:
    """Integrity checks (version, corrupted replay, missing events, dead
    letters, duplicate rows, gaps). `deep=true` adds drift detection by
    shadow-replaying the log in a rolled-back transaction."""
    return await rebuilder.verify(name, deep=deep)


@projections_router.delete("/{name}/reset", response_model=ResetResult)
async def reset_projection(name: str, rebuilder: Rebuilder, _: RelayOps) -> Any:
    """Clear derived rows and consumer position; the runner rebuilds it."""
    return await rebuilder.reset(name)


# --- Authorization --------------------------------------------------------
authz_router = APIRouter(prefix="/authz", tags=["authz"], route_class=IdempotentRoute)


@authz_router.get("/permissions")
async def list_permissions(_: CurrentPrincipal) -> dict[str, str]:
    return PERMISSIONS


class CreateRoleRequest(BaseModel):
    name: str
    permission_keys: list[str]


class RoleView(BaseModel):
    """A role as it actually exists, for the administration screen.

    DEMO-008 §10: there was no way to READ the roles, which is why the portal
    hard-coded a list of three names — one of which (`tenant-operator`) the
    backend had never had, so the page offered a role that could not be
    granted. A screen can only stop inventing roles once it can ask for them.
    """

    id: uuid.UUID
    name: str
    description: str
    #: NULL for a system role shared by every organization; set for a role
    #: this organization defined for itself.
    tenant_id: uuid.UUID | None
    system: bool
    permissions: list[str]
    #: How many grants reference it — an administrator must not remove the
    #: last role that lets anyone in.
    assignments: int


@authz_router.get("/roles", response_model=list[RoleView])
async def list_roles(
    session: deps.Session,
    principal: Annotated[Principal, Depends(require_permission("authz.role.read"))],
) -> list[RoleView]:
    """Roles visible to the caller: the system roles, plus their own tenant's.

    Another organization's custom roles are not listed — the same tenant rule
    every other collection follows.
    """
    from platform_core.modules.authz.models import Role, RolePermission, UserRole

    roles = (
        await session.scalars(
            select(Role)
            .where((Role.tenant_id.is_(None)) | (Role.tenant_id == principal.tenant_id))
            .order_by(Role.tenant_id.is_(None).desc(), Role.name)
        )
    ).all()
    ids = [r.id for r in roles]
    grants: dict[uuid.UUID, list[str]] = {}
    counts: dict[uuid.UUID, int] = {}
    if ids:
        for role_id, key in (
            await session.execute(
                select(RolePermission.role_id, RolePermission.permission_key).where(
                    RolePermission.role_id.in_(ids)
                )
            )
        ).all():
            grants.setdefault(role_id, []).append(key)
        for role_id, count in (
            await session.execute(
                select(UserRole.role_id, func.count())
                .where(
                    UserRole.role_id.in_(ids),
                    (UserRole.tenant_id == principal.tenant_id) | (UserRole.tenant_id.is_(None)),
                )
                .group_by(UserRole.role_id)
            )
        ).all():
            counts[role_id] = count
    return [
        RoleView(
            id=role.id,
            name=role.name,
            description=role.description,
            tenant_id=role.tenant_id,
            system=role.tenant_id is None,
            permissions=sorted(grants.get(role.id, [])),
            assignments=counts.get(role.id, 0),
        )
        for role in roles
    ]


@authz_router.post("/roles", status_code=201)
async def create_role(
    body: CreateRoleRequest,
    service: Annotated[AuthzService, Depends(deps.get_authz_service)],
    principal: Annotated[Principal, Depends(require_permission("authz.role.manage"))],
) -> dict:
    role = await service.create_role(
        tenant_id=principal.tenant_id, name=body.name, permission_keys=body.permission_keys
    )
    return {"id": str(role.id), "name": role.name}


class AssignRoleRequest(BaseModel):
    user_id: uuid.UUID
    role_name: str
    #: DEMO-008 — limit this grant to one collection centre. Omit for
    #: organization-wide, which is what every grant meant before.
    center_id: uuid.UUID | None = None


@authz_router.post("/assignments", status_code=201)
async def assign_role(
    body: AssignRoleRequest,
    service: Annotated[AuthzService, Depends(deps.get_authz_service)],
    principal: Annotated[Principal, Depends(require_permission("authz.role.manage"))],
) -> dict:
    assignment = await service.assign_role(
        user_id=body.user_id,
        role_name=body.role_name,
        tenant_id=principal.tenant_id,
        center_id=body.center_id,
        actor_id=principal.id,
    )
    return {"id": str(assignment.id)}


@authz_router.delete("/assignments", status_code=204)
async def revoke_role(
    user_id: uuid.UUID,
    role_name: str,
    service: Annotated[AuthzService, Depends(deps.get_authz_service)],
    principal: Annotated[Principal, Depends(require_permission("authz.role.manage"))],
) -> None:
    """Take a role back (SEC-003 / F-02).

    Query parameters rather than a body: DELETE bodies are legal but widely
    dropped by proxies, and this is the one verb where a silently discarded
    body would look like a successful revocation.

    204 whether or not the user held the role — the caller asked for an end
    state, and after this call the end state holds.
    """
    await service.revoke_role(
        user_id=user_id,
        role_name=role_name,
        tenant_id=principal.tenant_id,
        actor_id=principal.id,
    )


# --- Configuration --------------------------------------------------------
config_router = APIRouter(prefix="/config", tags=["configuration"], route_class=IdempotentRoute)


@config_router.get("/{key}")
async def get_config(
    key: str,
    service: Annotated[ConfigurationService, Depends(deps.get_configuration_service)],
    _: Annotated[Principal, Depends(require_permission("configuration.read"))],
) -> dict:
    return {"key": key, "value": await service.resolve(key)}


class SetConfigRequest(BaseModel):
    value: Any
    scope: str = "tenant"  # "tenant" | "global" (global requires platform admin in practice)


@config_router.put("/{key}")
async def set_config(
    key: str,
    body: SetConfigRequest,
    service: Annotated[ConfigurationService, Depends(deps.get_configuration_service)],
    principal: Annotated[Principal, Depends(require_permission("configuration.write"))],
) -> dict:
    await service.set_value(key, body.value, scope=body.scope, actor_id=principal.id)
    return {"key": key, "scope": body.scope, "status": "saved"}


# --- Audit ----------------------------------------------------------------
audit_router = APIRouter(prefix="/audit", tags=["audit"], route_class=IdempotentRoute)


@audit_router.get("", response_model=AuditPage)
async def list_audit(
    service: Annotated[deps.AuditService, Depends(deps.get_audit_service)],
    _: Annotated[Principal, Depends(require_permission("audit.read"))],
    q: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    actor_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> AuditPage:
    """Who did what, to which resource, when — filtered and paged.

    DEMO-007 replaced the unfiltered "newest 100" read: a screen that can only
    show the most recent hundred entries cannot answer an operational question,
    and filtering the rest in a browser would be wrong as soon as the hundred
    and first record existed.
    """
    return await service.search(
        q=q,
        action=action,
        resource_type=resource_type,
        actor_id=actor_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )


@audit_router.get("/actions", response_model=list[str])
async def list_audit_actions(
    service: Annotated[deps.AuditService, Depends(deps.get_audit_service)],
    _: Annotated[Principal, Depends(require_permission("audit.read"))],
) -> list[str]:
    """The action vocabulary present in this tenant's own history."""
    return await service.actions()


# --- tenant lifecycle (PROD-001) --------------------------------------------


class OffboardTenantRequest(BaseModel):
    """The confirmation gate. A boolean is too easy to send by accident from a
    script; typing the organization's name is the smallest gesture that cannot
    be made without meaning it."""

    confirmation: str = Field(min_length=1, max_length=200)


tenant_data_router = APIRouter(
    prefix="/tenant-data", tags=["tenant-lifecycle"], route_class=IdempotentRoute
)
TenantExport = Annotated[Principal, Depends(require_permission("organization.data.export"))]
TenantDelete = Annotated[Principal, Depends(require_permission("organization.data.delete"))]


def _lifecycle(session: deps.Session) -> TenantLifecycleService:
    return TenantLifecycleService(session)


Lifecycle = Annotated[TenantLifecycleService, Depends(_lifecycle)]


@tenant_data_router.get("/export")
async def export_tenant_data(service: Lifecycle, p: TenantExport, session: deps.Session) -> Any:
    """Everything the platform holds for the caller's tenant, as portable JSON.

    The tenant is taken from the authenticated principal and never from a
    parameter — there is no request shape that can ask for another tenant's
    data, which is a stronger guarantee than checking that it matches.
    """
    tenant_id = require_current_tenant()
    payload = await service.export(tenant_id)
    await record_security_event(
        session,
        action="tenant.data.exported",
        subject=str(tenant_id),
        actor_id=p.id,
        detail={"rows": payload["row_count"], "tables": payload["table_count"]},
    )
    return payload


@tenant_data_router.get("/offboarding-plan")
async def tenant_offboarding_plan(service: Lifecycle, _: TenantDelete) -> Any:
    """What offboarding WOULD do. Non-destructive, always available."""
    plan = await service.plan(require_current_tenant())
    return {
        "tenant_id": str(plan.tenant_id),
        "organization_name": plan.organization_name,
        "total_rows": plan.total_rows,
        "row_counts": plan.row_counts,
        "purge": [{"table": t.table, "reason": t.reason} for t in plan.purge],
        "anonymize": [
            {"table": t.table, "columns": list(t.columns), "reason": t.reason}
            for t in plan.anonymize
        ],
        "retain": [{"table": t.table, "reason": t.reason} for t in plan.retain],
        "confirmation_required": plan.organization_name,
    }


@tenant_data_router.post("/offboard", status_code=200)
async def offboard_tenant(
    body: OffboardTenantRequest,
    service: Lifecycle,
    p: TenantDelete,
    session: deps.Session,
) -> Any:
    """Irreversibly offboard the caller's tenant.

    Requires the organization's exact name as confirmation. Operational data is
    purged, financial and audit records are anonymized and kept, and the
    organization becomes a tombstone — see core/tenant_lifecycle.py for why
    those three treatments exist rather than one DELETE.
    """
    tenant_id = require_current_tenant()
    plan = await service.execute(tenant_id, confirmation=body.confirmation, actor_id=p.id)
    await record_security_event(
        session,
        action="tenant.data.offboarded",
        subject=str(tenant_id),
        actor_id=p.id,
        detail={"rows": plan.total_rows, "purged_tables": len(plan.purge)},
    )
    return {
        "tenant_id": str(tenant_id),
        "status": "offboarded",
        "rows_affected": plan.total_rows,
        "purged_tables": [t.table for t in plan.purge],
        "anonymized_tables": [t.table for t in plan.anonymize],
        "retained_tables": [t.table for t in plan.retain],
    }


# --- Sales: customers, deliveries, billing (DEMO-009 / CAP-0006 CMA) --------
#
# A separate vocabulary from procurement, deliberately. `sales.*` permissions
# guard these routes so that the right to record a milk DELIVERY is not the
# same grant as the right to record a milk COLLECTION.

customer_router = APIRouter(
    prefix="/customers", tags=["sales-customer"], route_class=IdempotentRoute
)
CustomerRead = Annotated[Principal, Depends(require_permission("sales.customer.read"))]
CustomerManage = Annotated[Principal, Depends(require_permission("sales.customer.manage"))]
CustomerSvc = Annotated[CustomerService, Depends(deps.get_customer_service)]


@customer_router.post("", response_model=CustomerView, status_code=201)
async def create_customer(
    cmd: CreateCustomerCommand, service: CustomerSvc, p: CustomerManage
) -> Any:
    return await service.create(cmd, actor_id=p.id)


@customer_router.get("", response_model=CustomerPage)
async def search_customers(
    service: CustomerSvc,
    _: CustomerRead,
    q: str | None = None,
    status: str | None = None,
    customer_type: str | None = None,
    # P1-PORTAL-SCALE-001: batch display-name resolution (see suppliers).
    ids: Annotated[list[uuid.UUID] | None, Query(max_length=100)] = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> CustomerPage:
    """Customers, filtered by the database — name, code or phone."""
    return await service.search(
        q=q, status=status, customer_type=customer_type, ids=ids, limit=limit, offset=offset
    )


@customer_router.post("/import", response_model=list[CustomerImportRowResult])
async def import_customers(body: ImportRequest, service: CustomerSvc, p: CustomerManage) -> Any:
    """P0-PILOT-002: outlet-list onboarding, mirroring `/suppliers/import` —
    per-row validation, inline standing orders, one bad row never fails the
    batch. Declared before the `/{customer_id}` routes so the literal path
    wins the match."""
    return await service.import_rows(body.rows, actor_id=p.id)


@customer_router.get("/{customer_id}", response_model=CustomerDetailView)
async def get_customer(customer_id: uuid.UUID, service: CustomerSvc, _: CustomerRead) -> Any:
    return await service.detail(customer_id)


@customer_router.put("/{customer_id}", response_model=CustomerView)
async def update_customer(
    customer_id: uuid.UUID, cmd: UpdateCustomerCommand, service: CustomerSvc, p: CustomerManage
) -> Any:
    return await service.update(customer_id, cmd, actor_id=p.id)


class CustomerStatusRequest(BaseModel):
    status: str


@customer_router.post("/{customer_id}/status", response_model=CustomerView)
async def set_customer_status(
    customer_id: uuid.UUID,
    body: CustomerStatusRequest,
    service: CustomerSvc,
    p: CustomerManage,
) -> Any:
    return await service.set_status(customer_id, body.status, actor_id=p.id)


@customer_router.post("/{customer_id}/plan", response_model=DeliveryPlanView, status_code=201)
async def set_delivery_plan(
    customer_id: uuid.UUID, body: DeliveryPlanInput, service: CustomerSvc, p: CustomerManage
) -> Any:
    """Agree what this customer takes, at what rate, and on which days.

    Supersedes the previous plan rather than editing it, so a delivery priced
    last week remains explainable — and so DEMO-016 §8 holds for free: changing
    a schedule creates a new row and history keeps pointing at the plan that
    generated it.
    """
    plan = await service.set_plan(customer_id, body, actor_id=p.id)
    return service.plan_view(plan, today=await service.business_today())


@customer_router.post("/plans/{plan_id}/pause", response_model=DeliveryPlanView)
async def pause_delivery_plan(
    plan_id: uuid.UUID, body: PausePlanCommand, service: CustomerSvc, p: CustomerManage
) -> Any:
    """Send a standing order on holiday. Generates nothing inside the window.

    Historical deliveries are untouched: the customer is coming back, and
    their August is still their August (§7).
    """
    plan = await service.pause_plan(plan_id, body, actor_id=p.id)
    return service.plan_view(plan, today=await service.business_today())


@customer_router.post("/plans/{plan_id}/resume", response_model=DeliveryPlanView)
async def resume_delivery_plan(plan_id: uuid.UUID, service: CustomerSvc, p: CustomerManage) -> Any:
    """Back from holiday. Does NOT backfill the days that were paused."""
    plan = await service.resume_plan(plan_id, actor_id=p.id)
    return service.plan_view(plan, today=await service.business_today())


delivery_router = APIRouter(tags=["sales-delivery"], route_class=IdempotentRoute)
DeliveryRead = Annotated[Principal, Depends(require_permission("sales.delivery.read"))]
DeliveryRecord = Annotated[Principal, Depends(require_permission("sales.delivery.record"))]
DeliveryGenerate = Annotated[Principal, Depends(require_permission("sales.delivery.generate"))]
DeliverySvc = Annotated[DeliveryService, Depends(deps.get_delivery_service)]


@delivery_router.post("/deliveries", response_model=DeliveryView, status_code=201)
async def record_delivery(
    cmd: RecordDeliveryCommand, service: DeliverySvc, p: DeliveryRecord
) -> Any:
    """Record one delivery.

    The rate comes from the customer's active plan and the amount is computed
    by the domain — neither is accepted from the client.
    """
    return await service.record(cmd, actor_id=p.id)


@delivery_router.get("/deliveries", response_model=DeliveryPage)
async def search_deliveries(
    service: DeliverySvc,
    _: DeliveryRead,
    customer_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    status: str | None = None,
    invoiced: bool | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> DeliveryPage:
    """Delivery history. The totals cover the whole filtered set, not the page."""
    return await service.search(
        customer_id=customer_id,
        date_from=date_from,
        date_to=date_to,
        status=status,
        invoiced=invoiced,
        limit=limit,
        offset=offset,
    )


@delivery_router.get("/deliveries/report", response_model=DeliveryReport)
async def delivery_report(
    service: DeliverySvc,
    session: deps.Session,
    _: DeliveryRead,
    date_from: date | None = None,
    date_to: date | None = None,
    customer_id: uuid.UUID | None = None,
) -> DeliveryReport:
    """ "What was delivered, and what is it worth?" — aggregated in SQL.

    DEMO-013: the dates became OPTIONAL, defaulting to the organization's
    today. That is not a convenience — it is the only way a client can ask for
    "today" correctly. A phone cannot compute an IANA calendar date without
    shipping a timezone database, and if it used its own clock a rider who had
    crossed a border, or whose handset was on the wrong setting, would file the
    round under the wrong day. The platform knows the dairy's zone; asking it
    is cheaper and right.

    The response echoes the dates it used, so a client can label the screen
    with the day it actually got.
    """

    # DEMO-037: the route breakdown is composed HERE, at the API, by handing the
    # report a callable that answers "which households does each route visit?".
    # The delivery module still knows nothing about routes, and a dairy with
    # none gets an empty list and a report identical to the one it got before.
    async def membership() -> list[RouteMembership]:
        return await route_memberships(session, require_current_tenant())

    return await service.report(
        date_from=date_from,
        date_to=date_to,
        customer_id=customer_id,
        route_membership=membership,
    )


class GenerateDeliveriesRequest(BaseModel):
    """Optional. Omit the date and the platform uses the dairy's own today."""

    for_date: date | None = None


@delivery_router.post("/deliveries/generate", response_model=GenerationResult)
async def generate_deliveries(
    body: GenerateDeliveriesRequest, service: DeliverySvc, p: DeliveryGenerate
) -> Any:
    """Turn today's standing orders into the day's round (DEMO-016).

    Safe to run more than once, and safe to run concurrently: idempotency is a
    unique constraint in the database, not a check in this process, so a second
    call returns `created: 0, already_present: N` rather than a duplicated
    round.

    Its own permission, separate from `sales.delivery.record`: recording is
    what a rider does all morning, and this creates a whole dairy's day.
    """
    return await service.generate(for_date=body.for_date, actor_id=p.id)


@delivery_router.get("/deliveries/generation-runs", response_model=list[GenerationRunView])
async def delivery_generation_runs(
    service: DeliverySvc, _: DeliveryRead, limit: int = Query(14, ge=1, le=60)
) -> Any:
    """What the scheduler has been doing (DEMO-017 §10).

    Newest first. `sales.delivery.read` rather than the generate grant: seeing
    whether this morning's round went out is something anyone who can read the
    round should be able to check, including the person who cannot run it.
    """
    return await service.generation_runs(limit=limit)


@delivery_router.get("/deliveries/report.csv")
async def delivery_report_csv(
    service: DeliverySvc,
    _: DeliveryRead,
    date_from: date | None = None,
    date_to: date | None = None,
    customer_id: uuid.UUID | None = None,
    status: str | None = None,
) -> Response:
    """The same report, as a file somebody can open (DEMO-015 §15).

    Declared BEFORE `/deliveries/{delivery_id}`, because FastAPI matches in
    declaration order and `report.csv` is not a UUID — routed the other way
    round this endpoint would answer 422 forever.

    The totals row is the platform's aggregate, not a sum of the lines above
    it, so the file and the screen cannot disagree.
    """
    export = await service.export(
        date_from=date_from, date_to=date_to, customer_id=customer_id, status=status
    )
    return Response(
        content=to_csv(export),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{export_filename(export)}"'},
    )


@delivery_router.get("/deliveries/{delivery_id}", response_model=DeliveryView)
async def get_delivery(delivery_id: uuid.UUID, service: DeliverySvc, _: DeliveryRead) -> Any:
    return await service.get(delivery_id)


@delivery_router.post("/deliveries/{delivery_id}/amend", response_model=DeliveryView)
async def amend_delivery(
    delivery_id: uuid.UUID, cmd: AmendDeliveryCommand, service: DeliverySvc, p: DeliveryRecord
) -> Any:
    return await service.amend(delivery_id, cmd, actor_id=p.id)


# --- Logistics: routes, fleet and the daily run (DEMO-034 / CAP-0003 MCL) ----
#
# Its own router because a route is not a sale. Six endpoints and no more:
# route management, the fleet lists, and a run's creation, assignment,
# retrieval and status. Everything a screen shows about a run is composed by
# the service at read time, so there is no per-stop endpoint to add — the
# delivery domain already owns what happened at a stop.

logistics_router = APIRouter(tags=["logistics"], route_class=IdempotentRoute)
RouteRead = Annotated[Principal, Depends(require_permission("logistics.route.read"))]
RouteManage = Annotated[Principal, Depends(require_permission("logistics.route.manage"))]
FleetRead = Annotated[Principal, Depends(require_permission("logistics.fleet.read"))]
FleetManage = Annotated[Principal, Depends(require_permission("logistics.fleet.manage"))]
RunRead = Annotated[Principal, Depends(require_permission("logistics.run.read"))]
RunManage = Annotated[Principal, Depends(require_permission("logistics.run.manage"))]
# P0-MOB-001: the driver's own grant. Distinct from RunManage (the office) and
# from the sales operator's DeliveryRecord — the personas must not collapse.
RunExecute = Annotated[Principal, Depends(require_permission("logistics.run.execute"))]
LogisticsSvc = Annotated[LogisticsService, Depends(deps.get_logistics_service)]


@logistics_router.post("/routes", response_model=RouteView, status_code=201)
async def create_route(
    body: RouteInput, service: LogisticsSvc, audit: deps.Audit, p: RouteManage
) -> Any:
    """Create a round. Its stops are set separately, by `PUT /routes/{id}/stops`."""
    route = await service.create_route(body, actor_id=p.id, audit=audit)
    return RouteView.model_validate(route)


@logistics_router.get("/routes", response_model=list[RouteView])
async def list_routes(service: LogisticsSvc, p: RouteRead, active: bool | None = None) -> Any:
    return await service.list_routes(active=active)


@logistics_router.get("/routes/{route_id}", response_model=RouteDetailView)
async def get_route(route_id: uuid.UUID, service: LogisticsSvc, p: RouteRead) -> Any:
    return await service.get_route(route_id)


@logistics_router.put("/routes/{route_id}/stops", response_model=RouteDetailView)
async def set_route_stops(
    route_id: uuid.UUID,
    body: RouteStopsInput,
    service: LogisticsSvc,
    audit: deps.Audit,
    p: RouteManage,
) -> Any:
    """Replace the route's stops with this ordered list.

    A PUT because the ORDER is the payload: an operator dragging stops into
    sequence sends the sequence, and add/remove endpoints would need a third
    one to reorder.
    """
    return await service.set_stops(route_id, body.customer_ids, actor_id=p.id, audit=audit)


@logistics_router.post("/vehicles", response_model=VehicleView, status_code=201)
async def create_vehicle(
    body: VehicleInput, service: LogisticsSvc, audit: deps.Audit, p: FleetManage
) -> Any:
    vehicle = await service.create_vehicle(body, actor_id=p.id, audit=audit)
    return VehicleView.model_validate(vehicle)


@logistics_router.get("/vehicles", response_model=list[VehicleView])
async def list_vehicles(service: LogisticsSvc, p: FleetRead, active: bool | None = None) -> Any:
    return await service.list_vehicles(active=active)


@logistics_router.post("/drivers", response_model=DriverView, status_code=201)
async def create_driver(
    body: DriverInput, service: LogisticsSvc, audit: deps.Audit, p: FleetManage
) -> Any:
    driver = await service.create_driver(body, actor_id=p.id, audit=audit)
    return DriverView.model_validate(driver)


@logistics_router.get("/drivers", response_model=list[DriverView])
async def list_drivers(service: LogisticsSvc, p: FleetRead, active: bool | None = None) -> Any:
    return await service.list_drivers(active=active)


@logistics_router.get("/drivers/me", response_model=DriverView)
async def my_driver_profile(service: LogisticsSvc, p: RunExecute) -> Any:
    """The caller's own driver profile (P0-MOB-001).

    404 when the login is not linked to a driver — which is how the app tells
    "you are not set up as a driver yet" apart from "no run assigned today".
    """
    driver = await service.driver_for_user(p.id)
    if driver is None:
        raise NotFoundError("no driver profile is linked to this login")
    return DriverView.model_validate(driver)


@logistics_router.post("/drivers/{driver_id}/user", response_model=DriverView)
async def link_driver_user(
    driver_id: uuid.UUID,
    body: DriverUserLink,
    service: LogisticsSvc,
    audit: deps.Audit,
    p: FleetManage,
) -> Any:
    """Give a driver a login, or clear it (P0-MOB-001). Office action, audited.

    One login drives at most one active driver — a second link is refused, not
    silently rehomed.
    """
    return await service.link_driver_user(driver_id, body.user_id, actor_id=p.id, audit=audit)


@logistics_router.get("/delivery-runs/mine", response_model=list[RunView])
async def my_delivery_runs(service: LogisticsSvc, p: RunExecute) -> Any:
    """Today's runs for the caller's own driver profile — the DAIRY's today.

    Declared BEFORE `/delivery-runs/{run_id}`, because FastAPI matches in
    declaration order and "mine" is not a UUID.
    """
    return await service.my_runs(user_id=p.id)


@logistics_router.post("/delivery-runs/{run_id}/start", response_model=RunView)
async def start_my_run(
    run_id: uuid.UUID, service: LogisticsSvc, audit: deps.Audit, p: RunExecute
) -> Any:
    """The driver starts their own run. BR-0028 still guards it; another
    driver's run is a 404."""
    return await service.start_my_run(run_id, user_id=p.id, audit=audit)


@logistics_router.post("/delivery-runs/{run_id}/complete", response_model=RunView)
async def complete_my_run(
    run_id: uuid.UUID, service: LogisticsSvc, audit: deps.Audit, p: RunExecute
) -> Any:
    """The driver closes their own round."""
    return await service.complete_my_run(run_id, user_id=p.id, audit=audit)


@logistics_router.post(
    "/delivery-runs/{run_id}/stops/{customer_id}/outcome",
    response_model=RunStopView,
    status_code=201,
)
async def record_stop_outcome(
    run_id: uuid.UUID,
    customer_id: uuid.UUID,
    body: StopOutcomeInput,
    service: LogisticsSvc,
    audit: deps.Audit,
    p: RunExecute,
) -> Any:
    """What happened at one stop, said by the driver who was there (P0-MOB-002).

    The narrow door that keeps the broad sales grant off a driver: own run,
    open run, customer on the route, the RUN's date and slot — then the
    delivery domain records it exactly as the operator's round, same
    idempotency (this router is an `IdempotentRoute`), same fill-in of a
    generated row, same money rules (none here: the platform prices it).
    """
    return await service.record_stop_outcome(run_id, customer_id, body, user_id=p.id, audit=audit)


@logistics_router.post("/delivery-runs", response_model=RunView, status_code=201)
async def create_delivery_run(
    body: RunInput, service: LogisticsSvc, audit: deps.Audit, p: RunManage
) -> Any:
    """Plan one route's round for one of the DAIRY's days.

    Omit `business_date` and the platform resolves the organization's today. A
    phone in Nairobi and a browser in Delhi must both get the dairy's date.
    """
    return await service.create_run(body, actor_id=p.id, audit=audit)


@logistics_router.get("/delivery-runs", response_model=list[RunView])
async def list_delivery_runs(
    service: LogisticsSvc,
    p: RunRead,
    business_date: date | None = None,
    route_id: uuid.UUID | None = None,
    status: str | None = None,
    driver_id: uuid.UUID | None = None,
) -> Any:
    """Today's runs by default — the dairy's today, not the caller's."""
    return await service.list_runs(
        business_date=business_date, route_id=route_id, status=status, driver_id=driver_id
    )


@logistics_router.get("/delivery-runs/{run_id}", response_model=RunView)
async def get_delivery_run(run_id: uuid.UUID, service: LogisticsSvc, p: RunRead) -> Any:
    """The run with its ordered stops and each stop's delivery outcome."""
    return await service.get_run(run_id)


@logistics_router.post(
    "/delivery-runs/{run_id}/generate", response_model=RunGenerationView, status_code=201
)
async def generate_delivery_run(
    run_id: uuid.UUID,
    service: LogisticsSvc,
    audit: deps.Audit,
    p: RunManage,
) -> Any:
    """Generate the deliveries this run's route is for (DEMO-035).

    Idempotent: calling it twice creates the round once and reports
    `created: 0` the second time, because `uq_delivery_customer_date_slot` and
    the generator's ON CONFLICT DO NOTHING decide — not a check in Python.

    Behind `logistics.run.manage`, which is the roundsman's grant. It creates
    `scheduled` deliveries worth 0.00 that become billable only when somebody
    says the milk arrived, so it moves no money.
    """
    return await service.generate_for_run(run_id, actor_id=p.id, audit=audit)


@logistics_router.post("/delivery-runs/{run_id}/assignment", response_model=RunView)
async def assign_delivery_run(
    run_id: uuid.UUID,
    body: RunAssignment,
    service: LogisticsSvc,
    audit: deps.Audit,
    p: RunManage,
) -> Any:
    """Put a vehicle and a driver on the run. Omitting one leaves it alone."""
    return await service.assign(run_id, body, actor_id=p.id, audit=audit)


@logistics_router.post("/delivery-runs/{run_id}/status", response_model=RunView)
async def set_delivery_run_status(
    run_id: uuid.UUID,
    body: RunStatusInput,
    service: LogisticsSvc,
    audit: deps.Audit,
    p: RunManage,
) -> Any:
    """Move the run along. Completing it creates NO financial record."""
    return await service.set_run_status(run_id, body.status, actor_id=p.id, audit=audit)


billing_router = APIRouter(tags=["sales-billing"], route_class=IdempotentRoute)
InvoiceRead = Annotated[Principal, Depends(require_permission("sales.invoice.read"))]
InvoiceManage = Annotated[Principal, Depends(require_permission("sales.invoice.manage"))]
InvoiceIssue = Annotated[Principal, Depends(require_permission("sales.invoice.issue"))]
CustomerPaymentRead = Annotated[Principal, Depends(require_permission("sales.payment.read"))]
CustomerPaymentRecord = Annotated[Principal, Depends(require_permission("sales.payment.record"))]
CustomerReceiptRead = Annotated[Principal, Depends(require_permission("sales.receipt.read"))]
BillingSvc = Annotated[BillingService, Depends(deps.get_billing_service)]


@billing_router.post("/invoices", response_model=InvoiceView, status_code=201)
async def generate_invoice(
    cmd: GenerateInvoiceCommand, service: BillingSvc, p: InvoiceManage
) -> Any:
    """Build a draft statement from the period's unbilled deliveries."""
    return await service.generate_invoice(cmd, actor_id=p.id)


@billing_router.get("/invoices", response_model=InvoicePage)
async def search_invoices(
    service: BillingSvc,
    _: InvoiceRead,
    customer_id: uuid.UUID | None = None,
    status: str | None = None,
    q: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> InvoicePage:
    return await service.search_invoices(
        customer_id=customer_id, status=status, q=q, limit=limit, offset=offset
    )


@billing_router.get("/invoices/{invoice_id}", response_model=InvoiceDetailView)
async def get_invoice(invoice_id: uuid.UUID, service: BillingSvc, _: InvoiceRead) -> Any:
    return await service.invoice_detail(invoice_id)


@billing_router.post("/invoices/{invoice_id}/issue", response_model=InvoiceView)
async def issue_invoice(invoice_id: uuid.UUID, service: BillingSvc, p: InvoiceIssue) -> Any:
    """Hand it to the customer. Irreversible — it becomes immutable and payable."""
    return await service.issue_invoice(invoice_id, actor_id=p.id)


class CancelInvoiceRequest(BaseModel):
    reason: str = Field(default="", max_length=300)


@billing_router.post("/invoices/{invoice_id}/cancel", response_model=InvoiceView)
async def cancel_invoice(
    invoice_id: uuid.UUID, body: CancelInvoiceRequest, service: BillingSvc, p: InvoiceManage
) -> Any:
    return await service.cancel_invoice(invoice_id, body.reason, actor_id=p.id)


@billing_router.post("/customer-payments", response_model=CustomerPaymentView, status_code=201)
async def record_customer_payment(
    cmd: RecordCustomerPaymentCommand, service: BillingSvc, p: CustomerPaymentRecord
) -> Any:
    """Money RECEIVED from a customer — the opposite direction to /v1/payments."""
    return await service.record_payment(cmd, actor_id=p.id)


@billing_router.get("/customer-payments", response_model=CustomerPaymentPage)
async def search_customer_payments(
    service: BillingSvc,
    _: CustomerPaymentRead,
    customer_id: uuid.UUID | None = None,
    method: str | None = None,
    q: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> CustomerPaymentPage:
    return await service.search_payments(
        customer_id=customer_id, method=method, q=q, limit=limit, offset=offset
    )


@billing_router.get("/customer-payments/{payment_id}", response_model=CustomerPaymentDetailView)
async def get_customer_payment(
    payment_id: uuid.UUID, service: BillingSvc, _: CustomerPaymentRead
) -> Any:
    return await service.payment_detail(payment_id)


@billing_router.get("/customers/{customer_id}/balance", response_model=CustomerBalanceView)
async def customer_balance(
    customer_id: uuid.UUID, service: BillingSvc, _: CustomerPaymentRead
) -> Any:
    """What this customer owes, including the bill still forming."""
    return await service.balance(customer_id)


@billing_router.get("/customers/{customer_id}/statement", response_model=CustomerStatement)
async def customer_statement(
    customer_id: uuid.UUID,
    service: BillingSvc,
    _: CustomerPaymentRead,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Any:
    """How they came to owe it: opening balance, bills, payments, closing.

    The dates are OPTIONAL and default to the dairy's current month, for the
    same reason the delivery report's do — a client cannot compute a local
    month without a timezone database, and the platform already knows the zone.
    """
    return await service.statement(customer_id, date_from=date_from, date_to=date_to)


@billing_router.get("/customer-receipts")
async def search_customer_receipts(
    service: BillingSvc,
    _: CustomerReceiptRead,
    customer_id: uuid.UUID | None = None,
    q: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    return await service.search_receipts(customer_id=customer_id, q=q, limit=limit, offset=offset)


for sub in (
    wellknown,
    security_router,
    auth,
    identity_router,
    org_router,
    structure_router,
    member_router,
    center_router,
    ops_router,
    supplier_router,
    milk_router,
    pricing_router,
    matrix_router,
    settlement_router,
    payment_router,
    receipt_router,
    sync_router,
    report_router,
    notification_router,
    relay_router,
    consumers_router,
    projections_router,
    ops_observability_router,
    authz_router,
    config_router,
    audit_router,
    tenant_data_router,
    customer_router,
    delivery_router,
    logistics_router,
    billing_router,
    locale_router,
    calendar_router,
    subscription_router,
    webhook_router,
    delivery_receipt_router,
):
    router.include_router(sub)
