"""Run research-only Alembic migrations through an async PostgreSQL engine.

Author: Damon Li
"""

from __future__ import annotations

import asyncio
import re
from logging.config import fileConfig

from alembic import context
from app.research.models import ResearchBase
from sqlalchemy import Connection, pool, text
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = ResearchBase.metadata
_VERSION_TABLE = "research_alembic_version"
_SCHEMA_PATTERN = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def _research_schema() -> str | None:
    """Return an optional validated, caller-injected isolated test schema."""
    schema = config.attributes.get("research_schema")
    if schema is None:
        return None
    if not isinstance(schema, str) or not _SCHEMA_PATTERN.fullmatch(schema):
        raise RuntimeError("research Alembic schema is invalid")
    return schema


def _configure_context(connection: Connection) -> None:
    """Configure one migration run exclusively against research metadata."""
    schema = _research_schema()
    if schema is not None:
        connection.execute(text(f'SET search_path TO "{schema}"'))
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table=_VERSION_TABLE,
        version_table_schema=schema,
        compare_type=False,
        compare_server_default=False,
        include_schemas=False,
    )


def run_migrations_offline() -> None:
    """Configure SQL rendering only when a caller supplies an async PostgreSQL URL."""
    url = config.get_main_option("sqlalchemy.url")
    if not url or not url.startswith("postgresql+asyncpg://"):
        raise RuntimeError("research Alembic requires an explicit async PostgreSQL URL")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table=_VERSION_TABLE,
        version_table_schema=_research_schema(),
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run an online additive research migration transaction."""
    _configure_context(connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Create an async engine only for this explicit Alembic invocation."""
    section = config.get_section(config.config_ini_section, {})
    url = section.get("sqlalchemy.url", "")
    if not url.startswith("postgresql+asyncpg://"):
        raise RuntimeError("research Alembic requires an explicit async PostgreSQL URL")
    connectable = async_engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    try:
        async with connectable.begin() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
