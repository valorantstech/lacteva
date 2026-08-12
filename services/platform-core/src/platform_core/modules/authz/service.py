"""Authorization module — permission engine and role administration."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.errors import ConflictError, NotFoundError
from platform_core.modules.authz.models import Role, RolePermission, UserRole
from platform_core.modules.authz.permissions import (
    ALL_SYSTEM_ROLES,
    WILDCARD,
    is_registered,
)

if TYPE_CHECKING:
    from platform_core.modules.audit.service import AuditService


class PermissionEngine:
    """Resolves and checks effective permissions.

    TODO(M1): per-principal permission cache in Redis with explicit
    invalidation on role/assignment change — resolution is per-request now.
    TODO(M2): attribute-based conditions (e.g. own-center-only) layered on
    top of RBAC when business modules need them; the check() signature
    already accepts a resource hint for that purpose.
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    async def effective_permissions(
        self, user_id: uuid.UUID, tenant_id: uuid.UUID | None
    ) -> set[str]:
        stmt = (
            select(RolePermission.permission_key)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .where(UserRole.user_id == user_id)
        )
        # Assignments for the current tenant plus platform-level assignments.
        stmt = stmt.where((UserRole.tenant_id == tenant_id) | (UserRole.tenant_id.is_(None)))
        return set((await self._session.scalars(stmt)).all())

    async def check(
        self,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID | None,
        permission: str,
        resource: object | None = None,  # reserved for ABAC conditions
    ) -> bool:
        perms = await self.effective_permissions(user_id, tenant_id)
        return WILDCARD in perms or permission in perms

    async def center_scope(
        self, user_id: uuid.UUID, tenant_id: uuid.UUID | None
    ) -> set[uuid.UUID] | None:
        """Which collection centres may this principal act at?

        `None` means "every centre in the organization" and is the answer for
        anyone holding at least one grant that carries no centre — which is
        every grant that existed before DEMO-008 added the column, so nothing
        that worked before is narrowed by this.

        A set means the principal is CENTRE-SCOPED: every one of their grants
        names a centre, and those are the only centres they may touch. The
        empty set cannot occur — a principal with no grants at all has no
        permissions either and is refused long before scope is consulted.

        This is the `resource` hint the engine reserved from the start, filled
        in for the one attribute the domain actually needs. It is deliberately
        not a general condition language: a centre id is the only scope this
        business has, and inventing an engine to express it would be a larger
        thing to get wrong.
        """
        rows = (
            await self._session.execute(
                select(UserRole.center_id).where(
                    UserRole.user_id == user_id,
                    (UserRole.tenant_id == tenant_id) | (UserRole.tenant_id.is_(None)),
                )
            )
        ).all()
        if not rows:
            return None
        scopes = {row[0] for row in rows}
        if None in scopes:
            return None
        return {scope for scope in scopes if scope is not None}


class AuthzService:
    def __init__(self, session: AsyncSession, audit: "AuditService | None" = None):
        self._session = session
        self._audit = audit

    async def _record(self, action: str, assignment: UserRole, actor_id: uuid.UUID | None) -> None:
        """Grants and revocations are the two entries an access review reads.

        `audit` is optional only because `ensure_system_roles` runs at startup
        where there is no actor and nothing to review; every caller that acts
        on behalf of a person passes one.
        """
        if self._audit is None or actor_id is None:
            return
        await self._audit.record(
            action=action,
            resource_type="user_role",
            resource_id=assignment.id,
            actor_id=actor_id,
            detail={"user_id": str(assignment.user_id), "role_id": str(assignment.role_id)},
        )

    async def ensure_system_roles(self) -> None:
        """Idempotent bootstrap/sync of system roles (called at startup).

        Creates missing roles and adds newly registered permissions to
        existing ones, so registry growth reaches running deployments.
        """
        for name, perms in ALL_SYSTEM_ROLES.items():
            role = await self._session.scalar(
                select(Role).where(Role.tenant_id.is_(None), Role.name == name)
            )
            if role is None:
                role = Role(tenant_id=None, name=name, description=f"System role {name}")
                self._session.add(role)
                try:
                    await self._session.flush()
                except IntegrityError:
                    # DEMO-008: another worker inserted it between our SELECT
                    # and our INSERT. Select-then-insert is not idempotent
                    # under concurrency, and every startup runs this — which is
                    # how three copies of `tenant-admin` came to exist before a
                    # partial unique index made the collision detectable at
                    # all. Losing the race is the correct outcome; adopt the
                    # winner's row and carry on.
                    await self._session.rollback()
                    role = await self._session.scalar(
                        select(Role).where(Role.tenant_id.is_(None), Role.name == name)
                    )
                    if role is None:  # pragma: no cover - defensive
                        raise
            existing = set(
                (
                    await self._session.scalars(
                        select(RolePermission.permission_key).where(
                            RolePermission.role_id == role.id
                        )
                    )
                ).all()
            )
            for key in perms:
                if key not in existing:
                    self._session.add(
                        RolePermission(
                            tenant_id=role.tenant_id, role_id=role.id, permission_key=key
                        )
                    )

    async def _resolve_role(self, role_name: str, tenant_id: uuid.UUID | None) -> Role:
        role = await self._session.scalar(
            select(Role).where(
                ((Role.tenant_id == tenant_id) | (Role.tenant_id.is_(None))),
                Role.name == role_name,
            )
        )
        if role is None:
            raise NotFoundError("role not found")
        return role

    async def assign_role(
        self,
        *,
        user_id: uuid.UUID,
        role_name: str,
        tenant_id: uuid.UUID | None,
        center_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> UserRole:
        """Grant a role, optionally limited to one collection centre.

        DEMO-008: `center_id=None` is organization-wide and is what every
        grant made before this parameter existed means. Re-granting the same
        role at a DIFFERENT centre updates the existing row rather than
        creating a second one, because the unique constraint is
        (user, role, tenant) — widening it would let one person accumulate
        silent, forgotten scopes.
        """
        role = await self._resolve_role(role_name, tenant_id)
        existing = await self._session.scalar(
            select(UserRole).where(
                UserRole.user_id == user_id,
                UserRole.role_id == role.id,
                UserRole.tenant_id == tenant_id,
            )
        )
        if existing:
            if existing.center_id != center_id:
                existing.center_id = center_id
                await self._record("authz.role.rescoped", existing, actor_id)
            return existing
        assignment = UserRole(
            user_id=user_id, role_id=role.id, tenant_id=tenant_id, center_id=center_id
        )
        self._session.add(assignment)
        await self._session.flush()
        await self._record("authz.role.granted", assignment, actor_id)
        return assignment

    async def revoke_role(
        self,
        *,
        user_id: uuid.UUID,
        role_name: str,
        tenant_id: uuid.UUID | None,
        actor_id: uuid.UUID | None = None,
    ) -> None:
        """Take a role back (SEC-003 / F-02).

        FINAL-001 found `assign_role` with no inverse anywhere in the
        platform: a mis-granted permission was permanent. Deleting the
        assignment row is the whole mechanism — `effective_permissions`
        resolves per request from exactly these rows, with no cache in front
        of it, so the next authorization check already disagrees with the
        previous one. That is why the TODO about a Redis permission cache
        matters more now than it did: whoever adds it owns the invalidation.

        Revoking a role the user does not hold is NOT an error. The caller
        asked for an end state and the end state is what they get; raising
        would only tempt an administrator to check first and race themselves.
        The assignment is scoped to the caller's tenant, so a platform-level
        grant cannot be revoked through a tenant-scoped request.
        """
        role = await self._resolve_role(role_name, tenant_id)
        assignment = await self._session.scalar(
            select(UserRole).where(
                UserRole.user_id == user_id,
                UserRole.role_id == role.id,
                UserRole.tenant_id == tenant_id,
            )
        )
        if assignment is None:
            return
        await self._record("authz.role.revoked", assignment, actor_id)
        await self._session.delete(assignment)
        await self._session.flush()

    async def create_role(
        self, *, tenant_id: uuid.UUID | None, name: str, permission_keys: list[str]
    ) -> Role:
        for key in permission_keys:
            if not is_registered(key):
                raise ConflictError(f"unknown permission key: {key}")
        existing = await self._session.scalar(
            select(Role).where(Role.tenant_id == tenant_id, Role.name == name)
        )
        if existing:
            raise ConflictError("role already exists")
        role = Role(tenant_id=tenant_id, name=name)
        self._session.add(role)
        await self._session.flush()
        for key in permission_keys:
            self._session.add(
                RolePermission(tenant_id=role.tenant_id, role_id=role.id, permission_key=key)
            )
        return role
