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
    # PROD-001 tenant lifecycle. Deliberately SEPARATE from organization.manage:
    # exporting every record the platform holds, and irreversibly offboarding a
    # tenant, are not the same authority as renaming a branch. A deployment can
    # grant day-to-day administration without granting either.
    "organization.data.export": "Export all of this tenant's data",
    "organization.data.delete": "Irreversibly offboard this tenant",
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
    "reporting.read": "Read operational reports and summaries",
    "notification.read": "Read notification history and templates",
    "notification.manage": "Retry notifications and operate the notification engine",
    "settlement.read": "Read settlements and their lines",
    "settlement.manage": "Create settlements, manage lines, calculate totals, cancel",
    "settlement.finalize": "Finalize settlements (makes them immutable)",
    "payment.read": "Read payments, attempts, and outstanding balances",
    "payment.manage": "Create, submit, execute, and complete payments",
    "payment.retry": "Retry a failed payment (opens a new attempt)",
    "payment.cancel": "Cancel a payment that has not completed",
    "receipt.read": "Read receipts and their history",
    "receipt.manage": "Mark receipts delivered and archive them",
    "receipt.download": "Render and download receipt artifacts",
    "sync.read": "Read the offline sync monitor (queue status, conflicts, statistics)",
    "platform.security.manage": (
        "Inspect signing keys and security configuration — platform staff only"
    ),
    "platform.relay.manage": (
        "Operate the event relay (replay, retry, dead letters) — platform staff only"
    ),
}

WILDCARD = "*"

# System roles seeded at bootstrap (see authz/service.py:ensure_system_roles).
SYSTEM_ROLES: dict[str, list[str]] = {
    "platform-admin": [WILDCARD],
    "tenant-admin": [
        # The tenant's own administrator owns their data — that is the whole
        # premise of an export/erasure right. Offboarding still requires the
        # organization's exact name as confirmation (core/tenant_lifecycle.py).
        "organization.data.export",
        "organization.data.delete",
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
        "payment.read",
        "payment.manage",
        "payment.retry",
        "payment.cancel",
        "receipt.read",
        "receipt.manage",
        "receipt.download",
        "sync.read",
        "reporting.read",
        "notification.read",
        "notification.manage",
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
        "payment.read",
        "receipt.read",
        "receipt.download",
        "sync.read",
        "reporting.read",
        "notification.read",
    ],
}


# --- DEMO-008: the named operational roles -----------------------------------
#
# These are composed ENTIRELY from the keys registered above. No permission was
# renamed to accommodate them: the registry spells capabilities
# `<module>.<entity>.<action>` and every guard, every seeded grant and every
# test in the tree already depends on those exact strings. Renaming
# `collection.center.read` to `centre.view` would have been a cosmetic change
# that broke DEMO-001 through DEMO-007 on the way past.
#
# What each role means is therefore expressed as a SET of existing permissions,
# and is resolved from the database at request time like every other grant —
# the role name is a label on a row, never a branch in the code.
#
# `tenant-admin` and `tenant-viewer` are kept unchanged. Every existing demo
# user, invitation and test holds one of them, and this work order does not get
# to invalidate them.

_FINANCE_OFFICER = [
    "reporting.read",
    "settlement.read",
    "settlement.manage",
    "payment.read",
    "payment.manage",
    "payment.retry",
    "receipt.read",
    "receipt.download",
    # Reading a settlement without being able to see the collections inside it
    # is not a job anyone can do.
    "collection.transaction.read",
    "supplier.read",
    "collection.center.read",
]

_AUDITOR_READS = [
    "audit.read",
    "reporting.read",
    "organization.read",
    "organization.structure.read",
    "organization.member.read",
    "identity.user.read",
    "authz.role.read",
    "collection.center.read",
    "operations.device.read",
    "operations.readiness.read",
    "supplier.read",
    "collection.transaction.read",
    "pricing.ratecard.read",
    "settlement.read",
    "payment.read",
    "receipt.read",
    "notification.read",
    "sync.read",
]

NAMED_ROLES: dict[str, list[str]] = {
    # Platform staff. The wildcard is the same grant `platform-admin` holds;
    # this is the name the DEMO-008 vocabulary uses for it.
    "PLATFORM_SUPER_ADMIN": [WILDCARD],
    # Everything inside one organization — the tenant's own administrator.
    "ORGANIZATION_ADMIN": list(SYSTEM_ROLES["tenant-admin"]),
    # Runs operations, but administers neither people nor prices. Deliberately
    # WITHOUT settlement.finalize, payment.manage, identity.user.manage and
    # pricing.ratecard.approve.
    "ORGANIZATION_MANAGER": [
        "organization.read",
        "organization.structure.read",
        "organization.member.read",
        "collection.center.read",
        "operations.device.read",
        "operations.readiness.read",
        "supplier.read",
        "collection.session.manage",
        "collection.transaction.read",
        "collection.transaction.record",
        "pricing.ratecard.read",
        "settlement.read",
        "payment.read",
        "receipt.read",
        "receipt.download",
        "reporting.read",
        "notification.read",
        "sync.read",
    ],
    # One centre's operation. The centre restriction is NOT expressed here —
    # a permission set cannot say "only centre A". It is enforced separately,
    # against `operator_assignment`, by `require_center_access`.
    "CENTRE_MANAGER": [
        "collection.center.read",
        "operations.device.read",
        "operations.readiness.read",
        "supplier.read",
        "collection.session.manage",
        "collection.transaction.read",
        "collection.transaction.record",
        "reporting.read",
        "settlement.read",
    ],
    # The person at the intake bay. Records collections; administers nothing.
    "COLLECTION_OPERATOR": [
        "collection.center.read",
        "operations.readiness.read",
        "supplier.read",
        "collection.session.manage",
        "collection.transaction.record",
        "collection.transaction.read",
    ],
    "FINANCE_OFFICER": list(_FINANCE_OFFICER),
    # Everything the officer can do, plus the two irreversible ones.
    "FINANCE_MANAGER": [
        *_FINANCE_OFFICER,
        "settlement.finalize",
        "payment.cancel",
        "receipt.manage",
    ],
    # Reads everything, changes nothing. Asserted by test rather than by
    # inspection: no key in this list ends in manage/record/finalize/retry.
    "AUDITOR": list(_AUDITOR_READS),
}


# Everything `ensure_system_roles` seeds. One dict, so a role cannot exist in
# the vocabulary and be absent from the database.
ALL_SYSTEM_ROLES: dict[str, list[str]] = {**SYSTEM_ROLES, **NAMED_ROLES}


def is_registered(key: str) -> bool:
    return key == WILDCARD or key in PERMISSIONS
