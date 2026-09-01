"""Dispatch module — bulk milk leaving a collection centre (BR-0030).

The third movement in a centre's day, and the one the platform could not see.
Milk arrives from farmers (`milk_collection`) and some of it leaves for named
customers on the round (`delivery`); the rest goes out in bulk — to a plant, a
chilling centre, a bulk buyer — and until now nothing recorded that at all, so
"what is left at this centre?" had no answer the platform could give.

A dispatch is a MOVEMENT, not a sale. It carries no customer, no rate, no
amount and no currency, and this module imports no customer, billing or
pricing model so it cannot quietly acquire one. Milk sold to a named customer
is a `milk_delivery` and counts as SOLD; milk moved out in bulk counts as
DISPATCHED. Keeping those apart is what stops the day book counting the same
litres twice — the same reasoning as BR-0028, where a delivery run holds no
money either.

And it is immutable. There is no edit path, here or in the API: a quantity
typed wrong is corrected by cancelling — with a reason — and recording the
right one. A day book somebody has already read cannot change shape behind
them without both versions being left behind.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from platform_core.core.db import Base, IdMixin, utcnow

#: Two states, and deliberately not a workflow. A dispatch has happened by the
#: time anyone records it; the only other thing that can be true of it is that
#: it was recorded in error.
DISPATCH_STATUSES = ("recorded", "cancelled")

#: Where bulk milk goes. Free text, because the receiving end is somebody
#: else's facility and the platform has no registry of them — a dropdown here
#: would be a list this platform cannot keep true. What it is NOT is a
#: customer id: see the module docstring.
DESTINATION_MAX = 120


class MilkDispatch(Base, IdMixin):
    __tablename__ = "milk_dispatch"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    center_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    #: The centre's own business date, supplied by the caller through the
    #: business-time helpers — never `date.today()` in a database default,
    #: which would be the server's midnight rather than the dairy's.
    business_date: Mapped[date] = mapped_column(Date, index=True)
    #: One of `core/milk.py: MILK_TYPES`. The day book subtracts this from
    #: collections of the same type, so the vocabularies must be the one
    #: vocabulary.
    milk_type: Mapped[str] = mapped_column(String(20), index=True)
    #: KILOGRAMS, at the same scale and in the same unit the collection side
    #: stores (`milk_collection_transaction.net_weight`). Deliberately not
    #: litres: the day book subtracts dispatches from collections, and a
    #: ledger that took kilograms in and gave litres out would be wrong by
    #: about 3% while looking entirely reasonable. The sales side measures in
    #: litres and is reported separately for exactly that reason.
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    quantity_unit: Mapped[str] = mapped_column(String(8), default="kg", server_default="kg")
    destination: Mapped[str] = mapped_column(String(DESTINATION_MAX))
    #: The tanker, the challan, the gate pass — whatever the dairy writes on
    #: the paper this replaces. Optional, and not made unique: two dairies'
    #: reference schemes are not the platform's business.
    reference: Mapped[str] = mapped_column(String(60), default="", server_default="")
    notes: Mapped[str] = mapped_column(String(300), default="", server_default="")

    status: Mapped[str] = mapped_column(
        String(16), default="recorded", server_default="recorded", index=True
    )
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    #: A cancellation is attributed and explained, or it is not allowed to
    #: happen (BR-0030). These three are written together and never cleared.
    cancelled_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str] = mapped_column(String(300), default="", server_default="")
