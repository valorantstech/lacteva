"""DEMO-012 push device registry

A field user is only reachable by push if the platform knows which handset to
push to. Nothing else in the platform knows a device exists, so unlike
`notification_recipient` — a projection that can be rebuilt from supplier
events — this table is authoritative and its loss is real.

The token is the ADDRESS of a handset and is capability-like: whoever holds it
can push to that phone through a configured gateway. It is never returned by
any endpoint, never logged in full, and deleted rather than deactivated on
revocation, because a revoked token is not evidence of anything.

`customer_id` is nullable and set only for a customer-scoped login. It is what
lets an invoice-issued event — which knows a customer and has never heard of a
user account — find a handset without the notification module reading an
identity table: the API layer copies it from the authenticated principal.

`token` is unique across the whole platform, not per tenant, and that is
deliberate: a gateway token identifies one installation on one handset. If it
appears again under a different user, the phone was signed into a different
account, and the registration MOVES rather than duplicating — the previous
owner must stop receiving its notifications at once.

Tenant-owned, so RLS is installed here with the same predicate as every other
tenant table (a policy created by migration, not by application code — MT-001).
The dispatch consumer reads this table on a platform-bound session with RLS
bypassed, which is why `_resolve_device_token` also filters by tenant in SQL:
the policy is defence in depth there, not the only defence.

Reversible: the downgrade drops the table, which returns the platform to
having no push channel — the state before DEMO-012.
"""

import sqlalchemy as sa
from alembic import op

from platform_core.core.rls import BYPASS_SETTING, TENANT_SETTING

revision = "e91b6c47a2d8"
down_revision = "d4f7a1c93e26"
branch_labels = None
depends_on = None

#: Snapshotted here on purpose. `tests/test_security.py` builds the covered
#: set from the UNION of these per-migration lists, so a new tenant-owned
#: table with no policy fails the build — and a migration is a historical
#: record that must not change meaning when the models later do.
POLICY_TABLES = ("notification_device",)

_TENANT_PREDICATE = (
    f"current_setting('{BYPASS_SETTING}', true) = 'on' "
    "OR tenant_id IS NULL "
    f"OR tenant_id::text = current_setting('{TENANT_SETTING}', true)"
)


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "notification_device",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("token", sa.String(length=400), nullable=False),
        sa.Column("platform", sa.String(length=10), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token", name="uq_notification_device_token"),
    )
    op.create_index("ix_notification_device_tenant_id", "notification_device", ["tenant_id"])
    op.create_index("ix_notification_device_user_id", "notification_device", ["user_id"])
    op.create_index("ix_notification_device_customer_id", "notification_device", ["customer_id"])
    op.create_index("ix_notification_device_user", "notification_device", ["tenant_id", "user_id"])

    if not _is_postgres():
        return
    for table in POLICY_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"USING ({_TENANT_PREDICATE}) WITH CHECK ({_TENANT_PREDICATE})"
        )


def downgrade() -> None:
    if _is_postgres():
        for table in POLICY_TABLES:
            op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
    op.drop_index("ix_notification_device_user", table_name="notification_device")
    op.drop_index("ix_notification_device_customer_id", table_name="notification_device")
    op.drop_index("ix_notification_device_user_id", table_name="notification_device")
    op.drop_index("ix_notification_device_tenant_id", table_name="notification_device")
    op.drop_table("notification_device")
