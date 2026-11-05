"""Same-ASGI-app HTTP/MCP wiring with in-memory identity and fake ledger service.

Author: Damon Li
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from jwt.algorithms import RSAAlgorithm
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.api.v1.research import get_identity_verifier, get_research_service, router
from app.mcp.finnews_server import ALLOWED_TOOL_NAMES, create_finnews_mcp_app
from app.research.auth import LocalRS256IdentityVerifier
from app.research.contracts import ResearchEnvelope, ResearchRunViewV1

NOW = datetime.now(UTC)
SUBJECT = UUID("11111111-1111-1111-1111-111111111111")
ENTITY = "CN.SH.600519"


class FakeService:
    def __init__(self) -> None:
        self.calls = []
        self.run_id = uuid4()

    def result(self):
        return ResearchRunViewV1(
            run_id=self.run_id,
            request_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            principal_id=SUBJECT,
            entity_ids=[ENTITY],
            as_of=NOW,
            status="queued",
            created_at=NOW,
            updated_at=NOW,
            model_id=None,
            prompt_version="p1",
            policy_version="s1",
            result_ref=None,
            error_code=None,
            brief=None,
        )

    async def start_research(self, *, principal, request, envelope=False):
        self.calls.append((principal.principal_id, request.model_dump(mode="json")))
        result = self.result()
        if not envelope:
            return result
        return ResearchEnvelope[ResearchRunViewV1](
            schema_version="research-v1.1",
            request_id=request.request_id,
            as_of=NOW,
            status="ok",
            data=result,
            source=[],
            license_status="unknown",
            warnings=[],
            error=None,
        )


def test_http_and_mcp_share_one_service_and_verified_principal():
    async def scenario():
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
        jwk.update({"kid": "memory", "alg": "RS256", "use": "sig"})
        verifier = LocalRS256IdentityVerifier(
            issuer="https://identity.test",
            audience="research-test",
            trusted_jwks={"keys": [jwk]},
        )
        token = jwt.encode(
            {
                "iss": "https://identity.test",
                "aud": "research-test",
                "sub": str(SUBJECT),
                "scope": "research:create research:read",
                "entity_ids": [ENTITY],
                "nbf": int((NOW - timedelta(seconds=1)).timestamp()),
                "exp": int((NOW + timedelta(minutes=10)).timestamp()),
            },
            key,
            algorithm="RS256",
            headers={"kid": "memory"},
        )
        service = FakeService()
        mcp = create_finnews_mcp_app(
            service=service,
            token_verifier=verifier,
            clock=lambda: NOW,
            allowed_hosts=["research.test"],
            allowed_origins=["https://research.test"],
        )

        @asynccontextmanager
        async def lifespan(app):
            async with mcp.lifespan():
                yield

        app = FastAPI(lifespan=lifespan)
        app.dependency_overrides[get_research_service] = lambda: service
        app.dependency_overrides[get_identity_verifier] = lambda: verifier
        app.include_router(router)
        app.mount("/api/v1/mcp", mcp.app)
        request_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        payload = {
            "request_id": str(request_id),
            "entity_ids": [ENTITY],
            "as_of": NOW.isoformat(),
            "seed_evidence_id": str(uuid4()),
            "question": "test question",
        }
        headers = {"Authorization": f"Bearer {token}"}
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="https://research.test"
            ) as client:
                http_result = await client.post(
                    "/api/v1/research/runs", json=payload, headers=headers
                )
                assert http_result.status_code == 200, http_result.text
                assert http_result.json()["run_id"] == str(service.run_id)
            async with (
                httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=mcp.app),
                    base_url="https://research.test",
                    headers={
                        **headers,
                        "Origin": "https://research.test",
                        "Accept": "application/json, text/event-stream",
                    },
                ) as client,
                streamable_http_client(
                    "https://research.test/", http_client=client
                ) as (read, write, _),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                tools = await session.list_tools()
                assert {tool.name for tool in tools.tools} == set(ALLOWED_TOOL_NAMES)
                called = await session.call_tool(
                    "finnews.start_research", arguments=payload
                )
                assert called.structuredContent["status"] == "ok"
                assert called.structuredContent["data"]["run_id"] == str(service.run_id)
            assert len(service.calls) == 2
            assert all(principal_id == SUBJECT for principal_id, _ in service.calls)
            assert service.calls[0][1] == service.calls[1][1]

    asyncio.run(asyncio.wait_for(scenario(), timeout=15))
