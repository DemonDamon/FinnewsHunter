"""Executor registry readiness and execution_unavailable gates."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from app.research.auth import ResearchAuthorizer
from app.research.contracts import StartResearchInput
from app.research.db import create_research_database
from app.research.errors import DomainError
from app.research.ledger import ResearchLedger
from app.research.ports import WorkerIdentity
from app.research.snapshot import ResearchSnapshotService
from app.research.worker import (
    FIXTURE_EXECUTOR_WORKER_ID,
    ResearchExecutorRegistry,
)

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
async def test_registry_requires_execution_switch_and_broker(postgres_context):
    await asyncio.to_thread(upgrade_head, postgres_context)
    database = create_research_database(
        postgres_context.url,
        connect_args={"server_settings": {"search_path": postgres_context.schema}},
    )
    try:
        registry = ResearchExecutorRegistry(
            database=database,
            execution_enabled=False,
            redis_url="redis://127.0.0.1:6379/0",
            broker_probe=lambda _url: True,
        )
        now = datetime.now(UTC)
        readiness = await registry.get_readiness(now=now)
        assert readiness.ready is False
        assert readiness.reason == "execution_disabled"
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_fixture_executor_does_not_make_production_ready(postgres_context):
    await asyncio.to_thread(upgrade_head, postgres_context)
    database = create_research_database(
        postgres_context.url,
        connect_args={"server_settings": {"search_path": postgres_context.schema}},
    )
    try:
        registry = ResearchExecutorRegistry(
            database=database,
            execution_enabled=True,
            redis_url="redis://127.0.0.1:6379/0",
            allow_fixture_executor=False,
            broker_probe=lambda _url: True,
        )
        now = datetime.now(UTC)
        worker = WorkerIdentity(
            FIXTURE_EXECUTOR_WORKER_ID, "research", "research-v1.1"
        )
        await registry.record_heartbeat(worker=worker, now=now)
        readiness = await registry.get_readiness(now=now)
        assert readiness.ready is False
        assert readiness.reason == "executor_not_approved"
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_create_run_fails_closed_when_executor_unready(postgres_context):
    await asyncio.to_thread(upgrade_head, postgres_context)
    database, _, now, _, _, evidence_id, principal, _, _ = await _setup(
        postgres_context
    )
    try:
        registry = ResearchExecutorRegistry(
            database=database,
            execution_enabled=True,
            redis_url="redis://127.0.0.1:6379/0",
            broker_probe=lambda _url: True,
        )
        ledger = ResearchLedger(
            database=database,
            authorizer=ResearchAuthorizer(),
            executor_registry=registry,
            snapshot_service=ResearchSnapshotService(database),
        )
        request = StartResearchInput(
            request_id=uuid4(),
            entity_ids=["CN.SH.600000"],
            as_of=now - timedelta(seconds=30),
            seed_evidence_id=evidence_id,
            question="readiness",
        )
        with pytest.raises(DomainError) as denied:
            await ledger.create_or_reuse_run(
                principal=principal, request=request, now=now
            )
        assert denied.value.code == "execution_unavailable"
    finally:
        await database.dispose()
