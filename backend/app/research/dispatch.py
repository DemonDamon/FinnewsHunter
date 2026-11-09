"""Research dispatcher supervisor and broker transport wiring.

Author: Damon Li
"""

from __future__ import annotations

import asyncio
import logging
import socket
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any, Protocol

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.research.outbox import ResearchOutboxPort
from app.research.ports import (
    DispatchTask,
    OutboxPort,
    ResearchDatabasePort,
    ResearchLedgerPort,
)

logger = logging.getLogger(__name__)

RESEARCH_CONTRACT_VERSION = "research-v1.1"
RESEARCH_EXECUTE_TASK_NAME = "finnews.research.execute_run.v1"
RESEARCH_QUEUE_NAME = "research"
DISPATCH_LEASE_DURATION = timedelta(seconds=30)
DISPATCH_BATCH_LIMIT = 16
SUPERVISOR_INTERVAL = timedelta(seconds=5)
REAP_BATCH_LIMIT = 32
ADVISORY_LOCK_KEY = int.from_bytes(
    sha256(b"finnews.research.dispatch.supervisor").digest()[:8], "big", signed=True
)


class DispatchTransport(Protocol):
    """Publish a fixed research execute payload to the broker."""

    def send(self, task: DispatchTask) -> None:
        """Enqueue one research execute task; raise on broker failure."""
        ...


@dataclass(frozen=True, slots=True)
class DispatchCycleResult:
    """Summarize one supervisor iteration without leaking row identifiers."""

    dispatched: int
    released: int
    reaped: int


def _aware_now() -> datetime:
    return datetime.now(UTC)


def broker_reachable(redis_url: str, *, timeout: float = 0.5) -> bool:
    """Return whether a Redis endpoint accepts a TCP connection."""
    if not redis_url.startswith("redis://"):
        return False
    try:
        remainder = redis_url.removeprefix("redis://")
        if "@" in remainder:
            _, host_part = remainder.split("@", 1)
        else:
            host_part = remainder
        host_port = host_part.split("/", 1)[0]
        host, _, port_text = host_port.partition(":")
        port = int(port_text or "6379")
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class CeleryDispatchTransport:
    """Send research tasks through the existing Celery application."""

    __slots__ = ("_queue", "_send_task")

    def __init__(self, *, celery_app: Any, queue: str = RESEARCH_QUEUE_NAME) -> None:
        self._send_task = celery_app.send_task
        self._queue = queue

    def send(self, task: DispatchTask) -> None:
        self._send_task(
            RESEARCH_EXECUTE_TASK_NAME,
            kwargs={
                "run_id": str(task.run_id),
                "dispatch_id": task.dispatch_id,
                "contract_version": task.contract_version,
            },
            queue=self._queue,
        )


class ResearchDispatcher:
    """Drain durable outbox leases into the broker with safe ack/release."""

    __slots__ = ("_dispatcher_id", "_lease_duration", "_outbox", "_transport")

    def __init__(
        self,
        *,
        outbox: OutboxPort,
        transport: DispatchTransport,
        dispatcher_id: str,
        lease_duration: timedelta = DISPATCH_LEASE_DURATION,
    ) -> None:
        self._outbox = outbox
        self._transport = transport
        self._dispatcher_id = dispatcher_id
        self._lease_duration = lease_duration

    async def drain_once(self, *, now: datetime) -> int:
        """Claim pending rows, publish tasks, and acknowledge successful sends."""
        dispatched = 0
        leases = await self._outbox.claim_pending_dispatches(
            dispatcher_id=self._dispatcher_id,
            now=now,
            lease_duration=self._lease_duration,
            limit=DISPATCH_BATCH_LIMIT,
        )
        for lease in leases:
            try:
                await asyncio.to_thread(self._transport.send, lease.task)
            except Exception:  # noqa: BLE001 — broker failures release without leaking details
                retry_at = now + timedelta(seconds=5)
                await self._outbox.release_dispatch(
                    lease=lease, retry_at=retry_at, now=now
                )
                continue
            await self._outbox.acknowledge_dispatch(lease=lease, now=now)
            dispatched += 1
        return dispatched


class ResearchDispatchSupervisor:
    """Run dispatcher drain and stale-run reaping under PostgreSQL advisory locks."""

    __slots__ = (
        "_clock",
        "_database",
        "_dispatcher",
        "_enabled",
        "_ledger",
        "_outbox",
        "_stop",
        "_task",
    )

    def __init__(
        self,
        *,
        database: ResearchDatabasePort,
        ledger: ResearchLedgerPort,
        outbox: ResearchOutboxPort,
        dispatcher: ResearchDispatcher,
        clock: Callable[[], datetime] | None = None,
        enabled: bool = True,
    ) -> None:
        self._database = database
        self._ledger = ledger
        self._outbox = outbox
        self._dispatcher = dispatcher
        self._clock = clock or _aware_now
        self._enabled = enabled
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def startup_recovery(self) -> DispatchCycleResult:
        """Scan stale runs and outbox leases immediately after process start."""
        now = self._clock()
        released = await self._outbox.release_expired_leases(now=now)
        reaped = len(await self._ledger.reap_stale(now=now, limit=REAP_BATCH_LIMIT))
        dispatched = await self._dispatcher.drain_once(now=now) if self._enabled else 0
        return DispatchCycleResult(
            dispatched=dispatched, released=released, reaped=reaped
        )

    def start_background(self) -> None:
        """Launch the periodic supervisor loop."""
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run_loop(), name="research-dispatch")

    async def stop_background(self) -> None:
        """Stop the supervisor loop and wait for the current iteration."""
        self._stop.set()
        if self._task is not None:
            await self._task
            self._task = None

    async def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self._cycle_once()
            except Exception:
                logger.exception("research dispatch supervisor cycle failed")
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=SUPERVISOR_INTERVAL.total_seconds()
                )
            except TimeoutError:
                continue

    async def _cycle_once(self) -> DispatchCycleResult:
        if not await self._try_advisory_lock():
            return DispatchCycleResult(dispatched=0, released=0, reaped=0)
        try:
            now = self._clock()
            released = await self._outbox.release_expired_leases(now=now)
            reaped = len(
                await self._ledger.reap_stale(now=now, limit=REAP_BATCH_LIMIT)
            )
            dispatched = (
                await self._dispatcher.drain_once(now=now) if self._enabled else 0
            )
            return DispatchCycleResult(
                dispatched=dispatched, released=released, reaped=reaped
            )
        finally:
            await self._release_advisory_lock()

    async def _try_advisory_lock(self) -> bool:
        try:
            async with self._database.session_factory() as session:
                result = await session.execute(
                    text("SELECT pg_try_advisory_lock(:key)"),
                    {"key": ADVISORY_LOCK_KEY},
                )
                return bool(result.scalar())
        except SQLAlchemyError:
            return False

    async def _release_advisory_lock(self) -> None:
        try:
            async with self._database.session_factory() as session:
                await session.execute(
                    text("SELECT pg_advisory_unlock(:key)"),
                    {"key": ADVISORY_LOCK_KEY},
                )
                await session.commit()
        except SQLAlchemyError:
            return


class InMemoryDispatchTransport:
    """Capture broker publishes for isolated dispatch tests."""

    __slots__ = ("messages",)

    def __init__(self) -> None:
        self.messages: list[DispatchTask] = []

    def send(self, task: DispatchTask) -> None:
        self.messages.append(task)

    def fail_next(self) -> None:
        """Replace send with a failing implementation for one call."""

        def _raise(_task: DispatchTask) -> None:
            raise RuntimeError("broker unavailable")

        self.send = _raise  # type: ignore[method-assign]
