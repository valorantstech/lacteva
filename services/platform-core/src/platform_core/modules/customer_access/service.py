"""Logins and bill links for one customer (WO-86).

Everything here is keyed on a customer the caller may already manage
(`sales.customer.manage`), and the customer is resolved through
`CustomerService.get` first — so a customer id from another tenant, or one
this principal is scoped away from, is a 404 before any invitation or token
exists for it.
"""

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.db import as_utc, utcnow
from platform_core.core.errors import ConflictError, NotFoundError
from platform_core.core.tenancy import require_current_tenant
from platform_core.modules.audit.service import AuditService
from platform_core.modules.customer.service import CustomerService
from platform_core.modules.customer_access.models import BILL_TOKEN_TTL, CustomerBillToken
from platform_core.modules.identity.service import IdentityService
from platform_core.modules.organization.models import Invitation
from platform_core.modules.organization.service import (
    CUSTOMER_ROLE_NAME as CUSTOMER_ROLE,
)
from platform_core.modules.organization.service import InvitationService


class CustomerLoginView(BaseModel):
    """Whether this household can sign in to the app, and how far along it is.

    `state` is one of:

    * `none` — nobody has been invited;
    * `invited` — an invitation is out and has not been accepted, expired or
      withdrawn (its email and expiry are shown so the dairy can chase it);
    * `active` — an account exists and is bound to this customer;
    * `suspended` — the account exists and has been deactivated.
    """

    customer_id: uuid.UUID
    state: str
    email: str | None = None
    invitation_id: uuid.UUID | None = None
    invited_at: datetime | None = None
    expires_at: datetime | None = None
    user_id: uuid.UUID | None = None
    full_name: str | None = None


class BillLinkView(BaseModel):
    """Whether a live bill link exists. Never the token — that was shown once."""

    customer_id: uuid.UUID
    active: bool
    created_at: datetime | None = None
    expires_at: datetime | None = None
    last_seen_at: datetime | None = None


class BillLinkMinted(BillLinkView):
    """The mint response: the ONLY time the raw token leaves the platform."""

    token: str


class CustomerAccessService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        customers: CustomerService,
        invitations: InvitationService,
        identity: IdentityService,
        audit: AuditService,
    ):
        self._session = session
        self._customers = customers
        self._invitations = invitations
        self._identity = identity
        self._audit = audit

    # --- logins ---------------------------------------------------------------

    async def invite(
        self, customer_id: uuid.UUID, *, email: str, actor_id: uuid.UUID
    ) -> CustomerLoginView:
        """Invite the household to sign in. Re-inviting withdraws the older
        invitation, so at most one is ever live for a customer."""
        customer = await self._customers.get(customer_id)
        if await self._identity.login_for_customer(customer.id) is not None:
            raise ConflictError("this customer already has a login")
        for pending in await self._invitations.pending_for_customer(customer.id):
            await self._invitations.revoke(pending, actor_id=actor_id)
        await self._invitations.invite(
            email=email, role_name=CUSTOMER_ROLE, actor_id=actor_id, customer_id=customer.id
        )
        return await self.login_status(customer.id)

    async def withdraw_invitation(
        self, customer_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> CustomerLoginView:
        customer = await self._customers.get(customer_id)
        pending = await self._invitations.pending_for_customer(customer.id)
        if not pending:
            raise NotFoundError("no pending invitation for this customer")
        for invitation in pending:
            await self._invitations.revoke(invitation, actor_id=actor_id)
        return await self.login_status(customer.id)

    async def login_status(self, customer_id: uuid.UUID) -> CustomerLoginView:
        customer = await self._customers.get(customer_id)
        user = await self._identity.login_for_customer(customer.id)
        if user is not None:
            return CustomerLoginView(
                customer_id=customer.id,
                state="active" if user.is_active else "suspended",
                email=user.email,
                user_id=user.id,
                full_name=user.full_name,
            )
        pending = await self._invitations.pending_for_customer(customer.id)
        if pending:
            latest: Invitation = pending[0]
            return CustomerLoginView(
                customer_id=customer.id,
                state="invited",
                email=latest.email,
                invitation_id=latest.id,
                invited_at=as_utc(latest.created_at),
                expires_at=as_utc(latest.expires_at),
            )
        return CustomerLoginView(customer_id=customer.id, state="none")

    # --- bill links -----------------------------------------------------------

    async def _live_tokens(self, customer_id: uuid.UUID) -> list[CustomerBillToken]:
        tenant_id = require_current_tenant()
        rows = await self._session.scalars(
            select(CustomerBillToken)
            .where(
                CustomerBillToken.tenant_id == tenant_id,
                CustomerBillToken.customer_id == customer_id,
                CustomerBillToken.revoked_at.is_(None),
            )
            .order_by(CustomerBillToken.created_at.desc())
        )
        now = utcnow()
        return [row for row in rows.all() if as_utc(row.expires_at) > now]

    async def mint_bill_link(
        self, customer_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> BillLinkMinted:
        """A new link. Any earlier link stops working at the same moment —
        minting IS rotating, so a dairy that suspects a link has travelled
        too far has one button to press."""
        customer = await self._customers.get(customer_id)
        now = utcnow()
        for old in await self._live_tokens(customer.id):
            old.revoked_at = now
        raw = secrets.token_urlsafe(32)
        row = CustomerBillToken(
            tenant_id=require_current_tenant(),
            customer_id=customer.id,
            token_hash=hashlib.sha256(raw.encode()).hexdigest(),
            created_by=actor_id,
            created_at=now,
            expires_at=now + BILL_TOKEN_TTL,
        )
        self._session.add(row)
        await self._session.flush()
        await self._audit.record(
            action="customer.bill_link.issued",
            resource_type="customer",
            resource_id=customer.id,
            actor_id=actor_id,
            detail={"expires_at": row.expires_at.isoformat()},
        )
        return BillLinkMinted(
            customer_id=customer.id,
            active=True,
            created_at=as_utc(row.created_at),
            expires_at=as_utc(row.expires_at),
            token=raw,
        )

    async def revoke_bill_link(
        self, customer_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> BillLinkView:
        customer = await self._customers.get(customer_id)
        live = await self._live_tokens(customer.id)
        if not live:
            raise NotFoundError("this customer has no bill link")
        now = utcnow()
        for row in live:
            row.revoked_at = now
        await self._audit.record(
            action="customer.bill_link.revoked",
            resource_type="customer",
            resource_id=customer.id,
            actor_id=actor_id,
            detail={"revoked": len(live)},
        )
        return BillLinkView(customer_id=customer.id, active=False)

    async def bill_link_status(self, customer_id: uuid.UUID) -> BillLinkView:
        customer = await self._customers.get(customer_id)
        live = await self._live_tokens(customer.id)
        if not live:
            return BillLinkView(customer_id=customer.id, active=False)
        row = live[0]
        return BillLinkView(
            customer_id=customer.id,
            active=True,
            created_at=as_utc(row.created_at),
            expires_at=as_utc(row.expires_at),
            last_seen_at=as_utc(row.last_seen_at) if row.last_seen_at else None,
        )


async def resolve_bill_token(session: AsyncSession, raw: str) -> CustomerBillToken:
    """The row a public link names, or a 404 — the SAME 404 for a token that
    never existed, one that expired and one that was revoked, because the
    holder of a dead link is not owed the difference.

    Pre-tenant by definition, like accepting an invitation: the caller has no
    session and the point of the lookup is to learn whose bill this is. So
    the session is bound to the platform context for exactly one indexed read,
    and the CALLER rebinds to the tenant the row reveals before reading a
    single business row. `hmac.compare_digest` on the stored hash, so the
    comparison does not leak how many leading bytes matched.
    """
    from platform_core.core.rls import bind_platform_context

    if not raw or len(raw) > 128:
        raise NotFoundError("bill link not found")
    digest = hashlib.sha256(raw.encode()).hexdigest()
    await bind_platform_context(session, reason="public bill link: resolve tenant from token")
    row = await session.scalar(
        select(CustomerBillToken).where(CustomerBillToken.token_hash == digest)
    )
    if (
        row is None
        or not hmac.compare_digest(row.token_hash, digest)
        or row.revoked_at is not None
        or as_utc(row.expires_at) <= utcnow()
    ):
        raise NotFoundError("bill link not found")
    row.last_seen_at = utcnow()
    return row
