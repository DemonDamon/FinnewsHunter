"""Isolated HTTP contract checks using local RS256 and an in-memory service."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import app.api.v1.research as research_http
from app.api.v1.research import (
    get_identity_verifier,
    get_research_service,
    router,
)
from app.research.contracts import RunEventV1, StartedEventPayloadV1
from app.research.errors import DomainError
from app.research.ports import RunEventPage
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.research.test_research_transport_auth import NOW, make_memory_identity

ENTITY = "CN.SH.600519"
RUN_ID = UUID("33333333-3333-3333-3333-333333333333")


class Service:
    """Test helper Service."""
    def __init__(self, *, execution_enabled: bool = False) -> None:
        """Test helper __init__."""
        self.execution_enabled = execution_enabled
        self.start_calls = 0
        self.get_run = AsyncMock(
            side_effect=DomainError(
                code="resource_not_found_or_denied",
                safe_message="resource was not found or access is denied",
                retryable=False,
            )
        )
        self.get_evidence = AsyncMock(
            side_effect=DomainError(
                code="resource_not_found_or_denied",
                safe_message="resource was not found or access is denied",
                retryable=False,
            )
        )
        self.read_events = AsyncMock()

    async def start_research(self, *, principal, request):
        """Test helper start_research."""
        self.start_calls += 1
        if "research:create" not in principal.scopes or not set(
            request.entity_ids
        ).issubset(principal.entity_ids):
            raise DomainError(
                code="resource_not_found_or_denied",
                safe_message="resource was not found or access is denied",
                retryable=False,
            )
        if not self.execution_enabled:
            raise DomainError(
                code="execution_unavailable",
                safe_message="research execution is unavailable",
                retryable=True,
            )
        return SimpleNamespace()


def _client(identity, service, monkeypatch):
    """Test helper for _client."""
    monkeypatch.setattr(research_http, "_now", lambda: NOW)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_identity_verifier] = lambda: identity.verifier
    app.dependency_overrides[get_research_service] = lambda: service
    return TestClient(app)


def _headers(token: str) -> dict[str, str]:
    """Test helper for _headers."""
    return {"Authorization": f"Bearer {token}"}


def test_router_exposes_exactly_four_paths() -> None:
    """Test helper test_router_exposes_exactly_four_paths."""
    paths = {
        (route.path, tuple(sorted(route.methods or []))) for route in router.routes
    }
    assert paths == {
        ("/api/v1/research/runs", ("POST",)),
        ("/api/v1/research/runs/{id}", ("GET",)),
        ("/api/v1/research/runs/{id}/events", ("GET",)),
        ("/api/v1/research/evidence/{id}", ("GET",)),
    }


def test_missing_and_invalid_bearer_are_rejected_without_reflection(
    monkeypatch,
) -> None:
    """Test helper test_missing_and_invalid_bearer_are_rejected_without_reflection."""
    identity, service = make_memory_identity(), Service()
    with _client(identity, service, monkeypatch) as client:
        assert client.get(f"/api/v1/research/runs/{RUN_ID}").status_code == 401
        token = identity.token()
        response = client.get(
            f"/api/v1/research/runs/{RUN_ID}", headers=_headers("invalid." + token)
        )
        assert response.status_code == 401
        assert token not in response.text


def test_identity_failures_use_fixed_error_dto_and_hide_verifier_exception(
    monkeypatch,
) -> None:
    """Test helper test_identity_failures_use_fixed_error_dto_and_hide_verifier_exception."""
    identity, service = make_memory_identity(), Service()

    class BrokenVerifier:
        """Test helper BrokenVerifier."""
        async def verify_bearer(self, *, credential, now):
            """Test helper verify_bearer."""
            raise RuntimeError("private verifier detail")

    with _client(identity, service, monkeypatch) as client:
        unauthenticated = client.get(f"/api/v1/research/runs/{RUN_ID}")
        assert unauthenticated.status_code == 401
        assert set(unauthenticated.json()) == {"code", "message", "request_id"}
        assert unauthenticated.json()["code"] == "identity_invalid"
        assert isinstance(UUID(unauthenticated.json()["request_id"]), UUID)

        identity.verifier = BrokenVerifier()
        unavailable = client.get(
            f"/api/v1/research/runs/{RUN_ID}", headers=_headers("valid-shaped-token")
        )
        assert unavailable.status_code == 503
        assert set(unavailable.json()) == {"code", "message", "request_id"}
        assert unavailable.json()["code"] == "identity_material_unavailable"
        assert "private verifier detail" not in unavailable.text


def test_disabled_execution_rejects_before_any_ledger_write(monkeypatch) -> None:
    """Test helper test_disabled_execution_rejects_before_any_ledger_write."""
    identity, service = make_memory_identity(), Service(execution_enabled=False)
    request = {
        "request_id": str(uuid4()),
        "entity_ids": [ENTITY],
        "as_of": "2026-10-29T02:00:00Z",
        "seed_evidence_id": str(uuid4()),
        "question": "synthetic",
    }
    with _client(identity, service, monkeypatch) as client:
        response = client.post(
            "/api/v1/research/runs", json=request, headers=_headers(identity.token())
        )
        assert response.status_code == 503
        assert response.json()["code"] == "execution_unavailable"
        assert service.start_calls == 1


def test_strict_body_and_invalid_ids_are_rejected(monkeypatch) -> None:
    """Test helper test_strict_body_and_invalid_ids_are_rejected."""
    identity, service = make_memory_identity(), Service()
    headers = _headers(identity.token())
    request = {
        "request_id": str(uuid4()),
        "entity_ids": [ENTITY],
        "as_of": "2026-10-29T02:00:00Z",
        "seed_evidence_id": str(uuid4()),
        "unexpected": "secret",
    }
    with _client(identity, service, monkeypatch) as client:
        bad_body = client.post("/api/v1/research/runs", json=request, headers=headers)
        assert bad_body.status_code == 422
        assert "secret" not in bad_body.text
        assert (
            client.get("/api/v1/research/runs/not-a-uuid", headers=headers).status_code
            == 422
        )
        assert (
            client.get(
                f"/api/v1/research/evidence/{uuid4()}", headers=headers
            ).status_code
            == 422
        )
        oversized = client.post(
            "/api/v1/research/runs",
            content=b" " * (64 * 1024 + 1),
            headers={**headers, "Content-Type": "application/json"},
        )
        assert oversized.status_code == 413
        assert oversized.json()["code"] == "invalid_request"
        assert service.start_calls == 0


def test_scope_and_entity_denial_are_non_enumerating(monkeypatch) -> None:
    """Test helper test_scope_and_entity_denial_are_non_enumerating."""
    identity, service = make_memory_identity(), Service(execution_enabled=True)
    body = {
        "request_id": str(uuid4()),
        "entity_ids": [ENTITY],
        "as_of": "2026-10-29T02:00:00Z",
        "seed_evidence_id": str(uuid4()),
    }
    with _client(identity, service, monkeypatch) as client:
        denied_scope = client.post(
            "/api/v1/research/runs",
            json=body,
            headers=_headers(identity.token(updates={"scope": "research:read"})),
        )
        denied_entity = client.post(
            "/api/v1/research/runs",
            json={**body, "entity_ids": ["CN.SZ.000001"]},
            headers=_headers(identity.token()),
        )
        assert denied_scope.status_code == denied_entity.status_code == 404
        assert denied_scope.json()["code"] == denied_entity.json()["code"]
        assert "not found or access is denied" in denied_scope.text
        assert "not found or access is denied" in denied_entity.text


def test_sse_is_one_finite_page_and_uses_event_uuid_and_type(monkeypatch) -> None:
    """Test helper test_sse_is_one_finite_page_and_uses_event_uuid_and_type."""
    identity, service = make_memory_identity(), Service()
    event_id = uuid4()
    event = RunEventV1(
        event_id=event_id,
        run_id=RUN_ID,
        seq=1,
        type="started",
        occurred_at=NOW,
        payload=StartedEventPayloadV1(dispatch_id=None),
    )
    service.read_events.return_value = RunEventPage(RUN_ID, (event,), None)
    with _client(identity, service, monkeypatch) as client:
        response = client.get(
            f"/api/v1/research/runs/{RUN_ID}/events", headers=_headers(identity.token())
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert f"id: {event_id}" in response.text
        assert "event: started" in response.text
        assert '"seq":1' in response.text
        assert service.read_events.await_count == 1


def test_cursor_must_be_uuid(monkeypatch) -> None:
    """Test helper test_cursor_must_be_uuid."""
    identity, service = make_memory_identity(), Service()
    with _client(identity, service, monkeypatch) as client:
        response = client.get(
            f"/api/v1/research/runs/{RUN_ID}/events",
            headers={**_headers(identity.token()), "Last-Event-ID": "not-a-uuid"},
        )
        assert response.status_code == 422
        service.read_events.assert_not_awaited()
