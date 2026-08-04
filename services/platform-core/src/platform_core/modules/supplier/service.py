"""Supplier module — application service: lifecycle, placement, QR, import."""

import base64
import hashlib
import hmac
import secrets
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.config import get_settings
from platform_core.core.errors import (
    ConflictError,
    InvalidTokenError,
    NotFoundError,
)
from platform_core.core.tenancy import require_current_tenant
from platform_core.infrastructure.events import EventBus, EventEnvelope
from platform_core.infrastructure.storage import ObjectStorage, tenant_key
from platform_core.modules.audit.service import AuditService
from platform_core.modules.collection_center.models import CollectionCenter
from platform_core.modules.organization.models import Branch
from platform_core.modules.supplier.models import (
    DOCUMENT_KINDS,
    SUPPLIER_STATUSES,
    Supplier,
    SupplierBankAccount,
    SupplierCenterAssignment,
    SupplierDocument,
    SupplierProfile,
)

SUPPLIER_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"active", "archived"},
    "active": {"suspended", "archived"},
    "suspended": {"active", "archived"},
    "archived": set(),
}

MAX_IMPORT_ROWS = 500
MAX_DOCUMENT_BYTES = 5 * 1024 * 1024


# --- DTOs ------------------------------------------------------------------


class SupplierProfileInput(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    phone: str = Field(default="", max_length=30)
    national_id: str = Field(default="", max_length=60)
    village: str = Field(default="", max_length=120)
    locale: str = "en"
    extra: dict[str, Any] = Field(default_factory=dict)


class CreateSupplierCommand(SupplierProfileInput):
    code: str | None = Field(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{1,18}$")
    branch_id: uuid.UUID | None = None


class SupplierView(BaseModel):
    id: uuid.UUID
    code: str
    status: str
    branch_id: uuid.UUID | None
    full_name: str
    phone: str


class BankAccountView(BaseModel):
    id: uuid.UUID
    account_name: str
    account_number_masked: str
    bank_code: str
    is_primary: bool


class DocumentView(BaseModel):
    id: uuid.UUID
    kind: str
    file_name: str
    content_type: str
    uploaded_at: datetime

    model_config = {"from_attributes": True}


class SupplierDetailView(BaseModel):
    supplier: SupplierView
    profile: SupplierProfileInput
    center_ids: list[uuid.UUID]
    bank_accounts: list[BankAccountView]
    documents: list[DocumentView]


class SupplierPage(BaseModel):
    items: list[SupplierView]
    total: int
    limit: int
    offset: int


class ImportRow(SupplierProfileInput):
    code: str | None = None
    center_codes: list[str] = Field(default_factory=list)


class ImportRowResult(BaseModel):
    row: int
    status: str  # created | error
    supplier_id: uuid.UUID | None = None
    error: str | None = None


class UploadDocumentCommand(BaseModel):
    kind: str
    file_name: str = Field(min_length=1, max_length=200)
    content_type: str = Field(min_length=3, max_length=100)
    content_base64: str

    @field_validator("kind")
    @classmethod
    def _valid_kind(cls, v: str) -> str:
        if v not in DOCUMENT_KINDS:
            raise ValueError(f"kind must be one of {DOCUMENT_KINDS}")
        return v


class AddBankAccountCommand(BaseModel):
    account_name: str = Field(min_length=2, max_length=200)
    account_number: str = Field(min_length=4, max_length=60)
    bank_code: str = Field(min_length=2, max_length=40)
    is_primary: bool = False


def _mask(account_number: str) -> str:
    return "•" * max(0, len(account_number) - 4) + account_number[-4:]


def qr_payload_for(supplier_id: uuid.UUID) -> str:
    """Offline-verifiable supplier QR payload: LCT1.<id-hex>.<hmac16>."""
    body = f"LCT1.{supplier_id.hex}"
    sig = hmac.new(get_settings().jwt_secret.encode(), body.encode(), hashlib.sha256).hexdigest()[
        :16
    ]
    return f"{body}.{sig}"


def parse_qr_payload(payload: str) -> uuid.UUID:
    try:
        prefix, id_hex, sig = payload.strip().split(".")
        if prefix != "LCT1":
            raise ValueError
        expected = hmac.new(
            get_settings().jwt_secret.encode(), f"{prefix}.{id_hex}".encode(), hashlib.sha256
        ).hexdigest()[:16]
        if not hmac.compare_digest(sig, expected):
            raise ValueError
        return uuid.UUID(hex=id_hex)
    except (ValueError, AttributeError) as exc:
        raise InvalidTokenError("invalid supplier QR payload") from exc


class SupplierService:
    def __init__(
        self,
        session: AsyncSession,
        bus: EventBus,
        audit: AuditService,
        storage: ObjectStorage,
    ):
        self._session = session
        self._bus = bus
        self._audit = audit
        self._storage = storage

    # --- lifecycle --------------------------------------------------------

    async def create(self, cmd: CreateSupplierCommand, *, actor_id: uuid.UUID) -> Supplier:
        tenant_id = require_current_tenant()
        if cmd.branch_id is not None:
            branch = await self._session.get(Branch, cmd.branch_id)
            if branch is None or branch.tenant_id != tenant_id:
                raise NotFoundError("branch not found")
        code = cmd.code or await self._generate_code(tenant_id)
        existing = await self._session.scalar(
            select(Supplier).where(Supplier.tenant_id == tenant_id, Supplier.code == code)
        )
        if existing is not None:
            raise ConflictError("supplier code already exists")
        supplier = Supplier(tenant_id=tenant_id, code=code, branch_id=cmd.branch_id)
        self._session.add(supplier)
        await self._session.flush()
        self._session.add(
            SupplierProfile(
                supplier_id=supplier.id,
                full_name=cmd.full_name,
                phone=cmd.phone,
                national_id=cmd.national_id,
                village=cmd.village,
                locale=cmd.locale,
                extra=cmd.extra,
            )
        )
        await self._audit.record(
            action="supplier.registered",
            resource_type="supplier",
            resource_id=supplier.id,
            actor_id=actor_id,
            detail={"code": code},
        )
        await self._bus.publish(
            EventEnvelope.new(
                "supplier.supplier-registered.v1",
                {
                    "supplier_id": str(supplier.id),
                    "code": code,
                    # Contact details for the notification recipient directory
                    # (NOT-001) — consumers must never query this module.
                    "full_name": cmd.full_name,
                    "phone": cmd.phone,
                    "locale": cmd.locale,
                },
                actor_id=actor_id,
            )
        )
        return supplier

    async def update_profile(
        self, supplier_id: uuid.UUID, cmd: SupplierProfileInput, *, actor_id: uuid.UUID
    ) -> SupplierProfile:
        supplier = await self.get(supplier_id)
        if supplier.status == "archived":
            raise ConflictError("archived suppliers are immutable")
        profile = await self._profile(supplier.id)
        profile.full_name = cmd.full_name
        profile.phone = cmd.phone
        profile.national_id = cmd.national_id
        profile.village = cmd.village
        profile.locale = cmd.locale
        profile.extra = cmd.extra
        await self._audit.record(
            action="supplier.profile_updated",
            resource_type="supplier",
            resource_id=supplier.id,
            actor_id=actor_id,
        )
        return profile

    async def set_status(
        self, supplier_id: uuid.UUID, new_status: str, *, actor_id: uuid.UUID
    ) -> Supplier:
        if new_status not in SUPPLIER_STATUSES:
            raise ConflictError(f"unknown status: {new_status}")
        supplier = await self.get(supplier_id)
        if new_status == supplier.status:
            return supplier
        if new_status not in SUPPLIER_TRANSITIONS[supplier.status]:
            raise ConflictError(f"cannot move from {supplier.status} to {new_status}")
        if new_status == "active":
            centers = await self._session.scalar(
                select(func.count())
                .select_from(SupplierCenterAssignment)
                .where(SupplierCenterAssignment.supplier_id == supplier.id)
            )
            if not centers:
                raise ConflictError(
                    "cannot activate a supplier without a collection center assignment"
                )
        previous = supplier.status
        supplier.status = new_status
        await self._audit.record(
            action="supplier.status_changed",
            resource_type="supplier",
            resource_id=supplier.id,
            actor_id=actor_id,
            detail={"from": previous, "to": new_status},
        )
        await self._bus.publish(
            EventEnvelope.new(
                "supplier.supplier-status-changed.v1",
                {
                    "supplier_id": str(supplier.id),
                    "code": supplier.code,
                    "from": previous,
                    "to": new_status,
                },
                actor_id=actor_id,
            )
        )
        return supplier

    # --- placement --------------------------------------------------------

    async def assign_center(
        self, supplier_id: uuid.UUID, center_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> SupplierCenterAssignment:
        tenant_id = require_current_tenant()
        supplier = await self.get(supplier_id)
        center = await self._session.get(CollectionCenter, center_id)
        if center is None or center.tenant_id != tenant_id:
            raise NotFoundError("collection center not found")
        existing = await self._session.scalar(
            select(SupplierCenterAssignment).where(
                SupplierCenterAssignment.supplier_id == supplier.id,
                SupplierCenterAssignment.center_id == center.id,
            )
        )
        if existing is not None:
            raise ConflictError("supplier already assigned to this center")
        assignment = SupplierCenterAssignment(
            tenant_id=tenant_id, supplier_id=supplier.id, center_id=center.id
        )
        self._session.add(assignment)
        await self._session.flush()
        await self._audit.record(
            action="supplier.center_assigned",
            resource_type="supplier",
            resource_id=supplier.id,
            actor_id=actor_id,
            detail={"center_id": str(center.id)},
        )
        await self._bus.publish(
            EventEnvelope.new(
                "supplier.supplier-assigned-to-center.v1",
                {"supplier_id": str(supplier.id), "center_id": str(center.id)},
                actor_id=actor_id,
            )
        )
        return assignment

    async def unassign_center(
        self, supplier_id: uuid.UUID, center_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> None:
        supplier = await self.get(supplier_id)
        assignment = await self._session.scalar(
            select(SupplierCenterAssignment).where(
                SupplierCenterAssignment.supplier_id == supplier.id,
                SupplierCenterAssignment.center_id == center_id,
            )
        )
        if assignment is None:
            raise NotFoundError("assignment not found")
        await self._session.delete(assignment)
        await self._audit.record(
            action="supplier.center_unassigned",
            resource_type="supplier",
            resource_id=supplier.id,
            actor_id=actor_id,
            detail={"center_id": str(center_id)},
        )

    async def set_branch(
        self, supplier_id: uuid.UUID, branch_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> Supplier:
        tenant_id = require_current_tenant()
        supplier = await self.get(supplier_id)
        branch = await self._session.get(Branch, branch_id)
        if branch is None or branch.tenant_id != tenant_id:
            raise NotFoundError("branch not found")
        supplier.branch_id = branch.id
        await self._audit.record(
            action="supplier.branch_assigned",
            resource_type="supplier",
            resource_id=supplier.id,
            actor_id=actor_id,
            detail={"branch_id": str(branch.id)},
        )
        return supplier

    # --- banking ----------------------------------------------------------

    async def add_bank_account(
        self, supplier_id: uuid.UUID, cmd: AddBankAccountCommand, *, actor_id: uuid.UUID
    ) -> SupplierBankAccount:
        supplier = await self.get(supplier_id)
        if cmd.is_primary:
            existing = await self._session.scalars(
                select(SupplierBankAccount).where(
                    SupplierBankAccount.supplier_id == supplier.id,
                    SupplierBankAccount.is_primary,
                )
            )
            for account in existing.all():
                account.is_primary = False
        account = SupplierBankAccount(
            supplier_id=supplier.id,
            account_name=cmd.account_name,
            account_number=cmd.account_number,
            bank_code=cmd.bank_code,
            is_primary=cmd.is_primary,
        )
        self._session.add(account)
        await self._session.flush()
        await self._audit.record(
            action="supplier.bank_account_added",
            resource_type="supplier",
            resource_id=supplier.id,
            actor_id=actor_id,
            detail={"bank_code": cmd.bank_code, "masked": _mask(cmd.account_number)},
        )
        return account

    async def list_bank_accounts(self, supplier_id: uuid.UUID) -> list[BankAccountView]:
        supplier = await self.get(supplier_id)
        rows = await self._session.scalars(
            select(SupplierBankAccount)
            .where(SupplierBankAccount.supplier_id == supplier.id)
            .order_by(SupplierBankAccount.created_at)
        )
        return [
            BankAccountView(
                id=a.id,
                account_name=a.account_name,
                account_number_masked=_mask(a.account_number),
                bank_code=a.bank_code,
                is_primary=a.is_primary,
            )
            for a in rows.all()
        ]

    # --- documents ---------------------------------------------------------

    async def add_document(
        self, supplier_id: uuid.UUID, cmd: UploadDocumentCommand, *, actor_id: uuid.UUID
    ) -> SupplierDocument:
        supplier = await self.get(supplier_id)
        try:
            content = base64.b64decode(cmd.content_base64, validate=True)
        except Exception as exc:
            raise InvalidTokenError("content_base64 is not valid base64") from exc
        if not content or len(content) > MAX_DOCUMENT_BYTES:
            raise ConflictError("document must be between 1 byte and 5 MiB")
        key = tenant_key(
            supplier.tenant_id,
            f"suppliers/{supplier.id}/{uuid.uuid4().hex}-{cmd.file_name}",
        )
        await self._storage.put_object(key, content, cmd.content_type)
        document = SupplierDocument(
            supplier_id=supplier.id,
            kind=cmd.kind,
            file_name=cmd.file_name,
            content_type=cmd.content_type,
            object_key=key,
            uploaded_by=actor_id,
        )
        self._session.add(document)
        await self._session.flush()
        await self._audit.record(
            action="supplier.document_added",
            resource_type="supplier",
            resource_id=supplier.id,
            actor_id=actor_id,
            detail={"kind": cmd.kind, "file": cmd.file_name},
        )
        return document

    async def list_documents(self, supplier_id: uuid.UUID) -> list[SupplierDocument]:
        supplier = await self.get(supplier_id)
        rows = await self._session.scalars(
            select(SupplierDocument)
            .where(SupplierDocument.supplier_id == supplier.id)
            .order_by(SupplierDocument.uploaded_at)
        )
        return list(rows.all())

    async def document_url(self, supplier_id: uuid.UUID, document_id: uuid.UUID) -> str:
        supplier = await self.get(supplier_id)
        document = await self._session.get(SupplierDocument, document_id)
        if document is None or document.supplier_id != supplier.id:
            raise NotFoundError("document not found")
        return await self._storage.presigned_get_url(document.object_key)

    # --- queries -----------------------------------------------------------

    async def get(self, supplier_id: uuid.UUID) -> Supplier:
        tenant_id = require_current_tenant()
        supplier = await self._session.get(Supplier, supplier_id)
        if supplier is None or supplier.tenant_id != tenant_id:
            raise NotFoundError("supplier not found")
        return supplier

    async def detail(self, supplier_id: uuid.UUID) -> SupplierDetailView:
        supplier = await self.get(supplier_id)
        profile = await self._profile(supplier.id)
        centers = await self._session.scalars(
            select(SupplierCenterAssignment.center_id).where(
                SupplierCenterAssignment.supplier_id == supplier.id
            )
        )
        return SupplierDetailView(
            supplier=self._view(supplier, profile),
            profile=SupplierProfileInput(
                full_name=profile.full_name,
                phone=profile.phone,
                national_id=profile.national_id,
                village=profile.village,
                locale=profile.locale,
                extra=profile.extra,
            ),
            center_ids=list(centers.all()),
            bank_accounts=await self.list_bank_accounts(supplier.id),
            documents=[
                DocumentView.model_validate(d) for d in await self.list_documents(supplier.id)
            ],
        )

    async def search(
        self,
        *,
        q: str | None = None,
        status: str | None = None,
        center_id: uuid.UUID | None = None,
        branch_id: uuid.UUID | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> SupplierPage:
        tenant_id = require_current_tenant()
        limit = max(1, min(limit, 100))
        stmt = (
            select(Supplier, SupplierProfile)
            .join(SupplierProfile, SupplierProfile.supplier_id == Supplier.id)
            .where(Supplier.tenant_id == tenant_id)
        )
        if q:
            like = f"%{q.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(SupplierProfile.full_name).like(like),
                    func.lower(Supplier.code).like(like),
                    func.lower(SupplierProfile.phone).like(like),
                )
            )
        if status:
            stmt = stmt.where(Supplier.status == status)
        if branch_id:
            stmt = stmt.where(Supplier.branch_id == branch_id)
        if center_id:
            stmt = stmt.join(
                SupplierCenterAssignment,
                SupplierCenterAssignment.supplier_id == Supplier.id,
            ).where(SupplierCenterAssignment.center_id == center_id)
        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = await self._session.execute(stmt.order_by(Supplier.code).limit(limit).offset(offset))
        return SupplierPage(
            items=[self._view(s, p) for s, p in rows.all()],
            total=total or 0,
            limit=limit,
            offset=offset,
        )

    # --- import -------------------------------------------------------------

    async def import_rows(
        self, rows: list[dict[str, Any]], *, actor_id: uuid.UUID
    ) -> list[ImportRowResult]:
        """Rows are validated individually so one bad row cannot fail the batch."""
        if len(rows) > MAX_IMPORT_ROWS:
            raise ConflictError(f"import limited to {MAX_IMPORT_ROWS} rows")
        tenant_id = require_current_tenant()
        results: list[ImportRowResult] = []
        centers_by_code = {
            c.code: c
            for c in (
                await self._session.scalars(
                    select(CollectionCenter).where(CollectionCenter.tenant_id == tenant_id)
                )
            ).all()
        }
        for index, raw in enumerate(rows):
            try:
                row = ImportRow(**raw)
                supplier = await self.create(
                    CreateSupplierCommand(**row.model_dump(exclude={"center_codes"})),
                    actor_id=actor_id,
                )
                for center_code in row.center_codes:
                    center = centers_by_code.get(center_code)
                    if center is None:
                        raise NotFoundError(f"unknown center code: {center_code}")
                    await self.assign_center(supplier.id, center.id, actor_id=actor_id)
                results.append(
                    ImportRowResult(row=index, status="created", supplier_id=supplier.id)
                )
            except Exception as exc:
                results.append(ImportRowResult(row=index, status="error", error=str(exc)))
        created = sum(1 for r in results if r.status == "created")
        await self._bus.publish(
            EventEnvelope.new(
                "supplier.supplier-import-completed.v1",
                {"total": len(rows), "created": created, "failed": len(rows) - created},
                actor_id=actor_id,
            )
        )
        return results

    # --- QR -----------------------------------------------------------------

    async def resolve_qr(self, payload: str) -> Supplier:
        supplier_id = parse_qr_payload(payload)
        return await self.get(supplier_id)  # tenant check inside get()

    # --- helpers ------------------------------------------------------------

    def _view(self, supplier: Supplier, profile: SupplierProfile) -> SupplierView:
        return SupplierView(
            id=supplier.id,
            code=supplier.code,
            status=supplier.status,
            branch_id=supplier.branch_id,
            full_name=profile.full_name,
            phone=profile.phone,
        )

    async def _profile(self, supplier_id: uuid.UUID) -> SupplierProfile:
        profile = await self._session.scalar(
            select(SupplierProfile).where(SupplierProfile.supplier_id == supplier_id)
        )
        if profile is None:  # defensive: created together in create()
            raise NotFoundError("supplier profile missing")
        return profile

    async def _generate_code(self, tenant_id: uuid.UUID) -> str:
        for _ in range(5):
            candidate = "S-" + secrets.token_hex(3).upper()
            exists = await self._session.scalar(
                select(Supplier).where(Supplier.tenant_id == tenant_id, Supplier.code == candidate)
            )
            if exists is None:
                return candidate
        raise ConflictError("could not generate a unique supplier code")
