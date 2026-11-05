"""Create the isolated research-v1.1 persistence substrate.

Revision ID: 20261030_research_v11
Revises:
Create Date: 2026-10-30 10:58:00+00:00

This is intentionally additive.  Research evidence-bearing objects are never
removed by an automated migration rollback.

Author: Damon Li
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20261030_research_v11"
down_revision = None
branch_labels = None
depends_on = None


def _timestamp_column(name: str, *, nullable: bool = False) -> sa.Column[object]:
    """Build a timezone-aware timestamp column for PostgreSQL UTC instants."""
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    """Add the research-only tables, constraints, and immutable projections."""
    op.create_table(
        "research_principal_quota",
        sa.Column("principal_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "max_concurrent_runs", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("active_run_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("daily_run_limit", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("daily_run_count", sa.Integer(), nullable=False, server_default="0"),
        _timestamp_column("window_started_at"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "max_concurrent_runs >= 0", name="research_quota_max_concurrent_check"
        ),
        sa.CheckConstraint(
            "active_run_count >= 0", name="research_quota_active_count_check"
        ),
        sa.CheckConstraint(
            "daily_run_limit >= 0", name="research_quota_daily_limit_check"
        ),
        sa.CheckConstraint(
            "daily_run_count >= 0", name="research_quota_daily_count_check"
        ),
    )
    op.create_table(
        "research_source_policy",
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("policy_version", sa.String(length=128), nullable=False),
        sa.Column("license_id", sa.String(length=128), nullable=False),
        sa.Column("terms_ref", sa.String(length=512), nullable=False),
        _timestamp_column("approved_at"),
        _timestamp_column("expires_at"),
        sa.Column("redisplay_allowed", sa.Boolean(), nullable=False),
        sa.Column("model_use_allowed", sa.Boolean(), nullable=False),
        sa.Column("storage_allowed", sa.Boolean(), nullable=False),
        sa.Column("allowed_excerpt_length", sa.Integer(), nullable=False),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint(
            "source_id", "policy_version", name="research_source_policy_pk"
        ),
        sa.CheckConstraint(
            "allowed_excerpt_length >= 0", name="research_policy_excerpt_length_check"
        ),
        sa.CheckConstraint(
            "expires_at >= approved_at", name="research_policy_time_check"
        ),
    )
    op.create_table(
        "research_evidence",
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        _timestamp_column("published_at"),
        _timestamp_column("fetched_at"),
        _timestamp_column("available_at"),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("license_scope", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.String(length=12), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("quality_status", sa.String(length=32), nullable=False),
        sa.Column("evidence_kind", sa.String(length=16), nullable=False),
        sa.Column("version", sa.String(length=128), nullable=False),
        sa.Column("source_policy_version", sa.String(length=128), nullable=False),
        sa.Column("origin", sa.String(length=16), nullable=False),
        _timestamp_column("admitted_at"),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "source_id", "version", name="research_evidence_source_version_key"
        ),
        sa.UniqueConstraint(
            "evidence_id",
            "version",
            "content_hash",
            name="research_evidence_identity_version_hash_key",
        ),
        sa.ForeignKeyConstraint(
            ["source_id", "source_policy_version"],
            [
                "research_source_policy.source_id",
                "research_source_policy.policy_version",
            ],
            name="research_evidence_source_policy_fk",
        ),
        sa.CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'", name="research_evidence_hash_check"
        ),
        sa.CheckConstraint(
            "license_scope IN ('redisplay', 'metadata_only', 'no_redisplay', 'unknown')",
            name="research_evidence_license_scope_check",
        ),
        sa.CheckConstraint(
            "quality_status IN ('verified_metadata', 'incomplete', 'rejected')",
            name="research_evidence_quality_status_check",
        ),
        sa.CheckConstraint(
            "evidence_kind IN ('event', 'market')", name="research_evidence_kind_check"
        ),
        sa.CheckConstraint(
            "origin IN ('live', 'fixture')", name="research_evidence_origin_check"
        ),
        sa.CheckConstraint(
            "fetched_at >= available_at", name="research_evidence_fetch_time_check"
        ),
        sa.CheckConstraint(
            "published_at <= available_at", name="research_evidence_publish_time_check"
        ),
    )
    op.create_table(
        "research_market_payload",
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("symbol", sa.String(length=12), nullable=False),
        _timestamp_column("observed_at"),
        _timestamp_column("available_at"),
        _timestamp_column("fetched_at"),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("adjustment", sa.String(length=16), nullable=False),
        sa.Column(
            "fields_projection", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("provider", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=128), nullable=False),
        sa.Column("is_mock", sa.Boolean(), nullable=False),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id"],
            ["research_evidence.evidence_id"],
            name="research_market_evidence_fk",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "adjustment IN ('none', 'forward', 'backward')",
            name="research_market_adjustment_check",
        ),
        sa.CheckConstraint(
            "available_at <= fetched_at", name="research_market_time_check"
        ),
    )
    op.create_table(
        "research_run",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("principal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", sa.String(length=12), nullable=False),
        sa.Column("seed_evidence_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        _timestamp_column("as_of"),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "snapshot_state",
            sa.String(length=16),
            nullable=False,
            server_default="none",
        ),
        sa.Column("policy_version", sa.String(length=128), nullable=False),
        sa.Column("prompt_version", sa.String(length=128), nullable=False),
        sa.Column("model_id", sa.String(length=128), nullable=True),
        sa.Column("result_ref", sa.String(length=512), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("execution_token_hash", sa.String(length=64), nullable=True),
        sa.Column("execution_worker_id", sa.String(length=128), nullable=True),
        _timestamp_column("lease_expires_at", nullable=True),
        _timestamp_column("deadline_at", nullable=True),
        _timestamp_column("snapshot_frozen_at", nullable=True),
        _timestamp_column("created_at"),
        _timestamp_column("updated_at"),
        sa.UniqueConstraint(
            "principal_id", "request_id", name="research_run_principal_request_key"
        ),
        sa.ForeignKeyConstraint(
            ["seed_evidence_id"],
            ["research_evidence.evidence_id"],
            name="research_run_seed_evidence_fk",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'needs_review', 'cancelled')",
            name="research_run_status_check",
        ),
        sa.CheckConstraint(
            "snapshot_state IN ('none', 'materialized', 'frozen')",
            name="research_run_snapshot_state_check",
        ),
        sa.CheckConstraint(
            "updated_at >= created_at", name="research_run_update_time_check"
        ),
        sa.CheckConstraint(
            "execution_token_hash IS NULL OR execution_token_hash ~ '^[0-9a-f]{64}$'",
            name="research_run_execution_token_hash_check",
        ),
    )
    op.create_table(
        "research_snapshot_member",
        sa.Column(
            "snapshot_member_id", postgresql.UUID(as_uuid=True), primary_key=True
        ),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_version", sa.String(length=128), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        _timestamp_column("selected_at"),
        sa.UniqueConstraint(
            "run_id", "evidence_id", name="research_snapshot_run_evidence_key"
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["research_run.run_id"],
            name="research_snapshot_run_fk",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id", "evidence_version", "content_hash"],
            [
                "research_evidence.evidence_id",
                "research_evidence.version",
                "research_evidence.content_hash",
            ],
            name="research_snapshot_evidence_identity_fk",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'", name="research_snapshot_hash_check"
        ),
    )
    op.create_table(
        "research_brief",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), primary_key=True),
        _timestamp_column("as_of"),
        sa.Column(
            "brief_projection", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("model_profile_id", sa.String(length=128), nullable=False),
        sa.Column("policy_version", sa.String(length=128), nullable=False),
        sa.Column("evaluation_digest", sa.String(length=64), nullable=False),
        sa.Column("result_ref", sa.String(length=512), nullable=False, unique=True),
        _timestamp_column("approved_at"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["research_run.run_id"],
            name="research_brief_run_fk",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "evaluation_digest ~ '^[0-9a-f]{64}$'",
            name="research_brief_evaluation_digest_check",
        ),
    )
    op.create_table(
        "research_brief_citation",
        sa.Column("citation_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=False),
        _timestamp_column("created_at"),
        sa.UniqueConstraint(
            "run_id",
            "claim_id",
            "evidence_id",
            name="research_citation_claim_evidence_key",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["research_brief.run_id"],
            name="research_citation_brief_run_fk",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "evidence_id"],
            ["research_snapshot_member.run_id", "research_snapshot_member.evidence_id"],
            name="research_citation_snapshot_member_fk",
        ),
    )
    op.create_table(
        "research_run_event",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        _timestamp_column("occurred_at"),
        sa.Column(
            "payload_projection",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.UniqueConstraint("run_id", "seq", name="research_event_run_seq_key"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["research_run.run_id"],
            name="research_event_run_fk",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("seq >= 1", name="research_event_seq_check"),
        sa.CheckConstraint(
            "event_type IN ('started', 'step_started', 'evidence_added', 'claim_checked', "
            "'needs_review', 'completed', 'failed', 'cancelled')",
            name="research_event_type_check",
        ),
    )
    op.create_table(
        "research_audit",
        sa.Column("audit_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("principal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("safe_code", sa.String(length=128), nullable=True),
        sa.Column(
            "details_projection",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        _timestamp_column("occurred_at"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["research_run.run_id"],
            name="research_audit_run_fk",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id"],
            ["research_evidence.evidence_id"],
            name="research_audit_evidence_fk",
            ondelete="RESTRICT",
        ),
    )
    op.create_table(
        "research_outbox",
        sa.Column("outbox_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dispatch_id", sa.String(length=128), nullable=False),
        sa.Column("contract_version", sa.String(length=128), nullable=False),
        sa.Column("delivery_status", sa.String(length=16), nullable=False),
        _timestamp_column("available_at"),
        sa.Column("lease_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("dispatcher_id", sa.String(length=128), nullable=True),
        _timestamp_column("lease_expires_at", nullable=True),
        _timestamp_column("submitted_at", nullable=True),
        _timestamp_column("created_at"),
        sa.UniqueConstraint(
            "run_id", "dispatch_id", name="research_outbox_run_dispatch_key"
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["research_run.run_id"],
            name="research_outbox_run_fk",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "delivery_status IN ('pending', 'leased', 'submitted')",
            name="research_outbox_status_check",
        ),
    )
    op.create_table(
        "research_worker_heartbeat",
        sa.Column("worker_id", sa.String(length=128), primary_key=True),
        sa.Column("queue_name", sa.String(length=128), nullable=False),
        sa.Column("contract_version", sa.String(length=128), nullable=False),
        sa.Column("worker_status", sa.String(length=16), nullable=False),
        _timestamp_column("heartbeat_at"),
        _timestamp_column("expires_at"),
        sa.CheckConstraint(
            "worker_status IN ('active', 'inactive')",
            name="research_worker_status_check",
        ),
        sa.CheckConstraint(
            "expires_at >= heartbeat_at", name="research_worker_expiry_check"
        ),
    )
    op.execute(
        """
        CREATE FUNCTION research_reject_immutable_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'immutable research projection cannot be modified'
                USING ERRCODE = '55000';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE FUNCTION research_check_market_evidence_pair()
        RETURNS trigger AS $$
        DECLARE
            checked_evidence_id uuid;
            evidence_type text;
            payload_exists boolean;
        BEGIN
            IF TG_TABLE_NAME = 'research_evidence' THEN
                checked_evidence_id := COALESCE(NEW.evidence_id, OLD.evidence_id);
            ELSE
                checked_evidence_id := COALESCE(NEW.evidence_id, OLD.evidence_id);
            END IF;
            SELECT evidence_kind INTO evidence_type
              FROM research_evidence WHERE evidence_id = checked_evidence_id;
            SELECT EXISTS (
                SELECT 1 FROM research_market_payload WHERE evidence_id = checked_evidence_id
            ) INTO payload_exists;
            IF (evidence_type = 'market' AND NOT payload_exists)
               OR (evidence_type IS DISTINCT FROM 'market' AND payload_exists) THEN
                RAISE EXCEPTION 'research evidence and market payload must match'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER research_evidence_market_pair_check
        AFTER INSERT OR UPDATE ON research_evidence
        DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
        EXECUTE FUNCTION research_check_market_evidence_pair()
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER research_payload_market_pair_check
        AFTER INSERT OR UPDATE OR DELETE ON research_market_payload
        DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
        EXECUTE FUNCTION research_check_market_evidence_pair()
        """
    )
    op.execute(
        """
        CREATE TRIGGER research_source_policy_immutable
        BEFORE UPDATE OR DELETE ON research_source_policy
        FOR EACH ROW EXECUTE FUNCTION research_reject_immutable_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER research_evidence_immutable
        BEFORE UPDATE OR DELETE ON research_evidence
        FOR EACH ROW EXECUTE FUNCTION research_reject_immutable_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER research_brief_immutable
        BEFORE UPDATE OR DELETE ON research_brief
        FOR EACH ROW EXECUTE FUNCTION research_reject_immutable_mutation()
        """
    )


def downgrade() -> None:
    """Keep evidence-bearing objects intact; operational rollback disables research."""
    raise RuntimeError("research migrations do not support automatic downgrade")
