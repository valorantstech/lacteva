"""Catalog application service (WO-81 · LACTEVA-SALES-001).

Create, edit, deactivate, list — and the one question every other sales
module asks of it: *is this code an active product here?* That question is a
service call, not a foreign key, because `DeliveryPlan.product`,
`MilkDelivery.product` and `CustomerInvoiceLine.product` are string columns
that predate the catalogue by a year of data, and nothing already written is
touched by this module's arrival.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.codes import unique_code
from platform_core.core.db import as_utc
from platform_core.core.errors import ConflictError, NotFoundError, ValidationError
from platform_core.core.money import quantize_money
from platform_core.core.org_context import tenant_currency
from platform_core.core.tenancy import require_current_tenant
from platform_core.modules.audit.service import AuditService
from platform_core.modules.catalog.models import (
    CODE_MAX,
    MILK_PRODUCTS,
    NAME_MAX,
    OTHER_PRODUCT_CODE,
    OTHER_PRODUCT_NAME,
    PRODUCT_UNITS,
    UNIT_MAX,
    Product,
)

#: Spellings a form or a CSV might send for a unit. Stored value is always one
#: of `PRODUCT_UNITS`.
_UNIT_SPELLINGS = {
    "l": "L",
    "litre": "L",
    "litres": "L",
    "liter": "L",
    "liters": "L",
    "ltr": "L",
    "kg": "kg",
    "kgs": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "pc": "pc",
    "pcs": "pc",
    "piece": "pc",
    "pieces": "pc",
    "unit": "pc",
    "units": "pc",
}


def normalise_unit(value: str | None) -> str:
    """A known spelling of `L`, `kg` or `pc` canonicalised — or, since WO-107
    §5, any label a shop sells by (`packet`, `dozen`, `250 g`), trimmed, 1 to
    `UNIT_MAX` characters, letters, digits, spaces and a few marks. The
    suggestions stay suggestions; the label is what the customer sees on the
    bill."""
    raw = (value or "").strip()
    key = raw.lower()
    if key in _UNIT_SPELLINGS:
        return _UNIT_SPELLINGS[key]
    if not raw:
        raise ValueError(f"unit is required — {', '.join(PRODUCT_UNITS)}, or the label you sell by")
    if len(raw) > UNIT_MAX:
        raise ValueError(f"unit must be at most {UNIT_MAX} characters")
    if not all(ch.isalnum() or ch in " .-/µ" for ch in raw):
        raise ValueError("unit may hold letters, digits, spaces, '.', '-', '/' and 'µ'")
    return raw


def normalise_code(value: str) -> str:
    """Upper-case slug: letters, digits, hyphen. `dahi 500g` → `DAHI-500G`."""
    cleaned = "-".join(part for part in value.strip().upper().replace("_", "-").split())
    if not cleaned or any(ch for ch in cleaned if not (ch.isalnum() or ch == "-")):
        raise ValueError("code must be letters, digits and hyphens")
    return cleaned


# --- commands ----------------------------------------------------------------


class CreateProductCommand(BaseModel):
    #: WO-107 §3: optional — generated from the name (upper-case slug, made
    #: unique) when the caller does not care. Editable for those who do.
    code: str | None = Field(default=None, min_length=1, max_length=CODE_MAX)
    name: str = Field(min_length=1, max_length=NAME_MAX)
    unit: str = Field(default="pc", max_length=UNIT_MAX)
    #: A suggestion for forms, and the price of a sale item recorded without
    #: one. Never the rate of a standing order.
    default_price: Decimal | None = Field(default=None, ge=0)
    sort_order: int = Field(default=0, ge=0, le=10_000)

    @field_validator("code")
    @classmethod
    def _slug(cls, v: str | None) -> str | None:
        return None if v is None or not v.strip() else normalise_code(v)

    @field_validator("unit")
    @classmethod
    def _known_unit(cls, v: str) -> str:
        return normalise_unit(v)


class UpdateProductCommand(BaseModel):
    """Everything but the code. The code is the join key from every plan,
    delivery and invoice line ever written, and renaming it would orphan them."""

    name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX)
    unit: str | None = Field(default=None, max_length=12)
    default_price: Decimal | None = Field(default=None, ge=0)
    #: Explicit, because `default_price=None` in a PATCH must be able to mean
    #: "remove the price" and not "leave it alone".
    clear_default_price: bool = False
    active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=10_000)

    @field_validator("unit")
    @classmethod
    def _known_unit(cls, v: str | None) -> str | None:
        return None if v is None else normalise_unit(v)


# --- views -------------------------------------------------------------------


class ProductView(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    unit: str
    default_price: Decimal | None
    currency: str
    active: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime


class ProductPage(BaseModel):
    items: list[ProductView]
    total: int


def _view(row: Product) -> ProductView:
    return ProductView(
        id=row.id,
        code=row.code,
        name=row.name,
        unit=row.unit,
        default_price=(
            None
            if row.default_price is None
            else quantize_money(Decimal(row.default_price), row.currency)
        ),
        currency=row.currency,
        active=bool(row.active),
        sort_order=row.sort_order,
        created_at=as_utc(row.created_at),
        updated_at=as_utc(row.updated_at),
    )


class CatalogService:
    def __init__(self, session: AsyncSession, audit: AuditService | None = None):
        self._session = session
        self._audit = audit

    # --- the question every sales write asks --------------------------------

    async def require_active(self, code: str) -> Product:
        """The active product with this code in the current tenant, or a
        refusal that says what to do about it.

        A `ValidationError` (422), because the caller sent a code that names
        nothing: the fix is on their side — add the product, or activate it.
        """
        tenant_id = require_current_tenant()
        row = await self._session.scalar(
            select(Product).where(Product.tenant_id == tenant_id, Product.code == code)
        )
        if row is None:
            raise ValidationError(
                f"{code!r} is not a product in this organisation's catalogue — "
                "add it under Admin → Products first"
            )
        if not row.active:
            raise ValidationError(
                f"product {code} is deactivated — reactivate it before selling it again"
            )
        return row

    async def names_for(self, codes: set[str]) -> dict[str, str]:
        """Code → name, for a bill that must read 'Dahi 500 g' rather than a
        code. A code the catalogue does not know maps to itself, so a line
        written before the catalogue existed still prints."""
        if not codes:
            return {}
        tenant_id = require_current_tenant()
        rows = await self._session.execute(
            select(Product.code, Product.name).where(
                Product.tenant_id == tenant_id, Product.code.in_(codes)
            )
        )
        names = {code: name for code, name in rows}
        return {code: names.get(code, code) for code in codes}

    # --- writes ------------------------------------------------------------------

    async def default_standing_order_product(self) -> Product:
        """WO-107: the product a standing order is for when the caller named
        none — the organisation's first ACTIVE milk product (code or name
        says MILK), by catalogue order. None at all is a refusal that says
        what to do, never a guess at `OTHER`."""
        tenant_id = require_current_tenant()
        row = await self._session.scalar(
            select(Product)
            .where(
                Product.tenant_id == tenant_id,
                Product.active.is_(True),
                (func.upper(Product.code).like("%MILK%"))
                | (func.upper(Product.name).like("%MILK%")),
            )
            .order_by(Product.sort_order, Product.code)
            .limit(1)
        )
        if row is None:
            raise ValidationError(
                "name the product this standing order is for — add your milk products first"
            )
        return row

    async def _code_taken(self, tenant_id: uuid.UUID, code: str) -> bool:
        return (
            await self._session.scalar(
                select(Product.id).where(Product.tenant_id == tenant_id, Product.code == code)
            )
        ) is not None

    async def create(self, cmd: CreateProductCommand, *, actor_id: uuid.UUID) -> ProductView:
        tenant_id = require_current_tenant()
        if cmd.code is None:
            # WO-107 §3: the owner names the thing; the platform spells its code.
            code = await unique_code(
                cmd.name, lambda c: self._code_taken(tenant_id, c), max_length=CODE_MAX
            )
        else:
            code = cmd.code
            if await self._code_taken(tenant_id, code):
                raise ConflictError(f"product {code} already exists — edit or reactivate it")
        currency = await tenant_currency(self._session)
        row = Product(
            tenant_id=tenant_id,
            code=code,
            name=cmd.name.strip(),
            unit=cmd.unit,
            default_price=(
                None if cmd.default_price is None else quantize_money(cmd.default_price, currency)
            ),
            currency=currency,
            active=True,
            sort_order=cmd.sort_order,
        )
        self._session.add(row)
        await self._session.flush()
        if self._audit is not None:
            await self._audit.record(
                action="catalog.product.created",
                resource_type="product",
                resource_id=row.id,
                actor_id=actor_id,
                detail={"code": row.code, "name": row.name, "unit": row.unit},
            )
        return _view(row)

    async def update(
        self, product_id: uuid.UUID, cmd: UpdateProductCommand, *, actor_id: uuid.UUID
    ) -> ProductView:
        row = await self.get(product_id)
        changed: dict[str, str] = {}
        if cmd.name is not None and cmd.name.strip() != row.name:
            row.name = cmd.name.strip()
            changed["name"] = row.name
        if cmd.unit is not None and cmd.unit != row.unit:
            row.unit = cmd.unit
            changed["unit"] = row.unit
        if cmd.clear_default_price:
            row.default_price = None
            changed["default_price"] = "cleared"
        elif cmd.default_price is not None:
            row.default_price = quantize_money(cmd.default_price, row.currency)
            changed["default_price"] = str(row.default_price)
        if cmd.active is not None and cmd.active != bool(row.active):
            row.active = cmd.active
            changed["active"] = str(cmd.active)
        if cmd.sort_order is not None and cmd.sort_order != row.sort_order:
            row.sort_order = cmd.sort_order
            changed["sort_order"] = str(cmd.sort_order)
        await self._session.flush()
        if changed and self._audit is not None:
            await self._audit.record(
                action="catalog.product.updated",
                resource_type="product",
                resource_id=row.id,
                actor_id=actor_id,
                detail={"code": row.code, **changed},
            )
        return _view(row)

    async def ensure(
        self,
        *,
        tenant_id: uuid.UUID,
        code: str,
        name: str,
        unit: str,
        currency: str,
        default_price: Decimal | None = None,
        sort_order: int = 0,
    ) -> Product:
        """Get-or-create, for the two places a catalogue is written without a
        person: a new organisation's `OTHER`, and the demo seeder. Idempotent,
        so a re-run changes nothing."""
        row = await self._session.scalar(
            select(Product).where(Product.tenant_id == tenant_id, Product.code == code)
        )
        if row is not None:
            return row
        row = Product(
            tenant_id=tenant_id,
            code=code,
            name=name,
            unit=unit,
            default_price=default_price,
            currency=currency,
            active=True,
            sort_order=sort_order,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def seed_new_organisation(
        self, *, tenant_id: uuid.UUID, currency: str, modules: list[str] | None = None
    ) -> Product:
        """Day one: `OTHER` for everyone, and — WO-107 §2 — for an
        organisation that SELLS, Cow milk and Buffalo milk in litres, unpriced.
        The first shop owner asked "where is the option to add cow milk or
        buffalo milk, do we need to add those in products?"; the answer is
        now "they are already there; set your prices". A catalogue holding
        only `OTHER` made the New customer form impossible to complete.

        EVERY organisation, not only the ones running `sales` — D-31 says no
        business rule branches on the modules (`test_modules.py` greps for
        it), and two unpriced products a collection-only dairy never uses
        cost nothing. `modules` is accepted and unused, for the caller's
        clarity."""
        del modules
        for order, (code, name) in enumerate(MILK_PRODUCTS, start=1):
            await self.ensure(
                tenant_id=tenant_id,
                code=code,
                name=name,
                unit="L",
                currency=currency,
                sort_order=order * 10,
            )
        return await self.ensure(
            tenant_id=tenant_id,
            code=OTHER_PRODUCT_CODE,
            name=OTHER_PRODUCT_NAME,
            unit="pc",
            currency=currency,
            sort_order=10_000,
        )

    # --- reads -------------------------------------------------------------------

    async def get(self, product_id: uuid.UUID) -> Product:
        tenant_id = require_current_tenant()
        row = await self._session.get(Product, product_id)
        if row is None or row.tenant_id != tenant_id:
            raise NotFoundError("product not found")
        return row

    async def view(self, product_id: uuid.UUID) -> ProductView:
        return _view(await self.get(product_id))

    async def list(self, *, active: bool | None = True) -> ProductPage:
        """The catalogue, active ones by default, in the shop's own order.

        Not paginated: a catalogue is a form's dropdown, and a shop with two
        hundred products has a different problem than paging.
        """
        tenant_id = require_current_tenant()
        stmt = select(Product).where(Product.tenant_id == tenant_id)
        if active is not None:
            stmt = stmt.where(Product.active.is_(active))
        rows = (await self._session.scalars(stmt.order_by(Product.sort_order, Product.name))).all()
        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        return ProductPage(items=[_view(r) for r in rows], total=int(total or 0))
