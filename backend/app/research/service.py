"""Share the frozen ledger operations between research HTTP and MCP.

No environment, database session, provider, or identity discovery belongs here.
Authorization remains the ledger's responsibility: the injected policy is the
same composition-owned policy, not a second preflight resource check.

Author: Damon Li
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Literal, TypeVar, overload
from uuid import UUID, uuid4

from app.research.contracts import (
    SCHEMA_VERSION,
    ArticlesSearchResult,
    EvidenceV1,
    GetEvidenceInput,
    GetMarketSnapshotInput,
    GetRunInput,
    MarketPayloadV1,
    ResearchEnvelope,
    ResearchRunViewV1,
    SearchArticlesInput,
    StartResearchInput,
)
from app.research.errors import DomainError, DomainErrorCode
from app.research.ports import (
    AuthorizationPort,
    Principal,
    ResearchLedgerPort,
    RunEventPage,
)

Clock = Callable[[], datetime]
EVENT_PAGE_SIZE = 100
T = TypeVar("T")

# Never reflect a caller-supplied question, ledger diagnostic, or exception text.
_ERROR_MESSAGES: dict[DomainErrorCode, str] = {
    "identity_invalid": "identity verification failed",
    "identity_material_unavailable": "identity material is unavailable",
    "resource_not_found_or_denied": "resource was not found or access is denied",
    "request_conflict": "request conflicts with an existing research run",
    "evidence_ineligible": "evidence is not eligible for research",
    "market_data_unverifiable": "registered market data is unavailable",
    "license_revoked": "evidence license is revoked",
    "execution_unavailable": "research execution is unavailable",
    "quota_exceeded": "research quota is exceeded",
    "invalid_run_state": "research run state is invalid",
    "dispatch_mismatch": "research dispatch does not match",
    "snapshot_frozen": "research snapshot is frozen",
    "lease_expired": "research lease is expired",
    "execution_fenced": "research execution is fenced",
    "terminal_state": "research run is terminal",
    "citation_invalid": "research citation is invalid",
    "brief_gate_rejected": "research brief was not approved",
    "event_cursor_invalid": "event cursor is invalid",
    "persistence_failed": "research persistence is unavailable",
}
_INFRASTRUCTURE_CODES = frozenset(
    {"identity_material_unavailable", "execution_unavailable", "persistence_failed"}
)


def _safe_error(error: DomainError) -> DomainError:
    """Project only fixed codes/messages, including a defensive unknown-code case."""
    code = error.code if error.code in _ERROR_MESSAGES else "persistence_failed"
    return DomainError(
        code=code,
        safe_message=_ERROR_MESSAGES[code],
        retryable=error.retryable if code == error.code else True,
    )


class ResearchApplicationService:
    """Expose DTOs by default, or the same operation as an MCP envelope.

    Each invocation samples the injected clock exactly once. ``envelope=True``
    catches safe DomainError only; unexpected programming failures and task
    cancellation propagate to the transport's fixed internal-error handler.
    No cache or service-level idempotency can bypass the ledger's authorization.
    """

    __slots__ = ("_authorization", "_clock", "_execution_enabled", "_ledger")

    def __init__(
        self,
        *,
        ledger: ResearchLedgerPort,
        authorization: AuthorizationPort,
        clock: Clock,
        execution_enabled: bool = False,
    ) -> None:
        """Keep explicit composition-owned dependencies without performing I/O."""
        if type(execution_enabled) is not bool:
            raise ValueError("execution_enabled must be a boolean")
        self._ledger = ledger
        self._authorization = authorization
        self._clock = clock
        self._execution_enabled = execution_enabled

    def _now(self) -> datetime:
        """Require an aware clock before crossing any ledger boundary."""
        now = self._clock()
        if (
            not isinstance(now, datetime)
            or now.tzinfo is None
            or now.utcoffset() is None
        ):
            raise ValueError("research clock must return a timezone-aware datetime")
        return now.astimezone(UTC)

    async def _invoke(
        self,
        operation: Callable[[datetime], Awaitable[T]],
        *,
        output_model: type[T],
        envelope: bool,
    ) -> T | ResearchEnvelope[T]:
        """Use one clock/ledger path for both transports and safe error mapping."""
        now = self._now()
        request_id = uuid4()
        try:
            data = await operation(now)
        except DomainError as error:
            safe = _safe_error(error)
            if not envelope:
                raise safe from None
            return ResearchEnvelope[output_model](
                schema_version=SCHEMA_VERSION,
                request_id=request_id,
                as_of=now,
                status=(
                    "unavailable"
                    if safe.retryable and safe.code in _INFRASTRUCTURE_CODES
                    else "error"
                ),
                data=None,
                source=[],
                license_status="unknown",
                warnings=[],
                error=safe.as_contract_error(),
            )
        if not envelope:
            return data
        # The Port has no provider provenance for event evidence. Do not invent
        # SourceRefV1 fields; the returned DTO preserves the recorded provenance.
        license_status = "not_applicable"
        if isinstance(data, (EvidenceV1, ArticlesSearchResult, MarketPayloadV1)):
            license_status = "approved"
        elif (
            isinstance(data, ResearchRunViewV1) and data.error_code == "license_revoked"
        ):
            license_status = "revoked"
        return ResearchEnvelope[output_model](
            schema_version=SCHEMA_VERSION,
            request_id=request_id,
            as_of=now,
            status="ok",
            data=data,
            source=[],
            license_status=license_status,
            warnings=[],
            error=None,
        )

    @overload
    async def search_articles(
        self,
        *,
        principal: Principal,
        request: SearchArticlesInput,
        envelope: Literal[False] = False,
    ) -> ArticlesSearchResult:
        """Typed overload for plain DTO responses."""
        ...

    @overload
    async def search_articles(
        self,
        *,
        principal: Principal,
        request: SearchArticlesInput,
        envelope: Literal[True],
    ) -> ResearchEnvelope[ArticlesSearchResult]:
        """Typed overload for envelope responses."""
        ...

    async def search_articles(
        self,
        *,
        principal: Principal,
        request: SearchArticlesInput,
        envelope: bool = False,
    ) -> ArticlesSearchResult | ResearchEnvelope[ArticlesSearchResult]:
        """Search registered articles without refreshing their frozen cutoff."""
        return await self._invoke(
            lambda now: self._ledger.search_articles(
                principal=principal, request=request, now=now
            ),
            output_model=ArticlesSearchResult,
            envelope=envelope,
        )

    @overload
    async def get_evidence(
        self,
        *,
        principal: Principal,
        request: GetEvidenceInput,
        envelope: Literal[False] = False,
    ) -> EvidenceV1:
        """Typed overload for plain DTO responses."""
        ...

    @overload
    async def get_evidence(
        self,
        *,
        principal: Principal,
        request: GetEvidenceInput,
        envelope: Literal[True],
    ) -> ResearchEnvelope[EvidenceV1]:
        """Typed overload for envelope responses."""
        ...

    async def get_evidence(
        self,
        *,
        principal: Principal,
        request: GetEvidenceInput,
        envelope: bool = False,
    ) -> EvidenceV1 | ResearchEnvelope[EvidenceV1]:
        """Read only an authorized registered snapshot member."""
        return await self._invoke(
            lambda now: self._ledger.read_evidence(
                principal=principal, request=request, now=now
            ),
            output_model=EvidenceV1,
            envelope=envelope,
        )

    @overload
    async def get_market_snapshot(
        self,
        *,
        principal: Principal,
        request: GetMarketSnapshotInput,
        envelope: Literal[False] = False,
    ) -> MarketPayloadV1:
        """Typed overload for plain DTO responses."""
        ...

    @overload
    async def get_market_snapshot(
        self,
        *,
        principal: Principal,
        request: GetMarketSnapshotInput,
        envelope: Literal[True],
    ) -> ResearchEnvelope[MarketPayloadV1]:
        """Typed overload for envelope responses."""
        ...

    async def get_market_snapshot(
        self,
        *,
        principal: Principal,
        request: GetMarketSnapshotInput,
        envelope: bool = False,
    ) -> MarketPayloadV1 | ResearchEnvelope[MarketPayloadV1]:
        """Translate the Port's missing-data None into a truthful bounded failure."""

        async def read(now: datetime) -> MarketPayloadV1:
            """Load market payload or map absence to a bounded domain error."""
            data = await self._ledger.get_market_snapshot(
                principal=principal, request=request, now=now
            )
            if data is None:
                raise DomainError(
                    code="market_data_unverifiable",
                    safe_message=_ERROR_MESSAGES["market_data_unverifiable"],
                    retryable=False,
                )
            return data

        return await self._invoke(read, output_model=MarketPayloadV1, envelope=envelope)

    @overload
    async def start_research(
        self,
        *,
        principal: Principal,
        request: StartResearchInput,
        envelope: Literal[False] = False,
    ) -> ResearchRunViewV1:
        """Typed overload for plain DTO responses."""
        ...

    @overload
    async def start_research(
        self,
        *,
        principal: Principal,
        request: StartResearchInput,
        envelope: Literal[True],
    ) -> ResearchEnvelope[ResearchRunViewV1]:
        """Typed overload for envelope responses."""
        ...

    async def start_research(
        self,
        *,
        principal: Principal,
        request: StartResearchInput,
        envelope: bool = False,
    ) -> ResearchRunViewV1 | ResearchEnvelope[ResearchRunViewV1]:
        """Reject disabled execution before any ledger call or queued write.

        When enabled, executor readiness, quota, and idempotency remain inside
        create_or_reuse_run's frozen atomic Port contract.
        """

        async def create(now: datetime) -> ResearchRunViewV1:
            """Gate execution before delegating to the ledger idempotency path."""
            if not self._execution_enabled:
                raise DomainError(
                    code="execution_unavailable",
                    safe_message=_ERROR_MESSAGES["execution_unavailable"],
                    retryable=True,
                )
            return await self._ledger.create_or_reuse_run(
                principal=principal, request=request, now=now
            )

        return await self._invoke(
            create, output_model=ResearchRunViewV1, envelope=envelope
        )

    @overload
    async def get_run(
        self,
        *,
        principal: Principal,
        request: GetRunInput,
        envelope: Literal[False] = False,
    ) -> ResearchRunViewV1:
        """Typed overload for plain DTO responses."""
        ...

    @overload
    async def get_run(
        self,
        *,
        principal: Principal,
        request: GetRunInput,
        envelope: Literal[True],
    ) -> ResearchEnvelope[ResearchRunViewV1]:
        """Typed overload for envelope responses."""
        ...

    async def get_run(
        self,
        *,
        principal: Principal,
        request: GetRunInput,
        envelope: bool = False,
    ) -> ResearchRunViewV1 | ResearchEnvelope[ResearchRunViewV1]:
        """Preserve the ledger's safe run projection, including revoked Briefs."""
        return await self._invoke(
            lambda now: self._ledger.get_run(
                principal=principal, request=request, now=now
            ),
            output_model=ResearchRunViewV1,
            envelope=envelope,
        )

    async def read_events(
        self,
        *,
        principal: Principal,
        run_id: UUID,
        after_event_id: UUID | None = None,
    ) -> RunEventPage:
        """Replay a finite committed page with a fixed, non-client-sized limit."""
        now = self._now()
        try:
            return await self._ledger.read_events(
                principal=principal,
                run_id=run_id,
                after_event_id=after_event_id,
                limit=EVENT_PAGE_SIZE,
                now=now,
            )
        except DomainError as error:
            raise _safe_error(error) from None
