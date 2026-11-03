"""Real PostgreSQL tests for database-enforced snapshot immutability."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.research.db import create_research_database
from app.research.snapshot import ResearchSnapshotService
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from tests.research.postgres_fixtures import (
    IsolatedPostgres,
    create_postgres_context,
    upgrade_head,
)
from tests.research.test_snapshot_freeze import _run, _seed


@pytest.fixture
def postgres_context() -> IsolatedPostgres:
    """Allocate an isolated, additive schema in the task-owned test database."""
    return create_postgres_context()


def _sqlstate(error: DBAPIError) -> str | None:
    """Return the PostgreSQL SQLSTATE without exposing database details."""
    original = error.orig
    return getattr(original, "sqlstate", None) or getattr(
        getattr(original, "__cause__", None), "sqlstate", None
    )


@pytest.mark.asyncio
async def test_snapshot_membership_requires_materialized_and_freeze_is_immutable(
    postgres_context,
):
    """Only materialized runs accept INSERT; frozen membership rejects all writes."""
    await asyncio.to_thread(upgrade_head, postgres_context)
    database = create_research_database(
        postgres_context.url,
        connect_args={"server_settings": {"search_path": postgres_context.schema}},
    )
    engine = create_async_engine(
        postgres_context.url,
        poolclass=NullPool,
        connect_args={"server_settings": {"search_path": postgres_context.schema}},
    )
    now = datetime(2026, 10, 31, 10, 0, tzinfo=UTC)
    try:
        seed_id, _late_id, _other_id = await _seed(database, now)
        run_id, lease = await _run(database, seed_id=seed_id, now=now, as_of=now)
        async with engine.connect() as connection:
            evidence_row = (
                (
                    await connection.execute(
                        text(
                            "SELECT version, content_hash FROM research_evidence "
                            "WHERE evidence_id = :evidence_id"
                        ),
                        {"evidence_id": seed_id},
                    )
                )
                .mappings()
                .one()
            )
        member_id = uuid4()
        member_params = {
            "member_id": member_id,
            "run_id": run_id,
            "evidence_id": seed_id,
            "version": evidence_row["version"],
            "content_hash": evidence_row["content_hash"],
            "now": now,
        }
        insert_sql = text(
            "INSERT INTO research_snapshot_member "
            "(snapshot_member_id, run_id, evidence_id, evidence_version, "
            "content_hash, selected_at) VALUES "
            "(:member_id, :run_id, :evidence_id, :version, :content_hash, :now)"
        )

        async def rejected(statement, params):
            with pytest.raises(DBAPIError) as caught:
                async with engine.begin() as connection:
                    await connection.execute(text(statement), params)
            assert _sqlstate(caught.value) == "55000"

        # A freshly-created run is `none`; direct INSERT must fail closed.
        await rejected(insert_sql.text, member_params)

        # Simulate the legitimate state transition by its own SQL statement;
        # the service lifecycle below remains the authority for freezing.
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE research_run SET snapshot_state='materialized' "
                    "WHERE run_id=:run_id"
                ),
                {"run_id": run_id},
            )
            await connection.execute(insert_sql, member_params)

        # Freeze through the public service lifecycle, not an INSERT exception bypass.
        frozen = await ResearchSnapshotService(database).freeze_snapshot(
            run_id=run_id, lease=lease, now=now
        )
        assert len(frozen.members) == 1

        common = {"run_id": run_id, "evidence_id": seed_id}
        await rejected(
            "INSERT INTO research_snapshot_member "
            "(snapshot_member_id, run_id, evidence_id, evidence_version, "
            "content_hash, selected_at) SELECT :member_id, m.run_id, m.evidence_id, "
            "m.evidence_version, m.content_hash, :now FROM research_snapshot_member m "
            "WHERE m.run_id=:run_id AND m.evidence_id=:evidence_id",
            {**common, "member_id": uuid4(), "now": now},
        )
        await rejected(
            "UPDATE research_snapshot_member SET selected_at=:now "
            "WHERE run_id=:run_id AND evidence_id=:evidence_id",
            {**common, "now": now},
        )
        await rejected(
            "UPDATE research_snapshot_member SET content_hash=:new_hash "
            "WHERE run_id=:run_id AND evidence_id=:evidence_id",
            {**common, "new_hash": "d" * 64},
        )
        await rejected(
            "DELETE FROM research_snapshot_member "
            "WHERE run_id=:run_id AND evidence_id=:evidence_id",
            common,
        )
        await rejected(
            "UPDATE research_run SET snapshot_state='materialized' WHERE run_id=:run_id",
            {"run_id": run_id},
        )
        await rejected(
            "UPDATE research_run SET snapshot_frozen_at=NULL WHERE run_id=:run_id",
            {"run_id": run_id},
        )

        async with engine.connect() as connection:
            state = (
                await connection.execute(
                    text(
                        "SELECT r.snapshot_state, count(m.snapshot_member_id) "
                        "FROM research_run r LEFT JOIN research_snapshot_member m "
                        "ON m.run_id=r.run_id WHERE r.run_id=:run_id "
                        "GROUP BY r.snapshot_state"
                    ),
                    {"run_id": run_id},
                )
            ).one()
            assert state.snapshot_state == "frozen"
            assert state.count == 1
    finally:
        await database.dispose()
        await engine.dispose()
