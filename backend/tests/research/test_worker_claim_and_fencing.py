"""S04 duplicate delivery and dispatcher-before-claim integration tests."""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from app.research.dispatch import InMemoryDispatchTransport, ResearchDispatcher
from app.research.errors import DomainError
from app.research.outbox import ResearchOutboxPort

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
    database, ledger, now, _, _, _, _, worker, task = await _setup(postgres_context)
    try:
        outbox = ResearchOutboxPort(database=database)
        dispatcher = ResearchDispatcher(
            outbox=outbox,
            transport=InMemoryDispatchTransport(),
            dispatcher_id="test-dispatcher",
        )
        assert await dispatcher.drain_once(now=now) == 1
        lease = await _claim(ledger, now, worker, task)
        duplicate = await ledger.claim_run(
            task=task, worker=worker, now=now + timedelta(seconds=1)
        )
        assert duplicate is None
        with pytest.raises(DomainError) as fenced:
            await ledger.finish_run(
                run_id=lease.run_id,
                lease=lease,
                finish=__import__(
                    "app.research.ports", fromlist=["RunFinishRequest"]
                ).RunFinishRequest(
                    status="failed", code="late", cancellation_reason=None
                ),
                now=lease.deadline_at + timedelta(seconds=1),
            )
        assert fenced.value.code in {"lease_expired", "execution_fenced"}
    finally:
        await database.dispose()
