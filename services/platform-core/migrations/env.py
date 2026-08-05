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

from platform_core.core.db import Base
from platform_core.core.model_registry import import_all_models

# `Base.metadata` is only as complete as the imports a process has done, and
# autogenerate proposes DROPPING every table it cannot see — which happened
# once (OFF-001, caught in BAK-001) when a linter removed the model imports
# that used to live here. This is a CALL, so no autofix can remove it, and one
# registry now serves migrations and backup alike (CI-001).
import_all_models()

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
