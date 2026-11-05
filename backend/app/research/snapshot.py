"""Materialize, freeze, and read point-in-time research evidence snapshots."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.research.contracts import EvidenceV1, MarketFieldV1, MarketPayloadV1
from app.research.errors import DomainError
from app.research.models import (
    ResearchEvidence,
    ResearchMarketPayload,
    ResearchRun,
    ResearchSnapshotMember,
    ResearchSourcePolicy,
)
from app.research.ports import (
    FrozenSnapshot,
    ResearchDatabasePort,
    RunLease,
    SnapshotMaterialization,
    SnapshotMember,
)


def _error(code: str) -> DomainError:
    """Build a snapshot-specific domain error."""
    return DomainError(
        code=code, safe_message="snapshot operation was rejected", retryable=False
    )  # type: ignore[arg-type]


class ResearchSnapshotService:
    """Own snapshot lifecycle using only the injected research database."""

    def __init__(
        self,
        database: ResearchDatabasePort,
        authorization: object | None = None,
        *,
        max_members: int = 100,
    ) -> None:
        """Retain the injected database and snapshot member limits."""
        if max_members < 1:
            raise ValueError("max_members must be positive")
        self._database = database
        self._authorization = authorization
        self._max_members = max_members

    async def materialize_snapshot(
        self, *, run_id, lease: RunLease, now: datetime
    ) -> SnapshotMaterialization:
        """Materialize eligible evidence into a run-bound snapshot selection."""
        async with self._database.session_factory() as session, session.begin():
            run = await self._locked_run(session, run_id, lease, now)
            if run.snapshot_state == "frozen":
                raise _error("snapshot_frozen")
            rows = await self._eligible(session, run, now)
            existing = await session.scalar(
                select(ResearchSnapshotMember)
                .where(ResearchSnapshotMember.run_id == run.run_id)
                .limit(1)
            )
            if existing is not None:
                stored = await self._stored_members(session, run)
                if self._identity(stored) != self._identity(rows):
                    raise _error("request_conflict")
            else:
                # The schema guard allows membership writes only after this
                # state transition. Flush it in the same outer transaction.
                run.snapshot_state = "materialized"
                run.updated_at = now
                await session.flush()
                for row in rows:
                    session.add(
                        ResearchSnapshotMember(
                            snapshot_member_id=uuid4(),
                            run_id=run.run_id,
                            evidence_id=row.evidence_id,
                            evidence_version=row.version,
                            content_hash=row.content_hash,
                            selected_at=now,
                        )
                    )
            run.snapshot_state = "materialized"
            run.updated_at = now
            return SnapshotMaterialization(
                run_id=run.run_id, member_count=len(rows), materialized_at=now
            )

    async def freeze_snapshot(
        self, *, run_id, lease: RunLease, now: datetime
    ) -> FrozenSnapshot:
        """Freeze the materialized selection into an immutable snapshot."""
        async with self._database.session_factory() as session, session.begin():
            run = await self._locked_run(session, run_id, lease, now)
            return await self._freeze_snapshot_in_transaction(session, run, now=now)

    async def _freeze_snapshot_in_transaction(
        self, session: AsyncSession, run: ResearchRun, *, now: datetime
    ) -> FrozenSnapshot:
        """Freeze within a caller-owned PostgreSQL transaction; never close it."""
        await session.refresh(run, with_for_update=True)
        self._check_deadline(run, now)
        stored = await self._stored_members(session, run)
        if run.snapshot_state in {"materialized", "frozen"} and stored:
            # Materialization pins its exact selection. Later eligible arrivals
            # are intentionally not compared against that immutable set.
            rows = stored
        else:
            if run.snapshot_state == "frozen":
                raise _error("snapshot_frozen")
            rows = await self._eligible(session, run, now)
            if stored and self._identity(stored) != self._identity(rows):
                raise _error("request_conflict")
        if not stored:
            # A first-time freeze still follows the materialized lifecycle
            # inside this transaction; the schema guard requires this state
            # before any snapshot-member INSERT can run.
            run.snapshot_state = "materialized"
            run.updated_at = now
            await session.flush()
            for row in rows:
                session.add(self._new_member(run, row, now))
            await session.flush()
        if run.snapshot_state != "frozen":
            run.snapshot_state = "frozen"
            run.snapshot_frozen_at = now
            run.updated_at = now
            await session.flush()
        return FrozenSnapshot(
            run_id=run.run_id,
            as_of=run.as_of,
            frozen_at=run.snapshot_frozen_at or now,
            members=tuple([await self._member(session, row, now=now) for row in rows]),
        )

    async def read_snapshot(
        self, *, run_id, lease: RunLease, now: datetime
    ) -> FrozenSnapshot:
        """Read a frozen snapshot for an authorized worker lease."""
        async with self._database.session_factory() as session, session.begin():
            run = await self._locked_run(session, run_id, lease, now)
            if run.snapshot_state != "frozen":
                raise _error("invalid_run_state")
            stored = await self._stored_members(session, run)
            if len(stored) > self._max_members:
                raise _error("snapshot_frozen")
            members = []
            for row in stored:
                policy = await session.get(
                    ResearchSourcePolicy,
                    (row.source_id, row.source_policy_version),
                )
                members.append(await self._member(session, row, now=now, policy=policy))
            return FrozenSnapshot(
                run_id=run.run_id,
                as_of=run.as_of,
                frozen_at=run.snapshot_frozen_at or now,
                members=tuple(members),
            )

    async def _locked_run(self, session, run_id, lease, now):
        """Lock the run row and verify the worker lease fingerprint."""
        if lease.run_id != run_id:
            raise _error("execution_fenced")
        run = await session.scalar(
            select(ResearchRun).where(ResearchRun.run_id == run_id).with_for_update()
        )
        if run is None:
            raise _error("resource_not_found_or_denied")
        self._check_deadline(run, now)
        if run.execution_token_hash != lease.token.fingerprint():
            raise _error("execution_fenced")
        return run

    @staticmethod
    def _check_deadline(run: ResearchRun, now: datetime) -> None:
        """Reject runs whose lease or deadline has expired."""
        if (
            run.status != "running"
            or run.lease_expires_at is None
            or run.deadline_at is None
            or now >= run.lease_expires_at
            or now >= run.deadline_at
        ):
            raise _error("lease_expired")

    async def _eligible(self, session: AsyncSession, run: ResearchRun, now):
        """Select evidence rows eligible for snapshot membership."""
        query = (
            select(ResearchEvidence)
            .join(
                ResearchSourcePolicy,
                (ResearchEvidence.source_id == ResearchSourcePolicy.source_id)
                & (
                    ResearchEvidence.source_policy_version
                    == ResearchSourcePolicy.policy_version
                ),
            )
            .where(
                ResearchEvidence.entity_id == run.entity_id,
                ResearchEvidence.available_at <= run.as_of,
                ResearchEvidence.origin == "live",
                ResearchEvidence.quality_status == "verified_metadata",
                ResearchSourcePolicy.storage_allowed.is_(True),
                ResearchSourcePolicy.model_use_allowed.is_(True),
                ResearchSourcePolicy.approved_at <= now,
                ResearchSourcePolicy.expires_at > now,
            )
            .order_by(ResearchEvidence.available_at, ResearchEvidence.evidence_id)
            .limit(self._max_members + 1)
        )
        rows = list((await session.scalars(query)).all())
        if len(rows) > self._max_members:
            raise _error("snapshot_frozen")
        if run.seed_evidence_id not in {row.evidence_id for row in rows}:
            raise _error("evidence_ineligible")
        return rows

    async def _stored_members(self, session: AsyncSession, run: ResearchRun):
        """Load persisted snapshot members joined to their evidence rows."""
        query = (
            select(ResearchSnapshotMember, ResearchEvidence)
            .outerjoin(
                ResearchEvidence,
                (ResearchSnapshotMember.evidence_id == ResearchEvidence.evidence_id)
                & (ResearchSnapshotMember.evidence_version == ResearchEvidence.version)
                & (
                    ResearchSnapshotMember.content_hash == ResearchEvidence.content_hash
                ),
            )
            .where(ResearchSnapshotMember.run_id == run.run_id)
            .order_by(ResearchEvidence.available_at, ResearchEvidence.evidence_id)
        )
        pairs = list((await session.execute(query)).all())
        if any(evidence is None for _, evidence in pairs):
            raise _error("request_conflict")
        rows = [evidence for _, evidence in pairs]
        if any(
            row.entity_id != run.entity_id
            or row.available_at > run.as_of
            or row.origin != "live"
            or row.quality_status != "verified_metadata"
            for row in rows
        ):
            raise _error("request_conflict")
        return rows

    @staticmethod
    def _identity(rows):
        """Return a stable identity tuple for a snapshot member selection."""
        return tuple((row.evidence_id, row.version, row.content_hash) for row in rows)

    @staticmethod
    def _new_member(run, row, now):
        """Create a snapshot membership row for one eligible evidence item."""
        return ResearchSnapshotMember(
            snapshot_member_id=uuid4(),
            run_id=run.run_id,
            evidence_id=row.evidence_id,
            evidence_version=row.version,
            content_hash=row.content_hash,
            selected_at=now,
        )

    async def _member(
        self,
        session: AsyncSession,
        row: ResearchEvidence,
        *,
        now: datetime,
        policy=None,
    ) -> SnapshotMember:
        """Project one evidence row into the snapshot member contract."""
        policy = policy or await session.get(
            ResearchSourcePolicy, (row.source_id, row.source_policy_version)
        )
        if (
            policy is None
            or not policy.storage_allowed
            or not policy.model_use_allowed
            or policy.approved_at > now
            or policy.expires_at <= now
            or row.origin != "live"
            or row.quality_status != "verified_metadata"
        ):
            raise _error("license_revoked")
        market = None
        if row.evidence_kind == "market":
            payload = await session.get(ResearchMarketPayload, row.evidence_id)
            if payload is None:
                raise _error("market_data_unverifiable")
            try:
                market = MarketPayloadV1(
                    evidence_id=row.evidence_id,
                    symbol=payload.symbol,
                    observed_at=payload.observed_at,
                    available_at=payload.available_at,
                    fetched_at=payload.fetched_at,
                    timezone=payload.timezone,
                    currency=payload.currency,
                    adjustment=payload.adjustment,
                    fields=[
                        MarketFieldV1.model_validate(item)
                        for item in payload.fields_projection
                    ],
                    provider=payload.provider,
                    version=payload.version,
                    is_mock=payload.is_mock,
                )
            except (TypeError, ValueError):
                raise _error("market_data_unverifiable") from None
            if (
                market.evidence_id != row.evidence_id
                or market.provider != row.source_id
                or market.version != row.version
                or market.symbol != row.entity_id
                or market.available_at != row.available_at
                or market.fetched_at != row.fetched_at
                or market.observed_at != row.published_at
                or market.timezone != row.timezone
                or market.is_mock
            ):
                raise _error("market_data_unverifiable")
        evidence = EvidenceV1(
            evidence_id=row.evidence_id,
            source_id=row.source_id,
            source_url=row.source_url,
            content_hash=row.content_hash,
            published_at=row.published_at,
            fetched_at=row.fetched_at,
            available_at=row.available_at,
            timezone=row.timezone,
            license_scope=row.license_scope,
            entity_ids=[row.entity_id],
            excerpt=row.excerpt[: policy.allowed_excerpt_length],
            quality_status=row.quality_status,
            evidence_kind=row.evidence_kind,
            version=row.version,
            source_policy_version=row.source_policy_version,
            origin=row.origin,
            market_payload=market,
        )
        return SnapshotMember(
            evidence=evidence, version=row.version, content_hash=row.content_hash
        )
