"""Research Celery worker task, executor registry, and fixture executor.

Author: Damon Li
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError

from app.research.dispatch import (
    RESEARCH_CONTRACT_VERSION,
    RESEARCH_EXECUTE_TASK_NAME,
    RESEARCH_QUEUE_NAME,
    broker_reachable,
)
from app.research.errors import DomainError
from app.research.models import ResearchWorkerHeartbeat
from app.research.ports import (
    DispatchTask,
    ExecutorReadiness,
    ExecutorRegistryPort,
    ResearchDatabasePort,
    ResearchLedgerPort,
    RunFinishRequest,
    WorkerIdentity,
)

logger = logging.getLogger(__name__)

FIXTURE_EXECUTOR_WORKER_ID = "research.fixture.v1"
HEARTBEAT_INTERVAL = timedelta(seconds=10)
LEASE_HEARTBEAT = HEARTBEAT_INTERVAL
WORKER_HEARTBEAT_TTL = timedelta(seconds=90)
APPROVED_EXECUTOR_PREFIX = "research.worker."


def _aware_now() -> datetime:
    return datetime.now(UTC)


def is_fixture_executor(worker_id: str) -> bool:
    """Return whether a worker id identifies the controlled S04 fixture executor."""
    return worker_id == FIXTURE_EXECUTOR_WORKER_ID


def is_approved_live_executor(worker_id: str) -> bool:
    """Return whether a worker id counts toward production executor readiness."""
    return worker_id.startswith(APPROVED_EXECUTOR_PREFIX)


class ResearchExecutorRegistry(ExecutorRegistryPort):
    """Persist worker heartbeats and derive broker-backed readiness."""

    __slots__ = (
        "_allow_fixture_executor",
        "_broker_probe",
        "_database",
        "_execution_enabled",
        "_heartbeat_ttl",
        "_redis_url",
    )

    def __init__(
        self,
        *,
        database: ResearchDatabasePort,
        execution_enabled: bool,
        redis_url: str,
        heartbeat_ttl: timedelta = WORKER_HEARTBEAT_TTL,
        allow_fixture_executor: bool = False,
        broker_probe: Callable[[str], bool] | None = None,
    ) -> None:
        self._database = database
        self._execution_enabled = execution_enabled
        self._redis_url = redis_url
        self._heartbeat_ttl = heartbeat_ttl
        self._allow_fixture_executor = allow_fixture_executor
        self._broker_probe = broker_probe or broker_reachable

    async def record_heartbeat(
        self, *, worker: WorkerIdentity, now: datetime
    ) -> ExecutorReadiness:
        expires_at = now + self._heartbeat_ttl
        try:
            async with self._database.session_factory() as session, session.begin():
                await session.execute(
                    pg_insert(ResearchWorkerHeartbeat)
                    .values(
                        worker_id=worker.worker_id,
                        queue_name=worker.queue_name,
                        contract_version=worker.contract_version,
                        worker_status="active",
                        heartbeat_at=now,
                        expires_at=expires_at,
                    )
                    .on_conflict_do_update(
                        index_elements=[ResearchWorkerHeartbeat.worker_id],
                        set_={
                            "queue_name": worker.queue_name,
                            "contract_version": worker.contract_version,
                            "worker_status": "active",
                            "heartbeat_at": now,
                            "expires_at": expires_at,
                        },
                    )
                )
        except SQLAlchemyError:
            return ExecutorReadiness(
                ready=False,
                reason="persistence_failed",
                checked_at=now,
                expires_at=now,
            )
        return await self.get_readiness(now=now)

    async def get_readiness(self, *, now: datetime) -> ExecutorReadiness:
        checked_at = now
        expires_at = now + timedelta(seconds=30)
        if not self._execution_enabled:
            return ExecutorReadiness(
                ready=False,
                reason="execution_disabled",
                checked_at=checked_at,
                expires_at=expires_at,
            )
        if not self._broker_probe(self._redis_url):
            return ExecutorReadiness(
                ready=False,
                reason="broker_unreachable",
                checked_at=checked_at,
                expires_at=expires_at,
            )
        try:
            async with self._database.session_factory() as session:
                rows = (
                    await session.scalars(
                        select(ResearchWorkerHeartbeat).where(
                            ResearchWorkerHeartbeat.worker_status == "active",
                            ResearchWorkerHeartbeat.expires_at > now,
                            ResearchWorkerHeartbeat.contract_version
                            == RESEARCH_CONTRACT_VERSION,
                            ResearchWorkerHeartbeat.queue_name == RESEARCH_QUEUE_NAME,
                        )
                    )
                ).all()
        except SQLAlchemyError:
            return ExecutorReadiness(
                ready=False,
                reason="persistence_failed",
                checked_at=checked_at,
                expires_at=expires_at,
            )
        if not rows:
            return ExecutorReadiness(
                ready=False,
                reason="no_registered_worker",
                checked_at=checked_at,
                expires_at=expires_at,
            )
        approved = [
            row
            for row in rows
            if is_approved_live_executor(row.worker_id)
            or (
                self._allow_fixture_executor
                and is_fixture_executor(row.worker_id)
            )
        ]
        if not approved:
            return ExecutorReadiness(
                ready=False,
                reason="executor_not_approved",
                checked_at=checked_at,
                expires_at=expires_at,
            )
        return ExecutorReadiness(
            ready=True,
            reason="executor_ready",
            checked_at=checked_at,
            expires_at=min(row.expires_at for row in approved),
        )


class FixtureResearchExecutor:
    """Controlled S04 executor that never publishes a formal research Brief."""

    __slots__ = ("_clock", "_ledger", "_worker")

    def __init__(
        self,
        *,
        ledger: ResearchLedgerPort,
        worker: WorkerIdentity,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._ledger = ledger
        self._worker = worker
        self._clock = clock or _aware_now

    async def execute(self, task: DispatchTask) -> None:
        """Claim a run and close it safely without S05 Flow publication."""
        now = self._clock()
        lease = await self._ledger.claim_run(task=task, worker=self._worker, now=now)
        if lease is None:
            return
        await self._ledger.heartbeat_run(
            run_id=lease.run_id,
            lease=lease,
            worker=self._worker,
            now=now + timedelta(seconds=1),
        )
        await self._ledger.finish_run(
            run_id=lease.run_id,
            lease=lease,
            finish=RunFinishRequest(
                status="needs_review",
                code="fixture_executor",
                cancellation_reason=None,
            ),
            now=now + timedelta(seconds=2),
        )


_worker_stack: dict[str, Any] = {}


def build_research_worker_stack(settings: Any) -> dict[str, Any]:
    """Construct ledger/registry wiring for the Celery worker process."""
    from app.research.auth import ResearchAuthorizer
    from app.research.db import create_research_database
    from app.research.ledger import ResearchLedger
    from app.research.snapshot import ResearchSnapshotService

    database = create_research_database(settings.RESEARCH_DATABASE_URL)
    registry = ResearchExecutorRegistry(
        database=database,
        execution_enabled=settings.RESEARCH_EXECUTION_ENABLED,
        redis_url=settings.REDIS_URL,
        allow_fixture_executor=settings.RESEARCH_ALLOW_FIXTURE_EXECUTOR,
    )
    ledger = ResearchLedger(
        database=database,
        authorizer=ResearchAuthorizer(),
        executor_registry=registry,
        snapshot_service=ResearchSnapshotService(database),
    )
    return {
        "ledger": ledger,
        "executor_registry": registry,
        "allow_fixture": settings.RESEARCH_ALLOW_FIXTURE_EXECUTOR,
    }


def _run_async(coro):
    return asyncio.run(coro)


async def _execute_task_async(
    *,
    run_id: str,
    dispatch_id: str,
    contract_version: str,
    ledger: ResearchLedgerPort,
    registry: ExecutorRegistryPort,
    worker_id: str,
) -> None:
    task = DispatchTask(
        run_id=UUID(run_id),
        dispatch_id=dispatch_id,
        contract_version=contract_version,
    )
    worker = WorkerIdentity(
        worker_id=worker_id,
        queue_name=RESEARCH_QUEUE_NAME,
        contract_version=RESEARCH_CONTRACT_VERSION,
    )
    now = _aware_now()
    await registry.record_heartbeat(worker=worker, now=now)
    executor = FixtureResearchExecutor(ledger=ledger, worker=worker)
    await executor.execute(task)


def make_celery_task(celery_app: Any):
    """Register the research execute task on an existing Celery application."""

    @celery_app.task(
        name=RESEARCH_EXECUTE_TASK_NAME,
        bind=True,
        acks_late=True,
        reject_on_worker_lost=True,
        queue=RESEARCH_QUEUE_NAME,
    )
    def execute_research_run_v1(
        self,
        run_id: str,
        dispatch_id: str,
        contract_version: str,
    ) -> None:
        """Consume a fixed research dispatch payload without bearer or secrets."""
        from app.core.config import settings

        stack = _worker_stack.get("main")
        if stack is None:
            stack = build_research_worker_stack(settings)
            _worker_stack["main"] = stack
        worker_id = (
            FIXTURE_EXECUTOR_WORKER_ID
            if stack.get("allow_fixture") or settings.RESEARCH_ALLOW_FIXTURE_EXECUTOR
            else f"{APPROVED_EXECUTOR_PREFIX}{os.environ.get('HOSTNAME', 'local')}"
        )
        try:
            _run_async(
                _execute_task_async(
                    run_id=run_id,
                    dispatch_id=dispatch_id,
                    contract_version=contract_version,
                    ledger=stack["ledger"],
                    registry=stack["executor_registry"],
                    worker_id=worker_id,
                )
            )
        except DomainError as error:
            logger.warning("research worker domain failure code=%s", error.code)
        except Exception:
            logger.exception("research worker failed")

    return execute_research_run_v1


def register_research_worker_task() -> None:
    """Import-time registration hook for Celery worker modules."""
    from app.core.celery_app import celery_app

    make_celery_task(celery_app)


register_research_worker_task()
