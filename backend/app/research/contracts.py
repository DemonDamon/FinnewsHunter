"""Define the isolated, strict research-v1.1 data transfer contracts.

Author: Damon Li
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, ClassVar, Final, Generic, Literal, TypeVar
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AnyUrl,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

SCHEMA_VERSION = "research-v1.1"
MCP_ENDPOINT = "/api/v1/mcp"
MCP_RESULT_POLICY: Final[dict[str, bool]] = {
    "ok": False,
    "partial": False,
    "unavailable": False,
    "error": True,
}

CanonicalEntityId = Annotated[
    str,
    StringConstraints(
        pattern=r"^CN\.(SH|SZ|BJ)\.[0-9]{6}$", min_length=12, max_length=12, strict=True
    ),
]
DecimalString = Annotated[
    str,
    StringConstraints(
        pattern=r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?$", min_length=1, max_length=128, strict=True
    ),
]
SafeSlug = Annotated[
    str,
    StringConstraints(
        pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$", min_length=1, max_length=128, strict=True
    ),
]
ShortText = Annotated[str, StringConstraints(min_length=1, max_length=128, strict=True)]
OpaqueCursor = Annotated[
    str,
    StringConstraints(
        pattern=r"^[A-Za-z0-9_-]+={0,2}$", min_length=1, max_length=512, strict=True
    ),
]


def _normalize_entity_identifier(entity_id: object) -> object:
    """Normalize the one permitted short-form entity identifier at input boundaries."""
    if not isinstance(entity_id, str):
        return entity_id
    if len(entity_id) == 8 and entity_id[:2] in {"SH", "SZ", "BJ"} and entity_id[2:].isdigit():
        return f"CN.{entity_id[:2]}.{entity_id[2:]}"
    return entity_id


class ContractModel(BaseModel):
    """Apply shared strictness and IANA timezone validation to all DTOs."""

    model_config = ConfigDict(extra="forbid")

    @field_validator("timezone", check_fields=False)
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        """Require a valid IANA timezone name rather than a display label."""
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise PydanticCustomError(
                "iana_timezone", "timezone must be a valid IANA timezone name"
            ) from error
        return value


class ContractError(ContractModel):
    """Describe a safe, stable error returned to a contract caller."""

    code: SafeSlug
    message: Annotated[str, StringConstraints(min_length=1, max_length=512, strict=True)]
    retryable: bool


class SourceRefV1(ContractModel):
    """Reference evidence provenance in an envelope without exposing raw content."""

    source_id: Annotated[str, StringConstraints(min_length=1, max_length=128, strict=True)]
    evidence_id: UUID
    provider: ShortText
    version: ShortText
    hash: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$", strict=True)]


class MarketFieldV1(ContractModel):
    """Represent one bounded decimal-valued market observation field."""

    name: Annotated[str, StringConstraints(min_length=1, max_length=64, strict=True)]
    value: DecimalString
    unit: Annotated[str, StringConstraints(min_length=1, max_length=32, strict=True)]


class MarketPayloadV1(ContractModel):
    """Represent market observations that are linked to registered evidence."""

    evidence_id: UUID
    symbol: CanonicalEntityId
    observed_at: AwareDatetime
    available_at: AwareDatetime
    fetched_at: AwareDatetime
    timezone: Annotated[str, StringConstraints(min_length=1, max_length=64, strict=True)]
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$", strict=True)]
    adjustment: Literal["none", "forward", "backward"]
    fields: list[MarketFieldV1] = Field(min_length=1, max_length=32)
    provider: ShortText
    version: ShortText
    is_mock: bool

    @model_validator(mode="after")
    def validate_availability_order(self) -> MarketPayloadV1:
        """Ensure the recorded availability time is not after retrieval."""
        if self.available_at > self.fetched_at:
            raise PydanticCustomError(
                "available_after_fetched", "available_at must be on or before fetched_at"
            )
        return self


class EvidenceV1(ContractModel):
    """Describe a versioned event or market evidence record without admission policy."""

    evidence_id: UUID
    source_id: Annotated[str, StringConstraints(min_length=1, max_length=128, strict=True)]
    source_url: AnyUrl
    content_hash: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$", strict=True)]
    published_at: AwareDatetime
    fetched_at: AwareDatetime
    available_at: AwareDatetime
    timezone: Annotated[str, StringConstraints(min_length=1, max_length=64, strict=True)]
    license_scope: Literal["redisplay", "metadata_only", "no_redisplay", "unknown"]
    entity_ids: list[CanonicalEntityId] = Field(min_length=1, max_length=1)
    excerpt: Annotated[str, StringConstraints(max_length=4000, strict=True)]
    quality_status: Literal["verified_metadata", "incomplete", "rejected"]
    evidence_kind: Literal["event", "market"]
    version: ShortText
    source_policy_version: ShortText
    origin: Literal["live", "fixture"]
    market_payload: MarketPayloadV1 | None

    @field_validator("source_url")
    @classmethod
    def validate_https_source_url(cls, value: AnyUrl) -> AnyUrl:
        """Permit only HTTPS source URLs in a standalone evidence DTO."""
        if value.scheme != "https":
            raise PydanticCustomError("https_url_required", "source_url must use HTTPS")
        return value

    @model_validator(mode="after")
    def validate_evidence_order_and_market_link(self) -> EvidenceV1:
        """Apply temporal invariants and the mandatory market payload linkage."""
        if self.fetched_at < self.available_at:
            raise PydanticCustomError(
                "fetched_before_available", "fetched_at must not be earlier than available_at"
            )
        if self.published_at > self.available_at:
            raise PydanticCustomError(
                "published_after_available", "published_at must not be later than available_at"
            )
        if self.evidence_kind == "market":
            if self.market_payload is None:
                raise PydanticCustomError(
                    "market_payload_required", "market evidence requires market_payload"
                )
            if self.market_payload.evidence_id != self.evidence_id:
                raise PydanticCustomError(
                    "market_evidence_mismatch", "market payload evidence_id must match evidence_id"
                )
        elif self.market_payload is not None:
            raise PydanticCustomError(
                "event_market_payload_forbidden", "event evidence must not include market_payload"
            )
        return self


class OperandRefV1(ContractModel):
    """Reference a bounded evidence field operand for a numeric assertion."""

    evidence_id: UUID
    field: Annotated[str, StringConstraints(min_length=1, max_length=64, strict=True)]


class NumericAssertionV1(ContractModel):
    """Describe a structurally constrained numerical claim assertion."""

    evidence_id: UUID
    field: Annotated[str, StringConstraints(min_length=1, max_length=64, strict=True)]
    claimed_value: DecimalString
    unit: Annotated[str, StringConstraints(min_length=1, max_length=32, strict=True)]
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$", strict=True)]
    formula_id: Literal["identity", "percent_change", "unit_scale"]
    operand_refs: list[OperandRefV1] = Field(max_length=4)
    rounding: Annotated[int, Field(ge=0, le=8, strict=True)]


class ClaimV1(ContractModel):
    """Describe an evidence-linked fact, inference, or hypothesis in a brief."""

    claim_id: UUID
    kind: Literal["fact", "inference", "hypothesis"]
    text: Annotated[str, StringConstraints(min_length=1, max_length=4000, strict=True)]
    evidence_ids: list[UUID] = Field(min_length=0, max_length=20)
    as_of: AwareDatetime
    valid_until: AwareDatetime | None
    confidence: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
    numeric_assertions: list[NumericAssertionV1] = Field(default_factory=list, max_length=20)

    @field_validator("evidence_ids")
    @classmethod
    def validate_unique_evidence_ids(cls, value: list[UUID]) -> list[UUID]:
        """Prevent duplicated evidence citations in one claim."""
        if len(value) != len(set(value)):
            raise PydanticCustomError(
                "duplicate_evidence_ids", "evidence_ids must not contain duplicates"
            )
        return value

    @model_validator(mode="after")
    def validate_claim_invariants(self) -> ClaimV1:
        """Require evidence for facts and preserve the declared validity order."""
        if self.kind == "fact" and not self.evidence_ids:
            raise PydanticCustomError(
                "fact_requires_evidence", "fact claims require at least one evidence_id"
            )
        if self.valid_until is not None and self.valid_until < self.as_of:
            raise PydanticCustomError(
                "valid_until_before_as_of", "valid_until must not be earlier than as_of"
            )
        return self


class ModelTraceEntryV1(ContractModel):
    """Store bounded model execution metadata without prompts or reasoning content."""

    role: Literal["draft", "review"]
    provider: ShortText
    model_id: ShortText
    prompt_version: ShortText
    policy_version: ShortText
    eval_version: ShortText
    eval_digest: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$", strict=True)]
    fallback_reason: Annotated[str, StringConstraints(max_length=512, strict=True)] | None


class ResearchBriefV1(ContractModel):
    """Represent the locally published, bounded research result for a run."""

    run_id: UUID
    as_of: AwareDatetime
    claims: list[ClaimV1] = Field(max_length=64)
    counterarguments: list[ClaimV1] = Field(max_length=32)
    unknowns: list[Annotated[str, StringConstraints(max_length=2000, strict=True)]] = Field(
        max_length=32
    )
    limitations: list[Annotated[str, StringConstraints(max_length=2000, strict=True)]] = Field(
        max_length=32
    )
    model_trace: list[ModelTraceEntryV1] = Field(max_length=4)

    @model_validator(mode="after")
    def validate_claim_as_of(self) -> ResearchBriefV1:
        """Require every supporting or counter claim to share the brief cutoff."""
        for claim in [*self.claims, *self.counterarguments]:
            if claim.as_of != self.as_of:
                raise PydanticCustomError(
                    "claim_as_of_mismatch", "all claim as_of values must match brief as_of"
                )
        return self


class ResearchRunViewV1(ContractModel):
    """Expose the bounded read view for one research run and its published brief."""

    run_id: UUID
    request_id: UUID
    principal_id: UUID
    entity_ids: list[CanonicalEntityId] = Field(min_length=1, max_length=1)
    as_of: AwareDatetime
    status: Literal["queued", "running", "completed", "failed", "needs_review", "cancelled"]
    created_at: AwareDatetime
    updated_at: AwareDatetime
    model_id: ShortText | None
    prompt_version: ShortText
    policy_version: ShortText
    result_ref: OpaqueCursor | None
    error_code: SafeSlug | None
    brief: ResearchBriefV1 | None

    @model_validator(mode="after")
    def validate_run_state(self) -> ResearchRunViewV1:
        """Enforce timestamp ordering and legal completed Brief availability."""
        if self.updated_at < self.created_at:
            raise PydanticCustomError(
                "updated_before_created", "updated_at must not be earlier than created_at"
            )
        if self.error_code == "license_revoked":
            if self.status != "completed":
                raise PydanticCustomError(
                    "license_revoked_requires_completed",
                    "license_revoked may be returned only for a completed run",
                )
            if self.brief is not None:
                raise PydanticCustomError(
                    "license_revoked_brief_forbidden",
                    "license_revoked completed runs must not expose a brief",
                )
        if self.brief is not None:
            if self.status != "completed":
                raise PydanticCustomError(
                    "brief_requires_completed", "only completed runs may expose a brief"
                )
            if self.brief.run_id != self.run_id:
                raise PydanticCustomError(
                    "brief_run_id_mismatch", "brief run_id must match run_id"
                )
            if self.brief.as_of != self.as_of:
                raise PydanticCustomError(
                    "brief_as_of_mismatch", "brief as_of must match run as_of"
                )
        if self.status == "completed" and self.brief is None and self.error_code != "license_revoked":
            raise PydanticCustomError(
                "completed_brief_required", "completed runs require a brief unless license is revoked"
            )
        return self


class StartedEventPayloadV1(ContractModel):
    """Represent an empty or bounded dispatch marker for a started event."""

    dispatch_id: Annotated[
        str | None,
        StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,128}$", strict=True),
    ] = None


class StepStartedEventPayloadV1(ContractModel):
    """Represent the bounded name of a run processing step."""

    step_name: Annotated[str, StringConstraints(min_length=1, max_length=128, strict=True)]


class EvidenceAddedEventPayloadV1(ContractModel):
    """Reference evidence added to a run snapshot."""

    evidence_id: UUID


class ClaimCheckedEventPayloadV1(ContractModel):
    """Record a claim check result without stack traces or raw model output."""

    claim_id: UUID
    passed: bool
    error_code: SafeSlug | None


class NeedsReviewEventPayloadV1(ContractModel):
    """Record the stable safe reason a run needs review."""

    code: SafeSlug


class CompletedEventPayloadV1(ContractModel):
    """Reference the bounded opaque location of a published brief."""

    result_ref: OpaqueCursor


class FailedEventPayloadV1(ContractModel):
    """Record a stable safe failure code."""

    code: SafeSlug


class CancelledEventPayloadV1(ContractModel):
    """Record a bounded human-readable cancellation reason."""

    reason: Annotated[str, StringConstraints(min_length=1, max_length=512, strict=True)]


RunEventPayload = (
    StartedEventPayloadV1
    | StepStartedEventPayloadV1
    | EvidenceAddedEventPayloadV1
    | ClaimCheckedEventPayloadV1
    | NeedsReviewEventPayloadV1
    | CompletedEventPayloadV1
    | FailedEventPayloadV1
    | CancelledEventPayloadV1
)


class RunEventV1(ContractModel):
    """Represent one strictly typed, sequential research-run event."""

    event_id: UUID
    run_id: UUID
    seq: Annotated[int, Field(ge=1, strict=True)]
    type: Literal[
        "started",
        "step_started",
        "evidence_added",
        "claim_checked",
        "needs_review",
        "completed",
        "failed",
        "cancelled",
    ]
    occurred_at: AwareDatetime
    payload: RunEventPayload

    _PAYLOAD_TYPES: ClassVar[dict[str, type[ContractModel]]] = {
        "started": StartedEventPayloadV1,
        "step_started": StepStartedEventPayloadV1,
        "evidence_added": EvidenceAddedEventPayloadV1,
        "claim_checked": ClaimCheckedEventPayloadV1,
        "needs_review": NeedsReviewEventPayloadV1,
        "completed": CompletedEventPayloadV1,
        "failed": FailedEventPayloadV1,
        "cancelled": CancelledEventPayloadV1,
    }

    @model_validator(mode="after")
    def validate_event_payload_type(self) -> RunEventV1:
        """Bind each fixed event type to its one allowed bounded payload model."""
        if not isinstance(self.payload, self._PAYLOAD_TYPES[self.type]):
            raise PydanticCustomError(
                "event_payload_mismatch", "payload does not match event type"
            )
        return self


T = TypeVar("T")


class ResearchEnvelope(ContractModel, Generic[T]):
    """Wrap concrete research DTO data in the shared MCP response envelope."""

    schema_version: Literal[SCHEMA_VERSION]
    request_id: UUID
    status: Literal["ok", "partial", "unavailable", "error"]
    as_of: AwareDatetime
    data: T | None
    source: list[SourceRefV1] = Field(max_length=20)
    license_status: Literal["approved", "restricted", "unknown", "revoked", "not_applicable"]
    warnings: list[Annotated[str, StringConstraints(min_length=1, max_length=512, strict=True)]] = Field(
        max_length=20
    )
    error: ContractError | None

    @model_validator(mode="after")
    def validate_envelope_state(self) -> ResearchEnvelope[T]:
        """Prevent status values from masquerading as complete successful output."""
        if self.status == "ok" and (self.error is not None or self.data is None):
            raise PydanticCustomError(
                "ok_envelope_invalid", "ok requires data and a null error"
            )
        if self.status in {"error", "unavailable"} and self.error is None:
            raise PydanticCustomError(
                "error_envelope_missing_error", "error and unavailable require an error"
            )
        if self.status == "partial" and not self.warnings:
            raise PydanticCustomError(
                "partial_envelope_requires_warnings", "partial requires at least one warning"
            )
        return self


class ResearchToolInput(ContractModel):
    """Apply input-boundary entity normalization and nonfuture cutoff validation."""

    @field_validator("entity_ids", mode="before", check_fields=False)
    @classmethod
    def normalize_entity_ids(cls, value: object) -> object:
        """Normalize only SH/SZ/BJ short codes supplied to public tool inputs."""
        if not isinstance(value, list):
            return value
        return [_normalize_entity_identifier(entity_id) for entity_id in value]

    @field_validator("as_of", check_fields=False)
    @classmethod
    def validate_as_of_not_future(cls, value: AwareDatetime, info: object) -> AwareDatetime:
        """Reject future cutoffs against a caller-supplied test clock or UTC now."""
        context = getattr(info, "context", None) or {}
        now = context.get("now", datetime.now(UTC))
        if now.tzinfo is None or now.utcoffset() is None:
            raise PydanticCustomError("validator_now_naive", "validation now must be timezone-aware")
        if value > now:
            raise PydanticCustomError("as_of_in_future", "as_of must not be in the future")
        return value


class SearchArticlesInput(ResearchToolInput):
    """Accept bounded filtering and pagination parameters for registered articles."""

    query: Annotated[str, StringConstraints(min_length=1, max_length=256, strict=True)]
    entity_ids: list[CanonicalEntityId] = Field(min_length=1, max_length=1)
    as_of: AwareDatetime
    limit: Annotated[int, Field(ge=1, le=20, strict=True)] = 10
    cursor: OpaqueCursor | None = None


class GetEvidenceInput(ResearchToolInput):
    """Accept the evidence and run identifiers needed for an authorized read."""

    evidence_id: UUID
    run_id: UUID


class GetMarketSnapshotInput(ResearchToolInput):
    """Accept a bounded single-entity market snapshot request."""

    entity_ids: list[CanonicalEntityId] = Field(min_length=1, max_length=1)
    as_of: AwareDatetime
    run_id: UUID | None = None


class StartResearchInput(ResearchToolInput):
    """Accept the finite input needed to create a research run."""

    request_id: UUID
    entity_ids: list[CanonicalEntityId] = Field(min_length=1, max_length=1)
    as_of: AwareDatetime
    seed_evidence_id: UUID
    question: Annotated[str, StringConstraints(max_length=2000, strict=True)] | None = None


class GetRunInput(ResearchToolInput):
    """Accept the identifier for a bounded research-run status read."""

    run_id: UUID


class ArticlesSearchResult(ContractModel):
    """Return a bounded list of authorized article evidence previews."""

    articles: list[EvidenceV1] = Field(max_length=20)
    next_cursor: OpaqueCursor | None
    truncated: bool


@dataclass(frozen=True)
class ToolDefinition:
    """Bind one exact MCP tool name to concrete input and output DTO classes."""

    name: str
    input_model: type[ResearchToolInput]
    output_model: type[ResearchEnvelope[object]]


TOOL_REGISTRY: tuple[ToolDefinition, ...] = (
    ToolDefinition(
        "finnews.search_articles",
        SearchArticlesInput,
        ResearchEnvelope[ArticlesSearchResult],
    ),
    ToolDefinition(
        "finnews.get_evidence",
        GetEvidenceInput,
        ResearchEnvelope[EvidenceV1],
    ),
    ToolDefinition(
        "finnews.get_market_snapshot",
        GetMarketSnapshotInput,
        ResearchEnvelope[MarketPayloadV1],
    ),
    ToolDefinition(
        "finnews.start_research",
        StartResearchInput,
        ResearchEnvelope[ResearchRunViewV1],
    ),
    ToolDefinition(
        "finnews.get_run",
        GetRunInput,
        ResearchEnvelope[ResearchRunViewV1],
    ),
)

HTTP_PATHS: tuple[dict[str, str], ...] = (
    {"method": "POST", "path": "/api/v1/research/runs"},
    {"method": "GET", "path": "/api/v1/research/runs/{id}"},
    {"method": "GET", "path": "/api/v1/research/runs/{id}/events"},
    {"method": "GET", "path": "/api/v1/research/evidence/{id}?run_id={id}"},
)
