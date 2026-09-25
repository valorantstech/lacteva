"""The bill link's persistence (WO-86)."""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import DateTime, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from platform_core.core.db import Base, IdMixin, utcnow

#: A bill link lives a year. Long, because the household it is for will paste
#: it into a WhatsApp chat once and tap it every month for as long as they
#: take milk; short enough that a link on a phone sold on eventually stops
#: working without anybody remembering to revoke it.
BILL_TOKEN_TTL = timedelta(days=365)


class CustomerBillToken(Base, IdMixin):
    """One capability to read one customer's bills, by anyone holding it.

    The raw token is shown to the dairy ONCE, when minted, and travels to the
    household through whatever the dairy uses to talk to them. Only its
    SHA-256 lands here — the same discipline as `Invitation.token_hash` and
    the password-reset token, and for the same reason: a backup or a log line
    that contains this table must not be a list of working links.

    Rotation is a new row and a `revoked_at` on the old one, never an update
    of the hash in place, so the history says when each link was live.

    Tenant-owned: RLS is installed by the WO-86 migration. The public
    endpoint that consumes a token reads this table on a platform-bound
    session (it cannot know the tenant before the lookup), which is exactly
    the bypass `InvitationService.accept` already makes, and it rebinds to
    the tenant the row names before touching anything else.
    """

    __tablename__ = "customer_bill_token"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: When the link was last opened. Shown to the dairy so "did they ever
    #: look at it?" has an answer; never used for anything else.
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
