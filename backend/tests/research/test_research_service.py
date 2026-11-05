"""Verify the shared research service against a strictly in-memory ledger fake.

Fixture DTOs are inputs only: every test invokes production service behavior.
All Principals are produced by the local RS256 verifier, never client fixtures.

Author: Damon Li
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import get_args
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from app.research.contracts import (
    MCP_RESULT_POLICY,
    ArticlesSearchResult,
    EvidenceV1,
    GetEvidenceInput,
    GetMarketSnapshotInput,
    GetRunInput,
    MarketPayloadV1,
    ResearchEnvelope,
    ResearchRunViewV1,
    RunEventV1,
    SearchArticlesInput,
    StartedEventPayloadV1,
    StartResearchInput,
)
from app.research.errors import DomainError, DomainErrorCode
from app.research.ports import (
    AuthorizationPort,
    Principal,
    ResearchLedgerPort,
    RunEventPage,
)
from app.research.service import EVENT_PAGE_SIZE, ResearchApplicationService

from tests.research.test_research_transport_auth import (
    ENTITY,
    NOW,
    MemoryIdentity,
    make_memory_identity,
    no_network,  # noqa: F401 -- register the shared no-network pytest guard
)

CUTOFF = datetime(2026, 10, 29, 2, tzinfo=UTC)
RUN_ID = UUID("33333333-3333-3333-3333-333333333333")
EVIDENCE_ID = UUID("11111111-1111-1111-1111-111111111111")
INPUT_REQUEST_ID = UUID("77777777-7777-7777-7777-777777777777")
UNSAFE = (
    "question-secret bearer-secret JWKS-secret SELECT password FROM users traceback"
)
FIXTURES = Path(__file__).resolve().parents[3] / "docs/contracts/research-v1.1/fixtures"
OPERATIONS = (
    ("search_articles", "search_articles", ArticlesSearchResult),
    ("get_evidence", "read_evidence", EvidenceV1),
    ("get_market_snapshot", "get_market_snapshot", MarketPayloadV1),
    ("start_research", "create_or_reuse_run", ResearchRunViewV1),
    ("get_run", "get_run", ResearchRunViewV1),
)


@pytest.fixture
def identity() -> MemoryIdentity:
    """Generate an in-memory verifier, without importing a pytest fixture alias."""
    return make_memory_identity()


@pytest.fixture
def principal(identity: MemoryIdentity) -> Principal:
    """Use the same verified Principal path as an HTTP bearer dependency."""
    from app.research.identity_context import verify_http_principal

    return asyncio.run(
        verify_http_principal(
            headers=[(b"authorization", f"Bearer {identity.token()}".encode())],
            verifier=identity.verifier,
            clock=lambda: NOW,
        )
    )


@pytest.fixture
def ledger() -> AsyncMock:
    """Fake only the frozen Port, without any database/session/provider."""
    return AsyncMock(spec=ResearchLedgerPort)


@pytest.fixture
def authorization() -> Mock:
    """The ledger already owns resource rules; no duplicated service preflight."""
    return Mock(spec=AuthorizationPort)


def _service(ledger, authorization, *, enabled=True, clock=lambda: NOW):
    """Test helper for _service."""
    return ResearchApplicationService(
        ledger=ledger,
        authorization=authorization,
        clock=clock,
        execution_enabled=enabled,
    )


def _request(name: str):
    """Create strict frozen DTO inputs with a historical cutoff."""
    return {
        "search_articles": lambda: SearchArticlesInput(
            query="synthetic",
            entity_ids=[ENTITY],
            as_of=CUTOFF,
            limit=7,
            cursor="opaque_cursor",
        ),
        "get_evidence": lambda: GetEvidenceInput(
            evidence_id=EVIDENCE_ID, run_id=RUN_ID
        ),
        "get_market_snapshot": lambda: GetMarketSnapshotInput(
            entity_ids=[ENTITY],
            as_of=CUTOFF,
            run_id=RUN_ID,
        ),
        "start_research": lambda: StartResearchInput(
            request_id=INPUT_REQUEST_ID,
            entity_ids=[ENTITY],
            as_of=CUTOFF,
            seed_evidence_id=EVIDENCE_ID,
            question=UNSAFE,
        ),
        "get_run": lambda: GetRunInput(run_id=RUN_ID),
    }[name]()


def _result(name: str, model):
    """Use existing synthetic ledger output DTOs, not envelope expectations."""
    envelopes = json.loads((FIXTURES / "tool-success-envelopes.json").read_text())
    return model.model_validate(envelopes[f"finnews.{name}"]["structured"]["data"])


@pytest.mark.parametrize("name,port_name,model", OPERATIONS)
@pytest.mark.parametrize("envelope", [False, True])
def test_exact_port_mapping_and_same_clock_in_both_transports(
    ledger,
    authorization,
    principal,
    name,
    port_name,
    model,
    envelope,
) -> None:
    """Test helper test_exact_port_mapping_and_same_clock_in_both_transports."""
    request, result = _request(name), _result(name, model)
    getattr(ledger, port_name).return_value = result
    clock = Mock(return_value=NOW)
    service = _service(ledger, authorization, clock=clock)
    output = asyncio.run(
        getattr(service, name)(
            principal=principal,
            request=request,
            envelope=envelope,
        )
    )
    getattr(ledger, port_name).assert_awaited_once_with(
        principal=principal,
        request=request,
        now=NOW,
    )
    # Identity and request are not rebuilt or augmented by a transport/service.
    assert getattr(ledger, port_name).await_args.kwargs["principal"] is principal
    assert getattr(ledger, port_name).await_args.kwargs["request"] is request
    assert len(ledger.mock_calls) == 1
    assert not authorization.mock_calls
    clock.assert_called_once_with()
    if envelope:
        assert isinstance(output, ResearchEnvelope[model])
        assert output.data is result
        assert output.status == "ok" and output.error is None
        assert output.as_of == NOW
        assert output.request_id != INPUT_REQUEST_ID
        assert output.request_id.version == 4
        assert output.warnings == []
        assert output.source == []  # no fabricated event provider provenance
        assert model.model_validate(output.model_dump(mode="json")["data"]) == result
        assert not MCP_RESULT_POLICY[output.status]
    else:
        assert output is result
    if hasattr(request, "as_of"):
        assert request.as_of == CUTOFF != NOW


def test_envelopes_get_fresh_server_request_ids_and_single_clock_samples(
    ledger,
    authorization,
    principal,
) -> None:
    """Test helper test_envelopes_get_fresh_server_request_ids_and_single_..."""
    ledger.get_run.return_value = _result("get_run", ResearchRunViewV1)
    clock = Mock(side_effect=[NOW, NOW + timedelta(seconds=1)])
    service = _service(ledger, authorization, clock=clock)

    async def scenario():
        """Test helper scenario."""
        return [
            await service.get_run(
                principal=principal, request=_request("get_run"), envelope=True
            )
            for _ in range(2)
        ]

    first, second = asyncio.run(scenario())
    assert first.request_id != second.request_id
    assert [first.as_of, second.as_of] == [NOW, NOW + timedelta(seconds=1)]
    assert [call.kwargs["now"] for call in ledger.get_run.await_args_list] == [
        first.as_of,
        second.as_of,
    ]
    assert clock.call_count == 2


@pytest.mark.parametrize("envelope", [False, True])
def test_execution_disabled_never_calls_ledger(
    ledger,
    authorization,
    principal,
    envelope,
) -> None:
    """Test helper test_execution_disabled_never_calls_ledger."""
    service = _service(ledger, authorization, enabled=False)
    if envelope:
        result = asyncio.run(
            service.start_research(
                principal=principal,
                request=_request("start_research"),
                envelope=True,
            )
        )
        assert result.status == "unavailable"
        assert result.data is None
        assert result.error.code == "execution_unavailable"
        assert result.error.retryable is True
    else:
        with pytest.raises(DomainError) as raised:
            asyncio.run(
                service.start_research(
                    principal=principal,
                    request=_request("start_research"),
                )
            )
        assert raised.value.code == "execution_unavailable"
    assert not ledger.mock_calls
    assert not authorization.mock_calls


def test_enabled_execution_still_relies_on_atomic_ledger_readiness(
    ledger,
    authorization,
    principal,
) -> None:
    """Test helper test_enabled_execution_still_relies_on_atomic_ledger_readiness."""
    ledger.create_or_reuse_run.side_effect = DomainError(
        code="execution_unavailable",
        safe_message=UNSAFE,
        retryable=True,
    )
    output = asyncio.run(
        _service(ledger, authorization).start_research(
            principal=principal,
            request=_request("start_research"),
            envelope=True,
        )
    )
    assert output.status == "unavailable" and output.data is None
    assert output.error.code == "execution_unavailable"
    assert UNSAFE not in output.model_dump_json()
    assert ledger.create_or_reuse_run.await_count == 1


def test_idempotency_is_not_cached_or_decided_by_service(
    ledger, authorization, principal
) -> None:
    """Test helper test_idempotency_is_not_cached_or_decided_by_service."""
    result = _result("start_research", ResearchRunViewV1)
    ledger.create_or_reuse_run.return_value = result
    request = _request("start_research")
    service = _service(ledger, authorization)

    async def scenario():
        """Test helper scenario."""
        first = await service.start_research(principal=principal, request=request)
        second = await service.start_research(principal=principal, request=request)
        assert first is second is result

    asyncio.run(scenario())
    assert ledger.create_or_reuse_run.await_count == 2
    assert all(
        call.kwargs["request"] is request
        for call in ledger.create_or_reuse_run.await_args_list
    )


@pytest.mark.parametrize("code", get_args(DomainErrorCode))
@pytest.mark.parametrize("envelope", [False, True])
def test_all_domain_error_codes_have_safe_consistent_dto_or_envelope_outcomes(
    ledger,
    authorization,
    principal,
    code,
    envelope,
    caplog,
) -> None:
    """Test helper test_all_domain_error_codes_have_safe_consistent_dto_or..."""
    retryable = code in {
        "identity_material_unavailable",
        "execution_unavailable",
        "persistence_failed",
    }
    ledger.get_run.side_effect = DomainError(
        code=code, safe_message=UNSAFE, retryable=retryable
    )
    service = _service(ledger, authorization)
    if envelope:
        output = asyncio.run(
            service.get_run(
                principal=principal,
                request=_request("get_run"),
                envelope=True,
            )
        )
        assert isinstance(output, ResearchEnvelope[ResearchRunViewV1])
        assert output.status == ("unavailable" if retryable else "error")
        assert output.data is None
        assert output.error.code == code
        assert output.error.retryable is retryable
        assert UNSAFE not in output.model_dump_json()
        assert output.error.message != UNSAFE
        assert output.source == [] and output.warnings == []
        assert (
            ResearchEnvelope[ResearchRunViewV1].model_validate_json(
                output.model_dump_json()
            )
            == output
        )
    else:
        with pytest.raises(DomainError) as raised:
            asyncio.run(
                service.get_run(principal=principal, request=_request("get_run"))
            )
        assert raised.value.code == code
        assert raised.value.retryable is retryable
        assert UNSAFE not in raised.value.safe_message + repr(raised.value) + str(
            raised.value
        )
    ledger.get_run.assert_awaited_once_with(
        principal=principal, request=_request("get_run"), now=NOW
    )
    assert UNSAFE not in caplog.text


@pytest.mark.parametrize("name,port_name,model", OPERATIONS)
def test_denial_is_normalized_on_every_tool_path(
    ledger,
    authorization,
    principal,
    name,
    port_name,
    model,
) -> None:
    """Test helper test_denial_is_normalized_on_every_tool_path."""
    getattr(ledger, port_name).side_effect = DomainError(
        code="resource_not_found_or_denied",
        safe_message=UNSAFE,
        retryable=False,
    )
    output = asyncio.run(
        getattr(_service(ledger, authorization), name)(
            principal=principal,
            request=_request(name),
            envelope=True,
        )
    )
    assert output.status == "error" and output.data is None
    assert output.error.message == "resource was not found or access is denied"
    assert output.error.code == "resource_not_found_or_denied"
    assert len(ledger.mock_calls) == 1


@pytest.mark.parametrize("retryable", [False, True])
def test_only_retryable_infrastructure_errors_are_unavailable(
    ledger,
    authorization,
    principal,
    retryable,
) -> None:
    """Test helper test_only_retryable_infrastructure_errors_are_unavailable."""
    ledger.get_run.side_effect = DomainError(
        code="persistence_failed",
        safe_message=UNSAFE,
        retryable=retryable,
    )
    output = asyncio.run(
        _service(ledger, authorization).get_run(
            principal=principal,
            request=_request("get_run"),
            envelope=True,
        )
    )
    assert output.status == ("unavailable" if retryable else "error")


def test_retryable_business_error_does_not_masquerade_as_infrastructure(
    ledger,
    authorization,
    principal,
) -> None:
    """Test helper test_retryable_business_error_does_not_masquerade_as_in..."""
    ledger.get_run.side_effect = DomainError(
        code="quota_exceeded",
        safe_message=UNSAFE,
        retryable=True,
    )
    output = asyncio.run(
        _service(ledger, authorization).get_run(
            principal=principal,
            request=_request("get_run"),
            envelope=True,
        )
    )
    assert output.status == "error"
    assert output.error.retryable is True


@pytest.mark.parametrize("envelope", [False, True])
def test_missing_market_data_is_not_false_ok(
    ledger, authorization, principal, envelope
) -> None:
    """Test helper test_missing_market_data_is_not_false_ok."""
    ledger.get_market_snapshot.return_value = None
    service = _service(ledger, authorization)
    if envelope:
        output = asyncio.run(
            service.get_market_snapshot(
                principal=principal,
                request=_request("get_market_snapshot"),
                envelope=True,
            )
        )
        assert output.status == "error" and output.data is None
        assert output.error.code == "market_data_unverifiable"
    else:
        with pytest.raises(DomainError, match="^market_data_unverifiable$"):
            asyncio.run(
                service.get_market_snapshot(
                    principal=principal,
                    request=_request("get_market_snapshot"),
                )
            )
    assert ledger.get_market_snapshot.await_count == 1


def test_run_revoked_projection_is_preserved_without_brief_reconstruction(
    ledger,
    authorization,
    principal,
) -> None:
    """Test helper test_run_revoked_projection_is_preserved_without_brief_..."""
    base = _result("get_run", ResearchRunViewV1).model_dump()
    base.update(status="completed", brief=None, error_code="license_revoked")
    revoked = ResearchRunViewV1.model_validate(base)
    ledger.get_run.return_value = revoked
    output = asyncio.run(
        _service(ledger, authorization).get_run(
            principal=principal,
            request=_request("get_run"),
            envelope=True,
        )
    )
    assert output.status == "ok"
    assert output.license_status == "revoked"
    assert output.data is revoked and output.data.brief is None
    assert output.data.error_code == "license_revoked"


@pytest.mark.parametrize("cursor", [None, UUID("99999999-9999-9999-9999-999999999999")])
def test_event_page_uses_exact_cursor_clock_and_fixed_server_limit(
    ledger,
    authorization,
    principal,
    cursor,
) -> None:
    """Test helper test_event_page_uses_exact_cursor_clock_and_fixed_server_limit."""
    event = RunEventV1(
        event_id=uuid4(),
        run_id=RUN_ID,
        seq=1,
        type="started",
        occurred_at=CUTOFF,
        payload=StartedEventPayloadV1(dispatch_id="synthetic_dispatch"),
    )
    page = RunEventPage(run_id=RUN_ID, events=(event,), next_event_id=event.event_id)
    ledger.read_events.return_value = page
    output = asyncio.run(
        _service(ledger, authorization).read_events(
            principal=principal,
            run_id=RUN_ID,
            after_event_id=cursor,
        )
    )
    assert output is page
    assert output.events == (event,)
    ledger.read_events.assert_awaited_once_with(
        principal=principal,
        run_id=RUN_ID,
        after_event_id=cursor,
        limit=EVENT_PAGE_SIZE,
        now=NOW,
    )
    assert EVENT_PAGE_SIZE == 100
    assert not authorization.mock_calls


def test_event_cursor_denial_stays_safe(ledger, authorization, principal) -> None:
    """Test helper test_event_cursor_denial_stays_safe."""
    ledger.read_events.side_effect = DomainError(
        code="event_cursor_invalid",
        safe_message=UNSAFE,
        retryable=False,
    )
    with pytest.raises(DomainError) as raised:
        asyncio.run(
            _service(ledger, authorization).read_events(
                principal=principal, run_id=RUN_ID
            )
        )
    assert raised.value.code == "event_cursor_invalid"
    assert raised.value.safe_message == "event cursor is invalid"
    assert UNSAFE not in repr(raised.value)


@pytest.mark.parametrize("bad_now", [datetime(2026, 1, 1), None, "now"])
def test_bad_clock_never_reaches_ledger(
    ledger, authorization, principal, bad_now
) -> None:
    """Test helper test_bad_clock_never_reaches_ledger."""
    with pytest.raises(ValueError, match="timezone-aware"):
        asyncio.run(
            _service(ledger, authorization, clock=lambda: bad_now).get_run(
                principal=principal,
                request=_request("get_run"),
                envelope=True,
            )
        )
    assert not ledger.mock_calls


def test_aware_non_utc_clock_is_normalized_once(
    ledger, authorization, principal
) -> None:
    """Test helper test_aware_non_utc_clock_is_normalized_once."""
    offset_now = NOW.astimezone(timezone(timedelta(hours=8)))
    ledger.get_run.return_value = _result("get_run", ResearchRunViewV1)
    output = asyncio.run(
        _service(ledger, authorization, clock=lambda: offset_now).get_run(
            principal=principal,
            request=_request("get_run"),
            envelope=True,
        )
    )
    assert output.as_of == NOW and output.as_of.tzinfo is UTC
    assert ledger.get_run.await_args.kwargs["now"].tzinfo is UTC


@pytest.mark.parametrize("bad_enabled", ["false", "true", 1, 0, None])
def test_execution_switch_is_strictly_boolean(
    ledger, authorization, bad_enabled
) -> None:
    """Test helper test_execution_switch_is_strictly_boolean."""
    with pytest.raises(ValueError, match="boolean"):
        _service(ledger, authorization, enabled=bad_enabled)
    assert not ledger.mock_calls


@pytest.mark.parametrize(
    "error", [RuntimeError("programming failure"), asyncio.CancelledError()]
)
def test_unexpected_errors_and_cancellation_are_not_fabricated_as_success(
    ledger,
    authorization,
    principal,
    error,
) -> None:
    """Test helper test_unexpected_errors_and_cancellation_are_not_fabrica..."""
    ledger.get_run.side_effect = error
    with pytest.raises(type(error)):
        asyncio.run(
            _service(ledger, authorization).get_run(
                principal=principal,
                request=_request("get_run"),
                envelope=True,
            )
        )


def test_public_service_operation_set_is_exact() -> None:
    """Test helper test_public_service_operation_set_is_exact."""
    names = {
        name
        for name in vars(ResearchApplicationService)
        if not name.startswith("_")
        and callable(getattr(ResearchApplicationService, name))
    }
    assert names == {
        "search_articles",
        "get_evidence",
        "get_market_snapshot",
        "start_research",
        "get_run",
        "read_events",
    }
