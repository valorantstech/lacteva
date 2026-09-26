"""WO-107 — a new shop starts with its milk, and sells by any unit.

Revision ID: e5b7c2a91d04
Revises: d4a7c19e58b2

Two things the first shop owner hit on day one (LACTEVA-SALES-005).

1. Cow milk and Buffalo milk (`COW-MILK`, `BUFFALO-MILK`, litres, unpriced)
   for every organisation that SELLS and has no milk product yet — the new
   organisation seed does this from now on; this does it for Gavyam and Patel.
   "No milk product yet" is literal: a product whose code or name contains
   MILK. The demo tenants carry `RAW-COW-MILK` and are therefore left alone,
   as are organisations that do not run the sales module.

2. The unit is a label a shop sells by (`packet`, `dozen`), up to 12
   characters; the four columns that carry it were 8.

Reversible: the columns narrow back (every value written so far is at most
8 characters unless somebody used the new width, in which case the downgrade
refuses rather than truncating), and the two seeded products are removed
only where they are still unpriced and unused by any plan.
"""

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "e5b7c2a91d04"
down_revision = "d4a7c19e58b2"
branch_labels = None
depends_on = None

UNIT_COLUMNS = (
    ("products", "unit"),
    ("delivery_plan", "quantity_unit"),
    ("milk_delivery", "quantity_unit"),
    ("customer_invoice_line", "quantity_unit"),
)
MILK = (("COW-MILK", "Cow milk", 10), ("BUFFALO-MILK", "Buffalo milk", 20))


def upgrade() -> None:
    for table, column in UNIT_COLUMNS:
        with op.batch_alter_table(table) as batch:
            batch.alter_column(column, type_=sa.String(12), existing_type=sa.String(8))

    bind = op.get_bind()
    orgs = bind.execute(sa.text("SELECT id, currency_code, modules FROM organization")).fetchall()
    now = datetime.now(UTC)
    for org_id, currency, modules in orgs:
        listed = list(modules) if modules else []
        if listed and "sales" not in listed:
            continue
        has_milk = bind.execute(
            sa.text(
                "SELECT 1 FROM products WHERE tenant_id = :tenant "
                "AND (UPPER(code) LIKE '%MILK%' OR UPPER(name) LIKE '%MILK%') LIMIT 1"
            ),
            {"tenant": org_id},
        ).first()
        if has_milk:
            continue
        for code, name, order in MILK:
            bind.execute(
                sa.text(
                    "INSERT INTO products (id, tenant_id, code, name, unit, default_price, "
                    "currency, active, sort_order, created_at, updated_at) "
                    "VALUES (:id, :tenant, :code, :name, 'L', NULL, :currency, :active, "
                    ":order, :now, :now)"
                ),
                {
                    "id": uuid.uuid4(),
                    "tenant": org_id,
                    "code": code,
                    "name": name,
                    "currency": currency,
                    "active": True,
                    "order": order,
                    "now": now,
                },
            )


def downgrade() -> None:
    bind = op.get_bind()
    for table, column in UNIT_COLUMNS:
        wide = bind.execute(
            sa.text(f"SELECT COUNT(*) FROM {table} WHERE LENGTH({column}) > 8")  # noqa: S608 — constants
        ).scalar()
        if wide:
            raise RuntimeError(
                f"{table}.{column} holds {wide} value(s) longer than 8 characters — "
                "narrowing would truncate them; this downgrade refuses"
            )
    for table, column in UNIT_COLUMNS:
        with op.batch_alter_table(table) as batch:
            batch.alter_column(column, type_=sa.String(8), existing_type=sa.String(12))
    # The seeded milk products go only where they are still what the seed
    # wrote: unpriced and referenced by no plan.
    for code, _name, _order in MILK:
        bind.execute(
            sa.text(
                "DELETE FROM products WHERE code = :code AND default_price IS NULL "
                "AND NOT EXISTS (SELECT 1 FROM delivery_plan p "
                "WHERE p.tenant_id = products.tenant_id AND p.product = products.code)"
            ),
            {"code": code},
        )
