"""Who holds a platform role where they should not (WO-109 · LACTEVA-SEC-004).

Read-only. Lists every `user_role` row that grants a PLATFORM role — one
holding the wildcard, a `platform.*` permission or `organization.manage` —
to a TENANT-BOUND grant (the row names a tenant), and every invitation,
pending or accepted, that names a platform role. Before WO-109 a tenant
admin could create both; after it neither can be created, but what already
exists has to be looked for.

Run on the host, inside the API container, against production:

    docker compose -f docker-compose.production.yml --env-file /etc/lacteva/.env.production \\
        exec -T api python -m platform_core.modules.authz.audit

Exit 0 and "nothing found" is the good answer. Anything listed is an
incident (DEPLOYMENT.md §12): for a grant, revoke it —
`DELETE /v1/authz/assignments?user_id=…&role_name=…` as a platform session
acting in that tenant, or delete the `user_role` row — then revoke the
user's sessions (`AuthService.revoke_all_for_user`, or the Users page's
"sign out everywhere"); for an accepted invitation, the same for the account
it created; for a pending one, revoke the invitation. Nothing here writes.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.modules.authz.models import Role, RolePermission, UserRole
from platform_core.modules.authz.permissions import PLATFORM_ROLES, is_platform_grant


@dataclass(frozen=True)
class Finding:
    kind: str  # "grant" | "invitation"
    tenant_id: str
    subject: str  # user id, or the invited email
    role: str
    detail: str


async def platform_role_ids(session: AsyncSession) -> dict:
    """Every role — system or custom — whose permissions make its holder
    platform staff, by id → name."""
    grants: dict = {}
    for role_id, key in (
        await session.execute(select(RolePermission.role_id, RolePermission.permission_key))
    ).all():
        grants.setdefault(role_id, set()).add(key)
    names = dict((await session.execute(select(Role.id, Role.name))).all())
    return {rid: names.get(rid, "?") for rid, perms in grants.items() if is_platform_grant(perms)}


async def find_platform_grants(session: AsyncSession) -> list[Finding]:
    """The rows WO-109 forbids. The session must be platform-bound: this
    reads across every tenant on purpose (`core/rls.py` PlatformSessionFactory)."""
    from platform_core.modules.organization.models import Invitation

    platform = await platform_role_ids(session)
    findings: list[Finding] = []
    if platform:
        rows = (
            await session.execute(
                select(UserRole.user_id, UserRole.role_id, UserRole.tenant_id, UserRole.center_id)
                .where(UserRole.role_id.in_(list(platform)), UserRole.tenant_id.is_not(None))
                .order_by(UserRole.tenant_id)
            )
        ).all()
        for user_id, role_id, tenant_id, center_id in rows:
            findings.append(
                Finding(
                    kind="grant",
                    tenant_id=str(tenant_id),
                    subject=str(user_id),
                    role=platform[role_id],
                    detail="user_role grants a platform role inside a tenant"
                    + (f" (centre {center_id})" if center_id else ""),
                )
            )
    invitations = (
        await session.execute(
            select(
                Invitation.email,
                Invitation.role_name,
                Invitation.tenant_id,
                Invitation.accepted_at,
                Invitation.revoked_at,
            ).where(Invitation.role_name.in_(sorted(PLATFORM_ROLES)))
        )
    ).all()
    for email, role_name, tenant_id, accepted_at, revoked_at in invitations:
        state = "accepted" if accepted_at else ("revoked" if revoked_at else "pending")
        findings.append(
            Finding(
                kind="invitation",
                tenant_id=str(tenant_id),
                subject=email,
                role=role_name,
                detail=f"invitation names a platform role ({state})",
            )
        )
    return findings


def render(findings: list[Finding]) -> str:
    if not findings:
        return (
            "WO-109 audit: nothing found — no platform role is granted inside any tenant, "
            "and no invitation names one."
        )
    lines = [f"WO-109 audit: {len(findings)} finding(s) — this is an incident (DEPLOYMENT.md §12)"]
    for f in findings:
        lines.append(f"  {f.kind:<10} tenant={f.tenant_id} {f.subject} role={f.role} — {f.detail}")
    lines.append(
        "Remedy: revoke each grant (platform session, DELETE /v1/authz/assignments in that tenant, "
        "or delete the user_role row), then revoke that user's sessions; revoke pending "
        "invitations; treat accepted ones as the account they created."
    )
    return "\n".join(lines)


async def _run() -> int:
    from platform_core.core.rls import platform_factory

    async with platform_factory("WO-109 platform-role audit (read-only)")() as session:
        findings = await find_platform_grants(session)
    print(render(findings))  # noqa: T201 — a command's answer
    return 1 if findings else 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
