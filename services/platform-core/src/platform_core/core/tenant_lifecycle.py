"""Tenant export and offboarding (PROD-001).

QR-0007 recorded that a tenant could be onboarded but not offboarded: there was
no export, no deletion and no erasure path anywhere in the platform. A pilot
customer who withdrew, or exercised a right to erasure, could not be served —
and the immutability rules that protect the audit trail actively worked against
one.

## The tension this module resolves

Two obligations point in opposite directions and both are real:

* **Erasure.** A supplier is a natural person. Their name, phone number,
  national id and bank account are personal data, and a withdrawing customer
  can be required to have them removed.
* **Retention.** Settlements, payments and receipts are financial records.
  Most of the jurisdictions this platform targets require them to be kept for
  five to seven years for tax audit, and a receipt whose amounts were deleted
  is not a record of anything.

Deleting everything satisfies the first and breaks the second. Keeping
everything does the reverse. So offboarding is **not** one operation:

    PURGE      operational data with no retention duty — delete outright
    ANONYMIZE  financial and audit records — keep the amounts and the dates,
               destroy the identity they point at
    RETAIN     the tombstone proving the offboarding happened

After `execute`, the question "how much did this dairy pay in July 2026" is
still answerable and "who was S-004821" is not. That is the shape a data
protection officer and a tax auditor can both sign.

## Why the classification is derived, not listed

`core/rls.py` established the pattern and the reason: a hand-kept list is how a
new module quietly ships unprotected. The same failure applies here in the
other direction — a new table nobody classified is personal data nobody
deletes. Every tenant-owned table is therefore derived from the metadata, the
non-default treatments are declared with prose, and
`unclassified_for_offboarding()` is asserted empty by a test.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.errors import ConflictError, NotFoundError

log = structlog.get_logger("tenant.lifecycle")

PURGE = "purge"
ANONYMIZE = "anonymize"
RETAIN = "retain"

#: Tables whose rows must SURVIVE offboarding with their identifying columns
#: cleared. The value is the set of columns to blank and the reason the row
#: itself has to stay.
ANONYMIZE_COLUMNS: dict[str, tuple[tuple[str, ...], str]] = {
    "supplier_profile": (
        ("full_name", "phone", "national_id", "village", "extra"),
        "The natural person behind a supplier code. The supplier row itself is "
        "referenced by every settlement line, so it stays; the identity does not.",
    ),
    "supplier_bank_account": (
        ("account_name", "account_number", "bank_code"),
        "Payment instructions are personal financial data with no retention "
        "duty once the relationship ends, but the row is referenced by "
        "historical payments.",
    ),
    "supplier_document": (
        ("object_key", "original_filename"),
        "The stored file is deleted with the object; the row remains so a "
        "historical audit entry that references it still resolves.",
    ),
    "user_account": (
        ("email", "full_name", "password_hash"),
        "Operators and administrators are natural persons. The account row is "
        "referenced by every audit record's actor_id, which is precisely what "
        "an audit trail must not lose.",
    ),
    "audit_record": (
        ("detail",),
        "The trail of WHAT happened and WHEN must survive — that is the point "
        "of an audit record. Free-form detail can carry personal data, so it "
        "is cleared while the action, actor id and timestamp remain.",
    ),
    "notification": (
        ("recipient", "rendered_title", "rendered_body"),
        "Delivery history proves a supplier was told about a payment; the "
        "phone number and message body are the personal part.",
    ),
    "receipt": (
        ("supplier_name",),
        "A receipt is a financial document and is retained in full — except "
        "the payee's name, which is the only personal datum on it. The "
        "supplier code remains, so the document still reconciles.",
    ),
}

#: Financial and evidential tables retained WHOLE. Nothing on them identifies a
#: natural person once the tables above are anonymized.
RETAIN_WHOLE: dict[str, str] = {
    # PROD-001: found by the offboarding test, which asserted the parent/child
    # pair stayed consistent. `supplier_profile` was anonymized (kept) while
    # `supplier` defaulted to PURGE, so offboarding produced an orphan profile
    # whose supplier no longer existed — and every settlement line still
    # pointed at the deleted row. The supplier CODE is pseudonymous once the
    # profile is cleared, so retaining it erases nothing.
    "supplier": "Referenced by every settlement line; pseudonymous once its profile is cleared.",
    "settlement": "Financial record — tax retention.",
    "settlement_line": "The arithmetic behind a settlement; the parent needs it.",
    "payment": "Financial record — tax retention.",
    "payment_line": "Which settlement each payment discharged.",
    "payment_attempt": "Evidence of when and how money moved.",
    "receipt_line": "The detail of a retained receipt.",
    "milk_collection_transaction": (
        "The delivery a payment was made for. Anonymous once the supplier is."
    ),
    "organization": (
        "The tenant itself becomes a tombstone rather than disappearing (see `execute`)."
    ),
}


@dataclass
class TableTreatment:
    table: str
    treatment: str
    reason: str
    columns: tuple[str, ...] = ()


@dataclass
class OffboardingPlan:
    """What `execute` would do, without doing it."""

    tenant_id: uuid.UUID
    organization_name: str
    purge: list[TableTreatment] = field(default_factory=list)
    anonymize: list[TableTreatment] = field(default_factory=list)
    retain: list[TableTreatment] = field(default_factory=list)
    row_counts: dict[str, int] = field(default_factory=dict)

    @property
    def total_rows(self) -> int:
        return sum(self.row_counts.values())


def _tenant_tables() -> tuple[str, ...]:
    from platform_core.core.rls import tenant_tables

    return tenant_tables()


def treatment_for(table_name: str) -> TableTreatment:
    """One table's offboarding treatment. Purge is the default.

    Defaulting to PURGE rather than RETAIN is deliberate: a table nobody
    thought about is more dangerous kept than deleted, because keeping it is
    what an erasure request is about. The reverse default would quietly retain
    a new module's personal data forever.
    """
    if table_name in RETAIN_WHOLE:
        return TableTreatment(table_name, RETAIN, RETAIN_WHOLE[table_name])
    if table_name in ANONYMIZE_COLUMNS:
        columns, reason = ANONYMIZE_COLUMNS[table_name]
        return TableTreatment(table_name, ANONYMIZE, reason, columns)
    return TableTreatment(
        table_name,
        PURGE,
        "Operational data with no retention duty; deleted with the tenant.",
    )


def unclassified_for_offboarding() -> tuple[str, ...]:
    """Declared treatments naming a table that no longer exists.

    The inverse check to `rls.unclassified_tables()`: because PURGE is the
    default, a NEW table is always covered, but a RENAMED one leaves a
    declaration pointing at nothing — and a retention promise about a table
    that does not exist is worse than no promise.
    """
    from platform_core.core.db import Base

    known = set(Base.metadata.tables)
    declared = set(RETAIN_WHOLE) | set(ANONYMIZE_COLUMNS)
    return tuple(sorted(declared - known))


class TenantLifecycleService:
    """Export and offboarding for exactly one tenant.

    Every method takes the tenant explicitly rather than reading the context
    variable, because this is the one service where operating on the wrong
    tenant is unrecoverable. The API layer resolves it from the authenticated
    principal and passes it down; nothing here infers it.
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    # --- export -------------------------------------------------------------

    async def export(self, tenant_id: uuid.UUID) -> dict[str, Any]:
        """Everything the platform holds for this tenant, as portable JSON.

        Reuses the backup engine's encoder rather than inventing a second
        serialization: it already round-trips every column type in this schema
        and is covered by the DR suite (principle 9 — no duplicated concepts).

        Read under the caller's own session, so row-level security applies and
        an export cannot reach another tenant even if this code were wrong.
        """
        from platform_core.core.backup.engine import _encode
        from platform_core.core.db import Base

        organization = await self._organization(tenant_id)
        tables: dict[str, list[dict]] = {}
        counts: dict[str, int] = {}
        for name in _tenant_tables():
            model_table = Base.metadata.tables[name]
            rows = (
                await self._session.execute(
                    select(model_table).where(model_table.c.tenant_id == tenant_id)
                )
            ).mappings()
            encoded = [{k: _encode(v) for k, v in row.items()} for row in rows]
            if encoded:
                tables[name] = encoded
                counts[name] = len(encoded)

        # The organization row has no tenant_id — it IS the tenant.
        org_table = Base.metadata.tables["organization"]
        org_rows = (
            await self._session.execute(select(org_table).where(org_table.c.id == tenant_id))
        ).mappings()
        organization_rows = [{k: _encode(v) for k, v in row.items()} for row in org_rows]
        if organization_rows:
            tables["organization"] = organization_rows
            counts["organization"] = len(organization_rows)

        log.info(
            "tenant_exported",
            tenant_id=str(tenant_id),
            tables=len(tables),
            rows=sum(counts.values()),
        )
        return {
            "tenant_id": str(tenant_id),
            "organization_name": organization.name,
            "format_version": 1,
            "table_count": len(tables),
            "row_count": sum(counts.values()),
            "counts": counts,
            "tables": tables,
        }

    # --- offboarding --------------------------------------------------------

    async def plan(self, tenant_id: uuid.UUID) -> OffboardingPlan:
        """What deletion WOULD do. Always available, never destructive."""
        from platform_core.core.db import Base

        organization = await self._organization(tenant_id)
        plan = OffboardingPlan(tenant_id=tenant_id, organization_name=organization.name)
        for name in _tenant_tables():
            treatment = treatment_for(name)
            model_table = Base.metadata.tables[name]
            count = (
                await self._session.scalar(
                    select(func.count())
                    .select_from(model_table)
                    .where(model_table.c.tenant_id == tenant_id)
                )
            ) or 0
            if count:
                plan.row_counts[name] = count
            getattr(plan, treatment.treatment).append(treatment)
        return plan

    async def execute(
        self,
        tenant_id: uuid.UUID,
        *,
        confirmation: str,
        actor_id: uuid.UUID,
    ) -> OffboardingPlan:
        """Offboard the tenant. Irreversible.

        `confirmation` must be the organization's exact name. A boolean flag
        is too easy to send by accident from a script; typing the name is the
        smallest gesture that cannot be made without meaning it, and it is the
        same convention every platform uses for deleting a repository.
        """
        from platform_core.core.db import Base, utcnow

        organization = await self._organization(tenant_id)
        if confirmation != organization.name:
            raise ConflictError(
                "confirmation must be the organization's exact name — refusing to "
                "offboard a tenant on an unconfirmed request"
            )

        plan = await self.plan(tenant_id)

        # ANONYMIZE first. If the purge ran first and then failed, the rows
        # that must survive would still hold personal data; this order fails
        # safe in the direction erasure cares about.
        for treatment in plan.anonymize:
            model_table = Base.metadata.tables[treatment.table]
            values = {}
            for column in treatment.columns:
                if column not in model_table.c:  # pragma: no cover - guarded by a test
                    continue
                values[column] = _blank_for(model_table.c[column])
            if values:
                await self._session.execute(
                    update(model_table).where(model_table.c.tenant_id == tenant_id).values(**values)
                )

        # PURGE second, children before parents. Only four foreign keys exist
        # in this schema (DBR-001 F-2), so ordering is mostly advisory — but
        # where a constraint DOES exist, deleting the parent first fails.
        for treatment in sorted(plan.purge, key=lambda t: t.table, reverse=True):
            model_table = Base.metadata.tables[treatment.table]
            await self._session.execute(
                delete(model_table).where(model_table.c.tenant_id == tenant_id)
            )

        # The organization becomes a tombstone rather than disappearing: every
        # retained financial record still points at this tenant_id, and a
        # foreign key with nothing on the other end is how an export becomes
        # unreadable a year later.
        organization.name = f"[offboarded {tenant_id}]"
        organization.status = "offboarded"
        organization.offboarded_at = utcnow()

        log.warning(
            "tenant_offboarded",
            tenant_id=str(tenant_id),
            actor_id=str(actor_id),
            purged_tables=len(plan.purge),
            anonymized_tables=len(plan.anonymize),
            rows=plan.total_rows,
        )
        return plan

    async def _organization(self, tenant_id: uuid.UUID):
        from platform_core.modules.organization.models import Organization

        organization = await self._session.get(Organization, tenant_id)
        if organization is None:
            raise NotFoundError("organization not found")
        return organization


def _blank_for(column) -> Any:
    """The empty value for a column's type.

    NULL where the column allows it, because an absent value is the honest
    representation of erased data. Where it does not, the type's zero — a
    NOT NULL column cannot say "nothing" any other way.
    """
    if column.nullable:
        return None
    python_type = getattr(column.type, "python_type", str)
    try:
        resolved = python_type
    except NotImplementedError:  # pragma: no cover - exotic types
        return ""
    if resolved is dict:
        return {}
    if resolved is list:
        return []
    return ""


__all__ = [
    "ANONYMIZE",
    "ANONYMIZE_COLUMNS",
    "PURGE",
    "RETAIN",
    "RETAIN_WHOLE",
    "OffboardingPlan",
    "TableTreatment",
    "TenantLifecycleService",
    "treatment_for",
    "unclassified_for_offboarding",
]
