"""Freeze internal research-v1.1 ports without creating infrastructure.

Author: Damon Li
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Literal, Protocol, TypeAlias, runtime_checkable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.research.contracts import (
    ArticlesSearchResult,
    EvidenceV1,
    GetEvidenceInput,
    GetMarketSnapshotInput,
    GetRunInput,
    MarketPayloadV1,
    ResearchBriefV1,
    ResearchRunViewV1,
    RunEventPayload,
    RunEventV1,
    SearchArticlesInput,
    StartResearchInput,
)

ResearchAsyncSessionFactory: TypeAlias = async_sessionmaker[AsyncSession]
ResearchScope: TypeAlias = Literal["research:create", "research:read"]
TerminalRunStatus: TypeAlias = Literal["failed", "needs_review", "cancelled"]
StepEventType: TypeAlias = Literal[
    "step_started", "evidence_added", "claim_checked"
]


def _require_aware(value: datetime, field_name: str) -> None:
    """Reject a naive internal timestamp before it crosses a Port boundary."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _require_nonempty(value: str, field_name: str) -> None:
    """Reject an empty internal identifier before it reaches persistence."""
    if not value:
        raise ValueError(f"{field_name} must not be empty")


@dataclass(frozen=True, slots=True)
class Principal:
    """Represent only a bearer-verified financial resource principal."""

    principal_id: UUID
    scopes: frozenset[ResearchScope]
    entity_ids: frozenset[str]
    issuer: str
    audience: str
    expires_at: datetime

    def __post_init__(self) -> None:
        """Require complete verified identity metadata at construction time."""
        if not self.scopes:
            raise ValueError("scopes must not be empty")
        if not self.entity_ids:
            raise ValueError("entity_ids must not be empty")
        _require_nonempty(self.issuer, "issuer")
        _require_nonempty(self.audience, "audience")
        _require_aware(self.expires_at, "expires_at")


@dataclass(frozen=True, slots=True, repr=False)
class BearerCredential:
    """Contain a raw bearer only while the identity adapter verifies it."""

    _serialized: str = field(repr=False)

    def __post_init__(self) -> None:
        """Reject an empty credential without exposing its contents."""
        _require_nonempty(self._serialized, "credential")

    def __repr__(self) -> str:
        """Prevent diagnostic output from exposing bearer material."""
        return "BearerCredential(<redacted>)"

    def __str__(self) -> str:
        """Prevent accidental f-string logging from exposing bearer material."""
        return "<redacted-bearer>"

    def for_verification(self) -> str:
        """Return raw material solely to an IdentityVerifierPort implementation."""
        return self._serialized


@dataclass(frozen=True, slots=True, repr=False)
class ExecutionToken:
    """Represent an in-memory worker fence secret, never a public DTO field."""

    _secret: bytes = field(repr=False)

    def __post_init__(self) -> None:
        """Require non-empty secret material supplied by the trusted claimant."""
        if not self._secret:
            raise ValueError("execution token must not be empty")

    def __repr__(self) -> str:
        """Keep exception, audit, and debug representations secret-safe."""
        return "ExecutionToken(<redacted>)"

    def __str__(self) -> str:
        """Keep accidental interpolation from disclosing the fence secret."""
        return "<redacted-execution-token>"

    def fingerprint(self) -> str:
        """Return the one-way persistence comparison value, not the secret."""
        return sha256(self._secret).hexdigest()


@dataclass(frozen=True, slots=True)
class SourcePolicy:
    """Carry the human-approved policy required for one source version."""

    source_id: str
    policy_version: str
    license_id: str
    terms_ref: str
    approved_at: datetime
    expires_at: datetime
    redisplay_allowed: bool
    model_use_allowed: bool
    storage_allowed: bool
    allowed_excerpt_length: int

    def __post_init__(self) -> None:
        """Reject incomplete or temporally invalid policy values."""
        _require_nonempty(self.source_id, "source_id")
        _require_nonempty(self.policy_version, "policy_version")
        _require_nonempty(self.license_id, "license_id")
        _require_nonempty(self.terms_ref, "terms_ref")
        _require_aware(self.approved_at, "approved_at")
        _require_aware(self.expires_at, "expires_at")
        if self.expires_at < self.approved_at:
            raise ValueError("expires_at must not precede approved_at")
        if self.allowed_excerpt_length < 0:
            raise ValueError("allowed_excerpt_length must not be negative")


@dataclass(frozen=True, slots=True)
class AdmittedEvidence:
    """Bind an evidence DTO to the policy that admitted its exact version."""

    evidence: EvidenceV1
    policy: SourcePolicy
    admitted_at: datetime

    def __post_init__(self) -> None:
        """Keep source and policy versions aligned for persistence."""
        _require_aware(self.admitted_at, "admitted_at")
        if self.evidence.source_id != self.policy.source_id:
            raise ValueError("evidence source_id must match policy source_id")
        if self.evidence.source_policy_version != self.policy.policy_version:
            raise ValueError("evidence source_policy_version must match policy")


@dataclass(frozen=True, slots=True)
class LedgerReadiness:
    """Report the database readiness result without exposing a DSN."""

    ready: bool
    reason: str
    checked_at: datetime

    def __post_init__(self) -> None:
        """Require a stable reason and fixed check timestamp."""
        _require_nonempty(self.reason, "reason")
        _require_aware(self.checked_at, "checked_at")


@dataclass(frozen=True, slots=True)
class ExecutorReadiness:
    """Represent a bounded, expiring worker/broker readiness observation."""

    ready: bool
    reason: str
    checked_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        """Reject readiness records that are temporally inconsistent."""
        _require_nonempty(self.reason, "reason")
        _require_aware(self.checked_at, "checked_at")
        _require_aware(self.expires_at, "expires_at")
        if self.expires_at < self.checked_at:
            raise ValueError("expires_at must not precede checked_at")


@dataclass(frozen=True, slots=True)
class WorkerIdentity:
    """Identify an already-registered internal research worker."""

    worker_id: str
    queue_name: str
    contract_version: str

    def __post_init__(self) -> None:
        """Require explicit worker registration metadata."""
        _require_nonempty(self.worker_id, "worker_id")
        _require_nonempty(self.queue_name, "queue_name")
        _require_nonempty(self.contract_version, "contract_version")


@dataclass(frozen=True, slots=True)
class DispatchTask:
    """Contain the only safe task payload accepted by a research worker."""

    run_id: UUID
    dispatch_id: str
    contract_version: str

    def __post_init__(self) -> None:
        """Require opaque dispatch and fixed contract identifiers."""
        _require_nonempty(self.dispatch_id, "dispatch_id")
        _require_nonempty(self.contract_version, "contract_version")


@dataclass(frozen=True, slots=True)
class DispatchLease:
    """Bind an outbox delivery acknowledgement to one dispatcher lease."""

    task: DispatchTask
    dispatcher_id: str
    lease_id: UUID
    lease_expires_at: datetime

    def __post_init__(self) -> None:
        """Require a concrete dispatcher owner and expiry."""
        _require_nonempty(self.dispatcher_id, "dispatcher_id")
        _require_aware(self.lease_expires_at, "lease_expires_at")


@dataclass(frozen=True, slots=True)
class RunLease:
    """Bind a run, fence secret, and bounded execution lease together."""

    run_id: UUID
    token: ExecutionToken = field(repr=False)
    lease_expires_at: datetime
    deadline_at: datetime

    def __post_init__(self) -> None:
        """Reject a lease that can outlive its run deadline."""
        _require_aware(self.lease_expires_at, "lease_expires_at")
        _require_aware(self.deadline_at, "deadline_at")
        if self.lease_expires_at > self.deadline_at:
            raise ValueError("lease_expires_at must not exceed deadline_at")


@dataclass(frozen=True, slots=True)
class SnapshotMember:
    """Pin one evidence version and hash inside an immutable run snapshot."""

    evidence: EvidenceV1
    version: str
    content_hash: str

    def __post_init__(self) -> None:
        """Prevent a snapshot member from drifting from its evidence DTO."""
        _require_nonempty(self.version, "version")
        _require_nonempty(self.content_hash, "content_hash")
        if self.version != self.evidence.version:
            raise ValueError("snapshot version must match evidence version")
        if self.content_hash != self.evidence.content_hash:
            raise ValueError("snapshot hash must match evidence hash")


@dataclass(frozen=True, slots=True)
class SnapshotMaterialization:
    """Report the bounded set selected before snapshot freeze."""

    run_id: UUID
    member_count: int
    materialized_at: datetime

    def __post_init__(self) -> None:
        """Reject impossible materialization counts and naive timestamps."""
        if self.member_count < 0:
            raise ValueError("member_count must not be negative")
        _require_aware(self.materialized_at, "materialized_at")


@dataclass(frozen=True, slots=True)
class FrozenSnapshot:
    """Expose only the immutable, bounded projections available to S05."""

    run_id: UUID
    as_of: datetime
    frozen_at: datetime
    members: tuple[SnapshotMember, ...]

    def __post_init__(self) -> None:
        """Require a point-in-time snapshot without duplicated evidence IDs."""
        _require_aware(self.as_of, "as_of")
        _require_aware(self.frozen_at, "frozen_at")
        evidence_ids = tuple(member.evidence.evidence_id for member in self.members)
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("snapshot members must have unique evidence IDs")


@dataclass(frozen=True, slots=True)
class StepEvent:
    """Request one non-terminal, bounded worker event append."""

    type: StepEventType
    payload: RunEventPayload

    def __post_init__(self) -> None:
        """Restrict this Port to flow-step events rather than terminal transitions."""
        payload_type = type(self.payload)
        expected_names = {
            "step_started": "StepStartedEventPayloadV1",
            "evidence_added": "EvidenceAddedEventPayloadV1",
            "claim_checked": "ClaimCheckedEventPayloadV1",
        }
        if payload_type.__name__ != expected_names[self.type]:
            raise ValueError("step event payload does not match event type")


@dataclass(frozen=True, slots=True)
class ApprovedBrief:
    """Carry an S05-approved Brief across the fenced publication boundary."""

    brief: ResearchBriefV1
    model_profile_id: str
    policy_version: str
    evaluation_digest: str
    approved_at: datetime

    def __post_init__(self) -> None:
        """Require explicit approved-model and evaluation provenance."""
        _require_nonempty(self.model_profile_id, "model_profile_id")
        _require_nonempty(self.policy_version, "policy_version")
        _require_nonempty(self.evaluation_digest, "evaluation_digest")
        _require_aware(self.approved_at, "approved_at")


@dataclass(frozen=True, slots=True)
class RunFinishRequest:
    """Describe a safe non-completed terminal state requested by a worker."""

    status: TerminalRunStatus
    code: str
    cancellation_reason: str | None

    def __post_init__(self) -> None:
        """Require a stable code and cancellation reason only when applicable."""
        _require_nonempty(self.code, "code")
        if self.status == "cancelled" and not self.cancellation_reason:
            raise ValueError("cancelled runs require cancellation_reason")
        if self.status != "cancelled" and self.cancellation_reason is not None:
            raise ValueError("only cancelled runs may include cancellation_reason")


@dataclass(frozen=True, slots=True)
class RunTransition:
    """Return a safe internal summary of a committed terminal transition."""

    run_id: UUID
    status: Literal["completed", "failed", "needs_review", "cancelled"]
    occurred_at: datetime

    def __post_init__(self) -> None:
        """Require the transaction's fixed terminal timestamp."""
        _require_aware(self.occurred_at, "occurred_at")


@dataclass(frozen=True, slots=True)
class ReapedRun:
    """Report one stale run closed by the dispatcher supervisor."""

    run_id: UUID
    error_code: Literal["worker_lost", "dispatch_timeout"]
    reaped_at: datetime

    def __post_init__(self) -> None:
        """Require the supervisor's fixed reaping time."""
        _require_aware(self.reaped_at, "reaped_at")


@dataclass(frozen=True, slots=True)
class RunEventPage:
    """Return committed events with an optional opaque replay continuation."""

    run_id: UUID
    events: tuple[RunEventV1, ...]
    next_event_id: UUID | None

    def __post_init__(self) -> None:
        """Ensure the page cannot mix events from different runs."""
        if any(event.run_id != self.run_id for event in self.events):
            raise ValueError("event page must contain events for one run")
        sequences = tuple(event.seq for event in self.events)
        if sequences != tuple(sorted(sequences)):
            raise ValueError("event page sequence must be ordered")


@runtime_checkable
class ResearchDatabasePort(Protocol):
    """Expose the isolated SQLAlchemy async-session factory owned by S02-A."""

    @property
    def session_factory(self) -> ResearchAsyncSessionFactory:
        """Return the injected factory without opening a session at access time."""
        ...

    async def check_ready(self, *, now: datetime) -> LedgerReadiness:
        """Probe ledger readiness without exposing DSN or driver diagnostics."""
        ...


@runtime_checkable
class IdentityVerifierPort(Protocol):
    """Verify a bearer and create a Principal only after full validation."""

    async def verify_bearer(
        self,
        *,
        credential: BearerCredential,
        now: datetime,
    ) -> Principal:
        """Return a verified Principal or raise a safe identity DomainError."""
        ...


@runtime_checkable
class AuthorizationPort(Protocol):
    """Apply the single owner/scope/entity authorization rule everywhere."""

    def authorize_resource(
        self,
        *,
        principal: Principal,
        owner_id: UUID,
        entity_ids: frozenset[str],
        required_scope: ResearchScope,
        now: datetime,
    ) -> None:
        """Authorize access or raise a non-enumerating DomainError."""
        ...


@runtime_checkable
class EvidenceAdmissionPort(Protocol):
    """Perform deterministic policy and metadata admission without I/O."""

    def admit_evidence(
        self,
        *,
        evidence: EvidenceV1,
        policy: SourcePolicy,
        now: datetime,
    ) -> AdmittedEvidence:
        """Return admissible evidence or raise a safe policy DomainError."""
        ...


@runtime_checkable
class EvidenceRegistrationPort(Protocol):
    """Persist one already-admitted evidence version through S02-A only."""

    async def register_evidence(
        self,
        *,
        admission: AdmittedEvidence,
        now: datetime,
    ) -> EvidenceV1:
        """Atomically persist immutable evidence/policy projections or fail safely."""
        ...


@runtime_checkable
class ExecutorRegistryPort(Protocol):
    """Supply S04 heartbeat state to new-run readiness checks."""

    async def record_heartbeat(
        self,
        *,
        worker: WorkerIdentity,
        now: datetime,
    ) -> ExecutorReadiness:
        """Record a registered worker heartbeat and return the resulting readiness."""
        ...

    async def get_readiness(self, *, now: datetime) -> ExecutorReadiness:
        """Return an expiring readiness view used only by ledger create logic."""
        ...


@runtime_checkable
class OutboxPort(Protocol):
    """Expose S04's durable outbox leasing boundary without broker semantics."""

    async def claim_pending_dispatches(
        self,
        *,
        dispatcher_id: str,
        now: datetime,
        lease_duration: timedelta,
        limit: int,
    ) -> tuple[DispatchLease, ...]:
        """Lock and lease pending rows for at-least-once broker delivery."""
        ...

    async def acknowledge_dispatch(
        self,
        *,
        lease: DispatchLease,
        now: datetime,
    ) -> None:
        """Mark only the matching leased outbox row as broker-submitted."""
        ...

    async def release_dispatch(
        self,
        *,
        lease: DispatchLease,
        retry_at: datetime,
        now: datetime,
    ) -> None:
        """Release a failed delivery lease without deleting its durable task."""
        ...


@runtime_checkable
class ResearchReadPort(Protocol):
    """Serve S03 public reads through authorization and policy projections only."""

    async def search_articles(
        self,
        *,
        principal: Principal,
        request: SearchArticlesInput,
        now: datetime,
    ) -> ArticlesSearchResult:
        """Read bounded authorized evidence previews without live fetching."""
        ...

    async def get_run(
        self,
        *,
        principal: Principal,
        request: GetRunInput,
        now: datetime,
    ) -> ResearchRunViewV1:
        """Read one authorized run and redact a revoked Brief when required."""
        ...

    async def read_evidence(
        self,
        *,
        principal: Principal,
        request: GetEvidenceInput,
        now: datetime,
    ) -> EvidenceV1:
        """Read one authorized snapshot member with current-license revalidation."""
        ...

    async def get_market_snapshot(
        self,
        *,
        principal: Principal,
        request: GetMarketSnapshotInput,
        now: datetime,
    ) -> MarketPayloadV1 | None:
        """Read registered market data without provider fallback or live refresh."""
        ...

    async def read_events(
        self,
        *,
        principal: Principal,
        run_id: UUID,
        after_event_id: UUID | None,
        limit: int,
        now: datetime,
    ) -> RunEventPage:
        """Read committed bounded events after validating the run-scoped cursor."""
        ...


@runtime_checkable
class SnapshotPort(Protocol):
    """Provide the fenced immutable snapshot lifecycle consumed by S05."""

    async def materialize_snapshot(
        self,
        *,
        run_id: UUID,
        lease: RunLease,
        now: datetime,
    ) -> SnapshotMaterialization:
        """Select registered point-in-time evidence without live provider access."""
        ...

    async def freeze_snapshot(
        self,
        *,
        run_id: UUID,
        lease: RunLease,
        now: datetime,
    ) -> FrozenSnapshot:
        """Atomically freeze selected membership before worker step events append."""
        ...

    async def read_snapshot(
        self,
        *,
        run_id: UUID,
        lease: RunLease,
        now: datetime,
    ) -> FrozenSnapshot:
        """Return only the run's frozen projections to the fenced worker."""
        ...


@runtime_checkable
class ResearchLedgerPort(ResearchReadPort, SnapshotPort, Protocol):
    """Own the S02 run state machine without exposing ORM access to consumers."""

    async def create_or_reuse_run(
        self,
        *,
        principal: Principal,
        request: StartResearchInput,
        now: datetime,
    ) -> ResearchRunViewV1:
        """Atomically create a queued run or return an authorized idempotent run."""
        ...

    async def claim_run(
        self,
        *,
        task: DispatchTask,
        worker: WorkerIdentity,
        now: datetime,
    ) -> RunLease | None:
        """Claim one queued matching dispatch once or return None for a duplicate."""
        ...

    async def heartbeat_run(
        self,
        *,
        run_id: UUID,
        lease: RunLease,
        worker: WorkerIdentity,
        now: datetime,
    ) -> RunLease:
        """Renew a valid fenced lease within its fixed execution deadline."""
        ...

    async def append_step_event(
        self,
        *,
        run_id: UUID,
        lease: RunLease,
        event: StepEvent,
        now: datetime,
    ) -> RunEventV1:
        """Append one safe non-terminal event with database-assigned sequence."""
        ...

    async def publish_brief(
        self,
        *,
        run_id: UUID,
        lease: RunLease,
        approved_brief: ApprovedBrief,
        now: datetime,
    ) -> RunTransition:
        """Atomically publish one immutable approved Brief and complete the run."""
        ...

    async def finish_run(
        self,
        *,
        run_id: UUID,
        lease: RunLease,
        finish: RunFinishRequest,
        now: datetime,
    ) -> RunTransition:
        """Atomically write one allowed non-completed terminal transition."""
        ...

    async def reap_stale(
        self,
        *,
        now: datetime,
        limit: int,
    ) -> tuple[ReapedRun, ...]:
        """Fence and fail stale queued/running rows under database row locks."""
        ...
