"""Migration safety (BAK-001).

These tests exist because of a real incident found during BAK-001: a routine
`ruff --fix` stripped the model imports from `migrations/env.py`, because
those imports are deliberately "unused" — they exist only for the side effect
of registering tables in `Base.metadata`.

Nothing failed. Migrations still applied, the suite stayed green, and the
platform ran normally for three commits. The damage was latent: the next
`alembic revision --autogenerate` compared a nearly-empty metadata against a
full database and produced a migration that would have **dropped every
table** — including every payment, receipt, and settlement.

A test suite that cannot catch "the next migration you generate will destroy
production" is missing the most expensive bug class there is.
"""

import pathlib

import pytest


def _env_source() -> str:
    return (pathlib.Path(__file__).resolve().parents[1] / "migrations" / "env.py").read_text()


def test_the_registry_sees_every_table():
    """The guard. `import_all_models()` must register every mapped table, or
    autogenerate proposes dropping the ones it cannot see and a backup
    silently captures a fraction of the schema."""
    from platform_core.core.db import Base
    from platform_core.core.model_registry import import_all_models

    registered_count = import_all_models()
    registered = set(Base.metadata.tables)

    import platform_core.main  # noqa: F401 - imports the whole application

    complete = set(Base.metadata.tables)
    missing = complete - registered
    assert not missing, (
        f"the model registry does not register: {sorted(missing)} — "
        "autogenerate would propose DROPPING these, and a backup would skip them"
    )
    assert registered_count == len(complete)
    assert registered_count > 45, f"only {registered_count} tables registered"


def test_env_registers_models_through_a_call_no_linter_can_remove():
    """A bare import is removable by an autofix; a function CALL is not. That
    is the whole reason the registry exists rather than an import block."""
    source = _env_source()
    assert "import_all_models()" in source, "env.py must CALL the registry"
    stray = [
        line for line in source.splitlines() if line.startswith("import platform_core.modules")
    ]
    assert not stray, f"model imports belong in the registry, not env.py: {stray}"


def test_the_backup_engine_sees_the_whole_schema():
    """CI-001: the backup CLI once captured ONE table because its process had
    not imported the models. Classification must register them itself."""
    from platform_core.core.backup.classification import classify_all, tables_for_backup

    assert len(classify_all()) > 45
    assert len(tables_for_backup()) > 35
    for critical in ("payment", "receipt", "settlement", "event_outbox"):
        assert critical in tables_for_backup(), critical


def test_the_hazard_is_explained_where_someone_would_break_it():
    """A guard without a stated reason gets removed by someone who assumes it
    is stale. The explanation is part of the guard."""
    registry = (
        pathlib.Path(__file__).resolve().parents[1] / "src/platform_core/core/model_registry.py"
    ).read_text()
    assert "DROPPING" in registry.upper()
    assert "import-order" in registry or "import order" in registry
    assert "one table and three rows" in registry, "record what actually happened"


@pytest.mark.parametrize("required", ["payment", "receipt", "settlement", "event_outbox"])
def test_business_critical_tables_are_registered(required):
    """Named explicitly, so the failure message says which money-bearing
    table would have been dropped."""
    import platform_core.main  # noqa: F401
    from platform_core.core.db import Base

    assert required in Base.metadata.tables


def test_migration_chain_is_linear():
    """A branched migration history means two deploys can diverge, and a
    restore cannot know which head it should reach."""
    versions = pathlib.Path(__file__).resolve().parents[1] / "migrations" / "versions"
    down_revisions: list[str | None] = []
    revisions: list[str] = []
    for path in versions.glob("*.py"):
        source = path.read_text()
        for line in source.splitlines():
            if line.startswith("revision ="):
                revisions.append(line.split("=", 1)[1].strip().strip("\"'"))
            elif line.startswith("down_revision ="):
                value = line.split("=", 1)[1].strip().strip("\"'")
                down_revisions.append(None if value == "None" else value)
    assert len(revisions) == len(set(revisions)), "duplicate revision ids"
    parents = [d for d in down_revisions if d is not None]
    assert len(parents) == len(set(parents)), (
        "two migrations share a parent — the history has branched"
    )
    assert down_revisions.count(None) == 1, "there must be exactly one base migration"
