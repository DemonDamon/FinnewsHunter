"""Protected, composition-neutral HTTP surface for research-v1.1.

S03-D owns mounting this router and overriding its explicit dependencies.
Author: Damon Li
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import ValidationError

from app.research.contracts import (
    EvidenceV1,
    GetEvidenceInput,
    GetRunInput,
    ResearchRunViewV1,
    StartResearchInput,
)
from app.research.errors import DomainError
from app.research.identity_context import verify_http_principal
from app.research.ports import IdentityVerifierPort, Principal
from app.research.service import ResearchApplicationService

router = APIRouter(prefix="/api/v1/research", tags=["research"])
MAX_REQUEST_BODY_SIZE = 64 * 1024
_ERROR_STATUS = {
    "identity_invalid": 401,
    "identity_material_unavailable": 503,
    "resource_not_found_or_denied": 404,
    "request_conflict": 409,
    "event_cursor_invalid": 404,
    "execution_unavailable": 503,
    "persistence_failed": 503,
    "quota_exceeded": 409,
    "evidence_ineligible": 404,
    "license_revoked": 404,
    "invalid_run_state": 409,
    "invalid_request": 422,
}
_ERROR_MESSAGE = {
    "identity_invalid": "identity verification failed",
    "identity_material_unavailable": "identity material is unavailable",
    "resource_not_found_or_denied": "resource was not found or access is denied",
    "request_conflict": "request conflicts with an existing research run",
    "event_cursor_invalid": "event cursor is invalid",
    "execution_unavailable": "research execution is unavailable",
    "persistence_failed": "research persistence is unavailable",
    "quota_exceeded": "research quota is exceeded",
    "evidence_ineligible": "evidence is not eligible for research",
    "license_revoked": "evidence license is revoked",
    "invalid_run_state": "research run state is invalid",
    "invalid_request": "request is invalid",
}


class RequestBodyTooLarge(Exception):
    """Signal a bounded request stream exceeded the transport limit."""


def get_research_service() -> ResearchApplicationService:
    """Composition override point; no implicit global or app-state lookup."""
    raise RuntimeError("research service dependency is not configured")


def get_identity_verifier() -> IdentityVerifierPort:
    """Composition override point for the local, pinned RS256 verifier."""
    raise RuntimeError("research identity verifier dependency is not configured")


def _now() -> datetime:
    """Return the current UTC instant for identity verification."""
    return datetime.now(UTC)


async def get_principal(
    request: Request,
    verifier: IdentityVerifierPort,
) -> Principal | JSONResponse:
    """Verify the raw Authorization field and project failures to fixed JSON."""
    try:
        return await verify_http_principal(
            headers=request.scope.get("headers", []), verifier=verifier, clock=_now
        )
    except DomainError as error:
        return _domain_response(error)
    except Exception:  # noqa: BLE001 -- identity backend failures are secret-safe
        return _error("identity_material_unavailable")


def _error(code: str, status: int | None = None) -> JSONResponse:
    """Map a safe error code to the fixed public JSON envelope."""
    safe_code = code if code in _ERROR_STATUS else "persistence_failed"
    return JSONResponse(
        status_code=status or _ERROR_STATUS[safe_code],
        content={
            "code": safe_code,
            "message": _ERROR_MESSAGE[safe_code],
            "request_id": str(uuid4()),
        },
    )


def _domain_response(error: DomainError) -> JSONResponse:
    """Project a domain error into the HTTP error envelope."""
    return _error(error.code)


async def _strict_body(request: Request, model: type[Any]) -> Any:
    """Read at most the configured bytes, then validate strict C1 JSON."""
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_REQUEST_BODY_SIZE:
            raise RequestBodyTooLarge
        body.extend(chunk)
    try:
        return model.model_validate_json(bytes(body))
    except (ValidationError, ValueError):
        raise ValueError("invalid request") from None


def _uuid(value: str) -> UUID:
    """Parse a canonical lowercase UUID path segment."""
    try:
        parsed = UUID(value)
        if str(parsed) != value.lower():
            raise ValueError
        return parsed
    except (ValueError, AttributeError):
        raise ValueError("invalid identifier") from None


@router.post("/runs", response_model=ResearchRunViewV1)
async def start_run(
    request: Request,
    verifier: IdentityVerifierPort = Depends(get_identity_verifier),  # noqa: B008
    service: ResearchApplicationService = Depends(get_research_service),  # noqa: B008
) -> Any:
    """Create or reuse a research run using the strict C1 request DTO."""
    try:
        principal = await get_principal(request, verifier)
        if isinstance(principal, JSONResponse):
            return principal
        payload = await _strict_body(request, StartResearchInput)
        result = await service.start_research(principal=principal, request=payload)
        return ResearchRunViewV1.model_validate(result)
    except DomainError as error:
        return _domain_response(error)
    except RequestBodyTooLarge:
        return _error("invalid_request", 413)
    except ValueError:
        return _error("invalid_request", 422)
    except Exception:  # noqa: BLE001 -- stable, non-reflective public failure
        return _error("persistence_failed", 500)


@router.get("/runs/{id}", response_model=ResearchRunViewV1)
async def get_run(
    id: str,
    request: Request,
    verifier: IdentityVerifierPort = Depends(get_identity_verifier),  # noqa: B008
    service: ResearchApplicationService = Depends(get_research_service),  # noqa: B008
) -> Any:
    """Return the ledger's authorized and redacted run projection."""
    try:
        principal = await get_principal(request, verifier)
        if isinstance(principal, JSONResponse):
            return principal
        result = await service.get_run(
            principal=principal, request=GetRunInput(run_id=_uuid(id))
        )
        return ResearchRunViewV1.model_validate(result)
    except DomainError as error:
        return _domain_response(error)
    except ValueError:
        return _error("request_conflict", 422)
    except Exception:  # noqa: BLE001
        return _error("persistence_failed", 500)


@router.get("/runs/{id}/events")
async def get_run_events(
    id: str,
    request: Request,
    verifier: IdentityVerifierPort = Depends(get_identity_verifier),  # noqa: B008
    service: ResearchApplicationService = Depends(get_research_service),  # noqa: B008
) -> Response:
    """Replay one finite server-bounded page of committed events."""
    try:
        principal = await get_principal(request, verifier)
        if isinstance(principal, JSONResponse):
            return principal
        run_id = _uuid(id)
        raw_cursors = [
            v
            for k, v in request.scope.get("headers", [])
            if k.lower() == b"last-event-id"
        ]
        if len(raw_cursors) > 1:
            raise ValueError
        cursor = None
        if raw_cursors:
            cursor = _uuid(raw_cursors[0].decode("ascii"))
        page = await service.read_events(
            principal=principal, run_id=run_id, after_event_id=cursor
        )
        if page.run_id != run_id:
            raise DomainError(
                code="resource_not_found_or_denied",
                safe_message="resource was not found or access is denied",
                retryable=False,
            )
        blocks = []
        for event in page.events:
            payload = event.model_dump(mode="json")
            blocks.append(
                f"id: {event.event_id}\nevent: {event.type}\ndata: "
                f"{json.dumps(payload, separators=(',', ':'), ensure_ascii=False)}\n\n"
            )
        return StreamingResponse(
            iter(blocks),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    except DomainError as error:
        return _domain_response(error)
    except ValueError:
        return _error("event_cursor_invalid", 422)
    except Exception:  # noqa: BLE001
        return _error("persistence_failed", 500)


@router.get("/evidence/{id}", response_model=EvidenceV1)
async def get_evidence(
    id: str,
    request: Request,
    verifier: IdentityVerifierPort = Depends(get_identity_verifier),  # noqa: B008
    service: ResearchApplicationService = Depends(get_research_service),  # noqa: B008
) -> Any:
    """Read evidence only through its authorized frozen-run membership."""
    try:
        principal = await get_principal(request, verifier)
        if isinstance(principal, JSONResponse):
            return principal
        values = request.query_params.getlist("run_id")
        if len(values) != 1:
            raise ValueError
        result = await service.get_evidence(
            principal=principal,
            request=GetEvidenceInput(evidence_id=_uuid(id), run_id=_uuid(values[0])),
        )
        return EvidenceV1.model_validate(result)
    except DomainError as error:
        return _domain_response(error)
    except (ValueError, ValidationError):
        return _error("resource_not_found_or_denied", 422)
    except Exception:  # noqa: BLE001
        return _error("persistence_failed", 500)
