"""Exercise the official MCP 1.30.0 Streamable HTTP protocol in-process."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from importlib.metadata import version
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from app.mcp.finnews_server import ALLOWED_TOOL_NAMES, create_finnews_mcp_app
from app.research.contracts import (
    SCHEMA_VERSION,
    ArticlesSearchResult,
    ResearchEnvelope,
)
from app.research.errors import DomainError
from app.research.ports import BearerCredential, Principal
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

NOW = datetime(2035, 1, 1, tzinfo=UTC)
ISSUER = "https://identity.example.test"
AUDIENCE = "research-test"
ENTITY = "CN.SH.600519"
A = UUID("11111111-1111-1111-1111-111111111111")
B = UUID("22222222-2222-2222-2222-222222222222")


class MemoryVerifier:
    """Map opaque test tokens to verified principals without network access."""

    async def verify_bearer(
        self, *, credential: BearerCredential, now: datetime
    ) -> Principal:
        token = credential.for_verification()
        if token == "invalid":
            raise DomainError(
                code="identity_invalid",
                safe_message="identity verification failed",
                retryable=False,
            )
        subject = A if token.startswith("token-a") else B
        scopes = frozenset({"research:read"})
        return Principal(
            principal_id=subject,
            scopes=scopes,
            entity_ids=frozenset({ENTITY}),
            issuer=ISSUER,
            audience=AUDIENCE,
            expires_at=now + timedelta(minutes=10),
        )


class RecordingService:
    """Provide bounded service envelopes and record the current bound Principal."""

    def __init__(self) -> None:
        self.principals: list[UUID] = []

    async def search_articles(self, *, principal, request, envelope):
        assert envelope is True
        self.principals.append(principal.principal_id)
        now = NOW
        return ResearchEnvelope[ArticlesSearchResult](
            schema_version=SCHEMA_VERSION,
            request_id=uuid4(),
            status="ok",
            as_of=now,
            data=ArticlesSearchResult(articles=[], next_cursor=None, truncated=False),
            source=[],
            license_status="approved",
            warnings=[],
            error=None,
        )

    async def get_run(self, *, principal, request, envelope):
        assert envelope is True
        self.principals.append(principal.principal_id)
        return ResearchEnvelope[Any](
            schema_version=SCHEMA_VERSION,
            request_id=uuid4(),
            status="error",
            as_of=NOW,
            data=None,
            source=[],
            license_status="unknown",
            warnings=[],
            error={
                "code": "resource_not_found_or_denied",
                "message": "resource was not found or access is denied",
                "retryable": False,
            },
        )


class BlockingService:
    """Hold one tool call until the client cancels its in-flight request."""

    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.principals: list[UUID] = []

    async def search_articles(self, *, principal, request, envelope):
        assert envelope is True
        self.principals.append(principal.principal_id)
        self.entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            self.cancelled.set()


def _request(method: str, request_id: int, params: dict | None = None) -> dict:
    message = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        message["params"] = params
    return message


async def _post(client: httpx.AsyncClient, headers: dict[str, str], body: dict):
    return await client.post("/", headers=headers, json=body)


def test_lock_version_schema_strictness_and_explicit_security_policy() -> None:
    assert version("mcp") == "1.30.0"
    service = RecordingService()
    with pytest.raises(ValueError, match="explicit and non-empty"):
        create_finnews_mcp_app(
            service=service,
            token_verifier=MemoryVerifier(),
            clock=lambda: NOW,
            allowed_hosts=[],
            allowed_origins=["https://research.example.test"],
        )
    app = create_finnews_mcp_app(
        service=service,
        token_verifier=MemoryVerifier(),
        clock=lambda: NOW,
        allowed_hosts=["research.example.test"],
        allowed_origins=["https://research.example.test"],
    )
    tools = app.manager.app._tool_cache
    assert tuple(ALLOWED_TOOL_NAMES) == (
        "finnews.search_articles",
        "finnews.get_evidence",
        "finnews.get_market_snapshot",
        "finnews.start_research",
        "finnews.get_run",
    )
    assert app.readiness == {
        "mcp": False,
        "authentication": True,
        "transport_security": True,
    }
    assert tools == {}

    async def lifecycle() -> None:
        async with app.lifespan():
            assert app.readiness["mcp"] is True
        assert app.readiness["mcp"] is False
        assert app.manager._task_group is None
        assert app.manager._server_instances == {}
        assert app.manager._session_owners == {}
        with pytest.raises(RuntimeError, match="only be called once"):
            async with app.lifespan():
                pass
        assert app.readiness["mcp"] is False

    asyncio.run(lifecycle())


def test_streamable_http_transcript_session_identity_and_results() -> None:
    async def scenario() -> None:
        service = RecordingService()
        created = create_finnews_mcp_app(
            service=service,
            token_verifier=MemoryVerifier(),
            clock=lambda: NOW,
            allowed_hosts=["research.example.test"],
            allowed_origins=["https://research.example.test"],
        )
        base_headers = {
            "Accept": "application/json, text/event-stream",
            "Origin": "https://research.example.test",
            "Authorization": "Bearer token-a-initial",
        }
        async with (
            created.lifespan(),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=created.app),
                base_url="https://research.example.test",
            ) as client,
        ):
            initialized = await _post(
                client,
                base_headers,
                _request(
                    "initialize",
                    1,
                    {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {"name": "test-client", "version": "1"},
                    },
                ),
            )
            assert initialized.status_code == 200, initialized.text
            session_id = initialized.headers["mcp-session-id"]
            headers = {
                **base_headers,
                "Mcp-Session-Id": session_id,
                "Mcp-Protocol-Version": "2025-11-25",
            }
            notified = await _post(
                client,
                headers,
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
            )
            assert notified.status_code == 202

            listed = await _post(client, headers, _request("tools/list", 2))
            assert listed.status_code == 200, listed.text
            tools = listed.json()["result"]["tools"]
            assert {tool["name"] for tool in tools} == set(ALLOWED_TOOL_NAMES)
            assert len(tools) == 5
            for tool in tools:
                assert tool["inputSchema"]["additionalProperties"] is False

            args = {
                "query": "market",
                "entity_ids": [ENTITY],
                "as_of": "2025-12-31T00:00:00Z",
                "limit": 5,
            }
            call = await _post(
                client,
                headers,
                _request(
                    "tools/call",
                    3,
                    {"name": "finnews.search_articles", "arguments": args},
                ),
            )
            assert call.status_code == 200, call.text
            result = call.json()["result"]
            parsed_text = json.loads(result["content"][0]["text"])
            assert parsed_text == result["structuredContent"]
            assert parsed_text["status"] == "ok", parsed_text
            assert result["isError"] is False
            assert service.principals == [A]

            error_call = await _post(
                client,
                headers,
                _request(
                    "tools/call",
                    4,
                    {"name": "finnews.get_run", "arguments": {"run_id": str(uuid4())}},
                ),
            )
            error_result = error_call.json()["result"]
            assert (
                json.loads(error_result["content"][0]["text"])
                == error_result["structuredContent"]
            )
            assert error_result["structuredContent"]["status"] == "error"
            assert error_result["isError"] is True
            assert "token-a" not in error_result["content"][0]["text"]

            # SDK revalidates every HTTP message; B cannot take over A's session.
            stolen = await _post(
                client,
                {**headers, "Authorization": "Bearer token-b"},
                _request(
                    "tools/call",
                    5,
                    {"name": "finnews.search_articles", "arguments": args},
                ),
            )
            assert stolen.status_code == 404
            assert service.principals == [A, A]

            # Same verified owner reconnects to the same stateful session.
            reconnect = await _post(
                client,
                headers,
                _request(
                    "tools/call",
                    6,
                    {"name": "finnews.search_articles", "arguments": args},
                ),
            )
            assert reconnect.status_code == 200
            assert reconnect.json()["result"]["structuredContent"]["status"] == "ok"
            assert service.principals == [A, A, A]

            bad_host = await client.post(
                "/",
                headers={**headers, "Host": "attacker.invalid"},
                json=_request("tools/list", 7),
            )
            assert bad_host.status_code == 421
            bad_origin = await client.post(
                "/",
                headers={**headers, "Origin": "https://attacker.invalid"},
                json=_request("tools/list", 8),
            )
            assert bad_origin.status_code == 403
            bad_content = await client.post(
                "/",
                headers={**headers, "Content-Type": "text/plain"},
                content="not-json",
            )
            assert bad_content.status_code == 400
            oversized = await client.post(
                "/",
                headers={**headers, "Content-Type": "application/json"},
                content=b" " * (64 * 1024 + 1),
            )
            assert oversized.status_code == 413

            invalid = await _post(
                client,
                {**headers, "Authorization": "Bearer invalid"},
                _request("tools/list", 9),
            )
            assert invalid.status_code == 401

            async with (
                httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=created.app),
                    base_url="https://research.example.test",
                    headers={
                        "Authorization": "Bearer token-a-client",
                        "Origin": "https://research.example.test",
                        "Accept": "application/json, text/event-stream",
                    },
                ) as sdk_http_client,
                streamable_http_client(
                    "https://research.example.test/", http_client=sdk_http_client
                ) as (read_stream, write_stream, _get_session_id),
                ClientSession(read_stream, write_stream) as session,
            ):
                initialized = await session.initialize()
                assert initialized.serverInfo.name == "finnews-research"
                listed = await session.list_tools()
                assert {tool.name for tool in listed.tools} == set(ALLOWED_TOOL_NAMES)
                called = await session.call_tool(
                    "finnews.search_articles", arguments=args
                )
                assert called.structuredContent["status"] == "ok"
                assert json.loads(called.content[0].text) == called.structuredContent

    asyncio.run(asyncio.wait_for(scenario(), timeout=15))


def test_cancelled_client_request_cancels_handler_and_closes_manager() -> None:
    async def scenario() -> None:
        service = BlockingService()
        created = create_finnews_mcp_app(
            service=service,
            token_verifier=MemoryVerifier(),
            clock=lambda: NOW,
            allowed_hosts=["research.example.test"],
            allowed_origins=["https://research.example.test"],
        )
        base_headers = {
            "Accept": "application/json, text/event-stream",
            "Origin": "https://research.example.test",
            "Authorization": "Bearer token-a",
        }
        async with (
            created.lifespan(),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=created.app),
                base_url="https://research.example.test",
            ) as client,
        ):
            initialized = await _post(
                client,
                base_headers,
                _request(
                    "initialize",
                    1,
                    {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {"name": "cancel-client", "version": "1"},
                    },
                ),
            )
            assert initialized.status_code == 200
            headers = {
                **base_headers,
                "Mcp-Session-Id": initialized.headers["mcp-session-id"],
                "Mcp-Protocol-Version": "2025-11-25",
            }
            notified = await _post(
                client,
                headers,
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
            )
            assert notified.status_code == 202
            request_task = asyncio.create_task(
                _post(
                    client,
                    headers,
                    _request(
                        "tools/call",
                        2,
                        {
                            "name": "finnews.search_articles",
                            "arguments": {
                                "query": "synthetic",
                                "entity_ids": [ENTITY],
                                "as_of": "2025-12-31T00:00:00Z",
                                "limit": 5,
                            },
                        },
                    ),
                )
            )
            await asyncio.wait_for(service.entered.wait(), timeout=3)
            request_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await request_task
        await asyncio.wait_for(service.cancelled.wait(), timeout=3)
        assert created.readiness["mcp"] is False
        assert created.manager._task_group is None
        assert created.manager._server_instances == {}
        assert created.manager._session_owners == {}
        assert service.principals == [A]

    asyncio.run(asyncio.wait_for(scenario(), timeout=10))
