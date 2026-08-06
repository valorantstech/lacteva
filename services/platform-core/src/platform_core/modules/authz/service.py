"""Authorization module — permission engine and role administration."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.errors import ConflictError, NotFoundError
from platform_core.modules.authz.models import Role, RolePermission, UserRole
from platform_core.modules.authz.permissions import SYSTEM_ROLES, WILDCARD, is_registered


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


class AuthzService:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def ensure_system_roles(self) -> None:
        """Idempotent bootstrap/sync of system roles (called at startup).

        Creates missing roles and adds newly registered permissions to
        existing ones, so registry growth reaches running deployments.
        """
        for name, perms in SYSTEM_ROLES.items():
            role = await self._session.scalar(
                select(Role).where(Role.tenant_id.is_(None), Role.name == name)
            )
            if role is None:
                role = Role(tenant_id=None, name=name, description=f"System role {name}")
                self._session.add(role)
                await self._session.flush()
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

    async def assign_role(
        self, *, user_id: uuid.UUID, role_name: str, tenant_id: uuid.UUID | None
    ) -> UserRole:
        role = await self._session.scalar(
            select(Role).where(
                ((Role.tenant_id == tenant_id) | (Role.tenant_id.is_(None))),
                Role.name == role_name,
            )
        )
        if role is None:
            raise NotFoundError("role not found")
        existing = await self._session.scalar(
            select(UserRole).where(
                UserRole.user_id == user_id,
                UserRole.role_id == role.id,
                UserRole.tenant_id == tenant_id,
            )
        )
        if existing:
            return existing
        assignment = UserRole(user_id=user_id, role_id=role.id, tenant_id=tenant_id)
        self._session.add(assignment)
        return assignment

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
