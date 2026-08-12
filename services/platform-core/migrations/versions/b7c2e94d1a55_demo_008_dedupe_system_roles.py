"""DEMO-008 de-duplicate system roles and make the uniqueness enforceable

Found by running the platform, not by reading it: `GET /v1/authz/roles` on the
deployed system listed `platform-admin`, `tenant-admin` and `tenant-viewer`
three times each.

THE CAUSE. `role` carries `UNIQUE (tenant_id, name)`, and every system role has
`tenant_id IS NULL`. In SQL, NULL is not equal to NULL, so a composite unique
constraint containing a NULL never conflicts — PostgreSQL and SQLite both allow
unlimited rows with the same name as long as `tenant_id` is NULL. The
constraint that looked like it enforced "one system role per name" enforced
nothing at all for system roles.

`AuthzService.ensure_system_roles` runs at every startup and is written to be
idempotent: it selects the role, and inserts only if absent. That is correct in
isolation and useless under concurrency — two workers starting together both
select nothing, both insert, and the database accepts both. Three duplicates is
three racing starts.

WHY IT WAS NOT A SECURITY HOLE. Effective permissions are the UNION over a
user's grants, so a grant landing on one duplicate rather than another resolved
to the same permission set; all copies carried identical permissions. The
damage was a confusing administration screen and a latent hazard: had the
registry grown while grants were spread across copies, two users holding "the
same" role could have ended up with different access.

THE FIX, in order:

1. Merge. For each duplicated name the copy with the most grants is kept —
   it is the one the system has actually been using — and every `user_role`
   row pointing at a loser is repointed to it. A repointing that would collide
   with an existing grant is dropped instead, because the user already holds
   the role.
2. Delete the losers' `role_permission` rows, then the losers.
3. Add a PARTIAL unique index on `role (name) WHERE tenant_id IS NULL`. This is
   the thing that actually enforces it, and it is supported by both engines.

Reversible: the downgrade drops the index. It does not resurrect the duplicate
rows, and it should not — they were never meant to exist.
"""

import sqlalchemy as sa
from alembic import op

revision = "b7c2e94d1a55"
down_revision = "a3f81c46b204"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    duplicated = bind.execute(
        sa.text(
            """
            SELECT name FROM role
            WHERE tenant_id IS NULL
            GROUP BY name HAVING count(*) > 1
            """
        )
    ).scalars().all()

    for name in duplicated:
        rows = bind.execute(
            sa.text(
                """
                SELECT r.id AS id,
                       (SELECT count(*) FROM user_role ur WHERE ur.role_id = r.id) AS grants
                FROM role r
                WHERE r.tenant_id IS NULL AND r.name = :name
                ORDER BY grants DESC, r.id
                """
            ),
            {"name": name},
        ).all()
        keeper = rows[0].id
        losers = [row.id for row in rows[1:]]
        for loser in losers:
            # Repoint grants, unless the holder already has the keeper — the
            # (user, role, tenant) uniqueness must survive the merge.
            bind.execute(
                sa.text(
                    """
                    DELETE FROM user_role
                    WHERE role_id = :loser
                      AND EXISTS (
                        SELECT 1 FROM user_role k
                        WHERE k.role_id = :keeper
                          AND k.user_id = user_role.user_id
                          AND (k.tenant_id IS NOT DISTINCT FROM user_role.tenant_id)
                      )
                    """
                ),
                {"loser": loser, "keeper": keeper},
            )
            bind.execute(
                sa.text("UPDATE user_role SET role_id = :keeper WHERE role_id = :loser"),
                {"keeper": keeper, "loser": loser},
            )
            bind.execute(
                sa.text("DELETE FROM role_permission WHERE role_id = :loser"), {"loser": loser}
            )
            bind.execute(sa.text("DELETE FROM role WHERE id = :loser"), {"loser": loser})

    op.create_index(
        "uq_role_system_name",
        "role",
        ["name"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NULL"),
        sqlite_where=sa.text("tenant_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_role_system_name", table_name="role")
