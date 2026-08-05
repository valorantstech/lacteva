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


def test_migration_metadata_sees_every_table():
    """The guard. `env.py` must register every mapped table, or autogenerate
    will propose dropping the ones it cannot see."""
    import importlib

    from platform_core.core.db import Base

    # Import env.py's model modules exactly as Alembic does.
    for line in _env_source().splitlines():
        if line.startswith("import platform_core"):
            importlib.import_module(line.split()[1])

    registered = set(Base.metadata.tables)
    # Every module that defines tables must be reachable from env.py.
    import platform_core.main  # noqa: F401 - imports the whole application

    complete = set(Base.metadata.tables)
    missing = complete - registered
    assert not missing, (
        f"migrations/env.py does not register: {sorted(missing)} — "
        "autogenerate would propose DROPPING these tables"
    )


def test_the_linter_cannot_remove_the_model_imports():
    """The imports look unused to every linter that will ever run over this
    file, and a `noqa` marker is itself reported as unused. The durable guard
    is a per-file ignore in pyproject.toml — without it, the next autofix
    removes them again."""
    config = (pathlib.Path(__file__).resolve().parents[1] / "pyproject.toml").read_text()
    assert '"migrations/env.py"' in config, "env.py needs a per-file lint exemption"
    exemption = config.split('"migrations/env.py"')[1].split("\n")[0]
    assert "F401" in exemption, "F401 must be exempt or the imports get stripped"


def test_the_hazard_is_explained_where_someone_would_break_it():
    """A marker without a reason gets removed by someone who assumes it is
    stale. The comment is part of the guard."""
    source = _env_source()
    assert "DROPS" in source or "DROP EVERY TABLE" in source.upper()
    assert "side effect" in source


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
