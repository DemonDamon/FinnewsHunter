"""Test the deterministic research-v1.1 contract artifacts.

Author: Damon Li
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from app.research.contracts import (
    MCP_RESULT_POLICY,
    TOOL_REGISTRY,
    ArticlesSearchResult,
    ClaimV1,
    EvidenceV1,
    GetEvidenceInput,
    GetMarketSnapshotInput,
    GetRunInput,
    MarketPayloadV1,
    ResearchBriefV1,
    ResearchEnvelope,
    ResearchRunViewV1,
    RunEventV1,
    SearchArticlesInput,
    StartResearchInput,
    ToolDefinition,
)
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = BACKEND_ROOT.parent
CONTRACT_ROOT = REPOSITORY_ROOT / "docs" / "contracts" / "research-v1.1"
FIXTURE_ROOT = CONTRACT_ROOT / "fixtures"
TEST_NOW = datetime.fromisoformat("2026-10-29T10:05:00+08:00")


def _read_json(path: Path) -> Any:
    """Read a UTF-8 JSON fixture or generated contract file."""
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_json(payload: Any) -> str:
    """Serialize payloads using the contract's deterministic JSON form."""
    return json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )


def _validate_with_schema(schema_path: str, payload: Any) -> list[Any]:
    """Validate a JSON payload against one generated contract schema."""
    schema = _read_json(CONTRACT_ROOT / schema_path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return list(validator.iter_errors(payload))


def _walk_mappings(value: Any) -> list[dict[str, Any]]:
    """Return every JSON object nested below a fixture payload."""
    if isinstance(value, dict):
        return [
            value,
            *[item for child in value.values() for item in _walk_mappings(child)],
        ]
    if isinstance(value, list):
        return [item for child in value for item in _walk_mappings(child)]
    return []


def _assert_mcp_is_error_policy(status: str, is_error: bool) -> None:
    """Reject a CallToolResult isError bit that conflicts with frozen status policy."""
    if is_error is not MCP_RESULT_POLICY[status]:
        raise ValueError("mcp_is_error_mismatch")


def _model_for_name(model_name: str) -> type[Any]:
    """Return the public DTO class recorded by the fixture index."""
    models: dict[str, type[Any]] = {
        "EvidenceV1": EvidenceV1,
        "MarketPayloadV1": MarketPayloadV1,
        "ClaimV1": ClaimV1,
        "ResearchBriefV1": ResearchBriefV1,
        "ResearchRunViewV1": ResearchRunViewV1,
        "SearchArticlesInput": SearchArticlesInput,
        "GetEvidenceInput": GetEvidenceInput,
        "GetMarketSnapshotInput": GetMarketSnapshotInput,
        "StartResearchInput": StartResearchInput,
        "GetRunInput": GetRunInput,
        "ResearchEnvelope[ArticlesSearchResult]": ResearchEnvelope[
            ArticlesSearchResult
        ],
        "ResearchEnvelope[EvidenceV1]": ResearchEnvelope[EvidenceV1],
        "ResearchEnvelope[MarketPayloadV1]": ResearchEnvelope[MarketPayloadV1],
        "ResearchEnvelope[ResearchRunViewV1]": ResearchEnvelope[ResearchRunViewV1],
        "RunEventV1": RunEventV1,
    }
    return models[model_name]


def _model_validate(model: type[Any], payload: Any) -> Any:
    """Validate a DTO with the fixed test clock where the model accepts context."""
    return model.model_validate(payload, context={"now": TEST_NOW})


def _run_generator(*arguments: str) -> subprocess.CompletedProcess[str]:
    """Run the checked-in contract generator in the current isolated interpreter."""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(BACKEND_ROOT)
    return subprocess.run(
        [
            sys.executable,
            str(BACKEND_ROOT / "scripts" / "generate_research_contracts.py"),
            *arguments,
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def test_generator_check_is_deterministic() -> None:
    """Require generated artifacts to exactly match deterministic DTO output."""
    result = _run_generator("--check")
    assert result.returncode == 0, result.stdout + result.stderr


def test_manifest_has_exact_tools_paths_and_integrity_hashes() -> None:
    """Verify the immutable manifest surface and every generated file digest."""
    manifest = _read_json(CONTRACT_ROOT / "manifest.json")
    assert manifest["schema_version"] == "research-v1.1"
    assert manifest["mcp_endpoint"] == "/api/v1/mcp"
    assert [tool["name"] for tool in manifest["tools"]] == [
        "finnews.search_articles",
        "finnews.get_evidence",
        "finnews.get_market_snapshot",
        "finnews.start_research",
        "finnews.get_run",
    ]
    assert len(manifest["http_paths"]) == 4
    assert manifest["http_paths"] == [
        {"method": "POST", "path": "/api/v1/research/runs"},
        {"method": "GET", "path": "/api/v1/research/runs/{id}"},
        {"method": "GET", "path": "/api/v1/research/runs/{id}/events"},
        {"method": "GET", "path": "/api/v1/research/evidence/{id}?run_id={id}"},
    ]
    assert manifest["mcp_result_policy"] == MCP_RESULT_POLICY
    assert all(
        "ResearchEnvelope[Any]" not in tool["output_schema"]
        for tool in manifest["tools"]
    )

    for entry in [*manifest["schema_files"], *manifest["fixture_files"]]:
        assert not Path(entry["path"]).is_absolute()
        payload = (CONTRACT_ROOT / entry["path"]).read_bytes()
        assert entry["sha256"] == __import__("hashlib").sha256(payload).hexdigest()

    digest_payload = {
        key: value for key, value in manifest.items() if key != "contract_digest"
    }
    assert (
        manifest["contract_digest"]
        == __import__("hashlib")
        .sha256(_canonical_json(digest_payload).encode("utf-8"))
        .hexdigest()
    )
    assert "secret" not in _canonical_json(manifest).lower()


def test_registry_has_only_real_concrete_tool_contracts() -> None:
    """Ensure discovery can expose only the five bounded public tool definitions."""
    assert all(isinstance(tool, ToolDefinition) for tool in TOOL_REGISTRY)
    assert [tool.name for tool in TOOL_REGISTRY] == [
        "finnews.search_articles",
        "finnews.get_evidence",
        "finnews.get_market_snapshot",
        "finnews.start_research",
        "finnews.get_run",
    ]
    for tool in TOOL_REGISTRY:
        schema = tool.input_model.model_json_schema()
        assert schema["additionalProperties"] is False
        assert tool.output_model is not ResearchEnvelope
        assert "Any" not in json.dumps(
            tool.output_model.model_json_schema(), sort_keys=True
        )


def test_valid_fixtures_pass_pydantic_and_json_schema() -> None:
    """Require every registered positive fixture to pass both contract validators."""
    fixture_index = _read_json(FIXTURE_ROOT / "index.json")
    assert fixture_index["schema_version"] == "research-v1.1"
    for entry in fixture_index["valid"]:
        payload = _read_json(CONTRACT_ROOT / entry["path"])
        _model_validate(_model_for_name(entry["model"]), payload)
        assert not _validate_with_schema(entry["schema"], payload), entry["path"]


def test_negative_fixtures_fail_with_registered_pydantic_codes() -> None:
    """Verify invalid examples never appear in the schema-passing fixture list."""
    fixture_index = _read_json(FIXTURE_ROOT / "index.json")
    for entry in fixture_index["negative"]:
        payload = _read_json(CONTRACT_ROOT / entry["path"])
        with pytest.raises(ValidationError) as error:
            _model_validate(_model_for_name(entry["model"]), payload)
        assert entry["expected_validation_code"] in {
            item["type"] for item in error.value.errors()
        }, entry["path"]
        if "schema" in entry:
            assert _validate_with_schema(entry["schema"], payload), entry["path"]


def test_tool_text_and_structured_fixtures_are_equivalent() -> None:
    """Keep MCP text JSON and structuredContent representations identical."""
    comparisons = _read_json(FIXTURE_ROOT / "tool-success-envelopes.json")
    assert set(comparisons) == {tool.name for tool in TOOL_REGISTRY}
    tool_by_name = {tool.name: tool for tool in TOOL_REGISTRY}
    for name, comparison in comparisons.items():
        text_payload = json.loads(comparison["text"])
        structured_payload = comparison["structured"]
        assert text_payload == structured_payload
        _model_validate(tool_by_name[name].output_model, structured_payload)
        assert not _validate_with_schema(comparison["schema"], structured_payload)


def test_market_tool_provenance_matches_its_market_payload() -> None:
    """Require the market snapshot source reference to identify its exact \
payload evidence."""
    comparisons = _read_json(FIXTURE_ROOT / "tool-success-envelopes.json")
    market_envelope = comparisons["finnews.get_market_snapshot"]["structured"]
    market_evidence = _read_json(FIXTURE_ROOT / "market-evidence.json")
    market_payload = market_envelope["data"]
    assert market_envelope["source"] == [
        {
            "source_id": market_evidence["source_id"],
            "evidence_id": market_payload["evidence_id"],
            "provider": market_payload["provider"],
            "version": market_payload["version"],
            "hash": market_evidence["content_hash"],
        }
    ]


def test_synthetic_envelopes_never_claim_approved_license() -> None:
    """Keep all fixture-origin or mock envelope outputs out of approval semantics."""
    for path in sorted(FIXTURE_ROOT.rglob("*.json")):
        fixture = _read_json(path)
        for mapping in _walk_mappings(fixture):
            if {"schema_version", "status", "data", "license_status"}.issubset(mapping):
                assert mapping["license_status"] == "not_applicable", path


def test_mcp_result_policy_fixture_has_four_equivalent_transport_shapes() -> None:
    """Freeze text, structured content, and isError semantics for all \
envelope statuses."""
    fixture_index = _read_json(FIXTURE_ROOT / "index.json")
    fixture_entry = fixture_index["mcp_result_policy"]
    assert fixture_entry["mapping"] == MCP_RESULT_POLICY
    comparisons = _read_json(CONTRACT_ROOT / fixture_entry["path"])
    assert set(comparisons) == set(MCP_RESULT_POLICY)
    for status, comparison in comparisons.items():
        structured_payload = comparison["structured"]
        assert structured_payload["status"] == status
        assert json.loads(comparison["text"]) == structured_payload
        _assert_mcp_is_error_policy(status, comparison["isError"])
        _model_validate(_model_for_name(comparison["model"]), structured_payload)
        assert not _validate_with_schema(comparison["schema"], structured_payload)

    error_payload = comparisons["error"]["structured"]
    assert error_payload["error"]["code"] == "execution_unavailable"
    assert comparisons["error"]["isError"] is True


def test_mcp_result_policy_negative_fixture_rejects_contradictory_is_error() -> None:
    """Keep the registered negative fixture from normalizing a \
contradictory transport bit."""
    fixture_index = _read_json(FIXTURE_ROOT / "index.json")
    fixture_entry = fixture_index["mcp_result_policy"]
    negative = _read_json(CONTRACT_ROOT / fixture_entry["negative_path"])
    with pytest.raises(ValueError, match=negative["expected_validation_code"]):
        _assert_mcp_is_error_policy(negative["status"], negative["isError"])


def test_aware_datetime_and_as_of_runtime_rules_are_not_schema_guesses() -> None:
    """Reject naive and future tool times using runtime validation context."""
    future_payload = _read_json(FIXTURE_ROOT / "negative" / "future-as-of-input.json")
    naive_payload = _read_json(FIXTURE_ROOT / "negative" / "naive-time-input.json")
    with pytest.raises(ValidationError, match="future"):
        _model_validate(SearchArticlesInput, future_payload)
    with pytest.raises(ValidationError):
        _model_validate(SearchArticlesInput, naive_payload)

    schema = SearchArticlesInput.model_json_schema()
    assert "future" not in json.dumps(schema).lower()


def test_decimal_finite_and_identifier_guards_reject_unsafe_json_shapes() -> None:
    """Reject float decimals, nonfinite confidence, invalid UUIDs, and invalid zones."""
    bad_decimal = _read_json(FIXTURE_ROOT / "negative" / "bad-numeric.json")
    with pytest.raises(ValidationError):
        _model_validate(MarketPayloadV1, bad_decimal)

    evidence = _read_json(FIXTURE_ROOT / "event-evidence.json")
    evidence["evidence_id"] = "not-a-uuid"
    with pytest.raises(ValidationError):
        _model_validate(EvidenceV1, evidence)

    evidence = _read_json(FIXTURE_ROOT / "event-evidence.json")
    evidence["timezone"] = "Not/AZone"
    with pytest.raises(ValidationError):
        _model_validate(EvidenceV1, evidence)

    claim = _read_json(FIXTURE_ROOT / "claim.json")
    claim["confidence"] = float("nan")
    with pytest.raises(ValidationError):
        _model_validate(ClaimV1, claim)


def test_required_nullable_and_cross_object_invariants_are_enforced() -> None:
    """Enforce explicit null fields and Brief/Run time and identifier consistency."""
    missing_nullable = _read_json(
        FIXTURE_ROOT / "negative" / "missing-required-nullable.json"
    )
    with pytest.raises(ValidationError):
        _model_validate(ClaimV1, missing_nullable)

    fact_without_citation = _read_json(
        FIXTURE_ROOT / "negative" / "fact-without-citation.json"
    )
    with pytest.raises(ValidationError, match="evidence"):
        _model_validate(ClaimV1, fact_without_citation)

    completed = _read_json(FIXTURE_ROOT / "run-completed.json")
    completed["brief"]["run_id"] = "11111111-1111-1111-1111-111111111111"
    with pytest.raises(ValidationError):
        _model_validate(ResearchRunViewV1, completed)

    license_revoked = _read_json(FIXTURE_ROOT / "run-license-revoked.json")
    validated = _model_validate(ResearchRunViewV1, license_revoked)
    assert validated.status == "completed"
    assert validated.error_code == "license_revoked"
    assert validated.brief is None


def test_license_revoked_brief_is_rejected_by_direct_and_nested_contract_schemas() -> (
    None
):
    """Reject revoked Brief leakage through both DTO validation and \
generated nested schemas."""
    revoked_with_brief = _read_json(
        FIXTURE_ROOT / "negative" / "license-revoked-with-brief.json"
    )
    with pytest.raises(ValidationError) as error:
        _model_validate(ResearchRunViewV1, revoked_with_brief)
    assert "license_revoked_brief_forbidden" in {
        item["type"] for item in error.value.errors()
    }
    assert _validate_with_schema("schemas/ResearchRunViewV1.json", revoked_with_brief)

    comparisons = _read_json(FIXTURE_ROOT / "tool-success-envelopes.json")
    nested_envelope = comparisons["finnews.get_run"]["structured"]
    nested_envelope["data"] = revoked_with_brief
    with pytest.raises(ValidationError):
        _model_validate(ResearchEnvelope[ResearchRunViewV1], nested_envelope)
    for schema_path in (
        "schemas/ResearchEnvelope.ResearchRunViewV1.json",
        "schemas/finnews.get_run.output.json",
        "schemas/finnews.start_research.output.json",
    ):
        assert _validate_with_schema(schema_path, nested_envelope), schema_path


def test_entity_normalization_is_limited_to_tool_input_boundary() -> None:
    """Normalize only the documented short market identifier input form."""
    payload = _read_json(FIXTURE_ROOT / "search-articles-input.json")
    payload["entity_ids"] = ["SH600519"]
    normalized = _model_validate(SearchArticlesInput, payload)
    assert normalized.entity_ids == ["CN.SH.600519"]

    evidence = _read_json(FIXTURE_ROOT / "event-evidence.json")
    evidence["entity_ids"] = ["SH600519"]
    with pytest.raises(ValidationError):
        _model_validate(EvidenceV1, evidence)


def test_bounded_lists_extra_fields_and_event_payload_mapping_are_enforced() -> None:
    """Reject unbounded input shapes, extra fields, and mismatched event payloads."""
    too_many_entities = _read_json(FIXTURE_ROOT / "negative" / "too-many-entities.json")
    with pytest.raises(ValidationError):
        _model_validate(StartResearchInput, too_many_entities)

    extra_model = _read_json(FIXTURE_ROOT / "negative" / "extra-model-input.json")
    with pytest.raises(ValidationError):
        _model_validate(StartResearchInput, extra_model)

    event = _read_json(FIXTURE_ROOT / "event.json")
    event["type"] = "completed"
    with pytest.raises(ValidationError):
        _model_validate(RunEventV1, event)
    assert _validate_with_schema("schemas/RunEventV1.json", event)


def test_contract_module_has_no_runtime_dependencies_or_network_surface() -> None:
    """Keep DTO definitions independent from settings, storage, providers, and AGX."""
    contract_source = (BACKEND_ROOT / "app" / "research" / "contracts.py").read_text(
        encoding="utf-8"
    )
    forbidden = ("Settings", "database", "Provider", "agenticx", "FastAPI", "APIRouter")
    assert not any(token in contract_source for token in forbidden)
    assert not (BACKEND_ROOT / "app" / "research" / "routes.py").exists()
