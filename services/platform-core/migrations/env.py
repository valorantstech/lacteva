"""Alembic environment for platform-core (async engine).

Usage:
    uv run alembic revision --autogenerate -m "initial platform schema"
    uv run alembic upgrade head

TODO(M1): commit the baseline migration once the model set stabilizes; until
then, local/dev environments may also use metadata create_all via the app in
LACTEVA_ENV=dev|test only.
"""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import the metadata with every module's tables registered.
# EVERY model module must be imported here for its side effect: importing
# registers the tables in `Base.metadata`, which is what autogenerate compares
# the database against. They are deliberately "unused" — hence the noqa on
# each — and stripping them makes autogenerate emit a migration that DROPS
# EVERY TABLE — which happened once (OFF-001, caught and restored in BAK-001).
# `pyproject.toml` exempts this file from F401 so no autofix can remove them,
# and `tests/test_migrations.py` fails if any table stops being registered.
import platform_core.core.backup.models
import platform_core.modules.audit.models
import platform_core.modules.auth.models
import platform_core.modules.authz.models
import platform_core.modules.collection_center.models
import platform_core.modules.configuration.models
import platform_core.modules.event_relay.models
import platform_core.modules.identity.models
import platform_core.modules.milk_collection.models
import platform_core.modules.notification.models
import platform_core.modules.operational_readiness.models
import platform_core.modules.organization.models
import platform_core.modules.payment.models
import platform_core.modules.pricing.models
import platform_core.modules.receipt.models
import platform_core.modules.reporting.models
import platform_core.modules.settlement.models
import platform_core.modules.supplier.models
import platform_core.modules.sync.models

# Import the metadata with every module's tables registered.
from platform_core.core.db import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

url = os.environ.get("LACTEVA_DATABASE_URL")
if url:
    config.set_main_option("sqlalchemy.url", url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}), prefix="sqlalchemy."
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
