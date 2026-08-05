"""Backup, restore, and disaster recovery (BAK-001).

**A successful backup is not evidence. A successful restore is.**

The centre of this file is `test_a_destroyed_platform_is_fully_recovered`: it
builds a real dairy — collection, pricing, settlement, payment, receipt,
notifications — takes a backup, **deletes every row in the database**, and
then proves the platform comes back with its money, its evidence, and its
invariants intact.

That is the acceptance criterion of this work order executed rather than
described. Everything else here supports it: classification, checksums,
corruption detection, and the business-rule integrity checks that distinguish
"the rows arrived" from "the business is correct".
"""

import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from platform_core.core import db


@pytest.fixture
def backup_dir(tmp_path) -> Path:
    return tmp_path / "backup"


def _engine():
    from platform_core.core.backup.engine import BackupEngine

    return BackupEngine(db.get_session_factory())


def _service():
    from platform_core.core.backup.service import BackupService

    return BackupService(db.get_session_factory())


def _verifier():
    from platform_core.core.backup.integrity import IntegrityVerifier

    return IntegrityVerifier(db.get_session_factory())


async def _count(model) -> int:
    async with db.get_session_factory()() as session:
        return await session.scalar(select(func.count()).select_from(model)) or 0


async def _full_dairy(client):
    """A platform with real business records: a priced collection, a finalized
    settlement, a completed payment, its receipt, and the notifications the
    chain produced."""
    from tests.test_payments import _action, _pay, _payable
    from tests.test_receipts import _runner

    headers, center, supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement, method="MOBILE_MONEY")
    for action, body in (
        ("submit", {}),
        ("execute", {}),
        ("complete", {"reference": "MPESA-RESTORE"}),
    ):
        r = await _action(client, headers, payment["id"], action, body)
        assert r.status_code == 200, r.text
    await _runner().run_once()  # receipt + notifications
    await _runner().run_once()  # the receipt's own notification
    return headers, center, supplier, settlement, payment


async def _destroy_everything() -> None:
    """Simulate total data loss: every row, every table, gone.

    Deliberately not `DROP TABLE` — the schema survives a restore from
    migrations, and what we are testing is recovery of DATA.
    """
    from platform_core.core.db import Base

    async with db.get_session_factory()() as session:
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(table.delete())
        await session.commit()


# --- the demonstration --------------------------------------------------------


async def test_a_destroyed_platform_is_fully_recovered(client, backup_dir):
    """THE test this work order exists for.

    Build a dairy, back it up, destroy every row, restore, and prove the
    business survived — not merely that rows returned.
    """
    from platform_core.modules.audit.models import AuditRecord
    from platform_core.modules.event_relay.models import OutboxEvent
    from platform_core.modules.payment.models import Payment
    from platform_core.modules.receipt.models import Receipt
    from platform_core.modules.settlement.models import Settlement

    headers, _center, _supplier, settlement, payment = await _full_dairy(client)

    # What the world looked like before the disaster.
    before = {
        "settlements": await _count(Settlement),
        "payments": await _count(Payment),
        "receipts": await _count(Receipt),
        "events": await _count(OutboxEvent),
        "audit": await _count(AuditRecord),
    }
    assert all(before.values()), f"the fixture must produce real data: {before}"
    receipts_before = (await client.get("/v1/receipts", headers=headers)).json()
    assert receipts_before["total"] == 1
    receipt_number = receipts_before["items"][0]["receipt_number"]

    manifest = await _engine().backup(backup_dir)
    assert manifest.total_rows > 0

    # --- the disaster ---
    await _destroy_everything()
    assert await _count(Payment) == 0
    assert await _count(Receipt) == 0

    # --- the recovery ---
    restored = await _engine().restore(backup_dir)
    assert restored.backup_id == manifest.backup_id

    # 1. Every business record came back.
    after = {
        "settlements": await _count(Settlement),
        "payments": await _count(Payment),
        "receipts": await _count(Receipt),
        "events": await _count(OutboxEvent),
        "audit": await _count(AuditRecord),
    }
    assert after == before, f"row counts differ after restore: {before} -> {after}"

    # 2. The money is identical, to the cent.
    async with db.get_session_factory()() as session:
        recovered_payment = await session.get(Payment, uuid.UUID(payment["id"]))
        recovered_settlement = await session.get(Settlement, uuid.UUID(settlement["id"]))
    assert recovered_payment is not None
    assert Decimal(recovered_payment.amount) == Decimal(payment["amount"])
    assert recovered_payment.status == "completed"
    assert recovered_payment.reference == "MPESA-RESTORE"
    assert Decimal(recovered_settlement.net_amount) == Decimal(settlement["net_amount"])

    # 3. The evidence survived and is still readable through the API.
    listed = (await client.get("/v1/receipts", headers=headers)).json()
    assert listed["total"] == 1
    assert listed["items"][0]["receipt_number"] == receipt_number
    rendered = await client.get(
        f"/v1/receipts/{listed['items'][0]['id']}/render?format=html", headers=headers
    )
    assert rendered.status_code == 200
    assert receipt_number in rendered.json()["body"]

    # 4. The business invariants hold — the real definition of a good restore.
    report = await _verifier().verify(deep=True)
    assert report.healthy, f"integrity failures after restore: {report.failures}"


async def test_the_restored_platform_still_works(client, backup_dir):
    """A restore that produces a read-only museum is a failed restore. The
    platform must accept new business after recovery."""
    from tests.test_payments import _pay

    headers, center, supplier, settlement, _payment = await _full_dairy(client)
    await _engine().backup(backup_dir)
    await _destroy_everything()
    await _engine().restore(backup_dir)

    # The settlement is fully paid, so a second payment must be REFUSED for
    # the right business reason — proving rules were restored, not just rows.
    from tests.test_payments import _create_payment

    r = await _create_payment(
        client, headers, supplier["id"], [{"settlement_id": settlement["id"]}]
    )
    assert r.status_code == 409
    assert "already fully paid or allocated" in r.text

    # And genuinely new work still succeeds.
    from tests.test_payments import _second_settlement

    november = await _second_settlement(client, headers, center, supplier)
    fresh = await _pay(client, headers, november)
    assert fresh["status"] == "draft"


async def test_consumers_do_not_re_fire_after_a_restore(client, backup_dir):
    """The subtlest recovery failure: restoring business data WITHOUT the
    consumer ledger replays the whole event log, sending every notification
    and minting every receipt again. The classification exists to prevent
    exactly this."""
    from platform_core.modules.notification.models import Notification
    from platform_core.modules.receipt.models import Receipt
    from tests.test_receipts import _runner

    await _full_dairy(client)
    notifications_before = await _count(Notification)
    receipts_before = await _count(Receipt)

    await _engine().backup(backup_dir)
    await _destroy_everything()
    await _engine().restore(backup_dir)

    # Run the consumers as they would run after a restart.
    await _runner().run_once()
    await _runner().run_once()

    assert await _count(Receipt) == receipts_before, "a duplicate receipt was minted"
    assert await _count(Notification) == notifications_before, (
        "notifications were re-sent — the consumer ledger was not restored"
    )


# --- classification -----------------------------------------------------------


def test_every_table_is_classified():
    from platform_core.core.backup.classification import classify_all

    entries = classify_all()
    assert len(entries) >= 50
    assert all(entry.reason for entry in entries), "a classification without a reason is a guess"


def test_business_truth_is_classified_critical():
    from platform_core.core.backup.classification import CRITICAL, classify

    for table in ("payment", "receipt", "settlement", "event_outbox", "audit_record"):
        assert classify(table).classification == CRITICAL, table


def test_projections_are_rebuildable_not_backed_up():
    """They derive from the event log (BR-0015), so backing them up costs
    restore time and buys nothing."""
    from platform_core.core.backup.classification import REBUILDABLE, classify, tables_for_backup

    assert classify("projection_daily_totals").classification == REBUILDABLE
    assert "projection_daily_totals" not in tables_for_backup()
    assert "projection_daily_totals" in tables_for_backup(include_rebuildable=True)


def test_the_consumer_ledger_is_kept_because_losing_it_duplicates_effects():
    from platform_core.core.backup.classification import IMPORTANT, classify, tables_for_backup

    for table in ("consumer_cursor", "consumer_execution", "sync_operation"):
        assert classify(table).classification == IMPORTANT, table
        assert table in tables_for_backup(), f"{table} must be captured"


def test_an_unknown_table_defaults_to_critical():
    """The safe default for 'I do not know what this is' is 'keep it'."""
    from platform_core.core.backup.classification import CRITICAL, classify

    assert classify("some_future_table").classification == CRITICAL


# --- manifest and checksums ----------------------------------------------------


async def test_the_manifest_records_what_was_captured(client, backup_dir):
    await _full_dairy(client)
    manifest = await _engine().backup(backup_dir)

    assert manifest.format_version == 1
    assert manifest.backup_id and manifest.created_at
    assert manifest.total_rows > 0
    payments = next(t for t in manifest.tables if t.table == "payment")
    assert payments.rows == 1 and payments.checksum and payments.classification == "critical"
    # A manifest must never carry credentials. (`password_reset_token` is a
    # table NAME and legitimately appears — what must not appear is a
    # connection string or a secret value.)
    assert manifest.database_url_scheme == "sqlite+aiosqlite"
    body = manifest.to_json()
    assert "://" not in body, "a connection string leaked into the manifest"
    assert "@" not in body, "credentials leaked into the manifest"


async def test_a_backup_verifies_against_its_own_checksums(client, backup_dir):
    await _full_dairy(client)
    await _engine().backup(backup_dir)
    assert _engine().verify_files(backup_dir) == []


async def test_corruption_is_detected_before_a_restore_depends_on_it(client, backup_dir):
    """The worst moment to discover a corrupt backup is halfway through a
    recovery."""
    await _full_dairy(client)
    await _engine().backup(backup_dir)

    target = backup_dir / "tables" / "payment.jsonl"
    original = target.read_text()
    target.write_text(original.replace("MPESA-RESTORE", "TAMPERED-WITH"))

    problems = _engine().verify_files(backup_dir)
    assert problems and "checksum mismatch" in problems[0]


async def test_a_truncated_backup_is_detected(client, backup_dir):
    await _full_dairy(client)
    await _engine().backup(backup_dir)
    (backup_dir / "tables" / "settlement.jsonl").write_text("")
    problems = _engine().verify_files(backup_dir)
    assert any("rows" in p or "checksum" in p for p in problems)


async def test_checksums_are_deterministic(client, backup_dir, tmp_path):
    """A checksum that changes when nothing did is a checksum nobody trusts."""
    await _full_dairy(client)
    first = await _engine().backup(backup_dir)
    second = await _engine().backup(tmp_path / "again")
    assert {t.table: t.checksum for t in first.tables} == {
        t.table: t.checksum for t in second.tables
    }


async def test_a_backup_directory_without_a_manifest_is_refused(tmp_path):
    from platform_core.core.backup.engine import BackupError

    (tmp_path / "tables").mkdir(parents=True)
    with pytest.raises(BackupError, match="not a backup directory"):
        _engine().read_manifest(tmp_path)


# --- restore safety -------------------------------------------------------------


async def test_restoring_over_live_data_is_refused_by_default(client, backup_dir):
    """Restoring over a live database is the most destructive thing this
    platform can do. It must be a decision, never a default."""
    from platform_core.core.backup.engine import BackupError

    await _full_dairy(client)
    await _engine().backup(backup_dir)

    with pytest.raises(BackupError, match="refusing to restore over a non-empty database"):
        await _engine().restore(backup_dir)

    # …and can be overridden deliberately.
    manifest = await _engine().restore(backup_dir, allow_non_empty=True)
    assert manifest.total_rows > 0


async def test_a_future_backup_format_is_refused(client, backup_dir):
    from platform_core.core.backup.engine import MANIFEST, BackupError

    await _full_dairy(client)
    await _engine().backup(backup_dir)
    path = backup_dir / MANIFEST
    path.write_text(path.read_text().replace('"format_version": 1', '"format_version": 99'))

    await _destroy_everything()
    with pytest.raises(BackupError, match="format 99"):
        await _engine().restore(backup_dir)


async def test_restore_is_not_reachable_over_http(client):
    """A misrouted request must not be able to overwrite the database."""
    from platform_core.main import create_app

    paths = {getattr(route, "path", "") for route in create_app().routes}
    assert not any("restore" in path for path in paths)


async def test_types_survive_the_round_trip(client, backup_dir):
    """Decimals must not become floats (BR-0005) and UUIDs must not become
    strings — either would corrupt money or break foreign keys."""
    from platform_core.modules.payment.models import Payment

    _headers, _c, _s, _st, payment = await _full_dairy(client)
    await _engine().backup(backup_dir)
    await _destroy_everything()
    await _engine().restore(backup_dir)

    async with db.get_session_factory()() as session:
        restored = await session.get(Payment, uuid.UUID(payment["id"]))
    assert isinstance(restored.id, uuid.UUID)
    assert isinstance(restored.amount, Decimal)
    assert restored.amount == Decimal(payment["amount"])
    assert restored.method_details == {}


# --- integrity verification ------------------------------------------------------


async def test_integrity_verification_passes_on_a_healthy_platform(client):
    await _full_dairy(client)
    report = await _verifier().verify(deep=True)
    assert report.healthy, [f"{c.name}: {c.detail}" for c in report.failures]
    names = {check.name for check in report.checks}
    assert {
        "settlement_totals_match_lines",
        "payments_never_exceed_the_payable",
        "one_receipt_per_completed_payment",
        "no_orphaned_child_rows",
        "consumer_cursors_within_the_log",
        "audit_trail_restored",
        "projections_rebuild_from_the_event_log",
    } <= names


async def test_integrity_verification_catches_a_broken_settlement(client):
    """Prove the checks can actually fail — a verifier that only ever passes
    is decoration."""
    from platform_core.modules.settlement.models import Settlement

    _headers, _c, _s, settlement, _p = await _full_dairy(client)
    async with db.get_session_factory()() as session:
        stored = await session.get(Settlement, uuid.UUID(settlement["id"]))
        stored.gross_amount = Decimal("1.00")  # tamper
        await session.commit()

    report = await _verifier().verify()
    assert not report.healthy
    failed = {c.name for c in report.failures}
    assert "settlement_totals_match_lines" in failed


async def test_integrity_verification_catches_a_dangling_receipt(client):
    """A receipt whose payment is gone is evidence of something that no longer
    exists. (A *duplicate* receipt is unreachable — the unique constraint on
    (tenant, payment) prevents it, which is that constraint doing its job.)"""
    from platform_core.modules.receipt.models import Receipt

    await _full_dairy(client)
    async with db.get_session_factory()() as session:
        original = (await session.scalars(select(Receipt))).first()
        session.add(
            Receipt(
                tenant_id=original.tenant_id,
                receipt_number="RCP-DANGLING",
                payment_id=uuid.uuid4(),  # a payment that does not exist
                supplier_id=original.supplier_id,
                payment_number="PAY-GONE",
                payment_method=original.payment_method,
                currency=original.currency,
            )
        )
        await session.commit()

    report = await _verifier().verify()
    assert not report.healthy
    assert "one_receipt_per_completed_payment" in {c.name for c in report.failures}


async def test_integrity_verification_catches_orphaned_lines(client):
    from platform_core.modules.payment.models import Payment

    await _full_dairy(client)
    async with db.get_session_factory()() as session:
        payment = (await session.scalars(select(Payment))).first()
        await session.delete(payment)  # its lines are now orphans
        await session.commit()

    report = await _verifier().verify()
    assert not report.healthy
    assert "no_orphaned_child_rows" in {c.name for c in report.failures}


# --- operator surface -------------------------------------------------------------


async def test_backup_runs_are_recorded(client, backup_dir):
    await _full_dairy(client)
    service = _service()
    run = await service.run_backup(backup_dir)

    assert run.status == "succeeded" and run.verified is True
    assert run.rows > 0 and run.tables > 0 and run.bytes_written > 0
    assert run.duration_seconds is not None

    history = await service.history()
    assert history and history[0].kind == "backup" and history[0].status == "succeeded"


async def test_status_answers_are_we_protected(client, backup_dir):
    service = _service()

    cold = await service.status()
    assert cold.healthy is False
    assert "no successful backup" in cold.detail

    await _full_dairy(client)
    await service.run_backup(backup_dir)
    warm = await service.status()
    assert warm.healthy is True
    assert warm.last_successful_backup is not None
    assert warm.age_hours is not None and warm.age_hours < 1


async def test_a_stale_backup_is_reported_unhealthy(client, backup_dir):
    """A backup from last week is not protection."""
    from datetime import timedelta

    from platform_core.core.backup.models import BackupRun
    from platform_core.core.db import utcnow

    service = _service()
    await _full_dairy(client)
    await service.run_backup(backup_dir)
    async with db.get_session_factory()() as session:
        run = (await session.scalars(select(BackupRun))).first()
        run.started_at = utcnow() - timedelta(days=3)
        await session.commit()

    status = await service.status()
    assert status.healthy is False
    assert "hours old" in status.detail


async def test_an_unverified_backup_is_reported_unhealthy(client, backup_dir):
    service = _service()
    await _full_dairy(client)
    await service.run_backup(backup_dir, verify=False)
    status = await service.status()
    assert status.healthy is False
    assert "never verified" in status.detail


async def test_a_failed_backup_is_recorded_with_its_error(client, tmp_path):
    """A backup that failed silently is worse than no backup."""
    service = _service()
    impossible = tmp_path / "nope" / "\x00bad"  # an unopenable path
    with pytest.raises((OSError, ValueError)):
        await service.run_backup(impossible)
    history = await service.history()
    assert history[0].status == "failed" and history[0].error


async def test_the_operator_api_reports_status_and_history(client, backup_dir):
    from tests.conftest import register_and_login

    _, ops = await register_and_login(client, "backup-ops@example.com", admin=True)
    await _full_dairy(client)
    await _service().run_backup(backup_dir)

    status = (await client.get("/v1/_ops/backups/status", headers=ops)).json()
    assert status["healthy"] is True and status["last_successful_backup"]

    history = (await client.get("/v1/_ops/backups", headers=ops)).json()
    assert history and history[0]["kind"] == "backup"

    classes = (await client.get("/v1/_ops/backups/classification", headers=ops)).json()
    assert any(c["table"] == "payment" and c["classification"] == "critical" for c in classes)

    integrity = (await client.post("/v1/_ops/backups/verify-integrity", headers=ops)).json()
    assert integrity["status"] == "succeeded"


async def test_the_backup_api_is_platform_staff_only(client):
    from tests.test_org_structure import _tenant_admin

    _, tenant = await _tenant_admin(client)
    for path in ("/v1/_ops/backups", "/v1/_ops/backups/status"):
        assert (await client.get(path, headers=tenant)).status_code == 403, path
    assert (await client.get("/v1/_ops/backups/status")).status_code in (401, 403)


async def test_backup_health_surfaces_in_the_platform_health_model(client, backup_dir):
    """An operator should not need a second dashboard to learn that backups
    have been failing for a week."""
    from tests.conftest import register_and_login

    _, ops = await register_and_login(client, "backup-health@example.com", admin=True)
    body = (await client.get("/v1/_ops/health", headers=ops)).json()
    backups = next((c for c in body["components"] if c["name"] == "backups"), None)
    assert backups is not None, "backups must be a health component"
    assert backups["status"] in ("healthy", "warning", "degraded", "critical")
