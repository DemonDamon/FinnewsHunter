"""Implement only S02-A persistence adapters for frozen research Ports.

S02-B passes an already admitted value object to this module and never imports an
ORM model.  S02-C receives the same database factory after merge and owns every
run-state, snapshot, event, audit, and outbox state transition.

Author: Damon Li
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.research.errors import DomainError
from app.research.models import (
    ResearchEvidence,
    ResearchMarketPayload,
    ResearchSourcePolicy,
)
from app.research.ports import (
    AdmittedEvidence,
    EvidenceRegistrationPort,
    ResearchDatabasePort,
    SourcePolicy,
)


def _persistence_error() -> DomainError:
    """Return one safe failure projection without SQL or value diagnostics."""
    return DomainError(
        code="persistence_failed",
        safe_message="research evidence registration could not be persisted",
        retryable=True,
    )


def _policy_matches(existing: ResearchSourcePolicy, policy: SourcePolicy) -> bool:
    """Compare every immutable policy business field without diagnostics."""
    return (
        existing.license_id,
        existing.terms_ref,
        existing.approved_at,
        existing.expires_at,
        existing.redisplay_allowed,
        existing.model_use_allowed,
        existing.storage_allowed,
        existing.allowed_excerpt_length,
    ) == (
        policy.license_id,
        policy.terms_ref,
        policy.approved_at,
        policy.expires_at,
        policy.redisplay_allowed,
        policy.model_use_allowed,
        policy.storage_allowed,
        policy.allowed_excerpt_length,
    )


async def _find_registered_evidence(
    session: AsyncSession,
    admission: AdmittedEvidence,
) -> ResearchEvidence | None:
    """Look up the immutable source/version key after policy persistence."""
    return await session.scalar(
        select(ResearchEvidence).where(
            ResearchEvidence.source_id == admission.evidence.source_id,
            ResearchEvidence.version == admission.evidence.version,
        )
    )


async def _register_source_policy(
    session: AsyncSession,
    policy: SourcePolicy,
) -> None:
    """Insert an immutable policy projection or verify an exact existing copy."""
    statement = (
        insert(ResearchSourcePolicy)
        .values(
            source_id=policy.source_id,
            policy_version=policy.policy_version,
            license_id=policy.license_id,
            terms_ref=policy.terms_ref,
            approved_at=policy.approved_at,
            expires_at=policy.expires_at,
            redisplay_allowed=policy.redisplay_allowed,
            model_use_allowed=policy.model_use_allowed,
            storage_allowed=policy.storage_allowed,
            allowed_excerpt_length=policy.allowed_excerpt_length,
        )
        .on_conflict_do_nothing(constraint="research_source_policy_pk")
    )
    await session.execute(statement)
    existing = await session.scalar(
        select(ResearchSourcePolicy).where(
            ResearchSourcePolicy.source_id == policy.source_id,
            ResearchSourcePolicy.policy_version == policy.policy_version,
        )
    )
    if existing is None or not _policy_matches(existing, policy):
        raise _persistence_error()


class EvidenceRegistrationRepository(EvidenceRegistrationPort):
    """Atomically persist an admitted evidence/policy/market projection only."""

    def __init__(self, database: ResearchDatabasePort) -> None:
        """Receive the explicit A-owned research session factory by injection."""
        self._database = database

    async def register_evidence(
        self,
        *,
        admission: AdmittedEvidence,
        now: datetime,
    ):
        """Register an exact immutable evidence version or return its idempotent DTO.

        This method deliberately does not authenticate, evaluate policy, create
        runs, allocate quota, write audit rows, or make public transport calls.
        """
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        try:
            async with self._database.session_factory() as session, session.begin():
                await _register_source_policy(session, admission.policy)
                existing = await _find_registered_evidence(session, admission)
                if existing is None:
                    await self._insert_evidence(session, admission)
                elif not self._evidence_matches(existing, admission):
                    raise _persistence_error()
                await self._register_market_if_present(session, admission)
            return admission.evidence
        except DomainError:
            raise
        except SQLAlchemyError as error:
            raise _persistence_error() from error

    async def _insert_evidence(
        self,
        session: AsyncSession,
        admission: AdmittedEvidence,
    ) -> None:
        """Insert exactly one evidence version and resolve concurrent idempotency."""
        evidence = admission.evidence
        statement = (
            insert(ResearchEvidence)
            .values(
                evidence_id=evidence.evidence_id,
                source_id=evidence.source_id,
                source_url=str(evidence.source_url),
                content_hash=evidence.content_hash,
                published_at=evidence.published_at,
                fetched_at=evidence.fetched_at,
                available_at=evidence.available_at,
                timezone=evidence.timezone,
                license_scope=evidence.license_scope,
                entity_id=evidence.entity_ids[0],
                excerpt=evidence.excerpt,
                quality_status=evidence.quality_status,
                evidence_kind=evidence.evidence_kind,
                version=evidence.version,
                source_policy_version=evidence.source_policy_version,
                origin=evidence.origin,
                admitted_at=admission.admitted_at,
            )
            .on_conflict_do_nothing(constraint="research_evidence_source_version_key")
        )
        result = await session.execute(statement)
        if result.rowcount == 0:
            existing = await _find_registered_evidence(session, admission)
            if existing is None or not self._evidence_matches(existing, admission):
                raise _persistence_error()

    async def _register_market_if_present(
        self,
        session: AsyncSession,
        admission: AdmittedEvidence,
    ) -> None:
        """Persist or verify the bounded market projection in the same transaction."""
        market = admission.evidence.market_payload
        if market is None:
            return
        fields_projection = [field.model_dump(mode="json") for field in market.fields]
        statement = (
            insert(ResearchMarketPayload)
            .values(
                evidence_id=market.evidence_id,
                symbol=market.symbol,
                observed_at=market.observed_at,
                available_at=market.available_at,
                fetched_at=market.fetched_at,
                timezone=market.timezone,
                currency=market.currency,
                adjustment=market.adjustment,
                fields_projection=fields_projection,
                provider=market.provider,
                version=market.version,
                is_mock=market.is_mock,
            )
            .on_conflict_do_nothing(index_elements=["evidence_id"])
        )
        result = await session.execute(statement)
        if result.rowcount == 0:
            existing = await session.get(ResearchMarketPayload, market.evidence_id)
            if existing is None or not self._market_matches(
                existing, fields_projection, admission
            ):
                raise _persistence_error()

    @staticmethod
    def _evidence_matches(
        existing: ResearchEvidence, admission: AdmittedEvidence
    ) -> bool:
        """Compare each persisted immutable evidence projection field exactly."""
        evidence = admission.evidence
        return (
            existing.evidence_id,
            existing.source_url,
            existing.content_hash,
            existing.published_at,
            existing.fetched_at,
            existing.available_at,
            existing.timezone,
            existing.license_scope,
            existing.entity_id,
            existing.excerpt,
            existing.quality_status,
            existing.evidence_kind,
            existing.source_policy_version,
            existing.origin,
        ) == (
            evidence.evidence_id,
            str(evidence.source_url),
            evidence.content_hash,
            evidence.published_at,
            evidence.fetched_at,
            evidence.available_at,
            evidence.timezone,
            evidence.license_scope,
            evidence.entity_ids[0],
            evidence.excerpt,
            evidence.quality_status,
            evidence.evidence_kind,
            evidence.source_policy_version,
            evidence.origin,
        )

    @staticmethod
    def _market_matches(
        existing: ResearchMarketPayload,
        fields_projection: list[dict[str, object]],
        admission: AdmittedEvidence,
    ) -> bool:
        """Compare a stored market payload against its exact admitted projection."""
        market = admission.evidence.market_payload
        if market is None:
            return False
        return (
            existing.symbol,
            existing.observed_at,
            existing.available_at,
            existing.fetched_at,
            existing.timezone,
            existing.currency,
            existing.adjustment,
            existing.fields_projection,
            existing.provider,
            existing.version,
            existing.is_mock,
        ) == (
            market.symbol,
            market.observed_at,
            market.available_at,
            market.fetched_at,
            market.timezone,
            market.currency,
            market.adjustment,
            fields_projection,
            market.provider,
            market.version,
            market.is_mock,
        )
