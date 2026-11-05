"""PostgreSQL-backed S02-C1 transaction and run-state tests."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from app.research.auth import ResearchAuthorizer
from app.research.db import create_research_database
from app.research.errors import DomainError
from app.research.ledger import ResearchLedger
from app.research.models import (
    ResearchBrief,
    ResearchBriefCitation,
    ResearchEvidence,
    ResearchMarketPayload,
    ResearchOutbox,
    ResearchPrincipalQuota,
    ResearchRun,
    ResearchRunEvent,
    ResearchSnapshotMember,
    ResearchSourcePolicy,
    ResearchWorkerHeartbeat,
)
from app.research.ports import (
    ApprovedBrief,
    DispatchTask,
    ExecutorReadiness,
    Principal,
    RunFinishRequest,
    StepEvent,
    WorkerIdentity,
)
from app.research.snapshot import ResearchSnapshotService
from sqlalchemy import func, select

from backend.tests.research.postgres_fixtures import (
    IsolatedPostgres,
    create_postgres_context,
    upgrade_head,
)


@pytest.fixture
def postgres_context() -> IsolatedPostgres:
    """Test helper postgres_context."""
    return create_postgres_context()


class _ReadyExecutor:
    async def get_readiness(self, *, now):
        """Test helper get_readiness."""
        return ExecutorReadiness(
            ready=True,
            reason="test",
            checked_at=now,
            expires_at=now + timedelta(minutes=2),
        )


async def _setup(
    context: IsolatedPostgres,
    *,
    suffix: str = "",
    principal_id=None,
    excerpt: str = "test",
    allowed_excerpt_length: int = 80,
    policy_lifetime: timedelta = timedelta(days=1),
):
    """Create a production ledger and a legitimate queued run in isolated PG."""
    await asyncio.to_thread(upgrade_head, context)
    database = create_research_database(
        context.url, connect_args={"server_settings": {"search_path": context.schema}}
    )
    now = datetime.now(UTC)
    pid, run_id, request_id, evidence_id = (
        principal_id or uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    source_id = "test-source" + suffix
    worker = WorkerIdentity("worker-c1" + suffix, "research", "research-v1.1")
    principal = Principal(
        principal_id=pid,
        scopes=frozenset({"research:create", "research:read"}),
        entity_ids=frozenset({"CN.SH.600000"}),
        issuer="test",
        audience="test",
        expires_at=now + timedelta(hours=1),
    )
    async with database.session_factory() as session, session.begin():  # skipcq: PYL-E1102 -- async session factory from research port
        session.add(
            ResearchSourcePolicy(
                source_id=source_id,
                policy_version="v1",
                license_id="license",
                terms_ref="terms",
                approved_at=now - timedelta(days=1),
                expires_at=now + policy_lifetime,
                redisplay_allowed=True,
                model_use_allowed=True,
                storage_allowed=True,
                allowed_excerpt_length=allowed_excerpt_length,
            )
        )
        await session.flush()
        session.add(
            ResearchEvidence(
                evidence_id=evidence_id,
                source_id=source_id,
                source_url="https://example.test/evidence",
                content_hash="a" * 64,
                published_at=now - timedelta(minutes=5),
                fetched_at=now - timedelta(minutes=1),
                available_at=now - timedelta(minutes=1),
                timezone="UTC",
                license_scope="metadata_only",
                entity_id="CN.SH.600000",
                excerpt=excerpt,
                quality_status="verified_metadata",
                evidence_kind="event",
                version="v1",
                source_policy_version="v1",
                origin="live",
                admitted_at=now,
            )
        )
        session.add(
            ResearchRun(
                run_id=run_id,
                request_id=request_id,
                principal_id=pid,
                entity_id="CN.SH.600000",
                seed_evidence_id=evidence_id,
                request_hash="b" * 64,
                as_of=now - timedelta(seconds=30),
                status="queued",
                snapshot_state="none",
                policy_version="research-v1.1",
                prompt_version="research-v1.1",
                created_at=now,
                updated_at=now,
            )
        )
        await session.flush()
        rows = [
            ResearchOutbox(
                outbox_id=uuid4(),
                run_id=run_id,
                dispatch_id="dispatch-c1",
                contract_version="research-v1.1",
                delivery_status="pending",
                available_at=now,
                created_at=now,
            ),
            ResearchWorkerHeartbeat(
                worker_id=worker.worker_id,
                queue_name=worker.queue_name,
                contract_version=worker.contract_version,
                worker_status="active",
                heartbeat_at=now,
                expires_at=now + timedelta(minutes=2),
            ),
        ]
        if await session.get(ResearchPrincipalQuota, pid) is None:
            rows.append(
                ResearchPrincipalQuota(
                    principal_id=pid,
                    max_concurrent_runs=3,
                    active_run_count=1,
                    daily_run_limit=20,
                    daily_run_count=1,
                    window_started_at=now,
                    updated_at=now,
                )
            )
        else:
            quota = await session.get(ResearchPrincipalQuota, pid)
            quota.active_run_count += 1
            quota.daily_run_count += 1
            quota.updated_at = now
        session.add_all(rows)
    snapshots = ResearchSnapshotService(database)
    ledger = ResearchLedger(
        database=database,
        authorizer=ResearchAuthorizer(),
        executor_registry=_ReadyExecutor(),
        snapshot_service=snapshots,
        lease_duration=timedelta(seconds=30),
        worker_heartbeat_ttl=timedelta(minutes=2),
    )
    task = DispatchTask(run_id, "dispatch-c1", "research-v1.1")
    return database, ledger, now, pid, run_id, evidence_id, principal, worker, task


async def _claim(ledger, now, worker, task):
    lease = await ledger.claim_run(task=task, worker=worker, now=now)
    assert lease is not None
    return lease


@pytest.mark.asyncio
async def test_dispatch_claim_lease_heartbeat_and_fence(postgres_context):
    """Test helper test_dispatch_claim_lease_heartbeat_and_fence."""
    database, ledger, now, _, run_id, _, principal, worker, task = await _setup(
        postgres_context
    )
    try:
        lease = await _claim(ledger, now, worker, task)
        assert lease.run_id == run_id
        assert (
            await ledger.claim_run(
                task=task, worker=worker, now=now + timedelta(seconds=1)
            )
            is None
        )
        from app.research.errors import DomainError

        with pytest.raises(DomainError) as wrong_worker:
            await ledger.heartbeat_run(
                run_id=run_id,
                lease=lease,
                worker=WorkerIdentity(
                    "other", worker.queue_name, worker.contract_version
                ),
                now=now + timedelta(seconds=2),
            )
        assert wrong_worker.value.code == "execution_fenced"
        with pytest.raises(DomainError) as wrong_token:
            await ledger.heartbeat_run(
                run_id=run_id,
                lease=lease.__class__(
                    run_id,
                    type(lease.token)(b"x" * 32),
                    lease.lease_expires_at,
                    lease.deadline_at,
                ),
                worker=worker,
                now=now + timedelta(seconds=2),
            )
        assert wrong_token.value.code == "execution_fenced"
        renewed = await ledger.heartbeat_run(
            run_id=run_id, lease=lease, worker=worker, now=now + timedelta(seconds=2)
        )
        assert renewed.lease_expires_at > lease.lease_expires_at
        with pytest.raises(DomainError) as expired:
            await ledger.heartbeat_run(
                run_id=run_id,
                lease=renewed,
                worker=worker,
                now=renewed.lease_expires_at,
            )
        assert expired.value.code == "lease_expired"
        public = await ledger.get_run(
            principal=principal,
            request=__import__(
                "app.research.contracts", fromlist=["GetRunInput"]
            ).GetRunInput(run_id=run_id),
            now=now,
        )
        assert "token" not in json.dumps(public.model_dump(mode="json")).lower()
        async with database.session_factory() as session:  # skipcq: PYL-E1102 -- async session factory from research port
            row = await session.get(ResearchRun, run_id)
            assert row.execution_token_hash == lease.token.fingerprint()
            assert lease.token._secret.decode(errors="ignore") not in json.dumps(
                row.__dict__, default=str
            )
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_event_sequence_and_full_transaction_rollback(postgres_context):
    """Test helper test_event_sequence_and_full_transaction_rollback."""
    database, ledger, now, pid, run_id, _, principal, worker, task = await _setup(
        postgres_context
    )
    try:
        lease = await _claim(ledger, now, worker, task)
        from app.research.contracts import StepStartedEventPayloadV1

        payload = StepStartedEventPayloadV1(step_name="collect")
        events = await asyncio.gather(
            *[
                ledger.append_step_event(
                    run_id=run_id,
                    lease=lease,
                    event=StepEvent("step_started", payload),
                    now=now + timedelta(seconds=i + 1),
                )
                for i in range(6)
            ]
        )
        assert sorted(event.seq for event in events) == list(range(2, 8))
        first = await ledger.read_events(
            principal=principal, run_id=run_id, after_event_id=None, limit=3, now=now
        )
        assert [event.seq for event in first.events] == [1, 2, 3]
        assert first.next_event_id == first.events[-1].event_id
        second = await ledger.read_events(
            principal=principal,
            run_id=run_id,
            after_event_id=first.next_event_id,
            limit=3,
            now=now,
        )
        assert [event.seq for event in second.events] == [4, 5, 6]
        assert second.next_event_id == second.events[-1].event_id
        (
            foreign_db,
            foreign_ledger,
            foreign_now,
            _,
            foreign_run,
            _,
            _,
            foreign_worker,
            foreign_task,
        ) = await _setup(postgres_context, suffix="-cursor", principal_id=pid)
        try:
            await _claim(foreign_ledger, foreign_now, foreign_worker, foreign_task)
            foreign_page = await foreign_ledger.read_events(
                principal=principal,
                run_id=foreign_run,
                after_event_id=None,
                limit=1,
                now=foreign_now,
            )
            with pytest.raises(DomainError) as foreign_cursor:
                await ledger.read_events(
                    principal=principal,
                    run_id=run_id,
                    after_event_id=foreign_page.events[0].event_id,
                    limit=3,
                    now=now,
                )
            assert foreign_cursor.value.code == "event_cursor_invalid"
        finally:
            await foreign_db.dispose()
        with pytest.raises(DomainError) as bad_cursor:
            await ledger.read_events(
                principal=principal,
                run_id=run_id,
                after_event_id=uuid4(),
                limit=3,
                now=now,
            )
        assert bad_cursor.value.code == "event_cursor_invalid"
        transition = await ledger.finish_run(
            run_id=run_id,
            lease=lease,
            finish=RunFinishRequest(
                status="failed", code="worker_error", cancellation_reason=None
            ),
            now=now + timedelta(seconds=10),
        )
        assert transition.status == "failed"
        with pytest.raises(DomainError) as reused:
            await ledger.append_step_event(
                run_id=run_id,
                lease=lease,
                event=StepEvent("step_started", payload),
                now=now + timedelta(seconds=11),
            )
        assert reused.value.code == "terminal_state"
        async with database.session_factory() as session:  # skipcq: PYL-E1102 -- async session factory from research port
            run = await session.get(ResearchRun, run_id)
            quota = await session.get(ResearchPrincipalQuota, run.principal_id)
            assert run.execution_token_hash is None and quota.active_run_count == 1
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(ResearchRunEvent)
                    .where(ResearchRunEvent.run_id == run_id)
                )
                == 8
            )
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_terminal_publish_and_reap_race_is_atomic(postgres_context):
    """Test helper test_terminal_publish_and_reap_race_is_atomic."""
    database, ledger, now, pid, run_id, _evidence_id, _, worker, task = await _setup(
        postgres_context
    )
    try:
        lease = await _claim(ledger, now, worker, task)
        # Race a valid worker terminal finish against a reaper observing the same
        # lease after expiry. Row locking must make one winner and charge quota once.
        expire_time = lease.lease_expires_at

        async def finish():
            """Test helper finish."""
            try:
                return await ledger.finish_run(
                    run_id=run_id,
                    lease=lease,
                    finish=RunFinishRequest(
                        status="failed", code="worker_done", cancellation_reason=None
                    ),
                    now=expire_time - timedelta(microseconds=1),
                )
            except DomainError as exc:
                return exc.code

        async def reap():
            """Test helper reap."""
            return await ledger.reap_stale(
                now=expire_time + timedelta(seconds=1), limit=10
            )

        results = await asyncio.gather(finish(), reap())
        finish_won = not isinstance(results[0], str)
        reaper_won = any(item.run_id == run_id for item in results[1])
        assert finish_won != reaper_won
        async with database.session_factory() as session:  # skipcq: PYL-E1102 -- async session factory from research port
            run = await session.get(ResearchRun, run_id)
            quota = await session.get(ResearchPrincipalQuota, pid)
            event_rows = (
                await session.scalars(
                    select(ResearchRunEvent)
                    .where(ResearchRunEvent.run_id == run_id)
                    .order_by(ResearchRunEvent.seq)
                )
            ).all()
            assert run.status in {"failed"}
            assert run.execution_token_hash is None
            assert quota.active_run_count == 0
            assert [event.seq for event in event_rows] == list(
                range(1, len(event_rows) + 1)
            )
            assert run.status == "failed"
            assert run.error_code == ("worker_done" if finish_won else "worker_lost")
        # Separate real-PG publication behavior: cite an actual frozen member and
        # verify Brief/citation persistence, terminal fencing, and quota release.
        (
            database2,
            ledger2,
            now2,
            pid2,
            run2,
            evidence2,
            _,
            worker2,
            task2,
        ) = await _setup(postgres_context, suffix="-publish")
        try:
            lease2 = await _claim(ledger2, now2, worker2, task2)
            async with database2.session_factory() as session, session.begin():  # skipcq: PYL-E1102 -- async session factory from research port
                session.add(
                    ResearchSourcePolicy(
                        source_id="test-source-publish",
                        policy_version="v2",
                        license_id="denied-v2",
                        terms_ref="terms-v2",
                        approved_at=now2 - timedelta(days=1),
                        expires_at=now2 + timedelta(days=1),
                        redisplay_allowed=True,
                        model_use_allowed=True,
                        storage_allowed=False,
                        allowed_excerpt_length=0,
                    )
                )
            from app.research.contracts import ClaimV1, ResearchBriefV1

            brief = ResearchBriefV1(
                run_id=run2,
                as_of=now2 - timedelta(seconds=30),
                claims=[
                    ClaimV1(
                        claim_id=uuid4(),
                        text="A supported observation",
                        kind="fact",
                        evidence_ids=[evidence2],
                        as_of=now2 - timedelta(seconds=30),
                        valid_until=None,
                        confidence=0.9,
                    )
                ],
                counterarguments=[],
                unknowns=[],
                limitations=[],
                model_trace=[],
            )
            approved = ApprovedBrief(
                brief=brief,
                model_profile_id="test-profile",
                policy_version="research-v1.1",
                evaluation_digest="c" * 64,
                approved_at=now2,
            )
            published = await ledger2.publish_brief(
                run_id=run2,
                lease=lease2,
                approved_brief=approved,
                now=now2 + timedelta(seconds=1),
            )
            assert published.status == "completed"
            with pytest.raises(DomainError) as stale:
                await ledger2.finish_run(
                    run_id=run2,
                    lease=lease2,
                    finish=RunFinishRequest(
                        status="failed", code="late", cancellation_reason=None
                    ),
                    now=now2 + timedelta(seconds=2),
                )
            assert stale.value.code == "terminal_state"
            async with database2.session_factory() as session:  # skipcq: PYL-E1102 -- async session factory from research port
                row = await session.get(ResearchRun, run2)
                quota = await session.get(ResearchPrincipalQuota, pid2)
                assert row.execution_token_hash is None and row.status == "completed"
                assert quota.active_run_count == 0
                assert await session.get(ResearchBrief, run2) is not None
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(ResearchBriefCitation)
                        .where(ResearchBriefCitation.run_id == run2)
                    )
                    == 1
                )
                members = (
                    await session.scalars(
                        select(ResearchSnapshotMember.evidence_id).where(
                            ResearchSnapshotMember.run_id == run2
                        )
                    )
                ).all()
                assert evidence2 in members
        finally:
            await database2.dispose()
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_expired_exact_policy_redacts_completed_brief_on_read_and_retry(
    postgres_context,
):
    """Test helper test_expired_exact_policy_redacts_completed_brief_on_read_and_retry."""
    from hashlib import sha256

    from app.research.contracts import (
        ClaimV1,
        GetRunInput,
        ResearchBriefV1,
        StartResearchInput,
    )

    database, ledger, now, _, run_id, evidence_id, principal, _, _ = await _setup(
        postgres_context, suffix="-expired-brief"
    )
    try:
        later = now + timedelta(days=2)
        # Preserve principal validity while reading after the immutable policy expiry.
        principal = Principal(
            principal_id=principal.principal_id,
            scopes=principal.scopes,
            entity_ids=principal.entity_ids,
            issuer=principal.issuer,
            audience=principal.audience,
            expires_at=later + timedelta(hours=1),
        )
        brief = ResearchBriefV1(
            run_id=run_id,
            as_of=now - timedelta(seconds=30),
            claims=[
                ClaimV1(
                    claim_id=uuid4(),
                    text="Supported",
                    kind="fact",
                    evidence_ids=[evidence_id],
                    as_of=now - timedelta(seconds=30),
                    valid_until=None,
                    confidence=0.9,
                )
            ],
            counterarguments=[],
            unknowns=[],
            limitations=[],
            model_trace=[],
        )
        async with database.session_factory() as session, session.begin():  # skipcq: PYL-E1102 -- async session factory from research port
            run = await session.get(ResearchRun, run_id)
            run.snapshot_state = "materialized"
            run.updated_at = now
            await session.flush()
            session.add(
                ResearchSnapshotMember(
                    snapshot_member_id=uuid4(),
                    run_id=run_id,
                    evidence_id=evidence_id,
                    evidence_version="v1",
                    content_hash="a" * 64,
                    selected_at=now,
                )
            )
            await session.flush()
            run.status = "completed"
            run.snapshot_state = "frozen"
            run.snapshot_frozen_at = now
            session.add(
                ResearchBrief(
                    run_id=run_id,
                    as_of=brief.as_of,
                    brief_projection=brief.model_dump(mode="json"),
                    model_profile_id="test-profile",
                    policy_version="research-v1.1",
                    evaluation_digest="c" * 64,
                    result_ref="expired-brief-result",
                    approved_at=now,
                )
            )
            session.add(
                ResearchBriefCitation(
                    citation_id=uuid4(),
                    run_id=run_id,
                    claim_id=brief.claims[0].claim_id,
                    evidence_id=evidence_id,
                    created_at=now,
                )
            )
        async with database.session_factory() as session:  # skipcq: PYL-E1102 -- async session factory from research port
            policy = await session.get(
                ResearchSourcePolicy, ("test-source-expired-brief", "v1")
            )
            assert policy.expires_at < later
        read = await ledger.get_run(
            principal=principal, request=GetRunInput(run_id=run_id), now=later
        )
        request = StartResearchInput(
            request_id=uuid4(),
            entity_ids=["CN.SH.600000"],
            as_of=now - timedelta(seconds=30),
            seed_evidence_id=evidence_id,
            question="same request",
        )
        normalized = {
            "entity_id": "CN.SH.600000",
            "seed_evidence_id": str(evidence_id),
            "as_of": request.as_of.isoformat(),
            "question": "same request",
            "schema": "research-v1.1",
            "policy": "research-v1.1",
        }
        async with database.session_factory() as session, session.begin():  # skipcq: PYL-E1102 -- async session factory from research port
            run = await session.get(ResearchRun, run_id)
            run.request_id = request.request_id
            run.request_hash = sha256(
                __import__("json")
                .dumps(normalized, sort_keys=True, separators=(",", ":"))
                .encode()
            ).hexdigest()
        retry = await ledger.create_or_reuse_run(
            principal=principal, request=request, now=later
        )
        for result in (read, retry):
            assert result.run_id == run_id
            assert result.status == "completed"
            assert result.brief is None
            assert result.error_code == "license_revoked"
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_evidence_excerpt_and_market_reads_obey_current_policy(postgres_context):
    """Test helper test_evidence_excerpt_and_market_reads_obey_current_policy."""
    from app.research.contracts import (
        GetEvidenceInput,
        GetMarketSnapshotInput,
        SearchArticlesInput,
    )

    database, ledger, now, _, run_id, evidence_id, principal, _, _ = await _setup(
        postgres_context,
        suffix="-read-policy",
        excerpt="x" * 120,
        allowed_excerpt_length=7,
    )
    try:
        later = now + timedelta(days=2)
        principal = Principal(
            principal_id=principal.principal_id,
            scopes=principal.scopes,
            entity_ids=principal.entity_ids,
            issuer=principal.issuer,
            audience=principal.audience,
            expires_at=later + timedelta(hours=1),
        )
        async with database.session_factory() as session, session.begin():  # skipcq: PYL-E1102 -- async session factory from research port
            run = await session.get(ResearchRun, run_id)
            run.snapshot_state = "materialized"
            run.updated_at = now
            await session.flush()
            session.add(
                ResearchSnapshotMember(
                    snapshot_member_id=uuid4(),
                    run_id=run_id,
                    evidence_id=evidence_id,
                    evidence_version="v1",
                    content_hash="a" * 64,
                    selected_at=now,
                )
            )
            await session.flush()
        result = await ledger.search_articles(
            principal=principal,
            request=SearchArticlesInput(
                query="x", entity_ids=["CN.SH.600000"], as_of=now, limit=10
            ),
            now=now,
        )
        assert (
            next(
                item for item in result.articles if item.evidence_id == evidence_id
            ).excerpt
            == "x" * 7
        )
        evidence = await ledger.read_evidence(
            principal=principal,
            request=GetEvidenceInput(run_id=run_id, evidence_id=evidence_id),
            now=now,
        )
        assert evidence.excerpt == "x" * 7
        # Immutable policies are never changed after insert: construct each denied
        # policy with its final storage/approval/expiry values in the initial seed.
        denied = [
            ("deny-storage", False, now - timedelta(days=1), now + timedelta(days=1)),
            ("deny-approval", True, now + timedelta(days=1), now + timedelta(days=2)),
            ("deny-expiry", True, now - timedelta(days=1), now - timedelta(seconds=1)),
        ]
        denied_ids = []
        async with database.session_factory() as session, session.begin():  # skipcq: PYL-E1102 -- async session factory from research port
            for source_id, storage, approved_at, expires_at in denied:
                eid = uuid4()
                read_at = later if source_id == "deny-expiry" else now
                denied_ids.append((source_id, eid, read_at))
                session.add(
                    ResearchSourcePolicy(
                        source_id=source_id,
                        policy_version="v1",
                        license_id="l",
                        terms_ref="t",
                        approved_at=approved_at,
                        expires_at=expires_at,
                        redisplay_allowed=True,
                        model_use_allowed=True,
                        storage_allowed=storage,
                        allowed_excerpt_length=5,
                    )
                )
                await session.flush()
                session.add(
                    ResearchEvidence(
                        evidence_id=eid,
                        source_id=source_id,
                        source_url="https://example.test/denied",
                        content_hash=(
                            "d"
                            if source_id == "deny-storage"
                            else "e"
                            if source_id == "deny-approval"
                            else "f"
                        )
                        * 64,
                        published_at=now - timedelta(minutes=5),
                        fetched_at=now,
                        available_at=now - timedelta(minutes=1),
                        timezone="UTC",
                        license_scope="metadata_only",
                        entity_id="CN.SH.600000",
                        excerpt="secret",
                        quality_status="verified_metadata",
                        evidence_kind="event",
                        version="v1",
                        source_policy_version="v1",
                        origin="live",
                        admitted_at=now,
                    )
                )
                await session.flush()
                session.add(
                    ResearchSnapshotMember(
                        snapshot_member_id=uuid4(),
                        run_id=run_id,
                        evidence_id=eid,
                        evidence_version="v1",
                        content_hash=(
                            "d"
                            if source_id == "deny-storage"
                            else "e"
                            if source_id == "deny-approval"
                            else "f"
                        )
                        * 64,
                        selected_at=now,
                    )
                )
            market_id = uuid4()
            session.add(
                ResearchSourcePolicy(
                    source_id="deny-market-expiry",
                    policy_version="v1",
                    license_id="l",
                    terms_ref="t",
                    approved_at=now - timedelta(days=1),
                    expires_at=now - timedelta(seconds=1),
                    redisplay_allowed=True,
                    model_use_allowed=True,
                    storage_allowed=True,
                    allowed_excerpt_length=5,
                )
            )
            await session.flush()
            session.add(
                ResearchEvidence(
                    evidence_id=market_id,
                    source_id="deny-market-expiry",
                    source_url="https://example.test/market",
                    content_hash="9" * 64,
                    published_at=now - timedelta(minutes=5),
                    fetched_at=now,
                    available_at=now - timedelta(minutes=1),
                    timezone="UTC",
                    license_scope="metadata_only",
                    entity_id="CN.SH.600000",
                    excerpt="market",
                    quality_status="verified_metadata",
                    evidence_kind="market",
                    version="v1",
                    source_policy_version="v1",
                    origin="live",
                    admitted_at=now,
                )
            )
            session.add(
                ResearchMarketPayload(
                    evidence_id=market_id,
                    symbol="600000",
                    observed_at=now,
                    available_at=now - timedelta(minutes=1),
                    fetched_at=now,
                    timezone="UTC",
                    currency="CNY",
                    adjustment="none",
                    fields_projection={"close": 1},
                    provider="test",
                    version="v1",
                    is_mock=True,
                )
            )
            session.add(
                ResearchSnapshotMember(
                    snapshot_member_id=uuid4(),
                    run_id=run_id,
                    evidence_id=market_id,
                    evidence_version="v1",
                    content_hash="9" * 64,
                    selected_at=now,
                )
            )
            await session.flush()
            run = await session.get(ResearchRun, run_id)
            run.snapshot_state = "frozen"
            run.snapshot_frozen_at = now
        for _, eid, read_at in denied_ids:
            # Membership is required for scoped evidence reads; use the valid run's frozen member relation.
            with pytest.raises(DomainError) as denied_read:
                await ledger.read_evidence(
                    principal=principal,
                    request=GetEvidenceInput(run_id=run_id, evidence_id=eid),
                    now=read_at,
                )
            assert denied_read.value.code == "license_revoked"
            market = await ledger.get_market_snapshot(
                principal=principal,
                request=GetMarketSnapshotInput(entity_ids=["CN.SH.600000"], as_of=now),
                now=later,
            )
        assert market is None
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_publish_rejects_expired_exact_policy_without_partial_writes(
    postgres_context,
):
    """Test helper test_publish_rejects_expired_exact_policy_without_partial_writes."""
    from app.research.contracts import ClaimV1, ResearchBriefV1

    (
        database,
        ledger,
        now,
        principal_id,
        run_id,
        evidence_id,
        _principal,
        worker,
        task,
    ) = await _setup(
        postgres_context,
        suffix="-publish-expired",
        policy_lifetime=timedelta(seconds=5),
    )
    try:
        lease = await _claim(ledger, now, worker, task)
        brief = ResearchBriefV1(
            run_id=run_id,
            as_of=now - timedelta(seconds=30),
            claims=[
                ClaimV1(
                    claim_id=uuid4(),
                    text="Supported observation",
                    kind="fact",
                    evidence_ids=[evidence_id],
                    as_of=now - timedelta(seconds=30),
                    valid_until=None,
                    confidence=0.9,
                )
            ],
            counterarguments=[],
            unknowns=[],
            limitations=[],
            model_trace=[],
        )
        approved = ApprovedBrief(
            brief=brief,
            model_profile_id="test-profile",
            policy_version="research-v1.1",
            evaluation_digest="d" * 64,
            approved_at=now,
        )
        with pytest.raises(DomainError) as denied:
            await ledger.publish_brief(
                run_id=run_id,
                lease=lease,
                approved_brief=approved,
                now=now + timedelta(seconds=10),
            )
        assert denied.value.code == "license_revoked"
        async with database.session_factory() as session:  # skipcq: PYL-E1102 -- async session factory from research port
            run = await session.get(ResearchRun, run_id)
            quota = await session.get(ResearchPrincipalQuota, principal_id)
            assert run.status == "running"
            assert run.execution_token_hash is not None
            assert quota.active_run_count == 1
            assert await session.get(ResearchBrief, run_id) is None
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(ResearchBriefCitation)
                    .where(ResearchBriefCitation.run_id == run_id)
                )
                == 0
            )
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_direct_market_read_validates_non_mock_projection(postgres_context):
    """Test helper test_direct_market_read_validates_non_mock_projection."""
    from app.research.contracts import GetMarketSnapshotInput

    database, ledger, now, _, _, _, principal, _, _ = await _setup(
        postgres_context, suffix="-direct-market"
    )
    source = "direct-market-provider"
    try:
        async with database.session_factory() as session, session.begin():  # skipcq: PYL-E1102 -- async session factory from research port
            session.add(
                ResearchSourcePolicy(
                    source_id=source,
                    policy_version="v1",
                    license_id="market-license",
                    terms_ref="market-terms",
                    approved_at=now - timedelta(days=1),
                    expires_at=now + timedelta(days=1),
                    redisplay_allowed=True,
                    model_use_allowed=True,
                    storage_allowed=True,
                    allowed_excerpt_length=8,
                )
            )
        good_id = uuid4()
        good = ResearchEvidence(
            evidence_id=good_id,
            source_id=source,
            source_url="https://example.test/market",
            content_hash="b" * 64,
            published_at=now - timedelta(minutes=5),
            fetched_at=now - timedelta(minutes=1),
            available_at=now - timedelta(minutes=1),
            timezone="UTC",
            license_scope="metadata_only",
            entity_id="CN.SH.600000",
            excerpt="market",
            quality_status="verified_metadata",
            evidence_kind="market",
            version="market-v1",
            source_policy_version="v1",
            origin="live",
            admitted_at=now,
        )
        async with database.session_factory() as session, session.begin():  # skipcq: PYL-E1102 -- async session factory from research port
            session.add(good)
            await session.flush()
            session.add(
                ResearchMarketPayload(
                    evidence_id=good_id,
                    symbol=good.entity_id,
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
        request = GetMarketSnapshotInput(entity_ids=["CN.SH.600000"], as_of=now)
        result = await ledger.get_market_snapshot(
            principal=principal, request=request, now=now
        )
        assert result is not None
        assert result.evidence_id == good_id
        assert result.is_mock is False
        assert result.provider == source

        from sqlalchemy.exc import IntegrityError

        mock_id = uuid4()
        mock = ResearchEvidence(
            evidence_id=mock_id,
            source_id=source,
            source_url="https://example.test/market-mock",
            content_hash="e" * 64,
            published_at=now - timedelta(minutes=5),
            fetched_at=now - timedelta(seconds=5),
            available_at=now - timedelta(seconds=10),
            timezone="UTC",
            license_scope="metadata_only",
            entity_id="CN.SH.600000",
            excerpt="mock",
            quality_status="verified_metadata",
            evidence_kind="market",
            version="market-v2",
            source_policy_version="v1",
            origin="live",
            admitted_at=now,
        )
        try:
            async with database.session_factory() as session, session.begin():  # skipcq: PYL-E1102 -- async session factory from research port
                session.add(mock)
                await session.flush()
                session.add(
                    ResearchMarketPayload(
                        evidence_id=mock_id,
                        symbol=mock.entity_id,
                        observed_at=mock.published_at,
                        available_at=mock.available_at,
                        fetched_at=mock.fetched_at,
                        timezone=mock.timezone,
                        currency="CNY",
                        adjustment="none",
                        fields_projection=[
                            {"name": "close", "value": "12.35", "unit": "CNY"}
                        ],
                        provider=source,
                        version=mock.version,
                        is_mock=True,
                    )
                )
        except IntegrityError as error:
            assert "research evidence and market payload must match" in str(error)
        else:
            non_mock_result = await ledger.get_market_snapshot(
                principal=principal, request=request, now=now
            )
            assert non_mock_result is not None
            assert non_mock_result.evidence_id == good_id
            assert non_mock_result.is_mock is False

        malformed_id = uuid4()
        malformed = ResearchEvidence(
            evidence_id=malformed_id,
            source_id=source,
            source_url="https://example.test/market-malformed",
            content_hash="c" * 64,
            published_at=now - timedelta(minutes=2),
            fetched_at=now - timedelta(seconds=30),
            available_at=now - timedelta(seconds=30),
            timezone="UTC",
            license_scope="metadata_only",
            entity_id="CN.SH.600000",
            excerpt="market",
            quality_status="verified_metadata",
            evidence_kind="market",
            version="market-v3",
            source_policy_version="v1",
            origin="live",
            admitted_at=now,
        )
        async with database.session_factory() as session, session.begin():  # skipcq: PYL-E1102 -- async session factory from research port
            session.add(malformed)
            await session.flush()
            session.add(
                ResearchMarketPayload(
                    evidence_id=malformed_id,
                    symbol=malformed.entity_id,
                    observed_at=malformed.published_at,
                    available_at=malformed.available_at,
                    fetched_at=malformed.fetched_at,
                    timezone=malformed.timezone,
                    currency="CNY",
                    adjustment="none",
                    fields_projection=[{"unexpected": "invalid-field"}],
                    provider=source,
                    version=malformed.version,
                    is_mock=False,
                )
            )
        with pytest.raises(DomainError) as rejected:
            await ledger.get_market_snapshot(
                principal=principal, request=request, now=now
            )
        assert rejected.value.code == "market_data_unverifiable"
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_publish_uses_exact_policy_version_for_snapshot_evidence(
    postgres_context,
):
    """Test helper test_publish_uses_exact_policy_version_for_snapshot_evidence."""
    from app.research.contracts import ClaimV1, ResearchBriefV1

    database, ledger, now, _, run_id, evidence_id, _, worker, task = await _setup(
        postgres_context, suffix="-exact-policy-version"
    )
    try:
        lease = await _claim(ledger, now, worker, task)
        async with database.session_factory() as session, session.begin():  # skipcq: PYL-E1102 -- async session factory from research port
            original = await session.get(ResearchEvidence, evidence_id)
            assert original is not None
            denied_evidence_id = uuid4()
            session.add(
                ResearchSourcePolicy(
                    source_id=original.source_id,
                    policy_version="v2",
                    license_id="license-v2",
                    terms_ref="terms-v2",
                    approved_at=now - timedelta(days=1),
                    expires_at=now + timedelta(days=1),
                    redisplay_allowed=False,
                    model_use_allowed=False,
                    storage_allowed=False,
                    allowed_excerpt_length=0,
                )
            )
            await session.flush()
            session.add(
                ResearchEvidence(
                    evidence_id=denied_evidence_id,
                    source_id=original.source_id,
                    source_url="https://example.test/evidence-v2",
                    content_hash="c" * 64,
                    published_at=now - timedelta(minutes=4),
                    fetched_at=now - timedelta(minutes=1),
                    available_at=now - timedelta(minutes=1),
                    timezone="UTC",
                    license_scope="metadata_only",
                    entity_id="CN.SH.600000",
                    excerpt="denied newer version",
                    quality_status="verified_metadata",
                    evidence_kind="event",
                    version="v2",
                    source_policy_version="v2",
                    origin="live",
                    admitted_at=now,
                )
            )

        brief = ResearchBriefV1(
            run_id=run_id,
            as_of=now - timedelta(seconds=30),
            claims=[
                ClaimV1(
                    claim_id=uuid4(),
                    text="Supported by the frozen v1 evidence",
                    kind="fact",
                    evidence_ids=[evidence_id],
                    as_of=now - timedelta(seconds=30),
                    valid_until=None,
                    confidence=0.9,
                )
            ],
            counterarguments=[],
            unknowns=[],
            limitations=[],
            model_trace=[],
        )
        approved = ApprovedBrief(
            brief=brief,
            model_profile_id="test-profile",
            policy_version="research-v1.1",
            evaluation_digest="f" * 64,
            approved_at=now,
        )
        await ledger.publish_brief(
            run_id=run_id,
            lease=lease,
            approved_brief=approved,
            now=now + timedelta(seconds=1),
        )
        async with database.session_factory() as session:  # skipcq: PYL-E1102 -- async session factory from research port
            run = await session.get(ResearchRun, run_id)
            assert run.status == "completed"
            assert await session.get(ResearchBrief, run_id) is not None
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(ResearchBriefCitation)
                    .where(ResearchBriefCitation.run_id == run_id)
                )
                == 1
            )
    finally:
        await database.dispose()
