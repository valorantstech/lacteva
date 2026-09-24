"""WO-81 · LACTEVA-SALES-001 — a product catalogue, and things sold that are not the morning milk.

Revision ID: d1e6b4a92c07
Revises: c4d8a2f19e07

Four things, and each is a table or a constraint rather than a convention:

1. **`products`** — new, tenant-owned. The one list of what an organisation
   sells. Seeded for EVERY EXISTING TENANT from its own data: one product
   per distinct `delivery_plan.product` string per tenant (code = the string,
   name = the string title-cased, unit = the plan's unit, no default price).
   The demo dairy wakes up with `RAW-COW-MILK` and `RAW-BUFFALO-MILK` in its
   catalogue and nothing changes for it. Every tenant also receives `OTHER`
   ("Other shop item", `pc`, no price), which is what a new organisation
   starts with and what lets "₹160, sweets" be recorded before a product
   list exists.

2. **`sale_items`** — new, tenant-owned. A thing sold that is not a delivery.
   No uniqueness on (customer, date) on purpose; unique on the client's
   idempotency key because the phone replays.

3. **`uq_delivery_customer_date_slot` gains `product`.** The client's own
   month sheet has flat C-1603 twice, at ₹74 and ₹56 — cow and buffalo milk
   on the same mornings — and until now the second delivery was refused by
   the database. Rebuilt through `batch_alter_table` so SQLite (the test
   stack) can do it too.

4. **`customer_invoice_line` carries either a delivery or an item.**
   `delivery_id` becomes nullable, `item_id` and `line_kind` arrive, and a
   CHECK says exactly one of the two ids is set. Every existing line gets
   `line_kind = 'delivery'`, which is what every existing line is.

No money is recomputed. No invoice, delivery, payment or receipt changes
value; the catalogue rows are derived from strings that were already there.

The downgrade drops the two tables and the two columns and restores the
four-column constraint. It is refused if any invoice line is an item or any
customer has two deliveries on one slot, because those rows cannot be
expressed by the schema it would return to.
"""

import uuid as _uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "d1e6b4a92c07"
down_revision = "c4d8a2f19e07"
branch_labels = None
depends_on = None

#: The RLS drift guard in `tests/test_security.py` unions this into the
#: covered set, by hand, so a new tenant table cannot become protected by
#: accident.
POLICY_TABLES = ("products", "sale_items")


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("unit", sa.String(length=8), nullable=False, server_default="pc"),
        sa.Column("default_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "code", name="uq_product_tenant_code"),
    )
    op.create_index("ix_products_tenant_id", "products", ["tenant_id"])

    op.create_table(
        "sale_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("sale_date", sa.Date(), nullable=False),
        sa.Column("product_code", sa.String(length=40), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("unit", sa.String(length=8), nullable=False, server_default="pc"),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("amount", sa.Numeric(16, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="recorded"),
        sa.Column("notes", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("recorded_by", sa.Uuid(), nullable=True),
        sa.Column("recorded_via", sa.String(length=10), nullable=False, server_default="portal"),
        sa.Column("idempotency_key", sa.String(length=80), nullable=True),
        sa.Column("invoice_id", sa.Uuid(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_sale_item_idempotency"),
    )
    op.create_index("ix_sale_items_tenant_id", "sale_items", ["tenant_id"])
    op.create_index("ix_sale_items_customer_id", "sale_items", ["customer_id"])
    op.create_index("ix_sale_items_sale_date", "sale_items", ["sale_date"])
    op.create_index("ix_sale_items_status", "sale_items", ["status"])
    op.create_index("ix_sale_items_invoice_id", "sale_items", ["invoice_id"])
    op.create_index(
        "ix_sale_item_customer_date", "sale_items", ["tenant_id", "customer_id", "sale_date"]
    )

    # 3. The delivery constraint gains the product.
    with op.batch_alter_table("milk_delivery") as batch:
        batch.drop_constraint("uq_delivery_customer_date_slot", type_="unique")
        batch.create_unique_constraint(
            "uq_delivery_customer_date_slot",
            ["tenant_id", "customer_id", "delivery_date", "slot", "product"],
        )

    # 4. An invoice line is a delivery or an item.
    with op.batch_alter_table("customer_invoice_line") as batch:
        batch.add_column(
            sa.Column("line_kind", sa.String(length=10), nullable=False, server_default="delivery")
        )
        batch.add_column(sa.Column("item_id", sa.Uuid(), nullable=True))
        batch.alter_column("delivery_id", existing_type=sa.Uuid(), nullable=True)
        batch.create_unique_constraint("uq_invoice_line_item", ["tenant_id", "item_id"])
        batch.create_check_constraint(
            "ck_invoice_line_one_source",
            "(delivery_id IS NOT NULL AND item_id IS NULL) "
            "OR (delivery_id IS NULL AND item_id IS NOT NULL)",
        )
    op.create_index("ix_customer_invoice_line_item_id", "customer_invoice_line", ["item_id"])

    # 1b. Seed every existing tenant's catalogue from its own plans, plus
    #     OTHER. Plain SQL over the columns that exist at this revision — a
    #     migration must not import today's models.
    bind = op.get_bind()
    now = datetime.now(UTC)
    plans = bind.execute(
        sa.text(
            "SELECT DISTINCT p.tenant_id, p.product, p.quantity_unit, o.currency_code "
            "FROM delivery_plan p JOIN organization o ON o.id = p.tenant_id"
        )
    ).all()
    products = sa.table(
        "products",
        sa.column("id", sa.Uuid()),
        sa.column("tenant_id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("unit", sa.String()),
        sa.column("currency", sa.String()),
        sa.column("active", sa.Boolean()),
        sa.column("sort_order", sa.Integer()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    seen: set[tuple] = set()
    rows = []
    for tenant_id, product, unit, currency in plans:
        tenant_id = _as_uuid(tenant_id)
        key = (str(tenant_id), product)
        if key in seen or not product:
            continue
        seen.add(key)
        rows.append(
            {
                "id": _uuid.uuid4(),
                "tenant_id": tenant_id,
                "code": product,
                "name": product.replace("-", " ").title(),
                "unit": _product_unit(unit),
                "currency": currency or "INR",
                "active": True,
                "sort_order": 0,
                "created_at": now,
                "updated_at": now,
            }
        )
    tenants = bind.execute(sa.text("SELECT id, currency_code FROM organization")).all()
    for tenant_id, currency in tenants:
        tenant_id = _as_uuid(tenant_id)
        if (str(tenant_id), "OTHER") in seen:
            continue
        rows.append(
            {
                "id": _uuid.uuid4(),
                "tenant_id": tenant_id,
                "code": "OTHER",
                "name": "Other shop item",
                "unit": "pc",
                "currency": currency or "INR",
                "active": True,
                "sort_order": 10000,
                "created_at": now,
                "updated_at": now,
            }
        )
    if rows:
        op.bulk_insert(products, rows)

    if bind.dialect.name == "postgresql":
        from platform_core.core.rls import policy_statements

        for table in POLICY_TABLES:
            for statement in policy_statements(table):
                op.execute(statement)


def _as_uuid(value) -> _uuid.UUID:
    """A raw `tenant_id` is a UUID on PostgreSQL and a 32-hex string on
    SQLite; the `Uuid` column wants the object either way."""
    return value if isinstance(value, _uuid.UUID) else _uuid.UUID(str(value))


def _product_unit(plan_unit: str | None) -> str:
    """A plan's unit as the catalogue spells it. Plans have always carried
    `L` on the sales side; `kg` is the other unit a dairy trades in."""
    value = (plan_unit or "L").strip().lower()
    if value in ("kg", "kgs"):
        return "kg"
    if value in ("pc", "pcs", "piece", "pieces"):
        return "pc"
    return "L"


def downgrade() -> None:
    bind = op.get_bind()
    item_lines = bind.execute(
        sa.text("SELECT count(*) FROM customer_invoice_line WHERE item_id IS NOT NULL")
    ).scalar()
    if item_lines:
        raise RuntimeError(
            f"{item_lines} invoice line(s) are sale items; the previous schema cannot hold them"
        )
    twice = bind.execute(
        sa.text(
            "SELECT count(*) FROM (SELECT tenant_id, customer_id, delivery_date, slot "
            "FROM milk_delivery GROUP BY 1, 2, 3, 4 HAVING count(*) > 1) AS d"
        )
    ).scalar()
    if twice:
        raise RuntimeError(
            f"{twice} customer-slot(s) hold two products on one day; "
            "the previous constraint cannot hold them"
        )

    if bind.dialect.name == "postgresql":
        from platform_core.core.rls import drop_statements

        for table in POLICY_TABLES:
            for statement in drop_statements(table):
                op.execute(statement)

    op.drop_index("ix_customer_invoice_line_item_id", table_name="customer_invoice_line")
    with op.batch_alter_table("customer_invoice_line") as batch:
        batch.drop_constraint("ck_invoice_line_one_source", type_="check")
        batch.drop_constraint("uq_invoice_line_item", type_="unique")
        batch.alter_column("delivery_id", existing_type=sa.Uuid(), nullable=False)
        batch.drop_column("item_id")
        batch.drop_column("line_kind")

    with op.batch_alter_table("milk_delivery") as batch:
        batch.drop_constraint("uq_delivery_customer_date_slot", type_="unique")
        batch.create_unique_constraint(
            "uq_delivery_customer_date_slot",
            ["tenant_id", "customer_id", "delivery_date", "slot"],
        )

    for index in (
        "ix_sale_item_customer_date",
        "ix_sale_items_invoice_id",
        "ix_sale_items_status",
        "ix_sale_items_sale_date",
        "ix_sale_items_customer_id",
        "ix_sale_items_tenant_id",
    ):
        op.drop_index(index, table_name="sale_items")
    op.drop_table("sale_items")
    op.drop_index("ix_products_tenant_id", table_name="products")
    op.drop_table("products")
