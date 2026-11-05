"""PostgreSQL-backed S02-C1 idempotency acceptance tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from app.research.auth import ResearchAuthorizer
from app.research.contracts import StartResearchInput
from app.research.db import create_research_database
from app.research.ledger import ResearchLedger
from app.research.models import (
    ResearchOutbox,
    ResearchPrincipalQuota,
    ResearchRun,
)
from app.research.ports import ExecutorReadiness, Principal
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from backend.tests.research.postgres_fixtures import (
    IsolatedPostgres,
    create_postgres_context,
    upgrade_head,
)


@pytest.fixture
def postgres_context() -> IsolatedPostgres:
    """Test helper postgres_context."""
    return create_postgres_context()


class ReadyExecutor:
    """Test helper ReadyExecutor."""
    async def get_readiness(self, *, now):
        """Test helper get_readiness."""
        return ExecutorReadiness(
            ready=True,
            reason="test",
            checked_at=now,
            expires_at=now + timedelta(minutes=2),
        )


class SnapshotStub:
    """Test helper SnapshotStub."""
    async def materialize_snapshot(self, **kwargs):
        """Test helper materialize_snapshot."""
        raise NotImplementedError

    async def freeze_snapshot(self, **kwargs):
        """Test helper freeze_snapshot."""
        raise NotImplementedError

    async def read_snapshot(self, **kwargs):
        """Test helper read_snapshot."""
        raise NotImplementedError


def _principal(pid):
    return Principal(
        principal_id=pid,
        scopes=frozenset({"research:create", "research:read"}),
        entity_ids=frozenset({"CN.SH.600000"}),
        issuer="test",
        audience="test",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


@pytest.mark.asyncio
async def test_ten_concurrent_same_principal_requests_write_one_run(postgres_context):
    """Test helper test_ten_concurrent_same_principal_requests_write_one_run."""
    context = postgres_context
    await asyncio.to_thread(upgrade_head, context)
    engine = create_async_engine(
        context.url,
        poolclass=NullPool,
        connect_args={"server_settings": {"search_path": context.schema}},
    )
    database = create_research_database(
        context.url, connect_args={"server_settings": {"search_path": context.schema}}
    )
    now = datetime.now(UTC)
    pid = uuid4()
    principal = _principal(pid)
    # Seed a currently licensed evidence row using the isolated migrated schema.
    from app.research.models import ResearchEvidence, ResearchSourcePolicy

    eid = uuid4()
    async with database.session_factory() as s, s.begin():  # skipcq: PYL-E1102 -- async session factory from research port
        s.add(
            ResearchSourcePolicy(
                source_id="test",
                policy_version="v1",
                license_id="l",
                terms_ref="t",
                approved_at=now - timedelta(days=1),
                expires_at=now + timedelta(days=1),
                redisplay_allowed=True,
                model_use_allowed=True,
                storage_allowed=True,
                allowed_excerpt_length=1,
            )
        )
        await s.flush()
        s.add(
            ResearchEvidence(
                evidence_id=eid,
                source_id="test",
                source_url="https://example.test/a",
                content_hash="a" * 64,
                published_at=now - timedelta(minutes=5),
                fetched_at=now - timedelta(minutes=1),
                available_at=now - timedelta(minutes=1),
                timezone="UTC",
                license_scope="metadata_only",
                entity_id="CN.SH.600000",
                excerpt="",
                quality_status="verified_metadata",
                evidence_kind="event",
                version="v1",
                source_policy_version="v1",
                origin="live",
                admitted_at=now,
            )
        )
    ledger = ResearchLedger(
        database=database,
        authorizer=ResearchAuthorizer(),
        executor_registry=ReadyExecutor(),
        snapshot_service=SnapshotStub(),
        max_concurrent_runs=10,
        daily_run_limit=100,
    )
    req = StartResearchInput(
        request_id=uuid4(),
        entity_ids=["CN.SH.600000"],
        as_of=now - timedelta(seconds=30),
        seed_evidence_id=eid,
        question=None,
    )
    results = await asyncio.gather(
        *(
            ledger.create_or_reuse_run(principal=principal, request=req, now=now)
            for _ in range(10)
        )
    )
    assert len({r.run_id for r in results}) == 1
    async with database.session_factory() as s:  # skipcq: PYL-E1102 -- async session factory from research port
        assert await s.scalar(select(func.count()).select_from(ResearchRun)) == 1
        assert await s.scalar(select(func.count()).select_from(ResearchOutbox)) == 1
        quota = await s.get(ResearchPrincipalQuota, pid)
        assert quota.active_run_count == 1 and quota.daily_run_count == 1
    await database.dispose()
    await engine.dispose()


@pytest.mark.asyncio
async def test_distinct_requests_serialize_first_quota_creation(postgres_context):
    """Test helper test_distinct_requests_serialize_first_quota_creation."""
    context = postgres_context
    await asyncio.to_thread(upgrade_head, context)
    database = create_research_database(
        context.url, connect_args={"server_settings": {"search_path": context.schema}}
    )
    now, pid = datetime.now(UTC), uuid4()
    evidence_id = await _seed_evidence(database, now)
    ledger = ResearchLedger(
        database=database,
        authorizer=ResearchAuthorizer(),
        executor_registry=ReadyExecutor(),
        snapshot_service=SnapshotStub(),
        max_concurrent_runs=2,
        daily_run_limit=2,
    )
    principal = _principal(pid)
    requests = [
        StartResearchInput(
            request_id=uuid4(),
            entity_ids=["CN.SH.600000"],
            as_of=now - timedelta(seconds=30),
            seed_evidence_id=evidence_id,
            question=f"request-{index}",
        )
        for index in range(2)
    ]
    results = await asyncio.gather(
        *(
            ledger.create_or_reuse_run(principal=principal, request=req, now=now)
            for req in requests
        )
    )
    assert len({result.run_id for result in results}) == 2
    async with database.session_factory() as session:  # skipcq: PYL-E1102 -- async session factory from research port
        quota = await session.get(ResearchPrincipalQuota, pid)
        assert quota.active_run_count == 2
        assert quota.daily_run_count == 2
        assert await session.scalar(select(func.count()).select_from(ResearchRun)) == 2
        assert (
            await session.scalar(select(func.count()).select_from(ResearchOutbox)) == 2
        )
    await database.dispose()


async def _seed_evidence(database, now):
    from app.research.models import ResearchEvidence, ResearchSourcePolicy

    eid = uuid4()
    async with database.session_factory() as session, session.begin():  # skipcq: PYL-E1102 -- async session factory from research port
        session.add(
            ResearchSourcePolicy(
                source_id="test",
                policy_version="v1",
                license_id="l",
                terms_ref="t",
                approved_at=now - timedelta(days=1),
                expires_at=now + timedelta(days=1),
                redisplay_allowed=True,
                model_use_allowed=True,
                storage_allowed=True,
                allowed_excerpt_length=1,
            )
        )
        await session.flush()
        session.add(
            ResearchEvidence(
                evidence_id=eid,
                source_id="test",
                source_url="https://example.test/a",
                content_hash="a" * 64,
                published_at=now - timedelta(minutes=5),
                fetched_at=now - timedelta(minutes=1),
                available_at=now - timedelta(minutes=1),
                timezone="UTC",
                license_scope="metadata_only",
                entity_id="CN.SH.600000",
                excerpt="",
                quality_status="verified_metadata",
                evidence_kind="event",
                version="v1",
                source_policy_version="v1",
                origin="live",
                admitted_at=now,
            )
        )
    return eid


@pytest.mark.asyncio
async def test_hash_conflict_and_principal_isolation(postgres_context):
    """Test helper test_hash_conflict_and_principal_isolation."""
    from app.research.errors import DomainError
    from app.research.models import ResearchAudit
    from sqlalchemy import func

    context = postgres_context
    await asyncio.to_thread(upgrade_head, context)
    database = create_research_database(
        context.url, connect_args={"server_settings": {"search_path": context.schema}}
    )
    now, owner_id, other_id = datetime.now(UTC), uuid4(), uuid4()
    owner, other = _principal(owner_id), _principal(other_id)
    eid = await _seed_evidence(database, now)
    ledger = ResearchLedger(
        database=database,
        authorizer=ResearchAuthorizer(),
        executor_registry=ReadyExecutor(),
        snapshot_service=SnapshotStub(),
        max_concurrent_runs=10,
        daily_run_limit=100,
    )
    request = StartResearchInput(
        request_id=uuid4(),
        entity_ids=["CN.SH.600000"],
        as_of=now - timedelta(seconds=30),
        seed_evidence_id=eid,
        question="alpha",
    )
    created = await ledger.create_or_reuse_run(
        principal=owner, request=request, now=now
    )
    for altered in (
        request.model_copy(update={"question": "different"}),
        request.model_copy(update={"as_of": request.as_of - timedelta(seconds=1)}),
        request.model_copy(update={"seed_evidence_id": uuid4()}),
    ):
        with pytest.raises(DomainError) as error:
            await ledger.create_or_reuse_run(principal=owner, request=altered, now=now)
        assert error.value.code == "request_conflict"
    with pytest.raises(DomainError):
        await ledger.get_run(
            principal=other,
            request=__import__(
                "app.research.contracts", fromlist=["GetRunInput"]
            ).GetRunInput(run_id=created.run_id),
            now=now,
        )
    other_result = await ledger.create_or_reuse_run(
        principal=other, request=request, now=now
    )
    assert other_result.run_id != created.run_id
    async with database.session_factory() as session:  # skipcq: PYL-E1102 -- async session factory from research port
        assert await session.scalar(select(func.count()).select_from(ResearchRun)) == 2
        assert (
            await session.scalar(select(func.count()).select_from(ResearchOutbox)) == 2
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ResearchAudit)
                .where(ResearchAudit.action == "run_created")
            )
            == 2
        )
    await database.dispose()


@pytest.mark.asyncio
async def test_unready_executor_writes_no_ledger_rows(postgres_context):
    """Test helper test_unready_executor_writes_no_ledger_rows."""
    from app.research.errors import DomainError

    class Unready:
        """Test helper Unready."""
        async def get_readiness(self, *, now):
            """Test helper get_readiness."""
            return ExecutorReadiness(
                ready=False,
                reason="offline",
                checked_at=now,
                expires_at=now + timedelta(minutes=1),
            )

    context = postgres_context
    await asyncio.to_thread(upgrade_head, context)
    database = create_research_database(
        context.url, connect_args={"server_settings": {"search_path": context.schema}}
    )
    now = datetime.now(UTC)
    eid = await _seed_evidence(database, now)
    ledger = ResearchLedger(
        database=database,
        authorizer=ResearchAuthorizer(),
        executor_registry=Unready(),
        snapshot_service=SnapshotStub(),
    )
    with pytest.raises(DomainError) as error:
        await ledger.create_or_reuse_run(
            principal=_principal(uuid4()),
            request=StartResearchInput(
                request_id=uuid4(),
                entity_ids=["CN.SH.600000"],
                as_of=now - timedelta(seconds=30),
                seed_evidence_id=eid,
                question=None,
            ),
            now=now,
        )
    assert error.value.code == "execution_unavailable"
    async with database.session_factory() as session:  # skipcq: PYL-E1102 -- async session factory from research port
        assert await session.scalar(select(func.count()).select_from(ResearchRun)) == 0
        assert (
            await session.scalar(select(func.count()).select_from(ResearchOutbox)) == 0
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(ResearchPrincipalQuota)
            )
            == 0
        )
    await database.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("questions", "expect_conflict", "deny_fallback_read"),
    [
        ("same|same", False, False),
        ("first|second", True, False),
        ("same|same", False, True),
    ],
)
async def test_unique_request_race_uses_integrity_fallback(
    postgres_context, questions, expect_conflict, deny_fallback_read
):
    """Test helper test_unique_request_race_uses_integrity_fallback."""
    from app.research.errors import DomainError

    class ReadRevokedAuthorizer:
        """Deny the fallback's read recheck after allowing initial create calls."""

        def authorize_resource(self, **kwargs):
            """Test helper authorize_resource."""
            if kwargs["required_scope"] == "research:read":
                raise DomainError(
                    code="resource_not_found_or_denied",
                    safe_message="resource was not found or access is denied",
                    retryable=False,
                )
            return ResearchAuthorizer().authorize_resource(**kwargs)

    class BarrierReadyExecutor:
        """Hold both transactions after they observe no existing request."""

        def __init__(self):
            """Test helper __init__."""
            self._lock = asyncio.Lock()
            self._ready = asyncio.Event()
            self._calls = 0

        async def get_readiness(self, *, now):
            """Test helper get_readiness."""
            async with self._lock:
                self._calls += 1
                if self._calls == 2:
                    self._ready.set()
            await asyncio.wait_for(self._ready.wait(), timeout=10)
            return ExecutorReadiness(
                ready=True,
                reason="barrier-test",
                checked_at=now,
                expires_at=now + timedelta(minutes=2),
            )

    context = postgres_context
    await asyncio.to_thread(upgrade_head, context)
    database = create_research_database(
        context.url, connect_args={"server_settings": {"search_path": context.schema}}
    )
    now, principal_id, request_id = datetime.now(UTC), uuid4(), uuid4()
    principal = _principal(principal_id)
    evidence_id = await _seed_evidence(database, now)
    ledger = ResearchLedger(
        database=database,
        authorizer=ReadRevokedAuthorizer()
        if deny_fallback_read
        else ResearchAuthorizer(),
        executor_registry=BarrierReadyExecutor(),
        snapshot_service=SnapshotStub(),
        max_concurrent_runs=10,
        daily_run_limit=100,
    )
    safe_view_calls = []
    original_safe_view = ledger._safe_run_view

    async def count_safe_view(session, run, caller, checked_at):
        """Record when the committed-row fallback reauthorizes its result."""
        safe_view_calls.append(run.run_id)
        return await original_safe_view(session, run, caller, checked_at)

    ledger._safe_run_view = count_safe_view
    question_a, question_b = questions.split("|")
    requests = [
        StartResearchInput(
            request_id=request_id,
            entity_ids=["CN.SH.600000"],
            as_of=now - timedelta(seconds=30),
            seed_evidence_id=evidence_id,
            question=question,
        )
        for question in (question_a, question_b)
    ]

    async def create(request):
        """Test helper create."""
        try:
            return await ledger.create_or_reuse_run(
                principal=principal, request=request, now=now
            )
        except DomainError as error:
            return error

    try:
        results = await asyncio.wait_for(
            asyncio.gather(*(create(request) for request in requests)), timeout=15
        )
        errors = [result for result in results if isinstance(result, DomainError)]
        runs = [result for result in results if not isinstance(result, DomainError)]
        if expect_conflict:
            assert len(runs) == 1
            assert len(errors) == 1 and errors[0].code == "request_conflict"
            assert safe_view_calls == []
        elif deny_fallback_read:
            assert len(runs) == 1
            assert len(errors) == 1
            assert errors[0].code == "resource_not_found_or_denied"
            assert len(safe_view_calls) == 1
        else:
            assert len(runs) == 2 and not errors
            assert runs[0].run_id == runs[1].run_id
            assert safe_view_calls == [runs[0].run_id]

        async with database.session_factory() as session:  # skipcq: PYL-E1102 -- async session factory from research port
            persisted = (
                await session.scalars(
                    select(ResearchRun).where(ResearchRun.request_id == request_id)
                )
            ).all()
            assert len(persisted) == 1
            assert (
                await session.scalar(select(func.count()).select_from(ResearchOutbox))
                == 1
            )
            quota = await session.get(ResearchPrincipalQuota, principal_id)
            assert quota.active_run_count == 1
            assert quota.daily_run_count == 1
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_existing_run_retry_works_when_executor_down_and_quota_full(
    postgres_context,
):
    """Test helper test_existing_run_retry_works_when_executor_down_and_quota_full."""
    from app.research.errors import DomainError

    class ToggleExecutor:
        """Allow creation once, then simulate an unavailable worker."""

        ready = True

        async def get_readiness(self, *, now):
            """Test helper get_readiness."""
            return ExecutorReadiness(
                ready=self.ready,
                reason="test-ready" if self.ready else "offline",
                checked_at=now,
                expires_at=now + timedelta(minutes=1),
            )

    context = postgres_context
    await asyncio.to_thread(upgrade_head, context)
    database = create_research_database(
        context.url, connect_args={"server_settings": {"search_path": context.schema}}
    )
    now, principal_id = datetime.now(UTC), uuid4()
    principal = _principal(principal_id)
    evidence_id = await _seed_evidence(database, now)
    executor = ToggleExecutor()
    ledger = ResearchLedger(
        database=database,
        authorizer=ResearchAuthorizer(),
        executor_registry=executor,
        snapshot_service=SnapshotStub(),
        max_concurrent_runs=1,
        daily_run_limit=1,
    )
    request = StartResearchInput(
        request_id=uuid4(),
        entity_ids=["CN.SH.600000"],
        as_of=now - timedelta(seconds=30),
        seed_evidence_id=evidence_id,
        question="retry the existing run",
    )
    try:
        created = await ledger.create_or_reuse_run(
            principal=principal, request=request, now=now
        )
        executor.ready = False
        retried = await ledger.create_or_reuse_run(
            principal=principal, request=request, now=now
        )
        assert retried.run_id == created.run_id

        with pytest.raises(DomainError) as unavailable:
            await ledger.create_or_reuse_run(
                principal=principal,
                request=request.model_copy(update={"request_id": uuid4()}),
                now=now,
            )
        assert unavailable.value.code == "execution_unavailable"
        async with database.session_factory() as session:  # skipcq: PYL-E1102 -- async session factory from research port
            quota = await session.get(ResearchPrincipalQuota, principal_id)
            assert quota.active_run_count == 1
            assert quota.daily_run_count == 1
            assert (
                await session.scalar(select(func.count()).select_from(ResearchRun)) == 1
            )
            assert (
                await session.scalar(select(func.count()).select_from(ResearchOutbox))
                == 1
            )
    finally:
        await database.dispose()
