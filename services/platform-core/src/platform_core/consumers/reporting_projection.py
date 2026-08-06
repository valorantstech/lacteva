"""Reporting projection (SPRINT-008B; lifecycle since PLT-001).

Maintains the daily/center/supplier totals projections from completed
collection transactions — EXCLUSIVELY from event payloads, never by
querying transactional tables. Exactly-once per event is guaranteed by
the framework's idempotency ledger, so plain read-modify-write upserts
are safe here, and the same handler serves incremental processing and
full replay (so a rebuild can never diverge from live behavior).
"""

import uuid
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.infrastructure.events import EventEnvelope
from platform_core.modules.event_relay.projections import Projection, register_projection
from platform_core.modules.reporting.models import (
    CenterTotalsProjection,
    DailyTotalsProjection,
    SupplierTotalsProjection,
)

# The scales the projection columns actually store (reporting/models.py):
# total_net_weight NUMERIC(16,3) — grams; payable_amount NUMERIC(16,2) — minor
# units. Named here so the handler rounds to the same place the column does.
_WEIGHT_SCALE = Decimal("0.001")
_MONEY_SCALE = Decimal("0.01")


class ReportingProjection(Projection):
    name = "reporting-projection"
    version = 1
    owner_module = "reporting"
    description = "Daily, per-center and per-supplier collection totals."
    event_types = ("collection.transaction-completed.v1",)
    rebuild_strategy = "full-replay"
    replay_order = 10
    models = (DailyTotalsProjection, CenterTotalsProjection, SupplierTotalsProjection)

    async def handle(self, envelope: EventEnvelope, session: AsyncSession) -> None:
        data = envelope.data
        if envelope.tenant_id is None:  # defensive: collection events are tenant-scoped
            return
        day = datetime.fromisoformat(envelope.time).date()
        rejected = bool(data.get("rejected"))
        weight = Decimal(str(data.get("net_weight") or 0)) if not rejected else Decimal("0")
        gross = (
            Decimal(str(data["gross_amount"]))
            if (not rejected and data.get("gross_amount") is not None)
            else Decimal("0")
        )
        currency = data.get("currency") if not rejected else None

        await self._apply(
            session,
            DailyTotalsProjection,
            {"tenant_id": envelope.tenant_id, "day": day},
            rejected,
            weight,
            gross,
            currency,
        )
        await self._apply(
            session,
            CenterTotalsProjection,
            {
                "tenant_id": envelope.tenant_id,
                "day": day,
                "center_id": uuid.UUID(data["center_id"]),
            },
            rejected,
            weight,
            gross,
            currency,
        )
        if data.get("supplier_id"):
            await self._apply(
                session,
                SupplierTotalsProjection,
                {
                    "tenant_id": envelope.tenant_id,
                    "day": day,
                    "supplier_id": uuid.UUID(data["supplier_id"]),
                },
                rejected,
                weight,
                gross,
                currency,
            )

    @staticmethod
    async def _apply(
        session: AsyncSession,
        model,
        key: dict,
        rejected: bool,
        weight: Decimal,
        gross: Decimal,
        currency: str | None,
    ) -> None:
        row = await session.scalar(select(model).filter_by(**key))
        if row is None:
            row = model(**key)
            session.add(row)
            await session.flush()
        row.transactions += 1
        if rejected:
            row.rejected += 1
        else:
            row.accepted += 1
        # DB-002: quantize to the COLUMN's scale at every step, not whenever a
        # flush happens to occur.
        #
        # The accumulator IS the column, and the column has a scale. The
        # incremental consumer commits once per event, so it rounded after
        # every event; a rebuild commits once per BATCH, so the row stayed in
        # the identity map and rounded once per batch. With weights carrying
        # more decimals than the column stores — which `net_weight` does,
        # being a float — the two paths reached different totals, and two
        # rebuilds at different batch sizes reached different totals again.
        # That is a hole in BR-0015: a rebuilt projection must be provably
        # identical to an incrementally built one.
        #
        # Rounding explicitly here makes the flush boundary irrelevant, which
        # is the only property that makes replay reproducible.
        row.total_net_weight = (Decimal(str(row.total_net_weight)) + weight).quantize(
            _WEIGHT_SCALE, rounding=ROUND_HALF_UP
        )
        row.payable_amount = (Decimal(str(row.payable_amount)) + gross).quantize(
            _MONEY_SCALE, rounding=ROUND_HALF_UP
        )
        if currency:
            row.currency = currency if row.currency in (None, currency) else "MIX"


register_projection(ReportingProjection())
