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
    "collection.center.read": "Read collection centers, hours, and calendars",
    "collection.center.manage": "Create and administer collection centers",
    "operations.device.read": "Read the device registry and device health",
    "operations.device.manage": "Register, assign, and administer devices; assign operators",
    "operations.readiness.read": "Evaluate and read collection center readiness",
    "supplier.read": "Read suppliers, documents, and placements",
    "supplier.manage": "Register, import, and administer suppliers",
    "collection.session.manage": "Open and close collection sessions",
    "collection.transaction.record": "Record milk collection transactions",
    "collection.transaction.read": "Read milk collection transactions and their events",
    "pricing.ratecard.read": "Read rate cards and their assignments",
    "pricing.ratecard.manage": "Create, edit, submit, version, and archive rate cards",
    "pricing.ratecard.approve": "Approve and publish rate cards",
    "settlement.read": "Read settlements and their lines",
    "settlement.manage": "Create settlements, manage lines, calculate totals, cancel",
    "settlement.finalize": "Finalize settlements (makes them immutable)",
    "platform.relay.manage": (
        "Operate the event relay (replay, retry, dead letters) — platform staff only"
    ),
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
        "collection.center.read",
        "collection.center.manage",
        "operations.device.read",
        "operations.device.manage",
        "operations.readiness.read",
        "supplier.read",
        "supplier.manage",
        "collection.session.manage",
        "collection.transaction.record",
        "collection.transaction.read",
        "pricing.ratecard.read",
        "pricing.ratecard.manage",
        "pricing.ratecard.approve",
        "settlement.read",
        "settlement.manage",
        "settlement.finalize",
    ],
    "tenant-viewer": [
        "identity.user.read",
        "organization.read",
        "organization.structure.read",
        "organization.member.read",
        "audit.read",
        "collection.center.read",
        "operations.device.read",
        "operations.readiness.read",
        "supplier.read",
        "collection.transaction.read",
        "pricing.ratecard.read",
        "settlement.read",
    ],
}


def is_registered(key: str) -> bool:
    return key == WILDCARD or key in PERMISSIONS
