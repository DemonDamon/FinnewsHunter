"""Declare isolated ORM projections for the research PostgreSQL ledger.

The models contain no engine, session, configuration, or legacy application
imports.  They are intentionally a storage substrate; ledger state transitions
belong to the later C implementation.

Author: Damon Li
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class ResearchBase(DeclarativeBase):
    """Own metadata exclusively for ``research_`` PostgreSQL tables."""


class ResearchPrincipalQuota(ResearchBase):
    """Persist principal-local quota and active-run concurrency accounting."""

    __tablename__ = "research_principal_quota"
    __table_args__ = (
        CheckConstraint(
            "max_concurrent_runs >= 0", name="research_quota_max_concurrent_check"
        ),
        CheckConstraint(
            "active_run_count >= 0", name="research_quota_active_count_check"
        ),
        CheckConstraint(
            "daily_run_limit >= 0", name="research_quota_daily_limit_check"
        ),
        CheckConstraint(
            "daily_run_count >= 0", name="research_quota_daily_count_check"
        ),
    )

    principal_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    max_concurrent_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_run_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    daily_run_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    daily_run_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    window_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResearchSourcePolicy(ResearchBase):
    """Persist the immutable human-approved policy projection for a source version."""

    __tablename__ = "research_source_policy"
    __table_args__ = (
        PrimaryKeyConstraint(
            "source_id", "policy_version", name="research_source_policy_pk"
        ),
        CheckConstraint(
            "allowed_excerpt_length >= 0", name="research_policy_excerpt_length_check"
        ),
        CheckConstraint("expires_at >= approved_at", name="research_policy_time_check"),
    )

    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    license_id: Mapped[str] = mapped_column(String(128), nullable=False)
    terms_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    redisplay_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    model_use_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    storage_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    allowed_excerpt_length: Mapped[int] = mapped_column(Integer, nullable=False)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResearchEvidence(ResearchBase):
    """Persist one immutable, admitted evidence version and bounded projection."""

    __tablename__ = "research_evidence"
    __table_args__ = (
        UniqueConstraint(
            "source_id", "version", name="research_evidence_source_version_key"
        ),
        UniqueConstraint(
            "evidence_id",
            "version",
            "content_hash",
            name="research_evidence_identity_version_hash_key",
        ),
        ForeignKeyConstraint(
            ["source_id", "source_policy_version"],
            [
                "research_source_policy.source_id",
                "research_source_policy.policy_version",
            ],
            name="research_evidence_source_policy_fk",
        ),
        CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'", name="research_evidence_hash_check"
        ),
        CheckConstraint(
            "license_scope IN ('redisplay', 'metadata_only', 'no_redisplay', 'unknown')",
            name="research_evidence_license_scope_check",
        ),
        CheckConstraint(
            "quality_status IN ('verified_metadata', 'incomplete', 'rejected')",
            name="research_evidence_quality_status_check",
        ),
        CheckConstraint(
            "evidence_kind IN ('event', 'market')", name="research_evidence_kind_check"
        ),
        CheckConstraint(
            "origin IN ('live', 'fixture')", name="research_evidence_origin_check"
        ),
        CheckConstraint(
            "fetched_at >= available_at", name="research_evidence_fetch_time_check"
        ),
        CheckConstraint(
            "published_at <= available_at", name="research_evidence_publish_time_check"
        ),
    )

    evidence_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    license_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(12), nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    quality_status: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    version: Mapped[str] = mapped_column(String(128), nullable=False)
    source_policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    admitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResearchMarketPayload(ResearchBase):
    """Persist the one bounded market projection linked to market evidence."""

    __tablename__ = "research_market_payload"
    __table_args__ = (
        CheckConstraint(
            "adjustment IN ('none', 'forward', 'backward')",
            name="research_market_adjustment_check",
        ),
        CheckConstraint(
            "available_at <= fetched_at", name="research_market_time_check"
        ),
    )

    evidence_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("research_evidence.evidence_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    symbol: Mapped[str] = mapped_column(String(12), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    adjustment: Mapped[str] = mapped_column(String(16), nullable=False)
    fields_projection: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(128), nullable=False)
    is_mock: Mapped[bool] = mapped_column(Boolean, nullable=False)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResearchRun(ResearchBase):
    """Reserve ledger-owned run state and execution fence storage for C."""

    __tablename__ = "research_run"
    __table_args__ = (
        UniqueConstraint(
            "principal_id", "request_id", name="research_run_principal_request_key"
        ),
        ForeignKeyConstraint(
            ["seed_evidence_id"],
            ["research_evidence.evidence_id"],
            name="research_run_seed_evidence_fk",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'needs_review', 'cancelled')",
            name="research_run_status_check",
        ),
        CheckConstraint(
            "snapshot_state IN ('none', 'materialized', 'frozen')",
            name="research_run_snapshot_state_check",
        ),
        CheckConstraint(
            "updated_at >= created_at", name="research_run_update_time_check"
        ),
    )

    run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    request_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    principal_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(12), nullable=False)
    seed_evidence_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    snapshot_state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="none"
    )
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(128), nullable=False)
    model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    result_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    execution_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    execution_worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    snapshot_frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ResearchSnapshotMember(ResearchBase):
    """Pin an evidence hash/version inside one run's immutable snapshot."""

    __tablename__ = "research_snapshot_member"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "evidence_id", name="research_snapshot_run_evidence_key"
        ),
        ForeignKeyConstraint(
            ["evidence_id", "evidence_version", "content_hash"],
            [
                "research_evidence.evidence_id",
                "research_evidence.version",
                "research_evidence.content_hash",
            ],
            name="research_snapshot_evidence_identity_fk",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'", name="research_snapshot_hash_check"
        ),
    )

    snapshot_member_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True
    )
    run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("research_run.run_id", ondelete="RESTRICT"),
        nullable=False,
    )
    evidence_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    evidence_version: Mapped[str] = mapped_column(String(128), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    selected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ResearchBrief(ResearchBase):
    """Persist the single immutable approved Brief projection for a run."""

    __tablename__ = "research_brief"

    run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("research_run.run_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    brief_projection: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    model_profile_id: Mapped[str] = mapped_column(String(128), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    evaluation_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    result_ref: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ResearchBriefCitation(ResearchBase):
    """Constrain each stored Brief citation to a member of the same run snapshot."""

    __tablename__ = "research_brief_citation"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "claim_id",
            "evidence_id",
            name="research_citation_claim_evidence_key",
        ),
        ForeignKeyConstraint(
            ["run_id", "evidence_id"],
            ["research_snapshot_member.run_id", "research_snapshot_member.evidence_id"],
            name="research_citation_snapshot_member_fk",
        ),
    )

    citation_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("research_brief.run_id", ondelete="RESTRICT"),
        nullable=False,
    )
    claim_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    evidence_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ResearchRunEvent(ResearchBase):
    """Persist globally identified, sequential, bounded run event projections."""

    __tablename__ = "research_run_event"
    __table_args__ = (
        UniqueConstraint("run_id", "seq", name="research_event_run_seq_key"),
        CheckConstraint("seq >= 1", name="research_event_seq_check"),
        CheckConstraint(
            "event_type IN ('started', 'step_started', 'evidence_added', 'claim_checked', "
            "'needs_review', 'completed', 'failed', 'cancelled')",
            name="research_event_type_check",
        ),
    )

    event_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("research_run.run_id", ondelete="RESTRICT"),
        nullable=False,
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    payload_projection: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class ResearchAudit(ResearchBase):
    """Retain only IDs and bounded safe audit metadata, never bodies or secrets."""

    __tablename__ = "research_audit"

    audit_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    run_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("research_run.run_id", ondelete="RESTRICT"),
        nullable=True,
    )
    evidence_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("research_evidence.evidence_id", ondelete="RESTRICT"),
        nullable=True,
    )
    principal_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    safe_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    details_projection: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ResearchOutbox(ResearchBase):
    """Reserve durable dispatch leasing state for the later S04 dispatcher."""

    __tablename__ = "research_outbox"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "dispatch_id", name="research_outbox_run_dispatch_key"
        ),
        CheckConstraint(
            "delivery_status IN ('pending', 'leased', 'submitted')",
            name="research_outbox_status_check",
        ),
    )

    outbox_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("research_run.run_id", ondelete="RESTRICT"),
        nullable=False,
    )
    dispatch_id: Mapped[str] = mapped_column(String(128), nullable=False)
    contract_version: Mapped[str] = mapped_column(String(128), nullable=False)
    delivery_status: Mapped[str] = mapped_column(String(16), nullable=False)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    lease_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    dispatcher_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ResearchWorkerHeartbeat(ResearchBase):
    """Reserve persisted registered-worker heartbeat state for S04 readiness."""

    __tablename__ = "research_worker_heartbeat"
    __table_args__ = (
        CheckConstraint(
            "worker_status IN ('active', 'inactive')",
            name="research_worker_status_check",
        ),
        CheckConstraint(
            "expires_at >= heartbeat_at", name="research_worker_expiry_check"
        ),
    )

    worker_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    queue_name: Mapped[str] = mapped_column(String(128), nullable=False)
    contract_version: Mapped[str] = mapped_column(String(128), nullable=False)
    worker_status: Mapped[str] = mapped_column(String(16), nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
