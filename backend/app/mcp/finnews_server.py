"""Protected five-tool Streamable HTTP MCP surface for the research service.

The parent composition owns the returned manager lifespan and mounts ``app``
exactly once. This module never starts a server or stores a principal in shared
state.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from mcp.server import Server
from mcp.server.fastmcp.server import StreamableHTTPASGIApp
from mcp.server.streamable_http import TransportSecuritySettings
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import CallToolResult, TextContent, Tool
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.types import ASGIApp

from app.research.contracts import (
    TOOL_REGISTRY,
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
from app.research.errors import DomainError
from app.research.identity_context import (
    PrincipalContextMiddleware,
    ResearchBearerAuthBackend,
    ResearchTokenVerifier,
    bind_mcp_principal_context,
)
from app.research.ports import IdentityVerifierPort
from app.research.service import ResearchApplicationService

Clock = Callable[[], datetime]
MAX_REQUEST_BODY_SIZE = 64 * 1024
ALLOWED_TOOL_NAMES = tuple(definition.name for definition in TOOL_REGISTRY)


@dataclass(frozen=True, slots=True)
class FinnewsMCPApp:
    """ASGI transport and exactly-once manager lifespan for parent composition."""

    app: ASGIApp
    manager: StreamableHTTPSessionManager
    lifespan: Callable[[], Any]
    readiness: dict[str, bool]


_INPUT_MODELS = {
    "finnews.search_articles": SearchArticlesInput,
    "finnews.get_evidence": GetEvidenceInput,
    "finnews.get_market_snapshot": GetMarketSnapshotInput,
    "finnews.start_research": StartResearchInput,
    "finnews.get_run": GetRunInput,
}
_OUTPUT_MODELS = {
    "finnews.search_articles": ResearchEnvelope[ArticlesSearchResult],
    "finnews.get_evidence": ResearchEnvelope[EvidenceV1],
    "finnews.get_market_snapshot": ResearchEnvelope[MarketPayloadV1],
    "finnews.start_research": ResearchEnvelope[ResearchRunViewV1],
    "finnews.get_run": ResearchEnvelope[ResearchRunViewV1],
}


def _schema(model: type[Any]) -> dict[str, Any]:
    """Return the DTO's exact JSON Schema and fail closed on permissive roots."""
    schema = model.model_json_schema()
    if (
        schema.get("type") != "object"
        or schema.get("additionalProperties") is not False
    ):
        raise ValueError(
            "MCP input DTO must be an object with additionalProperties=false"
        )
    return schema


def _tool_definitions() -> list[Tool]:
    """Build the immutable exact five-tool surface from frozen input DTOs."""
    tools: list[Tool] = []
    for definition in TOOL_REGISTRY:
        if definition.name not in _INPUT_MODELS:
            raise RuntimeError("unexpected research tool registry entry")
        tools.append(
            Tool(
                name=definition.name,
                description=f"Research operation: {definition.name}",
                inputSchema=_schema(_INPUT_MODELS[definition.name]),
                outputSchema=_OUTPUT_MODELS[definition.name].model_json_schema(),
            )
        )
    if tuple(tool.name for tool in tools) != ALLOWED_TOOL_NAMES:
        raise RuntimeError("research MCP tool registry mismatch")
    return tools


def _safe_failure(
    code: str, message: str, *, retryable: bool = False
) -> dict[str, Any]:
    """Construct only fixed safe error envelopes for transport-level failures."""
    from datetime import UTC
    from uuid import uuid4

    envelope = ResearchEnvelope[Any](
        schema_version="research-v1.1",
        request_id=uuid4(),
        as_of=datetime.now(UTC),
        status="error",
        data=None,
        source=[],
        license_status="unknown",
        warnings=[],
        error={"code": code, "message": message, "retryable": retryable},
    )
    return envelope.model_dump(mode="json")


def _tool_result(payload: dict[str, Any]) -> CallToolResult:
    """Keep structured result and the sole JSON text block byte-for-byte equivalent."""
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        structuredContent=payload,
        isError=payload.get("status") == "error",
    )


def create_finnews_mcp_app(
    *,
    service: ResearchApplicationService,
    token_verifier: IdentityVerifierPort,
    clock: Clock,
    allowed_hosts: list[str],
    allowed_origins: list[str],
) -> FinnewsMCPApp:
    """Create one MCP server/manager and expose its manager.run lifespan.

    Parent composition must enter ``lifespan()`` exactly once and mount ``app``
    at the canonical ``/api/v1/mcp`` path. Both host and origin policy are
    mandatory; credentials and principal data are never stored here.
    """
    if not allowed_hosts or not allowed_origins:
        raise ValueError(
            "allowed_hosts and allowed_origins must be explicit and non-empty"
        )

    server = Server("finnews-research")
    tools = _tool_definitions()

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        scope = server.request_context.request.scope
        with bind_mcp_principal_context(scope, clock=clock):
            return tools

    @server.call_tool(validate_input=False)
    async def call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
        if name not in _INPUT_MODELS:
            return _tool_result(_safe_failure("tool_not_found", "tool is unavailable"))
        scope = server.request_context.request.scope
        try:
            with bind_mcp_principal_context(scope, clock=clock) as principal:
                model = _INPUT_MODELS[name]
                request = model.model_validate(arguments)
                if name == "finnews.search_articles":
                    result = await service.search_articles(
                        principal=principal, request=request, envelope=True
                    )
                elif name == "finnews.get_evidence":
                    result = await service.get_evidence(
                        principal=principal, request=request, envelope=True
                    )
                elif name == "finnews.get_market_snapshot":
                    result = await service.get_market_snapshot(
                        principal=principal, request=request, envelope=True
                    )
                elif name == "finnews.start_research":
                    result = await service.start_research(
                        principal=principal, request=request, envelope=True
                    )
                else:
                    result = await service.get_run(
                        principal=principal, request=request, envelope=True
                    )
            payload = result.model_dump(mode="json")
            return _tool_result(payload)
        except DomainError as error:
            # Service DomainErrors should already be envelopes. Identity failures
            # are mapped to a stable nonrevealing failure at the transport edge.
            return _tool_result(
                _safe_failure(error.code, error.safe_message, retryable=error.retryable)
            )
        except (ValueError, TypeError):
            return _tool_result(_safe_failure("invalid_request", "request is invalid"))
        except Exception:  # noqa: BLE001 -- no exception text crosses transport
            return _tool_result(
                _safe_failure(
                    "internal_error", "research operation failed", retryable=True
                )
            )

    manager = StreamableHTTPSessionManager(
        app=server,
        stateless=False,
        json_response=True,
        security_settings=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=list(allowed_hosts),
            allowed_origins=list(allowed_origins),
        ),
        max_request_body_size=MAX_REQUEST_BODY_SIZE,
    )
    transport = StreamableHTTPASGIApp(manager)
    authenticated = AuthenticationMiddleware(
        PrincipalContextMiddleware(transport, clock=clock),
        backend=ResearchBearerAuthBackend(
            ResearchTokenVerifier(verifier=token_verifier, clock=clock)
        ),
    )

    @asynccontextmanager
    async def lifespan() -> AsyncIterator[None]:
        async with manager.run():
            readiness["mcp"] = True
            try:
                yield
            finally:
                readiness["mcp"] = False

    readiness = {
        "mcp": False,
        "authentication": True,
        "transport_security": True,
    }

    return FinnewsMCPApp(
        app=authenticated,
        manager=manager,
        lifespan=lifespan,
        readiness=readiness,
    )
