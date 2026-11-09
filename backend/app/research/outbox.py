"""Durable research outbox leasing for at-least-once broker dispatch.

Author: Damon Li
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError

from app.research.errors import DomainError
from app.research.models import ResearchOutbox
from app.research.ports import (
    DispatchLease,
    DispatchTask,
    OutboxPort,
    ResearchDatabasePort,
)


def _persistence_error() -> DomainError:
    return DomainError(
        code="persistence_failed",
        safe_message="research outbox could not be persisted",
        retryable=True,
    )


class ResearchOutboxPort(OutboxPort):
    """Lease pending outbox rows without broker or worker semantics."""

    __slots__ = ("_database",)

    def __init__(self, *, database: ResearchDatabasePort) -> None:
        self._database = database

    async def claim_pending_dispatches(
        self,
        *,
        dispatcher_id: str,
        now: datetime,
        lease_duration: timedelta,
        limit: int,
    ) -> tuple[DispatchLease, ...]:
        """Lock eligible rows and return fixed Celery-safe task payloads."""
        if limit < 1:
            return ()
        lease_expires = now + lease_duration
        claimed: list[DispatchLease] = []
        try:
            async with self._database.session_factory() as session, session.begin():
                rows = (
                    await session.scalars(
                        select(ResearchOutbox)
                        .where(
                            ResearchOutbox.delivery_status == "pending",
                            ResearchOutbox.available_at <= now,
                        )
                        .order_by(ResearchOutbox.created_at)
                        .limit(max(1, min(limit, 100)))
                        .with_for_update(skip_locked=True)
                    )
                ).all()
                expired_leases = (
                    await session.scalars(
                        select(ResearchOutbox)
                        .where(
                            ResearchOutbox.delivery_status == "leased",
                            ResearchOutbox.lease_expires_at.is_not(None),
                            ResearchOutbox.lease_expires_at < now,
                        )
                        .order_by(ResearchOutbox.created_at)
                        .limit(max(1, min(limit, 100)))
                        .with_for_update(skip_locked=True)
                    )
                ).all()
                for row in (*rows, *expired_leases):
                    if row.delivery_status == "submitted":
                        continue
                    lease_id = uuid4()
                    row.delivery_status = "leased"
                    row.lease_id = lease_id
                    row.dispatcher_id = dispatcher_id
                    row.lease_expires_at = lease_expires
                    claimed.append(
                        DispatchLease(
                            task=DispatchTask(
                                run_id=row.run_id,
                                dispatch_id=row.dispatch_id,
                                contract_version=row.contract_version,
                            ),
                            dispatcher_id=dispatcher_id,
                            lease_id=lease_id,
                            lease_expires_at=lease_expires,
                        )
                    )
        except SQLAlchemyError:
            raise _persistence_error() from None
        return tuple(claimed)

    async def acknowledge_dispatch(
        self, *, lease: DispatchLease, now: datetime
    ) -> None:
        """Mark a leased row as broker-submitted for exactly this lease."""
        await self._mutate_lease(lease, mutate=lambda row: self._ack_row(row, now))

    async def release_dispatch(
        self,
        *,
        lease: DispatchLease,
        retry_at: datetime,
        now: datetime,
    ) -> None:
        """Return a failed delivery lease to pending without deleting the row."""
        await self._mutate_lease(
            lease, mutate=lambda row: self._release_row(row, retry_at)
        )

    async def _mutate_lease(
        self,
        lease: DispatchLease,
        *,
        mutate: Callable[[ResearchOutbox], None],
    ) -> None:
        try:
            async with self._database.session_factory() as session, session.begin():
                row = await session.scalar(
                    select(ResearchOutbox)
                    .where(
                        ResearchOutbox.run_id == lease.task.run_id,
                        ResearchOutbox.dispatch_id == lease.task.dispatch_id,
                        ResearchOutbox.contract_version == lease.task.contract_version,
                        ResearchOutbox.lease_id == lease.lease_id,
                        ResearchOutbox.dispatcher_id == lease.dispatcher_id,
                    )
                    .with_for_update()
                )
                if row is None:
                    raise DomainError(
                        code="dispatch_mismatch",
                        safe_message="research dispatch does not match",
                        retryable=False,
                    )
                mutate(row)
        except DomainError:
            raise
        except SQLAlchemyError:
            raise _persistence_error() from None

    @staticmethod
    def _ack_row(row: ResearchOutbox, now: datetime) -> None:
        row.delivery_status = "submitted"
        row.submitted_at = now

    @staticmethod
    def _release_row(row: ResearchOutbox, retry_at: datetime) -> None:
        row.delivery_status = "pending"
        row.lease_id = None
        row.dispatcher_id = None
        row.lease_expires_at = None
        row.available_at = retry_at

    async def release_expired_leases(self, *, now: datetime, limit: int = 100) -> int:
        """Requeue dispatcher leases that expired before broker acknowledgement."""
        try:
            async with self._database.session_factory() as session, session.begin():
                rows = (
                    await session.scalars(
                        select(ResearchOutbox)
                        .where(
                            ResearchOutbox.delivery_status == "leased",
                            or_(
                                ResearchOutbox.lease_expires_at.is_(None),
                                ResearchOutbox.lease_expires_at < now,
                            ),
                        )
                        .limit(max(1, min(limit, 100)))
                        .with_for_update(skip_locked=True)
                    )
                ).all()
                for row in rows:
                    row.delivery_status = "pending"
                    row.lease_id = None
                    row.dispatcher_id = None
                    row.lease_expires_at = None
                    row.available_at = now
                return len(rows)
        except SQLAlchemyError:
            raise _persistence_error() from None
