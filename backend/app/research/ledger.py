"""PostgreSQL-backed authoritative research ledger.

All mutable state changes are scoped to one caller-owned database transaction.
"""

from __future__ import annotations

import secrets
from collections.abc import Sequence
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.research.contracts import (
    ArticlesSearchResult,
    ResearchBriefV1,
    ResearchRunViewV1,
    RunEventV1,
)
from app.research.errors import NON_ENUMERATING_DENIAL_CODE, DomainError
from app.research.models import (
    ResearchAudit,
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
    AuthorizationPort,
    DispatchTask,
    ExecutionToken,
    ExecutorRegistryPort,
    FrozenSnapshot,
    GetEvidenceInput,
    GetMarketSnapshotInput,
    GetRunInput,
    Principal,
    ResearchDatabasePort,
    RunEventPage,
    RunFinishRequest,
    RunLease,
    RunTransition,
    SearchArticlesInput,
    StartResearchInput,
    StepEvent,
    WorkerIdentity,
)
from app.research.snapshot import _snapshot_member


def _err(code: str, message: str | None = None, retryable: bool = False) -> DomainError:
    """Build a domain error with a safe public message."""
    return DomainError(
        code=code, safe_message=message or code.replace("_", " "), retryable=retryable
    )  # type: ignore[arg-type]


def _json(model: Any) -> dict[str, Any]:
    """Serialize a Pydantic model to JSON-compatible data."""
    return model.model_dump(mode="json")


def _start_request_hash(request: StartResearchInput) -> str:
    """Hash normalized start-run input for idempotent reuse checks."""
    normalized = {
        "entity_id": request.entity_ids[0],
        "seed_evidence_id": str(request.seed_evidence_id),
        "as_of": request.as_of.isoformat(),
        "question": (request.question or "").strip() or None,
        "schema": "research-v1.1",
        "policy": "research-v1.1",
    }
    payload = (
        __import__("json")
        .dumps(normalized, sort_keys=True, separators=(",", ":"))
        .encode()
    )
    return sha256(payload).hexdigest()


def _brief_citation_evidence_ids(brief: ResearchBriefV1) -> set[object]:
    """Collect every evidence id cited by claims and counterarguments."""
    return {
        evidence_id
        for claim in [*brief.claims, *brief.counterarguments]
        for evidence_id in claim.evidence_ids
    }


def _snapshot_policies_allow_brief(
    policies: Sequence[ResearchSourcePolicy], now: datetime
) -> bool:
    """Return whether every snapshot policy permits brief redisplay at now."""
    return not any(
        not policy.storage_allowed
        or not policy.model_use_allowed
        or not policy.redisplay_allowed
        or policy.approved_at > now
        or now >= policy.expires_at
        for policy in policies
    )


def _run_view(
    run: ResearchRun,
    brief: ResearchBrief | None = None,
    error: str | None = None,
) -> ResearchRunViewV1:
    """Project a run row into the public run view contract."""
    return ResearchRunViewV1(
        run_id=run.run_id,
        request_id=run.request_id,
        principal_id=run.principal_id,
        entity_ids=[run.entity_id],
        as_of=run.as_of,
        status=run.status,
        created_at=run.created_at,
        updated_at=run.updated_at,
        model_id=run.model_id,
        prompt_version=run.prompt_version,
        policy_version=run.policy_version,
        result_ref=run.result_ref,
        error_code=error or run.error_code,
        brief=ResearchBriefV1.model_validate(brief.brief_projection) if brief else None,
    )


async def _append_audit(
    session: AsyncSession,
    *,
    action: str,
    now: datetime,
    run_id: UUID | None = None,
    principal_id: UUID | None = None,
    evidence_id: UUID | None = None,
    safe_code: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Append an audit row for a ledger-side action."""
    session.add(
        ResearchAudit(
            audit_id=uuid4(),
            run_id=run_id,
            evidence_id=evidence_id,
            principal_id=principal_id,
            action=action,
            safe_code=safe_code,
            details_projection=details or {},
            occurred_at=now,
        )
    )


async def _append_run_event(
    session: AsyncSession,
    run_id: UUID,
    event_type: str,
    payload: dict[str, Any],
    now: datetime,
) -> ResearchRunEvent:
    """Append the next sequenced run event inside the current transaction."""
    count = await session.scalar(
        select(func.coalesce(func.max(ResearchRunEvent.seq), 0)).where(
            ResearchRunEvent.run_id == run_id
        )
    )
    row = ResearchRunEvent(
        event_id=uuid4(),
        run_id=run_id,
        seq=int(count or 0) + 1,
        event_type=event_type,
        occurred_at=now,
        payload_projection=payload,
    )
    session.add(row)
    await session.flush()
    return row


async def _brief_policy_revoked(
    session: AsyncSession, run_id: UUID, now: datetime
) -> bool:
    """Return whether brief-linked source policies are no longer redisplayable."""
    policies = (
        (
            await session.execute(
                select(ResearchSourcePolicy)
                .join(
                    ResearchEvidence,
                    (ResearchEvidence.source_id == ResearchSourcePolicy.source_id)
                    & (
                        ResearchEvidence.source_policy_version
                        == ResearchSourcePolicy.policy_version
                    ),
                )
                .join(
                    ResearchSnapshotMember,
                    ResearchSnapshotMember.evidence_id == ResearchEvidence.evidence_id,
                )
                .where(ResearchSnapshotMember.run_id == run_id)
            )
        )
        .scalars()
        .all()
    )
    return any(
        not p.storage_allowed
        or not p.redisplay_allowed
        or p.approved_at > now
        or now >= p.expires_at
        for p in policies
    )


def _evidence_dto(row: ResearchEvidence, allowed_excerpt_length: int):
    """Map a stored evidence row into the public evidence contract."""
    from app.research.contracts import EvidenceV1

    return EvidenceV1(
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
        excerpt=row.excerpt[:allowed_excerpt_length],
        quality_status=row.quality_status,
        evidence_kind=row.evidence_kind,
        version=row.version,
        source_policy_version=row.source_policy_version,
        origin=row.origin,
        market_payload=None,
    )


async def _fenced_run(
    s: AsyncSession,
    run_id: UUID,
    lease: RunLease,
    now: datetime,
    *,
    lock: bool = True,
) -> ResearchRun:
    """Load a run and verify the worker lease fingerprint when required."""
    q = select(ResearchRun).where(ResearchRun.run_id == run_id)
    if lock:
        q = q.with_for_update()
    run = await s.scalar(q)
    if run is None:
        raise _err("resource_not_found_or_denied")
    if run.status != "running":
        raise _err(
            "terminal_state"
            if run.status in {"completed", "failed", "needs_review", "cancelled"}
            else "invalid_run_state"
        )
    if run.execution_token_hash != lease.token.fingerprint():
        raise _err("execution_fenced")
    if (
        run.lease_expires_at is None
        or now >= run.lease_expires_at
        or run.deadline_at is None
        or now >= run.deadline_at
    ):
        raise _err("lease_expired")
    return run


async def _authorized_run_view(
    authorizer: AuthorizationPort,
    session: AsyncSession,
    run: ResearchRun,
    principal: Principal,
    now: datetime,
    *,
    brief: ResearchBrief | None = None,
) -> ResearchRunViewV1:
    """Return a read-authorized run view with optional brief redaction."""
    authorizer.authorize_resource(
        principal=principal,
        owner_id=run.principal_id,
        entity_ids=frozenset({run.entity_id}),
        required_scope="research:read",
        now=now,
    )
    if brief is None:
        brief = await session.get(ResearchBrief, run.run_id)
    revoked = bool(brief) and await _brief_policy_revoked(session, run.run_id, now)
    return _run_view(
        run, None if revoked else brief, "license_revoked" if revoked else None
    )


async def _reuse_existing_start_run(
    session: AsyncSession,
    *,
    existing: ResearchRun,
    request_hash: str,
    principal: Principal,
    authorizer: AuthorizationPort,
    now: datetime,
) -> ResearchRunViewV1:
    """Return the run view when the caller retries with the same request id."""
    if existing.request_hash != request_hash:
        raise _err("request_conflict", "request_id was reused with different input")
    await _append_audit(
        session,
        action="run_retry",
        now=now,
        run_id=existing.run_id,
        principal_id=principal.principal_id,
    )
    return await _authorized_run_view(
        authorizer, session, existing, principal, now
    )


async def _load_start_seed_evidence(
    session: AsyncSession,
    request: StartResearchInput,
    now: datetime,
) -> tuple[ResearchEvidence, ResearchSourcePolicy]:
    """Load seed evidence and an active policy for a new research run."""
    evidence = await session.scalar(
        select(ResearchEvidence).where(
            ResearchEvidence.evidence_id == request.seed_evidence_id,
            ResearchEvidence.entity_id == request.entity_ids[0],
        )
    )
    if evidence is None or evidence.available_at > request.as_of:
        raise _err(
            "resource_not_found_or_denied",
            "resource was not found or access is denied",
        )
    policy = await session.get(
        ResearchSourcePolicy,
        (evidence.source_id, evidence.source_policy_version),
    )
    if (
        policy is None
        or not policy.storage_allowed
        or not policy.model_use_allowed
        or now >= policy.expires_at
    ):
        raise _err("license_revoked", "evidence license is unavailable")
    return evidence, policy


class ResearchLedger:
    """Implement the frozen non-snapshot ledger ports using injected adapters."""

    def __init__(
        self,
        *,
        database: ResearchDatabasePort,
        authorizer: AuthorizationPort,
        executor_registry: ExecutorRegistryPort,
        snapshot_service: Any,
        max_concurrent_runs: int = 3,
        daily_run_limit: int = 20,
        run_timeout: timedelta = timedelta(minutes=15),
        lease_duration: timedelta = timedelta(seconds=60),
        worker_heartbeat_ttl: timedelta = timedelta(seconds=90),
    ) -> None:
        """Wire database, authorization, executor, and snapshot adapters."""
        if (
            min(max_concurrent_runs, daily_run_limit) < 0
            or min(
                run_timeout.total_seconds(),
                lease_duration.total_seconds(),
                worker_heartbeat_ttl.total_seconds(),
            )
            <= 0
        ):
            raise ValueError("invalid bounded ledger policy")
        self._database, self._authorizer = database, authorizer
        self._executor, self._snapshots = executor_registry, snapshot_service
        self._max_concurrent_runs, self._daily_run_limit = (
            max_concurrent_runs,
            daily_run_limit,
        )
        self._run_timeout, self._lease_duration = run_timeout, lease_duration
        self._heartbeat_ttl = worker_heartbeat_ttl

    async def materialize_snapshot(self, **kwargs: Any):
        """Delegate snapshot materialization to the injected service."""
        snapshots = self._snapshots
        return await snapshots.materialize_snapshot(**kwargs)

    async def freeze_snapshot(self, **kwargs: Any):
        """Delegate snapshot freeze to the injected service."""
        snapshots = self._snapshots
        return await snapshots.freeze_snapshot(**kwargs)

    async def read_snapshot(self, **kwargs: Any):
        """Delegate snapshot reads to the injected service."""
        snapshots = self._snapshots
        return await snapshots.read_snapshot(**kwargs)

    async def _safe_run_view(
        self,
        session: AsyncSession,
        run: ResearchRun,
        principal: Principal,
        now: datetime,
        *,
        brief: ResearchBrief | None = None,
    ) -> ResearchRunViewV1:
        """Return a read-authorized run view with optional brief redaction."""
        return await _authorized_run_view(
            self._authorizer, session, run, principal, now, brief=brief
        )

    async def create_or_reuse_run(
        self, *, principal: Principal, request: StartResearchInput, now: datetime
    ) -> ResearchRunViewV1:
        """Create or reuse a run inside the caller transaction."""
        self._authorizer.authorize_resource(
            principal=principal,
            owner_id=principal.principal_id,
            entity_ids=frozenset(request.entity_ids),
            required_scope="research:create",
            now=now,
        )
        if request.as_of > now:
            raise _err("request_conflict", "as_of must not be in the future")
        request_hash = _start_request_hash(request)
        try:
            async with self._database.session_factory() as session, session.begin():
                existing = await session.scalar(
                    select(ResearchRun)
                    .where(
                        ResearchRun.principal_id == principal.principal_id,
                        ResearchRun.request_id == request.request_id,
                    )
                    .with_for_update()
                )
                if existing:
                    return await _reuse_existing_start_run(
                        session,
                        existing=existing,
                        request_hash=request_hash,
                        principal=principal,
                        authorizer=self._authorizer,
                        now=now,
                    )
                evidence, _policy = await _load_start_seed_evidence(
                    session, request, now
                )
                readiness = await self._executor.get_readiness(now=now)
                if not readiness.ready or now >= readiness.expires_at:
                    raise _err(
                        "execution_unavailable",
                        "research execution is unavailable",
                        True,
                    )
                # Create the principal's quota row atomically. ON CONFLICT waits
                # for an uncommitted competing insert, then the locked SELECT
                # serializes all distinct request IDs for this principal.
                await session.execute(
                    pg_insert(ResearchPrincipalQuota)
                    .values(
                        principal_id=principal.principal_id,
                        max_concurrent_runs=self._max_concurrent_runs,
                        active_run_count=0,
                        daily_run_limit=self._daily_run_limit,
                        daily_run_count=0,
                        window_started_at=now,
                        updated_at=now,
                    )
                    .on_conflict_do_nothing(
                        index_elements=[ResearchPrincipalQuota.principal_id]
                    )
                )
                quota = await session.scalar(
                    select(ResearchPrincipalQuota)
                    .where(
                        ResearchPrincipalQuota.principal_id == principal.principal_id
                    )
                    .with_for_update()
                )
                assert quota is not None
                if now - quota.window_started_at >= timedelta(days=1):
                    quota.daily_run_count = 0
                    quota.window_started_at = now
                if quota.active_run_count >= min(
                    quota.max_concurrent_runs, self._max_concurrent_runs
                ) or quota.daily_run_count >= min(
                    quota.daily_run_limit, self._daily_run_limit
                ):
                    raise _err("quota_exceeded", "research run quota exceeded")
                run = ResearchRun(
                    run_id=uuid4(),
                    request_id=request.request_id,
                    principal_id=principal.principal_id,
                    entity_id=request.entity_ids[0],
                    seed_evidence_id=evidence.evidence_id,
                    request_hash=request_hash,
                    as_of=request.as_of,
                    status="queued",
                    snapshot_state="none",
                    policy_version="research-v1.1",
                    prompt_version="research-v1.1",
                    created_at=now,
                    updated_at=now,
                )
                session.add(run)
                await session.flush()
                dispatch = secrets.token_urlsafe(24)
                session.add(
                    ResearchOutbox(
                        outbox_id=uuid4(),
                        run_id=run.run_id,
                        dispatch_id=dispatch,
                        contract_version="research-v1.1",
                        delivery_status="pending",
                        available_at=now,
                        created_at=now,
                    )
                )
                quota.active_run_count += 1
                quota.daily_run_count += 1
                quota.updated_at = now
                await _append_audit(
                    session,
                    action="run_created",
                    now=now,
                    run_id=run.run_id,
                    principal_id=principal.principal_id,
                )
                return _run_view(run)
        except DomainError:
            raise
        except IntegrityError:
            # Unique request key race: resolve from authoritative committed row.
            async with self._database.session_factory() as session:
                existing = await session.scalar(
                    select(ResearchRun).where(
                        ResearchRun.principal_id == principal.principal_id,
                        ResearchRun.request_id == request.request_id,
                    )
                )
                if existing and existing.request_hash == request_hash:
                    return await self._safe_run_view(session, existing, principal, now)
            raise _err("request_conflict", "request could not be created") from None
        except SQLAlchemyError:
            raise _err(
                "persistence_failed", "research run could not be persisted", True
            ) from None

    async def _authorized_run(
        self,
        session: AsyncSession,
        run_id: UUID,
        principal: Principal,
        now: datetime,
        scope: str = "research:read",
    ) -> ResearchRun:
        """Load a run after read authorization for the requested scope."""
        run = await session.get(ResearchRun, run_id)
        if run is None:
            raise _err(
                NON_ENUMERATING_DENIAL_CODE,
                "resource was not found or access is denied",
            )
        self._authorizer.authorize_resource(
            principal=principal,
            owner_id=run.principal_id,
            entity_ids=frozenset({run.entity_id}),
            required_scope=scope,
            now=now,
        )
        return run

    async def get_run(
        self, *, principal: Principal, request: GetRunInput, now: datetime
    ) -> ResearchRunViewV1:
        """Return an authorized run view or a non-enumerating denial."""
        async with self._database.session_factory() as s:
            run = await self._authorized_run(s, request.run_id, principal, now)
            return await self._safe_run_view(s, run, principal, now)

    async def search_articles(
        self, *, principal: Principal, request: SearchArticlesInput, now: datetime
    ) -> ArticlesSearchResult:
        """Search articles visible to the principal at the frozen cutoff."""
        self._authorizer.authorize_resource(
            principal=principal,
            owner_id=principal.principal_id,
            entity_ids=frozenset(request.entity_ids),
            required_scope="research:read",
            now=now,
        )
        async with self._database.session_factory() as s:
            rows = (
                await s.execute(
                    select(
                        ResearchEvidence, ResearchSourcePolicy.allowed_excerpt_length
                    )
                    .join(
                        ResearchSourcePolicy,
                        (ResearchSourcePolicy.source_id == ResearchEvidence.source_id)
                        & (
                            ResearchSourcePolicy.policy_version
                            == ResearchEvidence.source_policy_version
                        ),
                    )
                    .where(
                        ResearchEvidence.entity_id == request.entity_ids[0],
                        ResearchEvidence.available_at <= request.as_of,
                        ResearchEvidence.quality_status == "verified_metadata",
                        ResearchSourcePolicy.redisplay_allowed.is_(True),
                        ResearchSourcePolicy.storage_allowed.is_(True),
                        ResearchSourcePolicy.expires_at > now,
                        ResearchSourcePolicy.approved_at <= now,
                    )
                    .order_by(ResearchEvidence.published_at.desc())
                    .limit(request.limit + 1)
                )
            ).all()
            items = [_evidence_dto(r, n) for r, n in rows[: request.limit]]
            return ArticlesSearchResult(
                articles=items, next_cursor=None, truncated=len(rows) > request.limit
            )

    async def read_evidence(
        self, *, principal: Principal, request: GetEvidenceInput, now: datetime
    ):
        """Read evidence only through authorized snapshot membership."""
        async with self._database.session_factory() as s:
            run = await self._authorized_run(s, request.run_id, principal, now)
            member = await s.scalar(
                select(ResearchSnapshotMember).where(
                    ResearchSnapshotMember.run_id == run.run_id,
                    ResearchSnapshotMember.evidence_id == request.evidence_id,
                )
            )
            if member is None:
                raise _err(
                    NON_ENUMERATING_DENIAL_CODE,
                    "resource was not found or access is denied",
                )
            row = await s.get(ResearchEvidence, request.evidence_id)
            policy = (
                await s.get(
                    ResearchSourcePolicy, (row.source_id, row.source_policy_version)
                )
                if row
                else None
            )
            if (
                row is None
                or policy is None
                or not policy.storage_allowed
                or not policy.redisplay_allowed
                or policy.approved_at > now
                or now >= policy.expires_at
            ):
                raise _err("license_revoked", "evidence license is unavailable")
            return _evidence_dto(row, policy.allowed_excerpt_length)

    async def get_market_snapshot(
        self, *, principal: Principal, request: GetMarketSnapshotInput, now: datetime
    ):
        """Return a licensed market payload for authorized evidence."""
        self._authorizer.authorize_resource(
            principal=principal,
            owner_id=principal.principal_id,
            entity_ids=frozenset(request.entity_ids),
            required_scope="research:read",
            now=now,
        )
        async with self._database.session_factory() as s:
            q = (
                select(ResearchEvidence, ResearchSourcePolicy)
                .join(
                    ResearchSourcePolicy,
                    (ResearchSourcePolicy.source_id == ResearchEvidence.source_id)
                    & (
                        ResearchSourcePolicy.policy_version
                        == ResearchEvidence.source_policy_version
                    ),
                )
                .join(
                    ResearchMarketPayload,
                    ResearchMarketPayload.evidence_id == ResearchEvidence.evidence_id,
                )
                .where(
                    ResearchEvidence.entity_id == request.entity_ids[0],
                    ResearchEvidence.evidence_kind == "market",
                    ResearchEvidence.quality_status == "verified_metadata",
                    ResearchEvidence.origin == "live",
                    ResearchEvidence.available_at <= request.as_of,
                    ResearchMarketPayload.is_mock.is_(False),
                    ResearchSourcePolicy.expires_at > now,
                    ResearchSourcePolicy.approved_at <= now,
                    ResearchSourcePolicy.redisplay_allowed.is_(True),
                    ResearchSourcePolicy.storage_allowed.is_(True),
                )
                .order_by(ResearchEvidence.available_at.desc())
                .limit(1)
            )
            result = (await s.execute(q)).first()
            if result is None:
                return None
            evidence, policy = result
            member = await _snapshot_member(s, evidence, now=now, policy=policy)
            if member.evidence.market_payload is None:
                raise _err("market_data_unverifiable")
            return member.evidence.market_payload

    async def read_events(
        self,
        *,
        principal: Principal,
        run_id: UUID,
        after_event_id: UUID | None,
        limit: int,
        now: datetime,
    ) -> RunEventPage:
        """Page run events after an optional cursor for the principal."""
        async with self._database.session_factory() as s:
            run = await self._authorized_run(s, run_id, principal, now)
            after = 0
            if after_event_id:
                cursor = await s.get(ResearchRunEvent, after_event_id)
                if cursor is None or cursor.run_id != run.run_id:
                    raise _err("event_cursor_invalid", "event cursor is invalid")
                after = cursor.seq
            rows = (
                await s.scalars(
                    select(ResearchRunEvent)
                    .where(
                        ResearchRunEvent.run_id == run.run_id,
                        ResearchRunEvent.seq > after,
                    )
                    .order_by(ResearchRunEvent.seq)
                    .limit(max(1, min(limit, 100)) + 1)
                )
            ).all()
            page_limit = max(1, min(limit, 100))
            events = tuple(
                RunEventV1(
                    event_id=r.event_id,
                    run_id=r.run_id,
                    seq=r.seq,
                    type=r.event_type,
                    occurred_at=r.occurred_at,
                    payload=r.payload_projection,
                )
                for r in rows[:page_limit]
            )
            return RunEventPage(
                run_id=run.run_id,
                events=events,
                next_event_id=events[-1].event_id
                if len(rows) > page_limit and events
                else None,
            )

    async def claim_run(
        self, *, task: DispatchTask, worker: WorkerIdentity, now: datetime
    ) -> RunLease | None:
        """Claim a queued run with a bounded worker lease."""
        try:
            async with self._database.session_factory() as s, s.begin():
                hb = await s.scalar(
                    select(ResearchWorkerHeartbeat)
                    .where(ResearchWorkerHeartbeat.worker_id == worker.worker_id)
                    .with_for_update()
                )
                out = await s.scalar(
                    select(ResearchOutbox)
                    .where(
                        ResearchOutbox.run_id == task.run_id,
                        ResearchOutbox.dispatch_id == task.dispatch_id,
                        ResearchOutbox.contract_version == task.contract_version,
                    )
                    .with_for_update()
                )
                run = await s.scalar(
                    select(ResearchRun)
                    .where(ResearchRun.run_id == task.run_id)
                    .with_for_update()
                )
                if (
                    not run
                    or not out
                    or not hb
                    or hb.worker_status != "active"
                    or now >= hb.expires_at
                    or (
                        hb.queue_name != worker.queue_name
                        or hb.contract_version != worker.contract_version
                    )
                ):
                    return None
                if run.status != "queued" or out.delivery_status == "submitted":
                    return None
                token = ExecutionToken(secrets.token_bytes(32))
                deadline = now + self._run_timeout
                run.status = "running"
                run.updated_at = now
                run.execution_token_hash = token.fingerprint()
                run.execution_worker_id = worker.worker_id
                run.lease_expires_at = min(now + self._lease_duration, deadline)
                run.deadline_at = deadline
                await s.flush()
                frozen: FrozenSnapshot = (
                    # skipcq: PYL-W0212
                    await self._snapshots._freeze_snapshot_in_transaction(
                        s, run, now=now
                    )
                )
                run.snapshot_state = "frozen"
                run.snapshot_frozen_at = frozen.frozen_at
                await _append_run_event(s, run.run_id, "started", {}, now)
                await _append_audit(s, action="run_claimed", now=now, run_id=run.run_id)
                return RunLease(
                    run_id=run.run_id,
                    token=token,
                    lease_expires_at=run.lease_expires_at,
                    deadline_at=deadline,
                )
        except DomainError:
            raise
        except SQLAlchemyError:
            raise _err("persistence_failed", "run claim failed", True) from None

    async def heartbeat_run(
        self, *, run_id: UUID, lease: RunLease, worker: WorkerIdentity, now: datetime
    ) -> RunLease:
        """Extend an active worker lease for an in-flight run."""
        async with self._database.session_factory() as s, s.begin():
            run = await _fenced_run(s, run_id, lease, now)
            if run.execution_worker_id != worker.worker_id:
                raise _err("execution_fenced")
            end = min(now + self._lease_duration, run.deadline_at)
            run.lease_expires_at = end
            run.updated_at = now
            return RunLease(
                run_id=run_id,
                token=lease.token,
                lease_expires_at=end,
                deadline_at=run.deadline_at,
            )

    async def append_step_event(
        self, *, run_id: UUID, lease: RunLease, event: StepEvent, now: datetime
    ) -> RunEventV1:
        """Append a worker step event to the authoritative ledger."""
        async with self._database.session_factory() as s, s.begin():
            await _fenced_run(s, run_id, lease, now)
            row = await _append_run_event(
                s, run_id, event.type, _json(event.payload), now
            )
            return RunEventV1(
                event_id=row.event_id,
                run_id=run_id,
                seq=row.seq,
                type=row.event_type,
                occurred_at=now,
                payload=event.payload,
            )

    async def publish_brief(
        self,
        *,
        run_id: UUID,
        lease: RunLease,
        approved_brief: ApprovedBrief,
        now: datetime,
    ) -> RunTransition:
        """Publish a brief from a frozen, licensed snapshot only."""
        try:
            async with self._database.session_factory() as s, s.begin():
                run = await _fenced_run(s, run_id, lease, now)
                brief = approved_brief.brief
                if (
                    brief.run_id != run_id
                    or brief.as_of != run.as_of
                    or run.snapshot_state != "frozen"
                ):
                    raise _err("brief_gate_rejected")
                members = set(
                    (
                        await s.scalars(
                            select(ResearchSnapshotMember.evidence_id).where(
                                ResearchSnapshotMember.run_id == run_id
                            )
                        )
                    ).all()
                )
                cites = _brief_citation_evidence_ids(brief)
                if not cites.issubset(members):
                    raise _err("citation_invalid")
                policies = (
                    await s.scalars(
                        select(ResearchSourcePolicy)
                        .join(
                            ResearchEvidence,
                            (
                                ResearchEvidence.source_id
                                == ResearchSourcePolicy.source_id
                            )
                            & (
                                ResearchEvidence.source_policy_version
                                == ResearchSourcePolicy.policy_version
                            ),
                        )
                        .join(
                            ResearchSnapshotMember,
                            ResearchSnapshotMember.evidence_id
                            == ResearchEvidence.evidence_id,
                        )
                        .where(ResearchSnapshotMember.run_id == run_id)
                    )
                ).all()
                if not _snapshot_policies_allow_brief(policies, now):
                    raise _err("license_revoked")
                ref = secrets.token_urlsafe(24)
                s.add(
                    ResearchBrief(
                        run_id=run_id,
                        as_of=run.as_of,
                        brief_projection=_json(brief),
                        model_profile_id=approved_brief.model_profile_id,
                        policy_version=approved_brief.policy_version,
                        evaluation_digest=approved_brief.evaluation_digest,
                        result_ref=ref,
                        approved_at=approved_brief.approved_at,
                    )
                )
                for c in [*brief.claims, *brief.counterarguments]:
                    for eid in c.evidence_ids:
                        s.add(
                            ResearchBriefCitation(
                                citation_id=uuid4(),
                                run_id=run_id,
                                claim_id=c.claim_id,
                                evidence_id=eid,
                                created_at=now,
                            )
                        )
                run.status = "completed"
                run.result_ref = ref
                run.execution_token_hash = None
                run.updated_at = now
                quota = await s.scalar(
                    select(ResearchPrincipalQuota)
                    .where(ResearchPrincipalQuota.principal_id == run.principal_id)
                    .with_for_update()
                )
                if quota:
                    quota.active_run_count = max(0, quota.active_run_count - 1)
                    quota.updated_at = now
                await _append_run_event(
                    s, run_id, "completed", {"result_ref": ref}, now
                )
                await _append_audit(s, action="run_completed", now=now, run_id=run_id)
                return RunTransition(run_id=run_id, status="completed", occurred_at=now)
        except DomainError:
            raise
        except SQLAlchemyError:
            raise _err("persistence_failed", "brief publication failed", True) from None

    async def finish_run(
        self, *, run_id: UUID, lease: RunLease, finish: RunFinishRequest, now: datetime
    ) -> RunTransition:
        """Terminalize a run from an authorized worker transition."""
        async with self._database.session_factory() as s, s.begin():
            run = await _fenced_run(s, run_id, lease, now)
            run.status = finish.status
            run.error_code = finish.code
            run.updated_at = now
            run.execution_token_hash = None
            quota = await s.scalar(
                select(ResearchPrincipalQuota)
                .where(ResearchPrincipalQuota.principal_id == run.principal_id)
                .with_for_update()
            )
            if quota:
                quota.active_run_count = max(0, quota.active_run_count - 1)
                quota.updated_at = now
            etype = finish.status
            payload = (
                {"reason": finish.cancellation_reason}
                if etype == "cancelled"
                else {"code": finish.code}
            )
            await _append_run_event(s, run_id, etype, payload, now)
            await _append_audit(
                s,
                action="run_" + finish.status,
                now=now,
                run_id=run_id,
                safe_code=finish.code,
            )
            return RunTransition(run_id=run_id, status=finish.status, occurred_at=now)

    async def reap_stale(self, *, now: datetime, limit: int) -> tuple[Any, ...]:
        """Reap stale leases and timed-out runs without leaking secrets."""
        from app.research.ports import ReapedRun

        results = []
        async with self._database.session_factory() as s, s.begin():
            rows = (
                await s.scalars(
                    select(ResearchRun)
                    .where(
                        (
                            (ResearchRun.status == "queued")
                            & (ResearchRun.created_at + self._run_timeout < now)
                        )
                        | (
                            (ResearchRun.status == "running")
                            & (ResearchRun.lease_expires_at < now)
                        )
                    )
                    .order_by(ResearchRun.created_at)
                    .limit(max(1, min(limit, 100)))
                    .with_for_update(skip_locked=True)
                )
            ).all()
            for run in rows:
                code = "dispatch_timeout" if run.status == "queued" else "worker_lost"
                run.status = "failed"
                run.error_code = code
                run.execution_token_hash = None
                run.updated_at = now
                await _append_run_event(s, run.run_id, "failed", {"code": code}, now)
                await _append_audit(
                    s, action="run_reaped", now=now, run_id=run.run_id, safe_code=code
                )
                q = await s.scalar(
                    select(ResearchPrincipalQuota)
                    .where(ResearchPrincipalQuota.principal_id == run.principal_id)
                    .with_for_update()
                )
                if q:
                    q.active_run_count = max(0, q.active_run_count - 1)
                    q.updated_at = now
                results.append(
                    ReapedRun(run_id=run.run_id, error_code=code, reaped_at=now)
                )
        return tuple(results)
