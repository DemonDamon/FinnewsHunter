"""Provide isolated PostgreSQL schemas for research migration verification.

The stage runner injects only a task-owned disposable database URL.  Every test
gets a fresh schema and intentionally leaves it intact: tests never reset or
delete shared database state.

Author: Damon Li
"""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
ALEMBIC_DIR = BACKEND_ROOT / "alembic"
_SCHEMA_PATTERN = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


@dataclass(frozen=True, slots=True)
class IsolatedPostgres:
    """Identify a stage-owned PostgreSQL URL and one unique, additive test schema."""

    url: str
    schema: str


def _database_gate() -> str:
    """Require the runner-supplied task database without revealing its URL."""
    url = os.environ.get("RESEARCH_TEST_DATABASE_URL")
    namespace = os.environ.get("RESEARCH_TEST_NAMESPACE")
    if not url or not namespace:
        pytest.fail("database_gate=not_run: controlled PostgreSQL variables are absent")
    parsed = make_url(url)
    if (
        parsed.drivername != "postgresql+asyncpg"
        or parsed.host != "127.0.0.1"
        or parsed.port != 55432
        or parsed.database != "finnews_e2e_test"
    ):
        pytest.fail("database_gate=not_run: controlled PostgreSQL marker is invalid")
    return url


async def _create_isolated_schema(url: str, schema: str) -> None:
    """Create one new schema and assert the fixed task database marker."""
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            database_name = (
                await connection.execute(text("SELECT current_database()"))
            ).scalar_one()
            if database_name != "finnews_e2e_test":
                pytest.fail(
                    "database_gate=not_run: database isolation marker is invalid"
                )
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    finally:
        await engine.dispose()


def create_postgres_context() -> IsolatedPostgres:
    """Allocate a fresh non-destructive PostgreSQL schema for one migration test."""
    url = _database_gate()
    schema = f"research_s02a_{uuid4().hex}"
    if not _SCHEMA_PATTERN.fullmatch(schema):
        raise AssertionError("generated research schema is invalid")
    asyncio.run(_create_isolated_schema(url, schema))
    return IsolatedPostgres(url=url, schema=schema)


@pytest.fixture
def postgres_context() -> IsolatedPostgres:
    """Expose the controlled schema allocator for consumers using this fixture module."""
    return create_postgres_context()


def alembic_config(
    context: IsolatedPostgres,
    *,
    script_location: Path | None = None,
) -> Config:
    """Build an in-memory migration config with an explicit URL and test schema."""
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(script_location or ALEMBIC_DIR))
    config.set_main_option("sqlalchemy.url", context.url)
    config.attributes["research_schema"] = context.schema
    return config


def upgrade_head(context: IsolatedPostgres) -> None:
    """Apply the reviewed research migration head to one fresh test schema."""
    command.upgrade(alembic_config(context), "head")


async def set_search_path(connection: object, context: IsolatedPostgres) -> None:
    """Set a validated schema name on a test connection without interpolating input."""
    if not _SCHEMA_PATTERN.fullmatch(context.schema):
        raise AssertionError("test schema is invalid")
    execute = connection.execute
    await execute(text(f'SET search_path TO "{context.schema}"'))
