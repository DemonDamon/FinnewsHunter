"""Acceptance tests for pure evidence admission and registry handoff.

The recorder is intentionally Protocol-shaped and in-memory: no database,
provider, model, or network capability is used by these tests.

Author: Damon Li
"""

from __future__ import annotations

import ast
import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from app.research.contracts import EvidenceV1, MarketPayloadV1
from app.research.errors import DomainError
from app.research.evidence import (
    DeterministicEvidenceAdmission,
    EvidenceRegistrationService,
)
from app.research.ports import AdmittedEvidence, SourcePolicy

NOW = datetime(2026, 10, 30, 2, 0, tzinfo=UTC)
EVIDENCE_ID = UUID("33333333-3333-3333-3333-333333333333")
ENTITY_ID = "CN.SH.600519"
EXCERPT_SENTINEL = "restricted-excerpt-sentinel-must-not-reach-diagnostics"
HOST = "approved-source.example.test"


def _admission() -> DeterministicEvidenceAdmission:
    """Test helper for _admission."""
    return DeterministicEvidenceAdmission(
        approved_source_hosts={"approved-source": {HOST}}
    )


class ProtocolRecorder:
    """Record injected registry calls and model same-version idempotent behavior."""

    def __init__(self) -> None:
        """Start with no registered version and no database substitute."""
        self.calls: list[AdmittedEvidence] = []
        self._registered: EvidenceV1 | None = None

    async def register_evidence(
        self,
        *,
        admission: AdmittedEvidence,
        now: datetime,
    ) -> EvidenceV1:
        """Store the first version exactly and return it for same-version retries."""
        assert now == NOW
        self.calls.append(admission)
        if self._registered is None:
            self._registered = admission.evidence
        return self._registered


def _policy(**updates: object) -> SourcePolicy:
    """Return an active test-only source policy with explicit production permissions."""
    values: dict[str, object] = {
        "source_id": "approved-source",
        "policy_version": "policy-v1",
        "license_id": "approved-license",
        "terms_ref": "terms-2026-10",
        "approved_at": NOW - timedelta(days=1),
        "expires_at": NOW + timedelta(days=1),
        "redisplay_allowed": False,
        "model_use_allowed": True,
        "storage_allowed": True,
        "allowed_excerpt_length": 4000,
    }
    values.update(updates)
    return SourcePolicy(**values)  # type: ignore[arg-type]


def _event_evidence(**updates: object) -> EvidenceV1:
    """Build live verified event evidence without using a source fixture."""
    values: dict[str, object] = {
        "evidence_id": EVIDENCE_ID,
        "source_id": "approved-source",
        "source_url": "https://approved-source.example.test/evidence/one",
        "content_hash": "a" * 64,
        "published_at": NOW - timedelta(minutes=5),
        "fetched_at": NOW - timedelta(minutes=3),
        "available_at": NOW - timedelta(minutes=4),
        "timezone": "UTC",
        "license_scope": "metadata_only",
        "entity_ids": [ENTITY_ID],
        "excerpt": EXCERPT_SENTINEL,
        "quality_status": "verified_metadata",
        "evidence_kind": "event",
        "version": "event-v1",
        "source_policy_version": "policy-v1",
        "origin": "live",
        "market_payload": None,
    }
    values.update(updates)
    return EvidenceV1.model_validate(values)


def _market_evidence(**updates: object) -> EvidenceV1:
    """Build traceable live market evidence with required non-mock semantics."""
    market = MarketPayloadV1.model_validate(
        {
            "evidence_id": EVIDENCE_ID,
            "symbol": ENTITY_ID,
            "observed_at": NOW - timedelta(minutes=5),
            "available_at": NOW - timedelta(minutes=4),
            "fetched_at": NOW - timedelta(minutes=3),
            "timezone": "UTC",
            "currency": "CNY",
            "adjustment": "forward",
            "fields": [{"name": "close", "value": "123.45", "unit": "CNY"}],
            "provider": "approved-source",
            "version": "market-v1",
            "is_mock": False,
        }
    )
    values: dict[str, object] = {
        "evidence_id": EVIDENCE_ID,
        "source_id": "approved-source",
        "source_url": "https://approved-source.example.test/market/one",
        "content_hash": "c" * 64,
        "published_at": NOW - timedelta(minutes=5),
        "fetched_at": NOW - timedelta(minutes=3),
        "available_at": NOW - timedelta(minutes=4),
        "timezone": "UTC",
        "license_scope": "metadata_only",
        "entity_ids": [ENTITY_ID],
        "excerpt": EXCERPT_SENTINEL,
        "quality_status": "verified_metadata",
        "evidence_kind": "market",
        "version": "market-v1",
        "source_policy_version": "policy-v1",
        "origin": "live",
        "market_payload": market,
    }
    values.update(updates)
    return EvidenceV1.model_validate(values)


def _register(
    service: EvidenceRegistrationService,
    *,
    evidence: EvidenceV1,
    policy: SourcePolicy,
) -> EvidenceV1:
    """Run one async registration through the service with the fixed clock."""
    return asyncio.run(
        service.register_evidence(evidence=evidence, policy=policy, now=NOW)
    )


def test_live_verified_policy_admits_and_calls_registry_once() -> None:
    """AC-B4: valid live evidence passes pure admission then reaches registry once."""
    recorder = ProtocolRecorder()
    service = EvidenceRegistrationService(
        admission=_admission(),
        registry=recorder,
    )
    evidence = _market_evidence(excerpt="ok")

    registered = _register(
        service,
        evidence=evidence,
        policy=_policy(redisplay_allowed=True, allowed_excerpt_length=16),
    )

    assert registered is evidence
    assert len(recorder.calls) == 1
    admission = recorder.calls[0]
    assert admission.evidence is evidence
    assert admission.evidence.available_at == evidence.available_at
    assert admission.evidence.content_hash == evidence.content_hash
    assert admission.evidence.version == evidence.version
    assert admission.admitted_at == NOW


def test_ineligible_evidence_never_calls_registry() -> None:
    """AC-B5: every malformed policy, evidence, or market input stops pre-registry."""
    admission = _admission()
    recorder = ProtocolRecorder()
    service = EvidenceRegistrationService(admission=admission, registry=recorder)
    event = _event_evidence()
    market = _market_evidence()
    bad_chronology = event.model_copy(
        update={"fetched_at": event.available_at - timedelta(seconds=1)}
    )
    mock_market = market.model_copy(
        update={
            "market_payload": market.market_payload.model_copy(update={"is_mock": True})
        }
    )
    no_currency = market.model_copy(
        update={
            "market_payload": market.market_payload.model_copy(update={"currency": ""})
        }
    )
    no_unit_field = market.market_payload.fields[0].model_copy(update={"unit": ""})
    no_unit = market.model_copy(
        update={
            "market_payload": market.market_payload.model_copy(
                update={"fields": [no_unit_field]}
            )
        }
    )
    no_adjustment = market.model_copy(
        update={
            "market_payload": market.market_payload.model_copy(
                update={"adjustment": "unadjusted"}
            )
        }
    )

    cases: list[tuple[object, SourcePolicy]] = [
        (event.model_copy(update={"origin": "fixture"}), _policy()),
        (event.model_copy(update={"quality_status": "incomplete"}), _policy()),
        (event.model_copy(update={"quality_status": "rejected"}), _policy()),
        (event, _policy(source_id="unknown-source")),
        (event.model_copy(update={"source_policy_version": "policy-v2"}), _policy()),
        (event, _policy(expires_at=NOW)),
        (event, _policy(model_use_allowed=False)),
        (event, _policy(storage_allowed=False)),
        (bad_chronology, _policy()),
        (mock_market, _policy()),
        (no_currency, _policy()),
        (no_unit, _policy()),
        (no_adjustment, _policy()),
        (object(), _policy()),
    ]

    for candidate, policy in cases:
        with pytest.raises(DomainError) as raised:
            _register(service, evidence=candidate, policy=policy)  # type: ignore[arg-type]
        assert raised.value.code in {"evidence_ineligible", "market_data_unverifiable"}
        assert EXCERPT_SENTINEL not in raised.value.safe_message
        assert EXCERPT_SENTINEL not in str(raised.value)

    assert recorder.calls == []


def test_same_version_never_moves_available_at_or_leaks_excerpt() -> None:
    """AC-B6: the injected registry preserves first version provenance and diagnostics."""
    recorder = ProtocolRecorder()
    service = EvidenceRegistrationService(
        admission=_admission(),
        registry=recorder,
    )
    first = _event_evidence(excerpt="ok")
    changed_retry = first.model_copy(
        update={
            "content_hash": "b" * 64,
            "available_at": first.available_at - timedelta(seconds=30),
        }
    )

    initial_registered = _register(
        service,
        evidence=first,
        policy=_policy(redisplay_allowed=True, allowed_excerpt_length=16),
    )
    retry_registered = _register(
        service,
        evidence=changed_retry,
        policy=_policy(redisplay_allowed=True, allowed_excerpt_length=16),
    )

    assert len(recorder.calls) == 2
    assert initial_registered is first
    assert retry_registered is first
    assert retry_registered.available_at == first.available_at
    assert retry_registered.content_hash == first.content_hash
    assert retry_registered.version == first.version

    rejected = first.model_copy(update={"origin": "fixture"})
    with pytest.raises(DomainError) as raised:
        _register(service, evidence=rejected, policy=_policy())
    safe_diagnostic = raised.value.as_contract_error().model_dump_json()
    assert EXCERPT_SENTINEL not in safe_diagnostic
    assert EXCERPT_SENTINEL not in raised.value.safe_message
    assert EXCERPT_SENTINEL not in str(raised.value)


def test_admission_has_no_orm_or_provider_dependency() -> None:
    """AC-B7: pure admission imports no persistence, provider, or network surface."""
    import app.research.evidence as evidence_module

    source = Path(evidence_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    forbidden_prefixes = (
        "sqlalchemy",
        "app.models",
        "models",
        "requests",
        "httpx",
        "aiohttp",
        "urllib",
    )
    assert not any(
        imported == prefix or imported.startswith(f"{prefix}.")
        for imported in imported_names
        for prefix in forbidden_prefixes
    )

    admitted = _admission().admit_evidence(
        evidence=_event_evidence(excerpt="ok"),
        policy=_policy(redisplay_allowed=True, allowed_excerpt_length=16),
        now=NOW,
    )
    assert admitted.evidence.available_at == NOW - timedelta(minutes=4)


def test_source_host_policy_is_exact_frozen_and_fail_closed() -> None:
    """Test helper test_source_host_policy_is_exact_frozen_and_fail_closed."""
    hosts = {"approved-source": {HOST}}
    admission = DeterministicEvidenceAdmission(approved_source_hosts=hosts)
    hosts["approved-source"].add("attacker.example.test")
    hosts["other"] = {HOST}
    for url in (
        "https://attacker.example.test/fake",
        "https://sub.approved-source.example.test/fake",
        "https://approved-source.example.test@attacker.example.test/fake",
        "https://approved-source.example.test:444/fake",
    ):
        with pytest.raises(DomainError):
            admission.admit_evidence(
                evidence=_event_evidence(excerpt="ok", source_url=url),
                policy=_policy(redisplay_allowed=True, allowed_excerpt_length=16),
                now=NOW,
            )
    admission.admit_evidence(
        evidence=_event_evidence(excerpt="ok"),
        policy=_policy(redisplay_allowed=True, allowed_excerpt_length=16),
        now=NOW,
    )
    admission.admit_evidence(
        evidence=_event_evidence(
            excerpt="ok",
            source_url="https://approved-source.example.test./evidence/one",
        ),
        policy=_policy(redisplay_allowed=True, allowed_excerpt_length=16),
        now=NOW,
    )
    idna_admission = DeterministicEvidenceAdmission(
        approved_source_hosts={"approved-source": {"xn--bcher-kva.example.test"}}
    )
    idna_admission.admit_evidence(
        evidence=_event_evidence(
            excerpt="ok",
            source_url="https://xn--bcher-kva.example.test/evidence/one",
        ),
        policy=_policy(redisplay_allowed=True, allowed_excerpt_length=16),
        now=NOW,
    )
    unicode_policy = DeterministicEvidenceAdmission(
        approved_source_hosts={"approved-source": {"fass.example.test"}}
    )
    with pytest.raises(DomainError):
        unicode_policy.admit_evidence(
            evidence=_event_evidence(
                excerpt="ok", source_url="https://faß.example.test/evidence/one"
            ),
            policy=_policy(redisplay_allowed=True, allowed_excerpt_length=16),
            now=NOW,
        )
    with pytest.raises(DomainError):
        DeterministicEvidenceAdmission().admit_evidence(
            evidence=_event_evidence(excerpt="ok"),
            policy=_policy(redisplay_allowed=True, allowed_excerpt_length=16),
            now=NOW,
        )


def test_excerpt_policy_and_market_consistency_are_enforced() -> None:
    """Test helper test_excerpt_policy_and_market_consistency_are_enforced."""
    admission = _admission()
    for ev, pol in (
        (_event_evidence(), _policy()),
        (
            _event_evidence(excerpt="12345"),
            _policy(redisplay_allowed=True, allowed_excerpt_length=4),
        ),
    ):
        with pytest.raises(DomainError):
            admission.admit_evidence(evidence=ev, policy=pol, now=NOW)
    market = _market_evidence(excerpt="ok")
    for payload_update in (
        {"provider": "attacker"},
        {"version": "other"},
        {"observed_at": NOW},
    ):
        candidate = market.model_copy(
            update={
                "market_payload": market.market_payload.model_copy(
                    update=payload_update
                )
            }
        )
        with pytest.raises(DomainError):
            admission.admit_evidence(
                evidence=candidate,
                policy=_policy(redisplay_allowed=True, allowed_excerpt_length=16),
                now=NOW,
            )
