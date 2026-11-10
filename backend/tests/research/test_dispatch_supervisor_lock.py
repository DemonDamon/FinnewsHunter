"""PostgreSQL advisory-lock serialization for multi-instance supervisors."""

from __future__ import annotations

import asyncio

import pytest
from app.research.dispatch import (
    InMemoryDispatchTransport,
    ResearchDispatcher,
    ResearchDispatchSupervisor,
)
from app.research.outbox import ResearchOutboxPort

from backend.tests.research.postgres_fixtures import (
    IsolatedPostgres,
    create_postgres_context,
    upgrade_head,
)
from backend.tests.research.test_run_transactions import _setup


@pytest.fixture
def postgres_context() -> IsolatedPostgres:
    return create_postgres_context()


@pytest.mark.asyncio
async def test_dual_supervisor_advisory_lock_serializes_critical_section(
    postgres_context,
):
    await asyncio.to_thread(upgrade_head, postgres_context)
    database, ledger, _now, _, _, _, _, _, _ = await _setup(postgres_context)
    try:
        outbox = ResearchOutboxPort(database=database)
        supervisor = ResearchDispatchSupervisor(
            database=database,
            ledger=ledger,
            outbox=outbox,
            dispatcher=ResearchDispatcher(
                outbox=outbox,
                transport=InMemoryDispatchTransport(),
                dispatcher_id="d1",
            ),
            enabled=False,
        )
        holder_ready = asyncio.Event()
        contender_finished = asyncio.Event()
        contender_got_lock: dict[str, bool] = {"while_held": False, "after_release": False}

        async def holder() -> None:
            async with supervisor._advisory_lock() as session:
                assert session is not None
                holder_ready.set()
                await asyncio.sleep(0.4)

        async def contender() -> None:
            await holder_ready.wait()
            async with supervisor._advisory_lock() as session:
                contender_got_lock["while_held"] = session is not None
            await asyncio.sleep(0.6)
            async with supervisor._advisory_lock() as session:
                contender_got_lock["after_release"] = session is not None
            contender_finished.set()

        await asyncio.gather(holder(), contender())
        await contender_finished.wait()
        assert contender_got_lock["while_held"] is False
        assert contender_got_lock["after_release"] is True
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_startup_recovery_skips_when_advisory_lock_held(postgres_context):
    await asyncio.to_thread(upgrade_head, postgres_context)
    database, ledger, _now, _, _, _, _, _, _ = await _setup(postgres_context)
    try:
        outbox = ResearchOutboxPort(database=database)
        supervisor = ResearchDispatchSupervisor(
            database=database,
            ledger=ledger,
            outbox=outbox,
            dispatcher=ResearchDispatcher(
                outbox=outbox,
                transport=InMemoryDispatchTransport(),
                dispatcher_id="d1",
            ),
            enabled=False,
        )
        holder_ready = asyncio.Event()
        recovery_while_held: dict[str, int | None] = {"reaped": None}

        async def holder() -> None:
            async with supervisor._advisory_lock() as session:
                assert session is not None
                holder_ready.set()
                await asyncio.sleep(0.5)

        async def recovery_attempt() -> None:
            await holder_ready.wait()
            result = await supervisor.startup_recovery()
            recovery_while_held["reaped"] = result.reaped

        await asyncio.gather(holder(), recovery_attempt())
        assert recovery_while_held["reaped"] == 0
    finally:
        await database.dispose()
