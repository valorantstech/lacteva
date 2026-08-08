"""DEPLOY-001 pricing unit price: FLOAT -> NUMERIC(12,4)

`pricing_matrix_row.unit_price` is the PRICE — the number every calculation,
settlement, payment and receipt is ultimately derived from — and it was stored
as `double precision`. BR-0005 made all *arithmetic* exact (`Decimal(str(x))`),
but exact arithmetic on an inexact input is still inexact: the value was
already approximate before the first multiplication.

`NUMERIC(12, 4)` matches `milk_collection_transaction.unit_price`, which has
been the house standard for a unit price since PRC-004. The two are compared
and copied constantly, so they must agree.

## Why the cast is safe, and how that was established

Executed against PostgreSQL 16.2 before this migration was written, because the
answer decides whether the migration is safe at all:

    44.7291::double precision -> ::numeric(12,4)  =  44.7291     (exact)

PostgreSQL casts float8 to numeric through the float's SHORTEST round-trip text
representation, not through its binary expansion — so a price entered as
44.7291 converts to exactly 44.7291, and NOT to 44.729100000000002. That is the
property the whole migration rests on, and it is why this is a storage fix
rather than a data-correction exercise.

## Why it still refuses to run blind

The same experiment showed what the cast does NOT preserve:

    44.72915  -> 44.7292    (rounded away)
    0.00005   -> 0.0001     (rounded away)
    0.00001   -> 0.0000     (rounded to zero — and `ck_matrix_row_price`
                             requires unit_price > 0, so the row becomes
                             illegal as well as wrong)

A price with more than four decimals would be silently changed by this
migration. Silently changing a price is precisely the class of failure this
platform exists to prevent, so the migration **counts those rows first and
aborts naming them** rather than proceeding. On a database where every price
already has four decimals or fewer — which is every price the API can produce,
since `RowInput.unit_price` is now Decimal — the check passes and the ALTER
runs.

`from_value`/`to_value` are deliberately left as FLOAT. They are band
BOUNDARIES compared against a quality reading, not money; converting them
changes which band a boundary-valued reading selects, which is a behavioural
change to BR-0004 and needs its own analysis rather than a ride along with a
storage fix.

Revision ID: 5d12928a9564
Revises: e62a7e569a6a
Create Date: 2026-08-08 16:20:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "5d12928a9564"
down_revision = "e62a7e569a6a"
branch_labels = None
depends_on = None

PRECISION, SCALE = 12, 4


def upgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        # Pre-flight: refuse to round anybody's price.
        unsafe = bind.execute(
            sa.text(
                """
                SELECT id::text, unit_price
                FROM pricing_matrix_row
                WHERE unit_price IS NOT NULL
                  AND unit_price::numeric <> round(unit_price::numeric, :scale)
                LIMIT 20
                """
            ),
            {"scale": SCALE},
        ).all()
        if unsafe:
            listed = ", ".join(f"{row_id}={price}" for row_id, price in unsafe)
            raise RuntimeError(
                f"{len(unsafe)} pricing_matrix_row(s) hold a unit_price with more than "
                f"{SCALE} decimal places and would be ROUNDED by this migration: {listed}. "
                "Correct or archive those rows first — this migration will not change a "
                "price silently."
            )

    with op.batch_alter_table("pricing_matrix_row") as batch:
        batch.alter_column(
            "unit_price",
            existing_type=sa.Float(),
            type_=sa.Numeric(precision=PRECISION, scale=SCALE),
            existing_nullable=False,
            postgresql_using=f"unit_price::numeric({PRECISION},{SCALE})",
        )


def downgrade() -> None:
    # Reversible in shape, lossy in kind: going back reintroduces the float
    # representation this migration exists to remove. Values with four or fewer
    # decimals survive the round trip (proven by test), which is what makes the
    # rollback path in DEPLOYMENT.md usable.
    with op.batch_alter_table("pricing_matrix_row") as batch:
        batch.alter_column(
            "unit_price",
            existing_type=sa.Numeric(precision=PRECISION, scale=SCALE),
            type_=sa.Float(),
            existing_nullable=False,
            postgresql_using="unit_price::double precision",
        )
