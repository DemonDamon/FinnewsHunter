"""Real subprocess loss after worker claim must be reaped safely."""

from __future__ import annotations

import asyncio
import multiprocessing as mp
import os
import signal
import time
from datetime import UTC, datetime, timedelta

import pytest
from app.research.auth import ResearchAuthorizer
from app.research.db import create_research_database
from app.research.dispatch import ResearchDispatchSupervisor
from app.research.ledger import ResearchLedger
from app.research.models import ResearchRun
from app.research.ports import DispatchTask, WorkerIdentity
from app.research.snapshot import ResearchSnapshotService
from sqlalchemy import select

from backend.tests.research.postgres_fixtures import (
    IsolatedPostgres,
    create_postgres_context,
    upgrade_head,
)
from backend.tests.research.test_run_transactions import (
    _ReadyExecutor,
    _setup,
    _submit_outbox_for_worker_claim,
)


def _child_claim_and_block(
    url: str,
    schema: str,
    run_id: str,
    dispatch_id: str,
    worker_id: str,
) -> None:
    """Claim one run in a child process and block until SIGKILL."""
    asyncio.run(_child_claim_and_block_async(url, schema, run_id, dispatch_id, worker_id))


async def _child_claim_and_block_async(
    url: str,
    schema: str,
    run_id: str,
    dispatch_id: str,
    worker_id: str,
) -> None:
    from uuid import UUID

    database = create_research_database(
        url, connect_args={"server_settings": {"search_path": schema}}
    )
    ledger = ResearchLedger(
        database=database,
        authorizer=ResearchAuthorizer(),
        executor_registry=_ReadyExecutor(),
        snapshot_service=ResearchSnapshotService(database),
        lease_duration=timedelta(seconds=60),
    )
    task = DispatchTask(UUID(run_id), dispatch_id, "research-v1.1")
    worker = WorkerIdentity(worker_id, "research", "research-v1.1")
    now = datetime.now(UTC)
    lease = await ledger.claim_run(task=task, worker=worker, now=now)
    if lease is None:
        await database.dispose()
        raise SystemExit(17)
    while True:
        await asyncio.sleep(3600)


@pytest.fixture
def postgres_context() -> IsolatedPostgres:
    return create_postgres_context()


@pytest.mark.asyncio
async def test_subprocess_kill_after_claim_is_reaped_as_worker_lost(postgres_context):
    await asyncio.to_thread(upgrade_head, postgres_context)
    database, ledger, now, _, run_id, _, _, worker, task = await _setup(postgres_context)
    try:
        await _submit_outbox_for_worker_claim(database, run_id, now)
        process = mp.Process(
            target=_child_claim_and_block,
            args=(
                postgres_context.url,
                postgres_context.schema,
                str(run_id),
                task.dispatch_id,
                worker.worker_id,
            ),
        )
        process.start()
        deadline = time.monotonic() + 30
        claimed = False
        while time.monotonic() < deadline:
            async with database.session_factory() as session:
                row = await session.get(ResearchRun, run_id)
                if row is not None and row.status == "running":
                    claimed = True
                    break
            await asyncio.sleep(0.1)
        assert claimed
        os.kill(process.pid, signal.SIGKILL)
        process.join(timeout=10)
        assert process.exitcode is not None
        reaped = await ledger.reap_stale(
            now=now + timedelta(seconds=61), limit=10
        )
        assert any(item.run_id == run_id for item in reaped)
        async with database.session_factory() as session:
            row = await session.get(ResearchRun, run_id)
            assert row is not None
            assert row.status == "failed"
            assert row.error_code == "worker_lost"
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_restart_supervisor_scan_closes_dispatch_timeout(postgres_context):
    await asyncio.to_thread(upgrade_head, postgres_context)
    database, ledger, now, _, run_id, _, _, _, _ = await _setup(postgres_context)
    try:
        class _NoopDispatcher:
            async def drain_once(self, *, now):
                return 0

        supervisor = ResearchDispatchSupervisor(
            database=database,
            ledger=ledger,
            outbox=__import__(
                "app.research.outbox", fromlist=["ResearchOutboxPort"]
            ).ResearchOutboxPort(database=database),
            dispatcher=_NoopDispatcher(),
            enabled=False,
            clock=lambda: now + timedelta(seconds=121),
        )
        result = await supervisor.startup_recovery()
        assert result.reaped >= 1
        async with database.session_factory() as session:
            row = await session.scalar(
                select(ResearchRun).where(ResearchRun.run_id == run_id)
            )
            assert row is not None
            assert row.status == "failed"
            assert row.error_code == "dispatch_timeout"
    finally:
        await database.dispose()
