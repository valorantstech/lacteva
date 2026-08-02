"""Permission registry — the single source of permission keys.

Keys are `<module>.<action>`; modules register their permissions here so the
engine, admin portal, and docs enumerate one list. Business modules will
extend this registry (e.g. collect.shift.open) without touching the engine.
"""

PERMISSIONS: dict[str, str] = {
    "identity.user.read": "Read users in the tenant",
    "identity.user.manage": "Create/deactivate users in the tenant",
    "organization.read": "Read organization details",
    "organization.manage": "Create and administer organizations",
    "organization.structure.read": "Read workspaces and branches",
    "organization.structure.manage": "Create and administer workspaces and branches",
    "organization.member.read": "Read members and invitations",
    "organization.member.manage": "Invite and administer members",
    "authz.role.read": "Read roles and assignments",
    "authz.role.manage": "Define roles and assign them to users",
    "configuration.read": "Read configuration entries",
    "configuration.write": "Write configuration entries",
    "audit.read": "Read the audit trail",
}

WILDCARD = "*"

# System roles seeded at bootstrap (see authz/service.py:ensure_system_roles).
SYSTEM_ROLES: dict[str, list[str]] = {
    "platform-admin": [WILDCARD],
    "tenant-admin": [
        "identity.user.read",
        "identity.user.manage",
        "organization.read",
        "organization.structure.read",
        "organization.structure.manage",
        "organization.member.read",
        "organization.member.manage",
        "authz.role.read",
        "authz.role.manage",
        "configuration.read",
        "configuration.write",
        "audit.read",
    ],
    "tenant-viewer": [
        "identity.user.read",
        "organization.read",
        "organization.structure.read",
        "organization.member.read",
        "audit.read",
    ],
}


def is_registered(key: str) -> bool:
    return key == WILDCARD or key in PERMISSIONS
