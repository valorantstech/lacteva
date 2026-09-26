"""Catalog module — what the organisation SELLS (WO-81 · LACTEVA-SALES-001).

A milk shop sells more than the morning milk: home-made dahi, shrikhand,
sweets, a cold drink a household takes with the litre and sometimes does not.
Until this module the platform knew products only as a free-text string on a
standing order (`DeliveryPlan.product`, `RAW-COW-MILK` by default), so there
was nothing to record a dahi against and no name to print on a bill.

This is the one list. A standing order names a product from it; a sale item
names a product from it; an invoice line prints the product's NAME from it
rather than its code. It is a tenant-owned table like every other and RLS
covers it the same way.

**`default_price` is a SUGGESTION, never authority.** The client's own sheet
carries ₹74, ₹56 and ₹72 in the same price column: the rate belongs to the
household's standing order (`DeliveryPlan.unit_price`), which already exists
and already wins. A catalogue price only prefills a form, and prices a sale
item when the command carries no price of its own. A catalogue price that
overrode a plan's rate would silently re-rate four hundred households, and a
test asserts the opposite.

**Deactivate, never delete.** A product on an issued invoice line must keep
resolving to its name for as long as that invoice exists, so the row stays;
`active=False` removes it from every form and refuses new plans and items.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from platform_core.core.db import Base, IdMixin, utcnow

#: What a product is counted in. The two units the sales side has always
#: carried on a delivery (`L`, `kg` — see `core/units.py`), plus `pc` for
#: a thing that is counted rather than measured: a pot of dahi, a sweet box.
PRODUCT_UNITS = ("L", "kg", "pc")
#: WO-107 §5: those three are SUGGESTIONS. A shop sells packets, boxes,
#: bottles, dozens, grams — the unit is a label carried to delivery rows,
#: bill lines and the month sheet, and arithmetic is quantity x rate
#: whatever it says. Only `L` and `kg` take part in the D-21 measured-versus-
#: traded conversion (`core/units.py`), which is the collection side's and
#: never reads a product's unit.
UNIT_MAX = 12

#: WO-107 §2: a new organisation that SELLS starts with its milk beside
#: `OTHER` — unpriced, so the owner's first job is to set prices, not to
#: discover that "cow milk" has to be invented. Renameable, priceable,
#: deactivatable like any product.
MILK_PRODUCTS: tuple[tuple[str, str], ...] = (
    ("COW-MILK", "Cow milk"),
    ("BUFFALO-MILK", "Buffalo milk"),
)

#: The product every organisation starts with, and the reason the catalogue
#: needs no setup before the first "₹160, sweets" is written against a
#: household: the client's sheet has ONE `other item` amount per month, not a
#: list, and this lets them keep doing exactly that.
OTHER_PRODUCT_CODE = "OTHER"
OTHER_PRODUCT_NAME = "Other shop item"

CODE_MAX = 40
NAME_MAX = 120


class Product(Base, IdMixin):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_product_tenant_code"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    #: Upper-case slug, unique per tenant. What a plan, a delivery and a sale
    #: item name. Never renamed: it is the join key from every historical row.
    code: Mapped[str] = mapped_column(String(CODE_MAX))
    #: What a person reads, on a form and on a bill.
    name: Mapped[str] = mapped_column(String(NAME_MAX))
    unit: Mapped[str] = mapped_column(String(UNIT_MAX), default="pc")
    #: Nullable on purpose: a product without a price can only be sold at a
    #: price the recorder types, which is the only honest way to sell an
    #: "other item" whose value nobody itemised.
    default_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    #: ISO 4217, from the organisation at creation (DEMO-013: never a default).
    currency: Mapped[str] = mapped_column(String(3))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
