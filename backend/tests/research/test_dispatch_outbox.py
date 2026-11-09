"""PostgreSQL outbox leasing and dispatcher acknowledgement tests."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from app.research.db import create_research_database
from app.research.dispatch import InMemoryDispatchTransport, ResearchDispatcher
from app.research.models import ResearchOutbox, ResearchRun
from app.research.outbox import ResearchOutboxPort
from sqlalchemy import select

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
async def test_outbox_claim_ack_publishes_to_broker(postgres_context):
    await asyncio.to_thread(upgrade_head, postgres_context)
    database, _, now, _, run_id, _, _, _, _ = await _setup(postgres_context)
    try:
        outbox = ResearchOutboxPort(database=database)
        transport = InMemoryDispatchTransport()
        dispatcher = ResearchDispatcher(
            outbox=outbox,
            transport=transport,
            dispatcher_id="test-dispatcher",
            lease_duration=timedelta(seconds=30),
        )
        assert await dispatcher.drain_once(now=now) == 1
        assert len(transport.messages) == 1
        async with database.session_factory() as session:
            row = await session.scalar(
                select(ResearchOutbox).where(ResearchOutbox.run_id == run_id)
            )
            assert row is not None
            assert row.delivery_status == "submitted"
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_outbox_broker_failure_releases_without_deleting_row(postgres_context):
    await asyncio.to_thread(upgrade_head, postgres_context)
    database, _, now, _, run_id, _, _, _, _ = await _setup(postgres_context)
    try:
        outbox = ResearchOutboxPort(database=database)
        transport = InMemoryDispatchTransport()
        transport.fail_next()
        dispatcher = ResearchDispatcher(
            outbox=outbox,
            transport=transport,
            dispatcher_id="test-dispatcher",
            lease_duration=timedelta(seconds=30),
        )
        assert await dispatcher.drain_once(now=now) == 0
        async with database.session_factory() as session:
            row = await session.scalar(
                select(ResearchOutbox).where(ResearchOutbox.run_id == run_id)
            )
            assert row is not None
            assert row.delivery_status == "pending"
            assert row.available_at > now
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_outbox_crash_after_send_before_ack_reclaims_lease(postgres_context):
    await asyncio.to_thread(upgrade_head, postgres_context)
    database, _, now, _, run_id, _, _, _, _ = await _setup(postgres_context)
    try:
        outbox = ResearchOutboxPort(database=database)
        leases = await outbox.claim_pending_dispatches(
            dispatcher_id="d1",
            now=now,
            lease_duration=timedelta(seconds=1),
            limit=10,
        )
        assert len(leases) == 1
        after_expiry = now + timedelta(seconds=2)
        released = await outbox.release_expired_leases(now=after_expiry)
        assert released == 1
        reclaimed = await outbox.claim_pending_dispatches(
            dispatcher_id="d2",
            now=after_expiry,
            lease_duration=timedelta(seconds=30),
            limit=10,
        )
        assert len(reclaimed) == 1
        await outbox.acknowledge_dispatch(lease=reclaimed[0], now=after_expiry)
        async with database.session_factory() as session:
            row = await session.scalar(
                select(ResearchOutbox).where(ResearchOutbox.run_id == run_id)
            )
            assert row is not None
            assert row.delivery_status == "submitted"
    finally:
        await database.dispose()
