"""Create the isolated research PostgreSQL persistence context.

This module deliberately has no configuration, environment, legacy-model, or
network side effect at import time.  The composition owner supplies a DSN only
when research persistence is explicitly enabled.

Author: Damon Li
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.research.ports import (
    LedgerReadiness,
    ResearchAsyncSessionFactory,
    ResearchDatabasePort,
)

RESEARCH_ALEMBIC_HEAD = "20261030_research_v11"
_RESEARCH_VERSION_TABLE = "research_alembic_version"


class ResearchDatabase(ResearchDatabasePort):
    """Own one explicitly constructed research-only async SQLAlchemy context."""

    def __init__(
        self,
        *,
        engine: AsyncEngine | None,
        session_factory: ResearchAsyncSessionFactory | None,
        not_ready_reason: str | None,
    ) -> None:
        """Retain a factory without opening a connection or session."""
        self._engine = engine
        self._session_factory = session_factory
        self._not_ready_reason = not_ready_reason

    @property
    def session_factory(self) -> ResearchAsyncSessionFactory:
        """Return the injected factory without opening a database session."""
        if self._session_factory is None:
            raise RuntimeError("research database is not configured")
        return self._session_factory

    async def check_ready(self, *, now: datetime) -> LedgerReadiness:
        """Check only the isolated migration marker without exposing diagnostics."""
        if self._engine is None:
            return LedgerReadiness(
                ready=False,
                reason=self._not_ready_reason or "ledger_not_configured",
                checked_at=now,
            )
        try:
            async with self._engine.connect() as connection:
                version = (
                    await connection.execute(
                        text(f"SELECT version_num FROM {_RESEARCH_VERSION_TABLE}")
                    )
                ).scalar_one_or_none()
        except SQLAlchemyError:
            return LedgerReadiness(
                ready=False,
                reason="ledger_migration_unavailable",
                checked_at=now,
            )
        return LedgerReadiness(
            ready=version == RESEARCH_ALEMBIC_HEAD,
            reason="ledger_ready"
            if version == RESEARCH_ALEMBIC_HEAD
            else "ledger_migration_unavailable",
            checked_at=now,
        )

    async def dispose(self) -> None:
        """Release owned engine resources during an explicit parent cleanup."""
        if self._engine is not None:
            await self._engine.dispose()


def _postgresql_async_url(dsn: str | None) -> URL | None:
    """Accept only an explicit asyncpg PostgreSQL URL without logging its value."""
    if not dsn or not dsn.strip():
        return None
    try:
        url = make_url(dsn)
    except (TypeError, ValueError):
        return None
    if url.drivername != "postgresql+asyncpg" or not url.database:
        return None
    return url


def create_research_database(
    dsn: str | None,
    *,
    echo: bool = False,
    connect_args: Mapping[str, Any] | None = None,
) -> ResearchDatabase:
    """Build the research adapter only from a caller-supplied async PostgreSQL DSN.

    Invalid or absent input is represented as a safe not-ready adapter rather
    than a fallback to any legacy/default database.  ``connect_args`` exists for
    explicit driver configuration (including isolated test schema selection),
    never for configuration discovery.
    """
    url = _postgresql_async_url(dsn)
    if url is None:
        return ResearchDatabase(
            engine=None,
            session_factory=None,
            not_ready_reason="ledger_dsn_missing_or_invalid",
        )
    engine = create_async_engine(
        url,
        echo=echo,
        pool_pre_ping=True,
        connect_args=dict(connect_args or {}),
    )
    factory: ResearchAsyncSessionFactory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return ResearchDatabase(
        engine=engine,
        session_factory=factory,
        not_ready_reason=None,
    )
