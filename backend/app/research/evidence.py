"""Admit production evidence deterministically before registry handoff.

The admission decision is deliberately pure.  Registration is delegated only
to the injected frozen port so this module owns neither persistence nor source
retrieval.

Author: Damon Li
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from datetime import datetime
from types import MappingProxyType
from typing import Final
from urllib.parse import urlsplit

from app.research.contracts import EvidenceV1, MarketPayloadV1
from app.research.errors import DomainError
from app.research.ports import (
    AdmittedEvidence,
    EvidenceAdmissionPort,
    EvidenceRegistrationPort,
    SourcePolicy,
)

_ENTITY_ID_PATTERN: Final = re.compile(r"^CN\.(?:SH|SZ|BJ)\.[0-9]{6}$")
_ALLOWED_ADJUSTMENTS: Final = frozenset({"none", "forward", "backward"})
_DNS_LABEL_PATTERN: Final = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def _canonical_host(value: object) -> str | None:
    """Normalize an ASCII DNS/A-label host without Unicode IDNA mapping."""
    if (
        not isinstance(value, str)
        or not value
        or not value.isascii()
        or value != value.strip()
    ):
        return None
    host = value.removesuffix(".")
    if not host or host.endswith("."):
        return None
    ascii_host = host.lower()
    labels = ascii_host.split(".")
    if any(not _DNS_LABEL_PATTERN.fullmatch(label) for label in labels):
        return None
    return ascii_host


def _is_aware(value: object) -> bool:
    """Return whether a value has an explicit UTC offset without raising details."""
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _evidence_ineligible() -> DomainError:
    """Return a safe evidence failure without embedding supplied content."""
    return DomainError(
        code="evidence_ineligible",
        safe_message="evidence is not eligible for research use",
        retryable=False,
    )


def _market_unverifiable() -> DomainError:
    """Return a safe market failure without embedding supplied content."""
    return DomainError(
        code="market_data_unverifiable",
        safe_message="market data cannot be verified",
        retryable=False,
    )


class DeterministicEvidenceAdmission(EvidenceAdmissionPort):
    """Implement fail-closed production evidence and market admission."""

    __slots__ = ("_approved_source_hosts",)

    def __init__(
        self, *, approved_source_hosts: Mapping[str, AbstractSet[str]] | None = None
    ) -> None:
        """Snapshot explicit source-to-host trust; absent or empty trust denies."""
        snapshot: dict[str, frozenset[str]] = {}
        if isinstance(approved_source_hosts, Mapping):
            for source_id, hosts in approved_source_hosts.items():
                if (
                    isinstance(source_id, str)
                    and source_id
                    and isinstance(hosts, AbstractSet)
                    and not isinstance(hosts, (str, bytes))
                ):
                    normalized_hosts = {
                        normalized
                        for host in hosts
                        if (normalized := _canonical_host(host)) is not None
                    }
                    if normalized_hosts:
                        snapshot[source_id] = frozenset(normalized_hosts)
        self._approved_source_hosts = MappingProxyType(snapshot)

    def admit_evidence(
        self,
        *,
        evidence: EvidenceV1,
        policy: SourcePolicy,
        now: datetime,
    ) -> AdmittedEvidence:
        """Return an immutable admission only when every required fact is present."""
        if not isinstance(evidence, EvidenceV1) or not isinstance(policy, SourcePolicy):
            raise _evidence_ineligible()
        if not _is_aware(now) or not _evidence_is_admissible(
            evidence, self._approved_source_hosts
        ):
            raise _evidence_ineligible()
        if not _policy_is_admissible(evidence, policy, now):
            raise _evidence_ineligible()
        if evidence.evidence_kind == "market" and not _market_is_admissible(
            evidence, evidence.market_payload
        ):
            raise _market_unverifiable()
        if evidence.evidence_kind != "market" and evidence.market_payload is not None:
            raise _evidence_ineligible()
        try:
            return AdmittedEvidence(evidence=evidence, policy=policy, admitted_at=now)
        except ValueError:
            raise _evidence_ineligible() from None


def _evidence_https_trusted(
    evidence: EvidenceV1, approved_source_hosts: Mapping[str, frozenset[str]]
) -> bool:
    """Return whether the evidence URL is HTTPS on an approved host."""
    try:
        parsed_url = urlsplit(str(evidence.source_url))
    except ValueError:
        return False
    host = _canonical_host(parsed_url.hostname)
    if host is None:
        return False
    return (
        parsed_url.scheme.lower() == "https"
        and bool(parsed_url.hostname)
        and parsed_url.username is None
        and parsed_url.password is None
        and parsed_url.port in (None, 443)
        and host in approved_source_hosts.get(evidence.source_id, frozenset())
    )


def _evidence_entity_ids_valid(entity_ids: object) -> bool:
    """Return whether entity identifiers are a unique non-empty research set."""
    if not isinstance(entity_ids, Sequence) or not entity_ids:
        return False
    if len(entity_ids) != len(set(entity_ids)):
        return False
    return all(
        isinstance(entity_id, str)
        and _ENTITY_ID_PATTERN.fullmatch(entity_id) is not None
        for entity_id in entity_ids
    )


def _evidence_chronology_valid(evidence: EvidenceV1) -> bool:
    """Return whether evidence timestamps are aware and ordered."""
    return (
        _is_aware(evidence.published_at)
        and _is_aware(evidence.fetched_at)
        and _is_aware(evidence.available_at)
        and evidence.published_at <= evidence.available_at <= evidence.fetched_at
    )


def _evidence_is_admissible(
    evidence: EvidenceV1, approved_source_hosts: Mapping[str, frozenset[str]]
) -> bool:
    """Require verified HTTPS evidence with complete trusted chronology."""
    entity_ids = evidence.entity_ids
    return (
        evidence.origin == "live"
        and evidence.quality_status == "verified_metadata"
        and evidence.license_scope != "unknown"
        and isinstance(evidence.source_id, str)
        and bool(evidence.source_id)
        and _evidence_https_trusted(evidence, approved_source_hosts)
        and _evidence_entity_ids_valid(entity_ids)
        and _evidence_chronology_valid(evidence)
    )


def _policy_is_admissible(
    evidence: EvidenceV1,
    policy: SourcePolicy,
    now: datetime,
) -> bool:
    """Require active matched policy and explicit storage/model permissions."""
    return (
        _is_aware(policy.approved_at)
        and _is_aware(policy.expires_at)
        and policy.approved_at <= now < policy.expires_at
        and policy.storage_allowed
        and policy.model_use_allowed
        and (evidence.excerpt is None or policy.redisplay_allowed)
        and (
            evidence.excerpt is None
            or len(evidence.excerpt) <= policy.allowed_excerpt_length
        )
        and evidence.source_id == policy.source_id
        and evidence.source_policy_version == policy.policy_version
    )


def _market_field_metadata_valid(market: MarketPayloadV1) -> bool:
    """Return whether market field names and units are present."""
    return bool(market.fields) and all(
        isinstance(field.unit, str)
        and bool(field.unit)
        and isinstance(field.name, str)
        and bool(field.name)
        for field in market.fields
    )


def _market_trace_valid(evidence: EvidenceV1, market: MarketPayloadV1) -> bool:
    """Return whether market payload identifiers align with admitted evidence."""
    return (
        market.evidence_id == evidence.evidence_id
        and market.provider == evidence.source_id
        and market.version == evidence.version
        and market.symbol in evidence.entity_ids
        and market.is_mock is False
        and isinstance(market.currency, str)
        and len(market.currency) == 3
        and market.currency.isupper()
        and market.adjustment in _ALLOWED_ADJUSTMENTS
        and _market_field_metadata_valid(market)
        and _is_aware(market.observed_at)
        and _is_aware(market.fetched_at)
        and _is_aware(market.available_at)
        and market.observed_at <= market.available_at
        and market.available_at <= market.fetched_at
        and market.available_at == evidence.available_at
        and market.fetched_at == evidence.fetched_at
    )


def _market_is_admissible(
    evidence: EvidenceV1,
    market: MarketPayloadV1 | None,
) -> bool:
    """Require a fully traceable, non-mock market observation payload."""
    if not isinstance(market, MarketPayloadV1):
        return False
    return _market_trace_valid(evidence, market)


class EvidenceRegistrationService:
    """Run pure admission, then hand the immutable result to the injected port."""

    __slots__ = ("_admission", "_registry")

    def __init__(
        self,
        *,
        admission: EvidenceAdmissionPort,
        registry: EvidenceRegistrationPort,
    ) -> None:
        """Accept only collaborators supplied by the composition owner."""
        self._admission = admission
        self._registry = registry

    async def register_evidence(
        self,
        *,
        evidence: EvidenceV1,
        policy: SourcePolicy,
        now: datetime,
    ) -> EvidenceV1:
        """Admit first and make one registry call without diagnostics or rewrites."""
        admission = self._admission.admit_evidence(
            evidence=evidence,
            policy=policy,
            now=now,
        )
        try:
            registered = await self._registry.register_evidence(
                admission=admission,
                now=now,
            )
        except DomainError:
            raise
        except Exception:  # noqa: BLE001 - normalize unsafe injected adapter failures
            raise DomainError(
                code="persistence_failed",
                safe_message="evidence registration failed",
                retryable=True,
            ) from None
        if not isinstance(registered, EvidenceV1):
            raise DomainError(
                code="persistence_failed",
                safe_message="evidence registration failed",
                retryable=True,
            )
        return registered


def build_evidence_registration_service(
    *,
    admission: EvidenceAdmissionPort,
    registry: EvidenceRegistrationPort,
) -> EvidenceRegistrationService:
    """Create the small port-only registration service for composition wiring."""
    return EvidenceRegistrationService(admission=admission, registry=registry)
