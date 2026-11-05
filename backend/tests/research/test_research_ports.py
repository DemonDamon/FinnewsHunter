"""Test the frozen internal research Port boundary.

Author: Damon Li
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from inspect import signature
from pathlib import Path

import pytest
from app.research.errors import DomainError
from app.research.ports import (
    AuthorizationPort,
    BearerCredential,
    EvidenceAdmissionPort,
    EvidenceRegistrationPort,
    ExecutionToken,
    ExecutorRegistryPort,
    IdentityVerifierPort,
    OutboxPort,
    Principal,
    ResearchDatabasePort,
    ResearchLedgerPort,
    ResearchReadPort,
    SnapshotPort,
    SourcePolicy,
)

TEST_NOW = datetime(2026, 10, 30, 1, 0, tzinfo=UTC)


def _principal() -> Principal:
    """Build a verified-shaped test Principal without a bearer or API payload."""
    return Principal(
        principal_id=__import__("uuid").UUID("11111111-1111-1111-1111-111111111111"),
        scopes=frozenset({"research:read"}),
        entity_ids=frozenset({"CN.SH.600519"}),
        issuer="https://issuer.example.test",
        audience="finnews-research",
        expires_at=TEST_NOW,
    )


def test_ports_import_without_engine_constructor_or_environment_read() -> None:
    """Keep the frozen module declarative and independent from runtime setup."""
    from app.research import ports

    source = Path(ports.__file__).read_text(encoding="utf-8")
    assert "create_async_engine" not in source
    assert "os.environ" not in source
    assert "create_all" not in source
    assert "requests." not in source
    assert "httpx." not in source


def test_protocols_remain_protocols_with_explicit_boundary_signatures() -> None:
    """Freeze required S02/S03/S04/S05 method names and parameter order."""
    protocols = (
        ResearchDatabasePort,
        IdentityVerifierPort,
        AuthorizationPort,
        EvidenceAdmissionPort,
        EvidenceRegistrationPort,
        ExecutorRegistryPort,
        OutboxPort,
        ResearchReadPort,
        SnapshotPort,
        ResearchLedgerPort,
    )
    assert all(protocol._is_protocol for protocol in protocols)

    assert list(signature(AuthorizationPort.authorize_resource).parameters) == [
        "self",
        "principal",
        "owner_id",
        "entity_ids",
        "required_scope",
        "now",
    ]
    assert list(signature(ResearchLedgerPort.create_or_reuse_run).parameters) == [
        "self",
        "principal",
        "request",
        "now",
    ]
    assert list(signature(ResearchLedgerPort.claim_run).parameters) == [
        "self",
        "task",
        "worker",
        "now",
    ]
    assert list(signature(ResearchLedgerPort.heartbeat_run).parameters) == [
        "self",
        "run_id",
        "lease",
        "worker",
        "now",
    ]
    assert list(signature(ResearchLedgerPort.append_step_event).parameters) == [
        "self",
        "run_id",
        "lease",
        "event",
        "now",
    ]
    assert list(signature(ResearchLedgerPort.publish_brief).parameters) == [
        "self",
        "run_id",
        "lease",
        "approved_brief",
        "now",
    ]
    assert list(signature(ResearchLedgerPort.finish_run).parameters) == [
        "self",
        "run_id",
        "lease",
        "finish",
        "now",
    ]
    assert list(signature(ResearchLedgerPort.reap_stale).parameters) == [
        "self",
        "now",
        "limit",
    ]
    assert list(signature(SnapshotPort.materialize_snapshot).parameters) == [
        "self",
        "run_id",
        "lease",
        "now",
    ]
    assert list(signature(SnapshotPort.freeze_snapshot).parameters) == [
        "self",
        "run_id",
        "lease",
        "now",
    ]
    assert list(signature(SnapshotPort.read_snapshot).parameters) == [
        "self",
        "run_id",
        "lease",
        "now",
    ]
    assert list(signature(ResearchReadPort.read_evidence).parameters) == [
        "self",
        "principal",
        "request",
        "now",
    ]


def test_principal_and_policy_are_frozen_and_complete() -> None:
    """Keep caller-provided mutable identity and policy structures out of Ports."""
    principal = _principal()
    policy = SourcePolicy(
        source_id="approved_event_source",
        policy_version="v1",
        license_id="license-1",
        terms_ref="terms-2026-10",
        approved_at=TEST_NOW,
        expires_at=datetime(2026, 11, 1, tzinfo=UTC),
        redisplay_allowed=True,
        model_use_allowed=True,
        storage_allowed=True,
        allowed_excerpt_length=4000,
    )

    with pytest.raises(FrozenInstanceError):
        principal.issuer = "client-supplied-issuer"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        policy.license_id = "client-supplied-license"  # type: ignore[misc]


def test_secret_value_objects_do_not_render_raw_material() -> None:
    """Ensure bearer and execution secrets cannot cross ordinary diagnostics."""
    bearer = BearerCredential("header.payload.signature")
    execution_token = ExecutionToken(b"not-for-log-output")

    assert "header.payload.signature" not in repr(bearer)
    assert "header.payload.signature" not in str(bearer)
    assert "not-for-log-output" not in repr(execution_token)
    assert "not-for-log-output" not in str(execution_token)
    assert len(execution_token.fingerprint()) == 64


def test_domain_error_keeps_a_stable_safe_contract_projection() -> None:
    """Allow transport adapters to project only stable non-sensitive failures."""
    error = DomainError(
        code="execution_unavailable",
        safe_message="research execution is unavailable",
        retryable=True,
    )

    assert str(error) == "execution_unavailable"
    assert error.as_contract_error().model_dump() == {
        "code": "execution_unavailable",
        "message": "research execution is unavailable",
        "retryable": True,
    }
