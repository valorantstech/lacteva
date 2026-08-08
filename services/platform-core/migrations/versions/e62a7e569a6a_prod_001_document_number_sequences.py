"""PROD-001 document number sequences

Per-tenant, per-type, per-year counters for financial document numbers.
Settlements, payments and receipts previously used `secrets.token_hex(3)` —
24 bits of randomness — which cannot satisfy the sequential-numbering rules
several target jurisdictions apply to financial documents, and whose
check-then-act allocation loop also raced. See core/document_numbers.py for
the full decision, including what "gapless" does and does not mean here.

The table is tenant-owned, so it gets the standard policy: SEC-002 made an
unprotected tenant table a build failure. `tenant_id` is NOT NULL here — unlike
`idempotency_record`, a document series always belongs to exactly one dairy,
and a platform-global counter would let every tenant infer the others' volumes
from the numbers they were issued.

Revision ID: e62a7e569a6a
Revises: fe59b02bbc68
Create Date: 2026-08-08 12:53:51.029550
"""

import sqlalchemy as sa
from alembic import op

revision = "e62a7e569a6a"
down_revision = "fe59b02bbc68"
branch_labels = None
depends_on = None

#: Read by the SEC-002 coverage guard.
POLICY_TABLES = ("document_sequence",)


def upgrade() -> None:
    op.create_table(
        "document_sequence",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("doc_type", sa.String(length=30), nullable=False),
        sa.Column("period", sa.String(length=10), nullable=False),
        sa.Column("next_value", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "doc_type", "period", name="uq_document_sequence"),
    )
    op.create_index(
        op.f("ix_document_sequence_tenant_id"), "document_sequence", ["tenant_id"], unique=False
    )

    # SEC-002: tenant-owned means a policy, always.
    if op.get_bind().dialect.name == "postgresql":
        predicate = (
            "current_setting('lacteva.bypass_rls', true) = 'on' "
            "OR tenant_id IS NULL "
            "OR tenant_id::text = current_setting('lacteva.tenant_id', true)"
        )
        op.execute("ALTER TABLE document_sequence ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE document_sequence FORCE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY document_sequence_tenant_isolation ON document_sequence "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS document_sequence_tenant_isolation ON document_sequence")
    op.drop_index(op.f("ix_document_sequence_tenant_id"), table_name="document_sequence")
    op.drop_table("document_sequence")
