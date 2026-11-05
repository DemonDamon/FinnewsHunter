"""PostgreSQL integration coverage for snapshot freeze invariants."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from app.research.db import create_research_database
from app.research.errors import DomainError
from app.research.models import (
    ResearchEvidence,
    ResearchRun,
    ResearchSnapshotMember,
    ResearchSourcePolicy,
)
from app.research.ports import ExecutionToken, RunLease
from app.research.snapshot import ResearchSnapshotService
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from tests.research.postgres_fixtures import (
    IsolatedPostgres,
    create_postgres_context,
    upgrade_head,
)

ENTITY = "CN.SH.600000"
OTHER_ENTITY = "CN.SZ.000001"


@pytest.fixture
def postgres_context() -> IsolatedPostgres:
    """Test helper postgres_context."""
    return create_postgres_context()


def _policy(source: str, now: datetime, **changes) -> ResearchSourcePolicy:
    """Test helper for _policy."""
    values = {
        "source_id": source,
        "policy_version": "v1",
        "license_id": "license",
        "terms_ref": "terms",
        "approved_at": now - timedelta(days=1),
        "expires_at": now + timedelta(seconds=20),
        "redisplay_allowed": True,
        "model_use_allowed": True,
        "storage_allowed": True,
        "allowed_excerpt_length": 8,
    }
    values.update(changes)
    return ResearchSourcePolicy(**values)


def _evidence(eid, *, now, available, entity=ENTITY, source="news", **changes):
    """Test helper for _evidence."""
    values = {
        "evidence_id": eid,
        "source_id": source,
        "source_url": "https://example.test/source",
        "content_hash": ("a" if source == "news" else "b") * 64,
        "published_at": available - timedelta(minutes=1),
        "fetched_at": max(available, now),
        "available_at": available,
        "timezone": "Asia/Shanghai",
        "license_scope": "metadata_only",
        "entity_id": entity,
        "excerpt": "1234567890-long-excerpt",
        "quality_status": "verified_metadata",
        "evidence_kind": "event",
        "version": f"v-{available.timestamp()}-{uuid4().hex[:6]}",
        "source_policy_version": "v1",
        "origin": "live",
        "admitted_at": now,
    }
    values.update(changes)
    return ResearchEvidence(**values)


async def _seed(database, now):
    """Test helper for _seed."""
    seed_id, late_id = uuid4(), uuid4()
    other_id = uuid4()
    async with database.session_factory() as session, session.begin():  # skipcq: PYL-E1102 -- async session factory from research port
        # FK order is deliberate: policy rows must be flushed before evidence.
        session.add_all(
            [_policy("news", now), _policy("bad", now, model_use_allowed=False)]
        )
        await session.flush()
        session.add_all(
            [
                _evidence(seed_id, now=now, available=now - timedelta(minutes=5)),
                _evidence(late_id, now=now, available=now + timedelta(minutes=2)),
                _evidence(
                    other_id,
                    now=now,
                    available=now - timedelta(minutes=3),
                    entity=OTHER_ENTITY,
                ),
                _evidence(
                    uuid4(), now=now, available=now - timedelta(minutes=2), source="bad"
                ),
            ]
        )
    return seed_id, late_id, other_id


async def _run(database, *, seed_id, now, as_of, entity=ENTITY, state="none"):
    """Test helper for _run."""
    rid = uuid4()
    async with database.session_factory() as session, session.begin():  # skipcq: PYL-E1102 -- async session factory from research port
        session.add(
            ResearchRun(
                run_id=rid,
                request_id=uuid4(),
                principal_id=uuid4(),
                entity_id=entity,
                seed_evidence_id=seed_id,
                request_hash="c" * 64,
                as_of=as_of,
                status="running",
                snapshot_state=state,
                policy_version="v1",
                prompt_version="p1",
                execution_token_hash=ExecutionToken(b"secret").fingerprint(),
                lease_expires_at=now + timedelta(minutes=5),
                deadline_at=now + timedelta(minutes=10),
                created_at=now,
                updated_at=now,
            )
        )
    return rid, RunLease(
        run_id=rid,
        token=ExecutionToken(b"secret"),
        lease_expires_at=now + timedelta(minutes=5),
        deadline_at=now + timedelta(minutes=10),
    )


@pytest.mark.asyncio
async def test_duplicate_materialization_uses_eligibility_order(postgres_context):
    """Test helper test_duplicate_materialization_uses_eligibility_order."""
    await asyncio.to_thread(upgrade_head, postgres_context)
    database = create_research_database(
        postgres_context.url,
        connect_args={"server_settings": {"search_path": postgres_context.schema}},
    )
    now = datetime(2026, 10, 31, 10, 0, tzinfo=UTC)
    service = ResearchSnapshotService(database)
    lower_id = UUID("00000000-0000-0000-0000-000000000001")
    higher_id = UUID("00000000-0000-0000-0000-000000000002")
    try:
        async with database.session_factory() as session, session.begin():  # skipcq: PYL-E1102 -- async session factory from research port
            session.add(_policy("news", now))
            await session.flush()
            session.add_all(
                [
                    _evidence(
                        higher_id,
                        now=now,
                        available=now - timedelta(minutes=2),
                        content_hash="e" * 64,
                    ),
                    _evidence(
                        lower_id,
                        now=now,
                        available=now - timedelta(minutes=1),
                        content_hash="f" * 64,
                    ),
                ]
            )
        rid, lease = await _run(database, seed_id=higher_id, now=now, as_of=now)

        first = await service.materialize_snapshot(run_id=rid, lease=lease, now=now)
        second = await service.materialize_snapshot(run_id=rid, lease=lease, now=now)
        frozen = await service.freeze_snapshot(run_id=rid, lease=lease, now=now)

        assert first.member_count == second.member_count == 2
        assert [member.evidence.evidence_id for member in frozen.members] == [
            higher_id,
            lower_id,
        ]
        assert {member.evidence.evidence_id for member in frozen.members} == {
            higher_id,
            lower_id,
        }
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_snapshot_point_in_time_freeze_and_fail_closed(postgres_context):
    """Test helper test_snapshot_point_in_time_freeze_and_fail_closed."""
    await asyncio.to_thread(upgrade_head, postgres_context)
    database = create_research_database(
        postgres_context.url,
        connect_args={"server_settings": {"search_path": postgres_context.schema}},
    )
    engine = create_async_engine(
        postgres_context.url,
        poolclass=NullPool,
        connect_args={"server_settings": {"search_path": postgres_context.schema}},
    )
    now = datetime(2026, 10, 31, 10, 0, tzinfo=UTC)
    service = ResearchSnapshotService(database, max_members=20)
    try:
        seed_id, late_id, other_id = await _seed(database, now)
        rid, lease = await _run(database, seed_id=seed_id, now=now, as_of=now)
        at_1000 = await service.materialize_snapshot(run_id=rid, lease=lease, now=now)
        assert at_1000.member_count == 1
        # A newly inserted, now-eligible record after materialization must not
        # expand the pinned set when that run freezes.
        arrival_id = uuid4()
        async with database.session_factory() as session, session.begin():  # skipcq: PYL-E1102 -- async session factory from research port
            session.add(
                _evidence(
                    arrival_id,
                    now=now,
                    available=now - timedelta(minutes=1),
                )
            )
        pinned = await service.freeze_snapshot(run_id=rid, lease=lease, now=now)
        assert [m.evidence.evidence_id for m in pinned.members] == [seed_id]
        with pytest.raises(DomainError):
            await service.materialize_snapshot(run_id=uuid4(), lease=lease, now=now)

        # Pin before the later record becomes available to this as_of; new arrivals
        # must not change the already materialized member set during freeze.
        async with database.session_factory() as session, session.begin():  # skipcq: PYL-E1102 -- async session factory from research port
            run = await session.get(ResearchRun, rid)
            run.as_of = now + timedelta(minutes=5)
            run.updated_at = now
        # use a fresh run at 10:05 to verify the 10:02 record becomes eligible
        rid5, lease5 = await _run(
            database,
            seed_id=seed_id,
            now=now,
            as_of=now + timedelta(minutes=5),
        )
        materialized = await service.materialize_snapshot(
            run_id=rid5, lease=lease5, now=now
        )
        assert materialized.member_count == 3
        frozen = await service.freeze_snapshot(run_id=rid5, lease=lease5, now=now)
        assert len(frozen.members) == 3
        assert any(member.evidence.evidence_id == late_id for member in frozen.members)
        assert any(
            member.evidence.evidence_id == arrival_id for member in frozen.members
        )
        assert all(len(member.evidence.excerpt) <= 8 for member in frozen.members)
        again = await service.freeze_snapshot(run_id=rid5, lease=lease5, now=now)
        assert [m.evidence.evidence_id for m in again.members] == [
            m.evidence.evidence_id for m in frozen.members
        ]

        # Cross-run member borrowing is rejected by the service even though the
        # evidence itself is a valid global FK target.
        rid_other, lease_other = await _run(
            database, seed_id=seed_id, now=now, as_of=now
        )
        await service.materialize_snapshot(run_id=rid_other, lease=lease_other, now=now)
        async with database.session_factory() as session, session.begin():  # skipcq: PYL-E1102 -- async session factory from research port
            session.add(
                ResearchSnapshotMember(
                    snapshot_member_id=uuid4(),
                    run_id=rid_other,
                    evidence_id=other_id,
                    evidence_version=(
                        await session.get(ResearchEvidence, other_id)
                    ).version,
                    content_hash=(
                        await session.get(ResearchEvidence, other_id)
                    ).content_hash,
                    selected_at=now,
                )
            )
        with pytest.raises(DomainError):
            await service.read_snapshot(run_id=rid_other, lease=lease_other, now=now)

        # The composite evidence identity FK rejects an altered version/hash
        # after materialization; no schema-only assertion is used.
        drift_run, drift_lease = await _run(
            database, seed_id=seed_id, now=now, as_of=now
        )
        await service.materialize_snapshot(run_id=drift_run, lease=drift_lease, now=now)
        async with database.session_factory() as session, session.begin():  # skipcq: PYL-E1102 -- async session factory from research port
            member = await session.scalar(
                select(ResearchSnapshotMember).where(
                    ResearchSnapshotMember.run_id == drift_run
                )
            )
            member.evidence_version += "-tampered"
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()
        async with database.session_factory() as session, session.begin():  # skipcq: PYL-E1102 -- async session factory from research port
            member = await session.scalar(
                select(ResearchSnapshotMember).where(
                    ResearchSnapshotMember.run_id == drift_run
                )
            )
            member.content_hash = "9" * 64
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()

        # An unmaterialized run freezes the point-in-time selection at 10:00 only.
        freeze0 = await service.freeze_snapshot(run_id=rid, lease=lease, now=now)
        assert len(freeze0.members) == 1
        assert freeze0.members[0].evidence.evidence_id == seed_id
        # Wrong entity/seed cannot materialize, and cannot borrow another run's evidence.
        with pytest.raises(DomainError):
            wrong_id, wrong_lease = await _run(
                database, seed_id=seed_id, now=now, as_of=now, entity=OTHER_ENTITY
            )
            await service.materialize_snapshot(
                run_id=wrong_id, lease=wrong_lease, now=now
            )

        # Expiry of the immutable approved policy makes the frozen read fail closed.
        with pytest.raises(DomainError):
            await service.read_snapshot(
                run_id=rid, lease=lease, now=now + timedelta(seconds=30)
            )

        # Wrong token and expired deadline are rejected before reading or writing.
        wrong_lease = RunLease(
            run_id=rid,
            token=ExecutionToken(b"wrong"),
            lease_expires_at=now + timedelta(minutes=5),
            deadline_at=now + timedelta(minutes=10),
        )
        with pytest.raises(DomainError):
            await service.freeze_snapshot(run_id=rid, lease=wrong_lease, now=now)
        with pytest.raises(DomainError):
            await service.freeze_snapshot(
                run_id=rid, lease=lease, now=now + timedelta(minutes=11)
            )

        # The C1 transaction helper participates in, but never commits, its caller's transaction.
        rid3, _lease3 = await _run(database, seed_id=seed_id, now=now, as_of=now)
        async with database.session_factory() as session:  # skipcq: PYL-E1102 -- async session factory from research port
            transaction = await session.begin()
            run = await session.get(ResearchRun, rid3)
            await service._freeze_snapshot_in_transaction(session, run, now=now)
            count_inside = await session.scalar(
                select(func.count())
                .select_from(ResearchSnapshotMember)
                .where(ResearchSnapshotMember.run_id == rid3)
            )
            assert count_inside == 2 and transaction.is_active
            await transaction.rollback()
        async with database.session_factory() as session:  # skipcq: PYL-E1102 -- async session factory from research port
            count_after = await session.scalar(
                select(func.count())
                .select_from(ResearchSnapshotMember)
                .where(ResearchSnapshotMember.run_id == rid3)
            )
            assert count_after == 0
    finally:
        await database.dispose()
        await engine.dispose()


@pytest.mark.asyncio
async def test_freeze_rechecks_expiry_after_materialization(postgres_context):
    """Test helper test_freeze_rechecks_expiry_after_materialization."""
    await asyncio.to_thread(upgrade_head, postgres_context)
    database = create_research_database(
        postgres_context.url,
        connect_args={"server_settings": {"search_path": postgres_context.schema}},
    )
    now = datetime(2026, 10, 31, 10, 0, tzinfo=UTC)
    evidence_id = uuid4()
    service = ResearchSnapshotService(database)
    try:
        async with database.session_factory() as session, session.begin():  # skipcq: PYL-E1102 -- async session factory from research port
            session.add(
                _policy("expiring", now, expires_at=now + timedelta(seconds=20))
            )
            await session.flush()
            session.add(
                _evidence(
                    evidence_id,
                    now=now,
                    available=now - timedelta(minutes=1),
                    source="expiring",
                    excerpt="must-not-escape-on-expired-freeze",
                )
            )
        run_id, lease = await _run(database, seed_id=evidence_id, now=now, as_of=now)
        materialized = await service.materialize_snapshot(
            run_id=run_id, lease=lease, now=now
        )
        assert materialized.member_count == 1

        # The source policy is expired at the exact boundary while the worker
        # lease is still valid; freeze must not serialize the stored excerpt.
        with pytest.raises(DomainError) as error:
            await service.freeze_snapshot(
                run_id=run_id,
                lease=lease,
                now=now + timedelta(seconds=20),
            )
        assert error.value.code == "license_revoked"
        assert "must-not-escape-on-expired-freeze" not in str(error.value)

        async with database.session_factory() as session:  # skipcq: PYL-E1102 -- async session factory from research port
            run = await session.get(ResearchRun, run_id)
            count = await session.scalar(
                select(func.count())
                .select_from(ResearchSnapshotMember)
                .where(ResearchSnapshotMember.run_id == run_id)
            )
            assert run.snapshot_state == "materialized"
            assert run.snapshot_frozen_at is None
            assert count == 1
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_market_payload_round_trip_and_fail_closed(postgres_context):
    """Test helper test_market_payload_round_trip_and_fail_closed."""
    await asyncio.to_thread(upgrade_head, postgres_context)
    database = create_research_database(
        postgres_context.url,
        connect_args={"server_settings": {"search_path": postgres_context.schema}},
    )
    now = datetime(2026, 10, 31, 10, 0, tzinfo=UTC)
    service = ResearchSnapshotService(database)
    source = "market-provider"
    try:
        from app.research.models import ResearchMarketPayload

        async with database.session_factory() as session, session.begin():  # skipcq: PYL-E1102 -- async session factory from research port
            session.add(_policy(source, now))
        good_id = uuid4()
        good = _evidence(
            good_id,
            now=now,
            available=now - timedelta(minutes=2),
            source=source,
            evidence_kind="market",
            version="market-v1",
            content_hash="d" * 64,
        )
        async with database.session_factory() as session, session.begin():  # skipcq: PYL-E1102 -- async session factory from research port
            session.add(good)
            await session.flush()
            session.add(
                ResearchMarketPayload(
                    evidence_id=good_id,
                    symbol=ENTITY,
                    observed_at=good.published_at,
                    available_at=good.available_at,
                    fetched_at=good.fetched_at,
                    timezone=good.timezone,
                    currency="CNY",
                    adjustment="none",
                    fields_projection=[
                        {"name": "close", "value": "12.34", "unit": "CNY"}
                    ],
                    provider=source,
                    version=good.version,
                    is_mock=False,
                )
            )
        rid, lease = await _run(database, seed_id=good_id, now=now, as_of=now)
        await service.materialize_snapshot(run_id=rid, lease=lease, now=now)
        await service.freeze_snapshot(run_id=rid, lease=lease, now=now)
        result = await service.read_snapshot(run_id=rid, lease=lease, now=now)
        payload = result.members[0].evidence.market_payload
        assert payload is not None
        assert payload.evidence_id == good_id
        assert payload.symbol == ENTITY
        assert payload.observed_at == good.published_at
        assert payload.available_at == good.available_at
        assert payload.fetched_at == good.fetched_at
        assert payload.timezone == "Asia/Shanghai"
        assert payload.currency == "CNY"
        assert payload.adjustment == "none"
        assert [field.model_dump() for field in payload.fields] == [
            {"name": "close", "value": "12.34", "unit": "CNY"}
        ]
        assert payload.provider == source
        assert payload.version == good.version
        assert payload.is_mock is False

        # The database trigger rejects every persisted linkage mismatch.
        mismatches = {
            "provider": "different-provider",
            "version": "different-version",
            "symbol": OTHER_ENTITY,
            "available_at": good.available_at - timedelta(seconds=1),
            "fetched_at": good.fetched_at + timedelta(seconds=1),
            "observed_at": good.published_at - timedelta(seconds=1),
            "timezone": "UTC",
            "is_mock": True,
        }
        for index, (name, replacement) in enumerate(mismatches.items()):
            evidence_id = uuid4()
            row = _evidence(
                evidence_id,
                now=now,
                available=good.available_at,
                source=source,
                evidence_kind="market",
                content_hash=f"{index + 1:x}" * 64,
            )
            values = {
                "evidence_id": evidence_id,
                "symbol": ENTITY,
                "observed_at": row.published_at,
                "available_at": row.available_at,
                "fetched_at": row.fetched_at,
                "timezone": row.timezone,
                "currency": "CNY",
                "adjustment": "none",
                "fields_projection": [
                    {"name": "close", "value": "12.34", "unit": "CNY"}
                ],
                "provider": source,
                "version": row.version,
                "is_mock": False,
            }
            values[name] = replacement
            try:
                async with database.session_factory() as session, session.begin():  # skipcq: PYL-E1102 -- async session factory from research port
                    session.add(row)
                    await session.flush()
                    session.add(ResearchMarketPayload(**values))
            except IntegrityError as error:
                assert "research evidence and market payload must match" in str(error)
            else:
                case_run, case_lease = await _run(
                    database, seed_id=evidence_id, now=now, as_of=now
                )
                async with database.session_factory() as session, session.begin():  # skipcq: PYL-E1102 -- async session factory from research port
                    run = await session.get(ResearchRun, case_run)
                    run.snapshot_state = "materialized"
                    run.updated_at = now
                    await session.flush()
                    session.add(
                        ResearchSnapshotMember(
                            snapshot_member_id=uuid4(),
                            run_id=case_run,
                            evidence_id=evidence_id,
                            evidence_version=row.version,
                            content_hash=row.content_hash,
                            selected_at=now,
                        )
                    )
                    await session.flush()
                    run.snapshot_state = "frozen"
                    run.snapshot_frozen_at = now
                with pytest.raises(DomainError) as error:
                    await service.read_snapshot(
                        run_id=case_run, lease=case_lease, now=now
                    )
                assert error.value.code == "market_data_unverifiable"

        missing_id = uuid4()
        missing = _evidence(
            missing_id,
            now=now,
            available=good.available_at,
            source=source,
            evidence_kind="market",
            content_hash="9" * 64,
        )
        with pytest.raises(IntegrityError):
            async with database.session_factory() as session, session.begin():  # skipcq: PYL-E1102 -- async session factory from research port
                session.add(missing)
    finally:
        await database.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "policy_changes",
    [
        {
            "approved_at": datetime(2026, 10, 31, 10, 1, tzinfo=UTC),
            "expires_at": datetime(2026, 10, 31, 10, 2, tzinfo=UTC),
        },
        {"storage_allowed": False},
        {"model_use_allowed": False},
    ],
)
async def test_denied_policy_never_materializes_or_returns_content(
    postgres_context, policy_changes
):
    """Test helper test_denied_policy_never_materializes_or_returns_content."""
    await asyncio.to_thread(upgrade_head, postgres_context)
    database = create_research_database(
        postgres_context.url,
        connect_args={"server_settings": {"search_path": postgres_context.schema}},
    )
    now = datetime(2026, 10, 31, 10, 0, tzinfo=UTC)
    source = f"policy-{uuid4().hex}"
    evidence_id = uuid4()
    service = ResearchSnapshotService(database)
    try:
        async with database.session_factory() as session, session.begin():  # skipcq: PYL-E1102 -- async session factory from research port
            session.add(_policy(source, now, **policy_changes))
            await session.flush()
            evidence = _evidence(
                evidence_id,
                now=now,
                available=now - timedelta(minutes=1),
                source=source,
                excerpt="unauthorized-content-marker",
            )
            session.add(evidence)
        rid, lease = await _run(database, seed_id=evidence_id, now=now, as_of=now)
        with pytest.raises(DomainError) as error:
            await service.materialize_snapshot(run_id=rid, lease=lease, now=now)
        assert error.value.code == "evidence_ineligible"

        # Exercise read-time authorization against a persisted frozen membership.
        # Policies remain immutable; no UPDATE is used to simulate revocation.
        async with database.session_factory() as session, session.begin():  # skipcq: PYL-E1102 -- async session factory from research port
            run = await session.get(ResearchRun, rid)
            run.snapshot_state = "materialized"
            run.updated_at = now
            await session.flush()
            session.add(
                ResearchSnapshotMember(
                    snapshot_member_id=uuid4(),
                    run_id=rid,
                    evidence_id=evidence_id,
                    evidence_version=evidence.version,
                    content_hash=evidence.content_hash,
                    selected_at=now,
                )
            )
            await session.flush()
            run.snapshot_state = "frozen"
            run.snapshot_frozen_at = now
        with pytest.raises(DomainError) as error:
            await service.read_snapshot(run_id=rid, lease=lease, now=now)
        assert error.value.code == "license_revoked"
        assert "unauthorized-content-marker" not in str(error.value)
    finally:
        await database.dispose()
