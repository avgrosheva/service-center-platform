"""
Alembic environment configuration (Milestone 2), async-aware.

The DB URL is pulled from app.config.get_settings() rather than from
alembic.ini, so migrations always run against exactly the same database
the application itself is configured to use — no separate URL to keep in
sync.

IMPORTANT for later milestones: as domain models are added (Milestone 3
onward), import them here so Base.metadata is fully populated before
autogenerate compares it against the live database. Forgetting this is the
single most common way to get an autogenerate migration that silently
creates nothing.
    from app.models import organization, user  # noqa: F401  (example)
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import get_settings
from app.database import Base

# --- Milestone 3+: import every models module here so autogenerate sees
#     all tables, e.g.:
from app.models import organization, user

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)


def run_migrations_offline() -> None:
    """Generate SQL scripts without a live DB connection (`alembic upgrade head --sql`)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations against a live DB using the async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())