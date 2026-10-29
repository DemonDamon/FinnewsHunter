"""Generate deterministic research-v1.1 contract schemas and fixtures.

Author: Damon Li
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from app.research.contracts import (
    HTTP_PATHS,
    MCP_RESULT_POLICY,
    SCHEMA_VERSION,
    TOOL_REGISTRY,
    ArticlesSearchResult,
    ClaimV1,
    ContractError,
    EvidenceV1,
    GetEvidenceInput,
    GetMarketSnapshotInput,
    GetRunInput,
    MarketFieldV1,
    MarketPayloadV1,
    ModelTraceEntryV1,
    NumericAssertionV1,
    OperandRefV1,
    ResearchBriefV1,
    ResearchEnvelope,
    ResearchRunViewV1,
    RunEventV1,
    SearchArticlesInput,
    SourceRefV1,
    StartResearchInput,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = REPOSITORY_ROOT / "docs" / "contracts" / SCHEMA_VERSION

EVENT_EVIDENCE_ID = "11111111-1111-1111-1111-111111111111"
MARKET_EVIDENCE_ID = "22222222-2222-2222-2222-222222222222"
COMPLETED_RUN_ID = "33333333-3333-3333-3333-333333333333"
QUEUED_RUN_ID = "44444444-4444-4444-4444-444444444444"
REVOKED_RUN_ID = "55555555-5555-5555-5555-555555555555"
PRINCIPAL_ID = "66666666-6666-6666-6666-666666666666"
REQUEST_ID = "77777777-7777-7777-7777-777777777777"
CLAIM_ID = "88888888-8888-8888-8888-888888888888"
EVENT_ID = "99999999-9999-9999-9999-999999999999"
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def _canonical_json(payload: Any) -> bytes:
    """Encode content using the one stable JSON serialization used for hashes."""
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _compact_json(payload: Any) -> str:
    """Encode fixture text blocks using a stable compact JSON representation."""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _schema_file_name(name: str) -> str:
    """Map a model or tool name to a portable deterministic schema path."""
    return f"schemas/{name.replace('[', '.').replace(']', '').replace(' ', '')}.json"


def _schema_sources() -> list[tuple[str, type[Any]]]:
    """Return every public non-generic DTO schema in stable output order."""
    return [
        ("ContractError", ContractError),
        ("SourceRefV1", SourceRefV1),
        ("MarketFieldV1", MarketFieldV1),
        ("MarketPayloadV1", MarketPayloadV1),
        ("EvidenceV1", EvidenceV1),
        ("OperandRefV1", OperandRefV1),
        ("NumericAssertionV1", NumericAssertionV1),
        ("ClaimV1", ClaimV1),
        ("ModelTraceEntryV1", ModelTraceEntryV1),
        ("ResearchBriefV1", ResearchBriefV1),
        ("ResearchRunViewV1", ResearchRunViewV1),
        ("RunEventV1", RunEventV1),
        ("ArticlesSearchResult", ArticlesSearchResult),
        ("SearchArticlesInput", SearchArticlesInput),
        ("GetEvidenceInput", GetEvidenceInput),
        ("GetMarketSnapshotInput", GetMarketSnapshotInput),
        ("StartResearchInput", StartResearchInput),
        ("GetRunInput", GetRunInput),
        ("ResearchEnvelope.ArticlesSearchResult", ResearchEnvelope[ArticlesSearchResult]),
        ("ResearchEnvelope.EvidenceV1", ResearchEnvelope[EvidenceV1]),
        ("ResearchEnvelope.MarketPayloadV1", ResearchEnvelope[MarketPayloadV1]),
        ("ResearchEnvelope.ResearchRunViewV1", ResearchEnvelope[ResearchRunViewV1]),
    ]


def _apply_event_payload_conditions(schema: dict[str, Any]) -> dict[str, Any]:
    """Bind every RunEvent type value to the one allowed payload definition."""
    payload_definitions = {
        "started": "StartedEventPayloadV1",
        "step_started": "StepStartedEventPayloadV1",
        "evidence_added": "EvidenceAddedEventPayloadV1",
        "claim_checked": "ClaimCheckedEventPayloadV1",
        "needs_review": "NeedsReviewEventPayloadV1",
        "completed": "CompletedEventPayloadV1",
        "failed": "FailedEventPayloadV1",
        "cancelled": "CancelledEventPayloadV1",
    }
    schema["allOf"] = [
        {
            "if": {"properties": {"type": {"const": event_type}}, "required": ["type"]},
            "then": {"properties": {"payload": {"$ref": f"#/$defs/{payload_name}"}}},
        }
        for event_type, payload_name in payload_definitions.items()
    ]
    return schema


def _apply_run_state_conditions(schema: dict[str, Any]) -> dict[str, Any]:
    """Apply revoked-license run visibility rules to direct and nested model schemas."""
    def visit(node: Any) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict) and {"status", "error_code", "brief"}.issubset(
                properties
            ):
                node["allOf"] = [
                    *node.get("allOf", []),
                    {
                        "if": {
                            "properties": {"error_code": {"const": "license_revoked"}},
                            "required": ["error_code"],
                        },
                        "then": {
                            "properties": {
                                "status": {"const": "completed"},
                                "brief": {"type": "null"},
                            },
                            "required": ["status", "brief"],
                        },
                        "else": {
                            "if": {
                                "properties": {"status": {"const": "completed"}},
                                "required": ["status"],
                            },
                            "then": {
                                "properties": {"brief": {"not": {"type": "null"}}},
                                "required": ["brief"],
                            },
                        },
                    },
                ]
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(schema)
    return schema


def _event_evidence() -> dict[str, Any]:
    """Build a fixed synthetic event evidence fixture with no real source data."""
    return {
        "evidence_id": EVENT_EVIDENCE_ID,
        "source_id": "fixture-event-source",
        "source_url": "https://example.invalid/events/fixture-event",
        "content_hash": HASH_A,
        "published_at": "2026-10-29T09:00:00+08:00",
        "fetched_at": "2026-10-29T09:31:00+08:00",
        "available_at": "2026-10-29T09:30:00+08:00",
        "timezone": "Asia/Shanghai",
        "license_scope": "redisplay",
        "entity_ids": ["CN.SH.600519"],
        "excerpt": "Synthetic fixture event only; it is not financial research evidence.",
        "quality_status": "verified_metadata",
        "evidence_kind": "event",
        "version": "fixture-v1",
        "source_policy_version": "fixture-policy-v1",
        "origin": "fixture",
        "market_payload": None,
    }


def _market_payload() -> dict[str, Any]:
    """Build a fixed synthetic market payload linked to its fixture evidence."""
    return {
        "evidence_id": MARKET_EVIDENCE_ID,
        "symbol": "CN.SH.600519",
        "observed_at": "2026-10-29T09:30:00+08:00",
        "available_at": "2026-10-29T09:31:00+08:00",
        "fetched_at": "2026-10-29T09:32:00+08:00",
        "timezone": "Asia/Shanghai",
        "currency": "CNY",
        "adjustment": "none",
        "fields": [{"name": "close", "value": "1450.25", "unit": "CNY"}],
        "provider": "fixture-provider",
        "version": "fixture-v1",
        "is_mock": True,
    }


def _market_evidence() -> dict[str, Any]:
    """Build fixture market evidence that references the matching market payload."""
    return {
        **_event_evidence(),
        "evidence_id": MARKET_EVIDENCE_ID,
        "source_id": "fixture-market-source",
        "source_url": "https://example.invalid/market/fixture-snapshot",
        "content_hash": HASH_B,
        "published_at": "2026-10-29T09:30:00+08:00",
        "fetched_at": "2026-10-29T09:32:00+08:00",
        "available_at": "2026-10-29T09:31:00+08:00",
        "excerpt": "Synthetic fixture market payload only; it is not market data.",
        "evidence_kind": "market",
        "market_payload": _market_payload(),
    }


def _claim() -> dict[str, Any]:
    """Build a fixed fact claim that cites the synthetic event fixture."""
    return {
        "claim_id": CLAIM_ID,
        "kind": "fact",
        "text": "The fixture event was registered before the declared research cutoff.",
        "evidence_ids": [EVENT_EVIDENCE_ID],
        "as_of": "2026-10-29T10:00:00+08:00",
        "valid_until": None,
        "confidence": 0.8,
        "numeric_assertions": [],
    }


def _brief(run_id: str = COMPLETED_RUN_ID) -> dict[str, Any]:
    """Build a fixed locally readable brief for a completed fixture run."""
    return {
        "run_id": run_id,
        "as_of": "2026-10-29T10:00:00+08:00",
        "claims": [_claim()],
        "counterarguments": [],
        "unknowns": ["No live source, admission policy, or financial conclusion is represented."],
        "limitations": ["This is a synthetic fixture intended only for offline contract tests."],
        "model_trace": [
            {
                "role": "draft",
                "provider": "fixture-provider",
                "model_id": "fixture-model",
                "prompt_version": "fixture-prompt-v1",
                "policy_version": "fixture-policy-v1",
                "eval_version": "fixture-eval-v1",
                "eval_digest": HASH_C,
                "fallback_reason": None,
            }
        ],
    }


def _run_view(run_id: str, status: str, brief: dict[str, Any] | None, error_code: str | None) -> dict[str, Any]:
    """Build a stable run view for queued, completed, or revoked fixture states."""
    return {
        "run_id": run_id,
        "request_id": REQUEST_ID,
        "principal_id": PRINCIPAL_ID,
        "entity_ids": ["CN.SH.600519"],
        "as_of": "2026-10-29T10:00:00+08:00",
        "status": status,
        "created_at": "2026-10-29T10:00:00+08:00",
        "updated_at": "2026-10-29T10:04:00+08:00",
        "model_id": "fixture-model" if status == "completed" else None,
        "prompt_version": "fixture-prompt-v1",
        "policy_version": "fixture-policy-v1",
        "result_ref": "fixture_result_ref" if status == "completed" else None,
        "error_code": error_code,
        "brief": brief,
    }


def _event_source_ref() -> dict[str, Any]:
    """Build a fixed provenance reference for the synthetic event evidence."""
    return {
        "source_id": "fixture-event-source",
        "evidence_id": EVENT_EVIDENCE_ID,
        "provider": "fixture-provider",
        "version": "fixture-v1",
        "hash": HASH_A,
    }


def _market_source_ref() -> dict[str, Any]:
    """Build a fixed provenance reference for the matching synthetic market evidence."""
    return {
        "source_id": "fixture-market-source",
        "evidence_id": MARKET_EVIDENCE_ID,
        "provider": "fixture-provider",
        "version": "fixture-v1",
        "hash": HASH_B,
    }


def _envelope(
    request_id: str,
    data: Any,
    status: str = "ok",
    error: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    source: list[dict[str, Any]] | None = None,
    license_status: str = "not_applicable",
) -> dict[str, Any]:
    """Build a deterministic concrete shared envelope payload."""
    return {
        "schema_version": SCHEMA_VERSION,
        "request_id": request_id,
        "status": status,
        "as_of": "2026-10-29T10:00:00+08:00",
        "data": data,
        "source": [] if source is None else source,
        "license_status": license_status,
        "warnings": [] if warnings is None else warnings,
        "error": error,
    }


def _tool_success_envelopes() -> dict[str, Any]:
    """Build matching text and structured forms for every fixed MCP tool output."""
    search_output = _envelope(
        REQUEST_ID,
        {"articles": [_event_evidence()], "next_cursor": None, "truncated": False},
        source=[_event_source_ref()],
    )
    evidence_output = _envelope(REQUEST_ID, _event_evidence(), source=[_event_source_ref()])
    market_output = _envelope(REQUEST_ID, _market_payload(), source=[_market_source_ref()])
    start_output = _envelope(
        REQUEST_ID,
        _run_view(QUEUED_RUN_ID, "queued", None, None),
        source=[_event_source_ref()],
    )
    run_output = _envelope(
        REQUEST_ID,
        _run_view(COMPLETED_RUN_ID, "completed", _brief(), None),
        source=[_event_source_ref()],
    )
    outputs = {
        "finnews.search_articles": (search_output, "schemas/ResearchEnvelope.ArticlesSearchResult.json"),
        "finnews.get_evidence": (evidence_output, "schemas/ResearchEnvelope.EvidenceV1.json"),
        "finnews.get_market_snapshot": (market_output, "schemas/ResearchEnvelope.MarketPayloadV1.json"),
        "finnews.start_research": (start_output, "schemas/ResearchEnvelope.ResearchRunViewV1.json"),
        "finnews.get_run": (run_output, "schemas/ResearchEnvelope.ResearchRunViewV1.json"),
    }
    return {
        name: {"text": _compact_json(output), "structured": output, "schema": schema}
        for name, (output, schema) in outputs.items()
    }


def _mcp_result_policy_fixtures() -> dict[str, Any]:
    """Build frozen CallToolResult transport shapes without invoking an MCP SDK."""
    ok = _envelope(REQUEST_ID, _event_evidence(), source=[_event_source_ref()])
    partial = _envelope(
        REQUEST_ID,
        _event_evidence(),
        status="partial",
        warnings=["Fixture source metadata is intentionally synthetic."],
        source=[_event_source_ref()],
    )
    unavailable = _envelope(
        REQUEST_ID,
        None,
        status="unavailable",
        error={
            "code": "market_data_unverifiable",
            "message": "No approved market payload is available for this cutoff.",
            "retryable": False,
        },
        warnings=["No live refresh or mock fallback was performed."],
    )
    error = _envelope(
        REQUEST_ID,
        None,
        status="error",
        error={"code": "execution_unavailable", "message": "Fixture executor is disabled.", "retryable": True},
    )
    outputs = {
        "ok": (ok, "ResearchEnvelope[EvidenceV1]", "schemas/ResearchEnvelope.EvidenceV1.json"),
        "partial": (partial, "ResearchEnvelope[EvidenceV1]", "schemas/ResearchEnvelope.EvidenceV1.json"),
        "unavailable": (
            unavailable,
            "ResearchEnvelope[MarketPayloadV1]",
            "schemas/ResearchEnvelope.MarketPayloadV1.json",
        ),
        "error": (
            error,
            "ResearchEnvelope[ArticlesSearchResult]",
            "schemas/ResearchEnvelope.ArticlesSearchResult.json",
        ),
    }
    return {
        status: {
            "text": _compact_json(output),
            "structured": output,
            "isError": MCP_RESULT_POLICY[status],
            "model": model,
            "schema": schema,
        }
        for status, (output, model, schema) in outputs.items()
    }


def _fixtures() -> dict[str, Any]:
    """Return all fixed valid and negative contract fixtures without random values."""
    completed = _run_view(COMPLETED_RUN_ID, "completed", _brief(), None)
    queued = _run_view(QUEUED_RUN_ID, "queued", None, None)
    revoked = _run_view(REVOKED_RUN_ID, "completed", None, "license_revoked")
    revoked_with_brief = _run_view(
        REVOKED_RUN_ID, "completed", _brief(REVOKED_RUN_ID), "license_revoked"
    )
    revoked_not_completed = _run_view(REVOKED_RUN_ID, "failed", None, "license_revoked")
    search_input = {
        "query": "fixture event",
        "entity_ids": ["CN.SH.600519"],
        "as_of": "2026-10-29T10:00:00+08:00",
        "limit": 10,
        "cursor": None,
    }
    event = {
        "event_id": EVENT_ID,
        "run_id": COMPLETED_RUN_ID,
        "seq": 1,
        "type": "claim_checked",
        "occurred_at": "2026-10-29T10:03:00+08:00",
        "payload": {"claim_id": CLAIM_ID, "passed": True, "error_code": None},
    }
    unavailable = _envelope(
        REQUEST_ID,
        None,
        status="unavailable",
        error={
            "code": "market_data_unverifiable",
            "message": "No approved market payload is available for this cutoff.",
            "retryable": False,
        },
        warnings=["No live refresh or mock fallback was performed."],
        license_status="not_applicable",
    )
    error = _envelope(
        REQUEST_ID,
        None,
        status="error",
        error={"code": "execution_unavailable", "message": "Fixture executor is disabled.", "retryable": True},
        license_status="not_applicable",
    )
    missing_nullable = _claim()
    del missing_nullable["valid_until"]
    bad_numeric = _market_payload()
    bad_numeric["fields"] = [{"name": "close", "value": 1450.25, "unit": "CNY"}]
    fact_without_citation = _claim()
    fact_without_citation["evidence_ids"] = []
    too_many_entities = {
        "request_id": REQUEST_ID,
        "entity_ids": ["CN.SH.600519", "CN.SZ.000001"],
        "as_of": "2026-10-29T10:00:00+08:00",
        "seed_evidence_id": EVENT_EVIDENCE_ID,
        "question": None,
    }
    extra_model = {
        **too_many_entities,
        "entity_ids": ["CN.SH.600519"],
        "model_id": "caller-selected-model",
    }
    return {
        "fixtures/event-evidence.json": _event_evidence(),
        "fixtures/market-evidence.json": _market_evidence(),
        "fixtures/market-payload.json": _market_payload(),
        "fixtures/claim.json": _claim(),
        "fixtures/brief.json": _brief(),
        "fixtures/run-queued.json": queued,
        "fixtures/run-completed.json": completed,
        "fixtures/run-license-revoked.json": revoked,
        "fixtures/mcp-result-policy.json": _mcp_result_policy_fixtures(),
        "fixtures/event.json": event,
        "fixtures/search-articles-input.json": search_input,
        "fixtures/market-unavailable-envelope.json": unavailable,
        "fixtures/error-envelope.json": error,
        "fixtures/tool-success-envelopes.json": _tool_success_envelopes(),
        "fixtures/negative/future-as-of-input.json": {**search_input, "as_of": "2026-10-29T10:06:00+08:00"},
        "fixtures/negative/naive-time-input.json": {**search_input, "as_of": "2026-10-29T10:00:00"},
        "fixtures/negative/extra-model-input.json": extra_model,
        "fixtures/negative/bad-numeric.json": bad_numeric,
        "fixtures/negative/fact-without-citation.json": fact_without_citation,
        "fixtures/negative/missing-required-nullable.json": missing_nullable,
        "fixtures/negative/too-many-entities.json": too_many_entities,
        "fixtures/negative/license-revoked-with-brief.json": revoked_with_brief,
        "fixtures/negative/license-revoked-not-completed.json": revoked_not_completed,
        "fixtures/negative/mcp-is-error-conflict.json": {
            "status": "error",
            "isError": False,
            "expected_validation_code": "mcp_is_error_mismatch",
        },
    }


def _fixture_index() -> dict[str, Any]:
    """Register fixture validation intent and expected negative error codes."""
    return {
        "schema_version": SCHEMA_VERSION,
        "mcp_result_policy": {
            "path": "fixtures/mcp-result-policy.json",
            "negative_path": "fixtures/negative/mcp-is-error-conflict.json",
            "mapping": MCP_RESULT_POLICY,
        },
        "valid": [
            {"path": "fixtures/event-evidence.json", "model": "EvidenceV1", "schema": "schemas/EvidenceV1.json"},
            {"path": "fixtures/market-evidence.json", "model": "EvidenceV1", "schema": "schemas/EvidenceV1.json"},
            {"path": "fixtures/market-payload.json", "model": "MarketPayloadV1", "schema": "schemas/MarketPayloadV1.json"},
            {"path": "fixtures/claim.json", "model": "ClaimV1", "schema": "schemas/ClaimV1.json"},
            {"path": "fixtures/brief.json", "model": "ResearchBriefV1", "schema": "schemas/ResearchBriefV1.json"},
            {"path": "fixtures/run-queued.json", "model": "ResearchRunViewV1", "schema": "schemas/ResearchRunViewV1.json"},
            {"path": "fixtures/run-completed.json", "model": "ResearchRunViewV1", "schema": "schemas/ResearchRunViewV1.json"},
            {"path": "fixtures/run-license-revoked.json", "model": "ResearchRunViewV1", "schema": "schemas/ResearchRunViewV1.json"},
            {"path": "fixtures/event.json", "model": "RunEventV1", "schema": "schemas/RunEventV1.json"},
            {"path": "fixtures/search-articles-input.json", "model": "SearchArticlesInput", "schema": "schemas/SearchArticlesInput.json"},
            {"path": "fixtures/market-unavailable-envelope.json", "model": "ResearchEnvelope[MarketPayloadV1]", "schema": "schemas/ResearchEnvelope.MarketPayloadV1.json"},
            {"path": "fixtures/error-envelope.json", "model": "ResearchEnvelope[ArticlesSearchResult]", "schema": "schemas/ResearchEnvelope.ArticlesSearchResult.json"},
        ],
        "negative": [
            {"path": "fixtures/negative/future-as-of-input.json", "model": "SearchArticlesInput", "expected_validation_code": "as_of_in_future"},
            {"path": "fixtures/negative/naive-time-input.json", "model": "SearchArticlesInput", "expected_validation_code": "timezone_aware"},
            {"path": "fixtures/negative/extra-model-input.json", "model": "StartResearchInput", "expected_validation_code": "extra_forbidden"},
            {"path": "fixtures/negative/bad-numeric.json", "model": "MarketPayloadV1", "expected_validation_code": "string_type"},
            {"path": "fixtures/negative/fact-without-citation.json", "model": "ClaimV1", "expected_validation_code": "fact_requires_evidence"},
            {"path": "fixtures/negative/missing-required-nullable.json", "model": "ClaimV1", "expected_validation_code": "missing"},
            {"path": "fixtures/negative/too-many-entities.json", "model": "StartResearchInput", "expected_validation_code": "too_long"},
            {
                "path": "fixtures/negative/license-revoked-with-brief.json",
                "model": "ResearchRunViewV1",
                "schema": "schemas/ResearchRunViewV1.json",
                "expected_validation_code": "license_revoked_brief_forbidden",
            },
            {
                "path": "fixtures/negative/license-revoked-not-completed.json",
                "model": "ResearchRunViewV1",
                "schema": "schemas/ResearchRunViewV1.json",
                "expected_validation_code": "license_revoked_requires_completed",
            },
        ],
    }


def _generated_files() -> dict[str, bytes]:
    """Generate all schemas, fixtures, manifest hashes, and final manifest bytes."""
    files: dict[str, bytes] = {}
    schema_paths: dict[str, str] = {}
    for name, model in _schema_sources():
        path = _schema_file_name(name)
        schema_paths[name] = path
        schema = _apply_run_state_conditions(model.model_json_schema())
        if name == "RunEventV1":
            schema = _apply_event_payload_conditions(schema)
        files[path] = _canonical_json(schema)

    for tool in TOOL_REGISTRY:
        input_path = _schema_file_name(f"{tool.name}.input")
        output_path = _schema_file_name(f"{tool.name}.output")
        files[input_path] = _canonical_json(tool.input_model.model_json_schema())
        files[output_path] = _canonical_json(
            _apply_run_state_conditions(tool.output_model.model_json_schema())
        )
        schema_paths[f"{tool.name}:input"] = input_path
        schema_paths[f"{tool.name}:output"] = output_path

    fixtures = _fixtures()
    fixtures["fixtures/index.json"] = _fixture_index()
    for path, payload in fixtures.items():
        files[path] = _canonical_json(payload)

    schema_file_entries = [
        {"path": path, "sha256": hashlib.sha256(files[path]).hexdigest()}
        for path in sorted(path for path in files if path.startswith("schemas/"))
    ]
    fixture_file_entries = [
        {"path": path, "sha256": hashlib.sha256(files[path]).hexdigest()}
        for path in sorted(path for path in files if path.startswith("fixtures/"))
    ]
    manifest_without_digest = {
        "schema_version": SCHEMA_VERSION,
        "mcp_endpoint": "/api/v1/mcp",
        "tools": [
            {
                "name": tool.name,
                "input_schema": schema_paths[f"{tool.name}:input"],
                "output_schema": schema_paths[f"{tool.name}:output"],
            }
            for tool in TOOL_REGISTRY
        ],
        "http_paths": list(HTTP_PATHS),
        "mcp_result_policy": MCP_RESULT_POLICY,
        "schema_files": schema_file_entries,
        "fixture_files": fixture_file_entries,
    }
    manifest = {
        **manifest_without_digest,
        "contract_digest": hashlib.sha256(_compact_json(manifest_without_digest).encode("utf-8")).hexdigest(),
    }
    files["manifest.json"] = _canonical_json(manifest)
    return files


def _write_files(files: dict[str, bytes]) -> None:
    """Write only changed generated output files below the contract root."""
    for relative_path, content in files.items():
        target = CONTRACT_ROOT / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.read_bytes() != content:
            target.write_bytes(content)


def _check_files(files: dict[str, bytes]) -> list[str]:
    """Return deterministic differences between expected and checked-in generated files."""
    differences: list[str] = []
    expected_paths = set(files)
    for relative_path, content in files.items():
        target = CONTRACT_ROOT / relative_path
        if not target.exists():
            differences.append(f"missing {relative_path}")
        elif target.read_bytes() != content:
            differences.append(f"different {relative_path}")
    for directory in (CONTRACT_ROOT / "schemas", CONTRACT_ROOT / "fixtures"):
        if directory.exists():
            for path in sorted(directory.rglob("*.json")):
                relative_path = path.relative_to(CONTRACT_ROOT).as_posix()
                if relative_path not in expected_paths:
                    differences.append(f"unexpected {relative_path}")
    return differences


def main() -> int:
    """Generate artifacts or check that existing generated artifacts are current."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail when generated artifacts differ.")
    arguments = parser.parse_args()
    files = _generated_files()
    if arguments.check:
        differences = _check_files(files)
        if differences:
            print("research-v1.1 contract artifacts are not current:", file=sys.stderr)
            print("\n".join(differences), file=sys.stderr)
            return 1
        print("research-v1.1 contract artifacts are current")
        return 0
    _write_files(files)
    print(f"generated {len(files)} research-v1.1 contract artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
