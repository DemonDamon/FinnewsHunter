"""S04 duplicate delivery and dispatcher-before-claim integration tests."""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from app.research.dispatch import InMemoryDispatchTransport, ResearchDispatcher
from app.research.errors import DomainError
from app.research.outbox import ResearchOutboxPort
from app.research.ports import RunFinishRequest

from backend.tests.research.postgres_fixtures import (
    IsolatedPostgres,
    create_postgres_context,
    upgrade_head,
)
from backend.tests.research.test_run_transactions import _claim, _setup


@pytest.fixture
def postgres_context() -> IsolatedPostgres:
    return create_postgres_context()


@pytest.mark.asyncio
async def test_duplicate_delivery_after_claim_is_no_op(postgres_context):
    await asyncio.to_thread(upgrade_head, postgres_context)
    database, ledger, now, _, run_id, _, _, worker, task = await _setup(
        postgres_context
    )
    try:
        outbox = ResearchOutboxPort(database=database)
        dispatcher = ResearchDispatcher(
            outbox=outbox,
            transport=InMemoryDispatchTransport(),
            dispatcher_id="test-dispatcher",
        )
        assert await dispatcher.drain_once(now=now) == 1
        lease = await _claim(ledger, now, worker, task, database)
        duplicate = await ledger.claim_run(
            task=task, worker=worker, now=now + timedelta(seconds=1)
        )
        assert duplicate is None
        with pytest.raises(DomainError) as wrong_worker:
            await ledger.heartbeat_run(
                run_id=run_id,
                lease=lease,
                worker=__import__(
                    "app.research.ports", fromlist=["WorkerIdentity"]
                ).WorkerIdentity(
                    "other", worker.queue_name, worker.contract_version
                ),
                now=now + timedelta(seconds=2),
            )
        assert wrong_worker.value.code == "execution_fenced"
        renewed = await ledger.heartbeat_run(
            run_id=run_id, lease=lease, worker=worker, now=now + timedelta(seconds=2)
        )
        assert renewed.lease_expires_at > lease.lease_expires_at
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_late_finish_after_reap_is_fenced(postgres_context):
    await asyncio.to_thread(upgrade_head, postgres_context)
    database, ledger, now, _, run_id, _, _, worker, task = await _setup(
        postgres_context
    )
    try:
        lease = await _claim(ledger, now, worker, task, database)
        reaped = await ledger.reap_stale(
            now=lease.lease_expires_at + timedelta(seconds=1), limit=10
        )
        assert any(item.run_id == run_id for item in reaped)
        with pytest.raises(DomainError) as late:
            await ledger.finish_run(
                run_id=run_id,
                lease=lease,
                finish=RunFinishRequest(
                    status="failed", code="late_after_reap", cancellation_reason=None
                ),
                now=lease.lease_expires_at + timedelta(seconds=2),
            )
        assert late.value.code in {"lease_expired", "execution_fenced", "terminal_state"}
        async with database.session_factory() as session:
            from app.research.models import ResearchRun

            row = await session.get(ResearchRun, run_id)
            assert row is not None
            assert row.status == "failed"
            assert row.error_code == "worker_lost"
    finally:
        await database.dispose()
