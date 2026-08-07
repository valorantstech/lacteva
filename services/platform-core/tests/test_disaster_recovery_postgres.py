"""Disaster recovery, executed against a real engine (DR-001).

The backup and restore guarantees are the ones it is least acceptable to
assert without executing, because the moment they are needed is the moment
nobody has time to discover they were wrong. Every test here failed against
the code as it stood before DR-001.

These require PostgreSQL. Not for convenience — the defects they cover are
invisible on SQLite:

- the `time` columns that broke every backup live in a real schema
- a schema revision comes from `alembic_version`, which the SQLite suite
  never creates
- restoring across two databases needs two databases
"""

import json
import pathlib
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests import postgres_support

POSTGRES_URL = postgres_support.POSTGRES_URL
ADMIN_URL = postgres_support.ADMIN_URL
pytestmark = postgres_support.requires_postgres


@pytest_asyncio.fixture
async def engine_and_dir(tmp_path, monkeypatch):
    """A backup engine over the live database, plus a scratch directory."""
    from platform_core.core.backup.engine import BackupEngine
    from platform_core.core.config import get_settings
    from platform_core.core.rls import platform_factory

    monkeypatch.setattr(get_settings(), "database_url", POSTGRES_URL)
    engine = create_async_engine(POSTGRES_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    from platform_core.core.rls import PlatformSessionFactory

    backup = BackupEngine(PlatformSessionFactory(factory, "DR test"))
    yield backup, pathlib.Path(tmp_path), factory
    await engine.dispose()
    del platform_factory  # imported for symmetry with production wiring


async def test_a_time_column_survives_a_backup(engine_and_dir):
    """DR-001: `time` had no encoder, and its absence took the whole backup
    down rather than degrading it.

    `center_operating_window.opens/closes` are TIME columns, so any deployment
    that had configured opening hours — which is every real one — could not be
    backed up at all. The suite never seeded a center with operating hours, so
    nothing ever hit the branch.
    """
    from datetime import time

    from platform_core.core.backup.engine import _decode, _encode

    for value in (time(5, 0), time(23, 59, 59), time(0, 0)):
        assert _decode(_encode(value)) == value


async def test_every_column_type_in_the_schema_can_be_serialized():
    """The general form of the defect above.

    A model added with a type the engine cannot encode does not degrade the
    backup — it aborts it. Asserting over the whole schema means the next such
    type fails here, in a test, rather than during a recovery.
    """
    import datetime
    from decimal import Decimal

    from sqlalchemy import (
        JSON,
        Boolean,
        Date,
        DateTime,
        Float,
        Integer,
        Numeric,
        String,
        Text,
        Time,
        Uuid,
    )

    from platform_core.core.backup.engine import _decode, _encode
    from platform_core.core.db import Base
    from platform_core.core.model_registry import import_all_models

    # One representative value per SQLAlchemy type the schema actually uses.
    samples = {
        Boolean: True,
        Date: datetime.date(2026, 8, 7),
        DateTime: datetime.datetime(2026, 8, 7, 12, 0, tzinfo=datetime.UTC),
        Float: 1.5,
        Integer: 7,
        JSON: {"a": [1, 2]},
        Numeric: Decimal("5647.50"),
        String: "text",
        Text: "text",
        Time: datetime.time(5, 30),
        Uuid: uuid.uuid4(),
    }

    import_all_models()
    used = {type(c.type) for t in Base.metadata.sorted_tables for c in t.columns}
    unknown = used - set(samples)
    assert not unknown, (
        f"the schema uses column types this test has no sample for: {unknown}. "
        "Add one — and check the backup engine can encode it, because a type "
        "it cannot serialize aborts every backup."
    )
    for column_type in used:
        value = samples[column_type]
        assert _decode(_encode(value)) == value, f"{column_type.__name__} does not round-trip"


async def test_no_table_is_excluded_from_backup_without_a_rebuilder():
    """`rebuildable` is a claim about CODE, not about data.

    DR-001 found `transaction_metrics` classified rebuildable — so excluded
    from every backup — while nothing rebuilt it. It is written once, by
    `MilkCollectionService.complete()`, and is not a registered projection, so
    a restore left it permanently empty. The recovery comparison caught it as
    "reports: 2 rows in source, 0 restored".
    """
    from platform_core.core.backup.classification import (
        rebuildable_tables_without_a_rebuilder,
    )

    orphans = rebuildable_tables_without_a_rebuilder()
    assert orphans == [], (
        f"{orphans} are excluded from backup on the promise that they can be "
        "rebuilt, and no registered projection owns them. A restore loses them "
        "permanently and silently. Either classify them for backup, or write "
        "the rebuilder that justifies the exclusion."
    )


async def test_the_manifest_records_the_schema_it_came_from(engine_and_dir):
    """Without it, a restore cannot tell whether the target's schema matches."""
    backup, tmp, _ = engine_and_dir
    manifest = await backup.backup(tmp / "b")
    assert manifest.schema_revision, (
        "the manifest carries no Alembic revision, so a restore into a "
        "different schema cannot be detected"
    )
    on_disk = json.loads((tmp / "b" / "manifest.json").read_text())
    assert on_disk["schema_revision"] == manifest.schema_revision


async def test_a_corrupt_backup_is_refused_before_the_database_is_touched(engine_and_dir):
    """The defect this replaces was proven by executing it.

    `verify_files` existed and nothing called it before a restore, despite its
    own docstring saying that is exactly when it matters. Changing one number
    in `settlement.jsonl` produced a restore that reported 350 rows loaded and
    left a settlement worth 1.00 instead of 5647.50 — noticed only by the
    integrity check that runs AFTERWARDS, by which point the recovery target
    is already overwritten and the operator starts again, mid-outage.
    """
    from platform_core.core.backup.engine import BackupError

    backup, tmp, _ = engine_and_dir
    destination = tmp / "corrupt"
    await backup.backup(destination)

    # Corrupt a table file the way a bad disk or a truncated upload would.
    target = next((destination / "tables").glob("*.jsonl"))
    target.write_text(target.read_text() + '{"tampered":true}\n')

    with pytest.raises(BackupError) as caught:
        await backup.restore(destination, allow_non_empty=True)
    message = str(caught.value)
    assert "checksum" in message or "rows" in message
    assert "refusing" in message.lower()


async def test_a_damaged_backup_can_still_be_forced_when_that_is_the_better_option(
    engine_and_dir,
):
    """The refusal must be overridable, and say so.

    During a real recovery a partially damaged backup can be better than
    nothing. The escape hatch exists; it is explicit, and it is not the
    default.
    """
    backup, tmp, _ = engine_and_dir
    destination = tmp / "forced"
    await backup.backup(destination)
    target = next((destination / "tables").glob("*.jsonl"))
    target.write_text(target.read_text() + '{"tampered":true}\n')

    # Does not raise. (It will fail later on the tampered row, which is the
    # point: the operator chose to try.)
    with pytest.raises(Exception) as caught:
        await backup.restore(destination, allow_non_empty=True, verify_first=False)
    assert "refusing to restore a backup that does not match" not in str(caught.value)


async def test_restoring_into_a_different_schema_revision_is_refused(engine_and_dir):
    """Proven by executing it: a backup restored into a database one migration
    older loaded all 350 rows and reported `integrity_healthy: true`. The
    recovered system was missing the ARCH-001 `amount > 0` constraint, and
    nothing said so.
    """
    from platform_core.core.backup.engine import BackupError

    backup, tmp, _ = engine_and_dir
    destination = tmp / "revision"
    await backup.backup(destination)

    # Rewrite the manifest to claim a different revision — the same situation
    # as a target that has moved on, without moving the real database.
    manifest_path = destination / "manifest.json"
    data = json.loads(manifest_path.read_text())
    data["schema_revision"] = "0000deadbeef"
    manifest_path.write_text(json.dumps(data))

    with pytest.raises(BackupError) as caught:
        await backup.restore(destination, allow_non_empty=True)
    assert "0000deadbeef" in str(caught.value)
    assert "alembic" in str(caught.value).lower()

    # And the override exists, because sometimes the operator knows better.
    await backup.restore(destination, allow_non_empty=True, allow_schema_mismatch=True)


async def test_an_unknown_revision_warns_rather_than_blocking_a_recovery(engine_and_dir):
    """Backups taken before DR-001 have no revision recorded.

    Refusing those would make every existing backup unrestorable — a worse
    failure than the one being guarded against. Unknown warns; MISMATCHED
    refuses.
    """
    backup, tmp, _ = engine_and_dir
    destination = tmp / "unknown"
    await backup.backup(destination)
    manifest_path = destination / "manifest.json"
    data = json.loads(manifest_path.read_text())
    data["schema_revision"] = ""
    manifest_path.write_text(json.dumps(data))

    await backup.restore(destination, allow_non_empty=True)  # must not raise


async def test_the_restored_database_still_enforces_tenant_isolation(engine_and_dir):
    """A recovered system that has lost its isolation is not recovered.

    Policies come from migrations rather than from the backup, so this asserts
    the restore did not disturb them — and it runs as the unprivileged
    application role, because as a superuser it would pass regardless
    (VER-001).
    """
    backup, tmp, factory = engine_and_dir
    await backup.backup(tmp / "isolation")

    async with factory() as session:
        role, is_super, bypasses = (
            await session.execute(
                text(
                    "SELECT current_user, rolsuper, rolbypassrls "
                    "FROM pg_roles WHERE rolname = current_user"
                )
            )
        ).one()
        assert not is_super and not bypasses, (
            f"connected as {role!r}, which bypasses RLS — this assertion would "
            "pass no matter what the restore did"
        )

        unforced = await session.scalar(
            text("SELECT count(*) FROM pg_class WHERE relrowsecurity AND NOT relforcerowsecurity")
        )
        assert unforced == 0, f"{unforced} table(s) lost FORCE ROW LEVEL SECURITY"

        policies = await session.scalar(
            text("SELECT count(*) FROM pg_policies WHERE schemaname='public'")
        )
        assert policies > 30, f"only {policies} policies after restore"

        # An unbound session must see nothing, on restored rows as on any others.
        await session.execute(text("SELECT set_config('lacteva.tenant_id', '', true)"))
        await session.execute(text("SELECT set_config('lacteva.bypass_rls', 'off', true)"))
        leaked = await session.scalar(text("SELECT count(*) FROM settlement"))
        assert leaked == 0, f"an unbound session sees {leaked} restored settlements"


async def test_indexes_and_constraints_survive_a_restore(engine_and_dir):
    """The restore loads rows; the schema comes from migrations.

    Worth asserting anyway: a restore that dropped and recreated tables to go
    faster would take the indexes with it, and the first symptom would be a
    slow query months later rather than an error.
    """
    backup, tmp, factory = engine_and_dir
    destination = tmp / "schema"
    await backup.backup(destination)

    async with factory() as session:
        before = await session.scalar(
            text("SELECT count(*) FROM pg_indexes WHERE schemaname='public'")
        )
    await backup.restore(destination, allow_non_empty=True)
    async with factory() as session:
        after = await session.scalar(
            text("SELECT count(*) FROM pg_indexes WHERE schemaname='public'")
        )
    assert after == before, f"the restore changed the index count: {before} -> {after}"
    assert after > 100, f"only {after} indexes — the schema is not intact"
