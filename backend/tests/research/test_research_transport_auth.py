"""Exercise transport identity with in-memory RSA and the actual MCP SDK.

Author: Damon Li
"""

from __future__ import annotations

import asyncio
import json
import logging
import socket
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from importlib.metadata import version
from unittest.mock import AsyncMock
from uuid import UUID

import jwt
import pytest
from app.research.auth import LocalRS256IdentityVerifier
from app.research.errors import DomainError
from app.research.identity_context import (
    MAX_AUTHORIZATION_LENGTH,
    VERIFIED_TOKEN_MARKER,
    PrincipalContextMiddleware,
    ResearchBearerAuthBackend,
    ResearchTokenVerifier,
    get_current_principal,
    parse_bearer_headers,
    verify_http_principal,
)
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from starlette.authentication import AuthCredentials
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.types import ASGIApp, Message, Scope

NOW = datetime(2035, 1, 1, tzinfo=UTC)
ISSUER = "https://identity.example.test"
AUDIENCE = "research-test"
ENTITY = "CN.SH.600519"
A = UUID("11111111-1111-1111-1111-111111111111")
B = UUID("22222222-2222-2222-2222-222222222222")
IGNORED_SECRET = "untrusted-extra-claim-must-not-survive"


@pytest.fixture(autouse=True)
def no_network(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Make any accidental issuer/provider/network use fail the behavioral test."""
    caplog.set_level(logging.DEBUG)

    def forbidden(*args, **kwargs):
        """Test helper forbidden."""
        raise AssertionError("network is forbidden in S03-A tests")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)


@dataclass(repr=False)
class MemoryIdentity:
    """Keep the test-only signing key in memory, never in a temporary file."""

    key: rsa.RSAPrivateKey = field(repr=False)
    verifier: LocalRS256IdentityVerifier

    def token(
        self,
        subject: UUID = A,
        *,
        updates: dict | None = None,
        headers: dict | None = None,
    ) -> str:
        """Sign only local fixture claims with configurable negative cases."""
        claims = {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": str(subject),
            "scope": "research:create research:read",
            "entity_ids": [ENTITY],
            "nbf": int((NOW - timedelta(seconds=1)).timestamp()),
            "exp": int((NOW + timedelta(minutes=10)).timestamp()),
            "untrusted_extra": IGNORED_SECRET,
        }
        claims.update(updates or {})
        return jwt.encode(
            claims,
            self.key,
            algorithm="RS256",
            headers={"kid": "memory", **(headers or {})},
        )


def make_memory_identity() -> MemoryIdentity:
    """Generate only an in-memory keypair and inject its public JWKS."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
    public.update({"kid": "memory", "alg": "RS256", "use": "sig"})
    return MemoryIdentity(
        key=key,
        verifier=LocalRS256IdentityVerifier(
            issuer=ISSUER, audience=AUDIENCE, trusted_jwks={"keys": [public]}
        ),
    )


@pytest.fixture(scope="module")
def identity() -> MemoryIdentity:
    """Keep cryptographic fixture generation entirely in memory."""
    return make_memory_identity()


def _headers(token: str) -> list[tuple[bytes, bytes]]:
    """Represent the actual raw ASGI Authorization field."""
    return [(b"authorization", f"Bearer {token}".encode("ascii"))]


def _adapter(identity: MemoryIdentity) -> ResearchTokenVerifier:
    """Use the fixed identity time rather than the machine clock."""
    return ResearchTokenVerifier(verifier=identity.verifier, clock=lambda: NOW)


def _scope(token: str) -> Scope:
    """Build only an HTTP scope; authentication is performed by SDK middleware."""
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "method": "POST",
        "scheme": "https",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": _headers(token),
        "server": ("research.example.test", 443),
        "client": ("127.0.0.1", 1234),
        "http_version": "1.1",
    }


async def _receive() -> Message:
    """Test helper for _receive."""
    return {"type": "http.request", "body": b"", "more_body": False}


async def _send(message: Message) -> None:
    """Test helper for _send."""
    assert message["type"] in {"http.response.start", "http.response.body"}


def _protected(app: ASGIApp, identity: MemoryIdentity) -> ASGIApp:
    """Use the installed AuthenticationMiddleware and SDK backend implementation."""
    return AuthenticationMiddleware(
        PrincipalContextMiddleware(app, clock=lambda: NOW),
        backend=ResearchBearerAuthBackend(_adapter(identity)),
    )


def _assert_no_context() -> None:
    """Test helper for _assert_no_context."""
    with pytest.raises(DomainError, match="^identity_invalid$"):
        get_current_principal()


@pytest.mark.parametrize(
    "header", [b"Bearer abc.A_-~+/==", b"bearer opaque", b"bEaReR x"]
)
def test_parser_accepts_only_one_bounded_ascii_bearer(header: bytes) -> None:
    """Test helper test_parser_accepts_only_one_bounded_ascii_bearer."""
    credential = parse_bearer_headers([(b"Authorization", header)])
    assert credential.for_verification() == header.split(b" ")[1].decode("ascii")
    assert credential.for_verification() not in repr(credential)
    assert credential.for_verification() not in str(credential)


@pytest.mark.parametrize(
    "headers",
    [
        [],
        [(b"cookie", b"authorization=Bearer cookie-secret")],
        [(b"authorization", b"")],
        [(b"authorization", b"Bearer")],
        [(b"authorization", b"Bearer ")],
        [(b"authorization", b"Basic x")],
        [(b"authorization", b"Bearer  x")],
        [(b"authorization", b" Bearer x")],
        [(b"authorization", b"Bearer x ")],
        [(b"authorization", b"Bearer\tx")],
        [(b"authorization", b"Bearer x,y")],
        [(b"authorization", b"Bearer x, Bearer y")],
        [(b"authorization", b"Bearer x\r\n")],
        [(b"authorization", b"Bearer \xff")],
        [(b"authorization", b"Bearer x=y")],
        [(b"authorization", b"Bearer a"), (b"Authorization", b"Bearer a")],
        [(b"authorization", b"Bearer a"), (b"authorization", b"Bearer b")],
        [(b"authorization", b"Bearer " + b"x" * (MAX_AUTHORIZATION_LENGTH - 6))],
    ],
)
def test_parser_rejects_missing_ambiguous_or_malformed_headers(headers) -> None:
    """Test helper test_parser_rejects_missing_ambiguous_or_malformed_headers."""
    with pytest.raises(DomainError) as raised:
        parse_bearer_headers(headers)
    assert raised.value.code == "identity_invalid"
    assert raised.value.safe_message == "identity verification failed"
    assert repr(raised.value) == "DomainError('identity_invalid')"


def test_parser_exact_authorization_size_boundary() -> None:
    """Test helper test_parser_exact_authorization_size_boundary."""
    accepted = b"Bearer " + b"x" * (MAX_AUTHORIZATION_LENGTH - 7)
    assert len(accepted) == MAX_AUTHORIZATION_LENGTH
    assert parse_bearer_headers([(b"authorization", accepted)]).for_verification() == (
        "x" * (MAX_AUTHORIZATION_LENGTH - 7)
    )
    with pytest.raises(DomainError):
        parse_bearer_headers([(b"authorization", accepted + b"x")])


def test_http_and_sdk_bridge_share_verifier_and_safe_identity(
    identity: MemoryIdentity,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test helper test_http_and_sdk_bridge_share_verifier_and_safe_identity."""
    async def scenario():
        """Test helper scenario."""
        token = identity.token()
        spy = AsyncMock(wraps=identity.verifier.verify_bearer)
        verifier = AsyncMock()
        verifier.verify_bearer = spy
        http = await verify_http_principal(
            headers=_headers(token), verifier=verifier, clock=lambda: NOW
        )
        adapter = ResearchTokenVerifier(verifier=verifier, clock=lambda: NOW)
        access = await adapter.verify_token(token)
        assert version("mcp") == "1.30.0"
        assert isinstance(access, AccessToken)
        assert access.token == VERIFIED_TOKEN_MARKER
        assert access.subject == access.client_id == str(http.principal_id)
        assert access.scopes == sorted(http.scopes)
        assert access.expires_at == int(http.expires_at.timestamp())
        assert access.resource == AUDIENCE
        assert access.claims == {"iss": ISSUER, "aud": AUDIENCE, "entity_ids": [ENTITY]}
        assert len(spy.await_args_list) == 2
        for call in spy.await_args_list:
            assert call.kwargs["now"] == NOW
            assert call.kwargs["credential"].for_verification() == token
        # Successful identity is never inferred from a prior request/session.
        assert await adapter.verify_token(identity.token(B)) != access
        assert token not in repr(access) + repr(http) + repr(adapter) + caplog.text
        assert IGNORED_SECRET not in access.model_dump_json() + repr(http)
        return http

    principal = asyncio.run(scenario())
    with pytest.raises(AttributeError):
        principal.issuer = "mutated"  # type: ignore[misc]


@pytest.mark.parametrize(
    "case",
    [
        "issuer",
        "audience",
        "expired",
        "nbf",
        "subject",
        "scope",
        "entities",
        "jku",
        "x5u",
        "kid",
        "signature",
        "none",
        "hs256",
        "malformed",
    ],
)
def test_sdk_adapter_rejects_invalid_local_rs256_without_leaks(
    identity: MemoryIdentity,
    case: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test helper test_sdk_adapter_rejects_invalid_local_rs256_without_leaks."""
    updates = {
        "issuer": {"iss": "https://wrong.example.test"},
        "audience": {"aud": "wrong"},
        "expired": {"exp": int(NOW.timestamp())},
        "nbf": {"nbf": int((NOW + timedelta(seconds=1)).timestamp())},
        "subject": {"sub": "not-uuid"},
        "scope": {"scope": "admin"},
        "entities": {"entity_ids": ["SH600519"]},
    }
    headers = {
        "jku": {"jku": "https://no-network.example.test/key"},
        "x5u": {"x5u": "https://no-network.example.test/key"},
        "kid": {"kid": "unknown"},
    }
    token = identity.token(updates=updates.get(case), headers=headers.get(case))
    if case == "signature":
        head, body, sig = token.split(".")
        token = f"{head}.{body}.{'A' if sig[0] != 'A' else 'B'}{sig[1:]}"
    elif case in {"none", "hs256"}:
        # Only the fixture builder reads claims; the production bridge never does.
        claims = jwt.decode(token, options={"verify_signature": False})
        token = jwt.encode(
            claims,
            None if case == "none" else "x" * 64,
            algorithm="none" if case == "none" else "HS256",
            headers={"kid": "memory"},
        )
    elif case == "malformed":
        token = "not.a.jwt"
    assert asyncio.run(_adapter(identity).verify_token(token)) is None
    with pytest.raises(DomainError) as raised:
        asyncio.run(
            verify_http_principal(
                headers=_headers(token), verifier=identity.verifier, clock=lambda: NOW
            )
        )
    assert str(raised.value) == "identity_invalid"
    assert token not in repr(raised.value) + str(raised.value) + caplog.text
    assert IGNORED_SECRET not in repr(raised.value) + caplog.text


@pytest.mark.parametrize("token", ["", "x" * 4090, "a b", "a,b", "\xff", None])
def test_adapter_rejects_bad_token_before_verifier(token) -> None:
    """Test helper test_adapter_rejects_bad_token_before_verifier."""
    verifier = AsyncMock()
    adapter = ResearchTokenVerifier(verifier=verifier, clock=lambda: NOW)
    assert asyncio.run(adapter.verify_token(token)) is None
    verifier.verify_bearer.assert_not_called()


def test_adapter_unavailable_and_unexpected_errors_are_not_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test helper test_adapter_unavailable_and_unexpected_errors_are_not_logged."""
    verifier = AsyncMock()
    adapter = ResearchTokenVerifier(verifier=verifier, clock=lambda: NOW)
    for error in (
        DomainError(
            code="identity_material_unavailable",
            safe_message=IGNORED_SECRET,
            retryable=True,
        ),
        RuntimeError(IGNORED_SECRET),
    ):
        verifier.verify_bearer.side_effect = error
        assert asyncio.run(adapter.verify_token("opaque")) is None
    assert IGNORED_SECRET not in caplog.text


def test_sdk_backend_rejects_duplicate_headers_before_verification(
    identity: MemoryIdentity,
) -> None:
    """Test helper test_sdk_backend_rejects_duplicate_headers_before_verification."""
    async def scenario():
        """Test helper scenario."""
        verifier = AsyncMock(wraps=_adapter(identity))
        backend = ResearchBearerAuthBackend(verifier)
        from starlette.requests import HTTPConnection

        scope = _scope(identity.token())
        scope["headers"].append((b"Authorization", b"Bearer second"))
        assert await backend.authenticate(HTTPConnection(scope)) is None
        verifier.verify_token.assert_not_called()

    asyncio.run(scenario())


def test_concurrent_sdk_authenticated_requests_are_isolated(
    identity: MemoryIdentity,
) -> None:
    """Test helper test_concurrent_sdk_authenticated_requests_are_isolated."""
    async def scenario():
        """Test helper scenario."""
        arrived = 0
        both = asyncio.Event()
        observed = []

        async def app(scope, receive, send):
            """Test helper app."""
            nonlocal arrived
            first = get_current_principal()
            arrived += 1
            if arrived == 2:
                both.set()
            await asyncio.wait_for(both.wait(), timeout=3)
            await asyncio.sleep(0)
            assert get_current_principal() is first
            observed.append(first.principal_id)
            assert scope["user"].access_token.token == VERIFIED_TOKEN_MARKER
            assert IGNORED_SECRET not in repr(first)

        protected = _protected(app, identity)

        async def request(subject):
            """Test helper request."""
            _assert_no_context()
            await protected(_scope(identity.token(subject)), _receive, _send)
            _assert_no_context()

        await asyncio.gather(request(A), request(B))
        assert set(observed) == {A, B}
        _assert_no_context()

    asyncio.run(scenario())


@pytest.mark.parametrize("outcome", ["success", "exception", "cancelled", "send_error"])
def test_context_resets_in_same_task_after_every_exit(
    identity: MemoryIdentity,
    outcome: str,
) -> None:
    """Test helper test_context_resets_in_same_task_after_every_exit."""
    async def scenario():
        """Test helper scenario."""
        async def app(scope, receive, send):
            """Test helper app."""
            assert get_current_principal().principal_id == A
            await asyncio.sleep(0)
            if outcome == "exception":
                raise RuntimeError("downstream failure")
            if outcome == "cancelled":
                raise asyncio.CancelledError()
            if outcome == "send_error":
                await send({"type": "http.response.body", "body": b""})

        async def send(message):
            """Test helper send."""
            if outcome == "send_error":
                raise RuntimeError("send failure")

        protected = _protected(app, identity)
        if outcome == "success":
            await protected(_scope(identity.token()), _receive, send)
        else:
            expected = (
                asyncio.CancelledError if outcome == "cancelled" else RuntimeError
            )
            with pytest.raises(expected):
                await protected(_scope(identity.token()), _receive, send)
        _assert_no_context()

    asyncio.run(scenario())


def test_real_task_cancel_clears_context_before_task_finishes(
    identity: MemoryIdentity,
) -> None:
    """Test helper test_real_task_cancel_clears_context_before_task_finishes."""
    async def scenario():
        """Test helper scenario."""
        entered, wait_forever = asyncio.Event(), asyncio.Event()
        cleaned = []

        async def app(scope, receive, send):
            """Test helper app."""
            assert get_current_principal().principal_id == A
            entered.set()
            await wait_forever.wait()

        async def request():
            """Test helper request."""
            try:
                await _protected(app, identity)(
                    _scope(identity.token()), _receive, _send
                )
            finally:
                _assert_no_context()
                cleaned.append(True)

        task = asyncio.create_task(request())
        await asyncio.wait_for(entered.wait(), timeout=3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cleaned == [True]
        _assert_no_context()

    asyncio.run(scenario())


def test_nested_request_restores_previous_verified_principal(
    identity: MemoryIdentity,
) -> None:
    """Test helper test_nested_request_restores_previous_verified_principal."""
    async def scenario():
        """Test helper scenario."""
        async def inner(scope, receive, send):
            """Test helper inner."""
            assert get_current_principal().principal_id == B

        async def outer(scope, receive, send):
            """Test helper outer."""
            before = get_current_principal()
            assert before.principal_id == A
            await _protected(inner, identity)(_scope(identity.token(B)), receive, send)
            assert get_current_principal() is before

        await _protected(outer, identity)(_scope(identity.token()), _receive, _send)
        _assert_no_context()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "mutation",
    [
        "unauthenticated",
        "claims_none",
        "claims_extra",
        "issuer_type",
        "aud_type",
        "entity_string",
        "entity_bad",
        "entity_duplicate",
        "scope_bad",
        "scope_empty",
        "scope_duplicate",
        "scope_nonstring",
        "auth_mismatch",
        "subject_bad",
        "client_mismatch",
        "expiry_bool",
        "expiry_missing",
        "expiry_expired",
        "expiry_overflow",
        "raw_token",
        "resource_mismatch",
        "duplicate_header",
        "no_header",
    ],
)
def test_context_middleware_fails_closed_for_untrusted_or_malformed_scope(
    identity: MemoryIdentity,
    mutation: str,
) -> None:
    """Test helper test_context_middleware_fails_closed_for_untrusted_or_m..."""
    async def scenario():
        """Test helper scenario."""
        raw = identity.token()
        access = await _adapter(identity).verify_token(raw)
        assert access is not None
        scope = _scope(raw)
        scope["user"] = AuthenticatedUser(access)
        scope["auth"] = AuthCredentials(access.scopes)
        if mutation == "unauthenticated":
            scope.pop("user")
        elif mutation == "claims_none":
            access.claims = None
        elif mutation == "claims_extra":
            access.claims["untrusted_extra"] = IGNORED_SECRET
        elif mutation == "issuer_type":
            access.claims["iss"] = [ISSUER]
        elif mutation == "aud_type":
            access.claims["aud"] = [AUDIENCE]
        elif mutation.startswith("entity_"):
            access.claims["entity_ids"] = {
                "entity_string": ENTITY,
                "entity_bad": ["SH600519"],
                "entity_duplicate": [ENTITY, ENTITY],
            }[mutation]
        elif mutation.startswith("scope_"):
            access.scopes = {
                "scope_bad": ["admin"],
                "scope_empty": [],
                "scope_duplicate": ["research:read", "research:read"],
                "scope_nonstring": [1],
            }[mutation]
        elif mutation == "auth_mismatch":
            scope["auth"] = AuthCredentials(["admin"])
        elif mutation == "subject_bad":
            access.subject = access.client_id = "bad-subject"
        elif mutation == "client_mismatch":
            access.client_id = str(B)
        elif mutation.startswith("expiry_"):
            access.expires_at = {
                "expiry_bool": True,
                "expiry_missing": None,
                "expiry_expired": int(NOW.timestamp()),
                "expiry_overflow": 10**100,
            }[mutation]
        elif mutation == "raw_token":
            access.token = raw
        elif mutation == "resource_mismatch":
            access.resource = "wrong"
        elif mutation == "duplicate_header":
            scope["headers"].append((b"Authorization", b"Bearer other"))
        elif mutation == "no_header":
            scope["headers"] = [(b"cookie", f"token={raw}".encode())]
            scope["query_string"] = f"token={raw}".encode()
        called, messages = [], []

        async def app(scope, receive, send):
            """Test helper app."""
            called.append(True)

        async def send(message):
            """Test helper send."""
            messages.append(message)

        await PrincipalContextMiddleware(app, clock=lambda: NOW)(scope, _receive, send)
        assert called == []
        assert messages[0]["status"] == 401
        assert json.loads(messages[1]["body"]) == {"error": "identity_invalid"}
        assert raw not in repr(messages)
        assert IGNORED_SECRET not in repr(messages)
        _assert_no_context()

    asyncio.run(scenario())


def test_non_http_lifecycle_is_passed_through_without_identity(
    identity: MemoryIdentity,
) -> None:
    """Test helper test_non_http_lifecycle_is_passed_through_without_identity."""
    calls = []

    async def app(scope, receive, send):
        """Test helper app."""
        _assert_no_context()
        calls.append(scope)

    scope = {"type": "lifespan"}
    asyncio.run(
        PrincipalContextMiddleware(app, clock=lambda: NOW)(scope, _receive, _send)
    )
    assert calls == [scope]


@pytest.mark.parametrize("outcome", ["success", "exception", "cancelled"])
def test_copied_background_context_cannot_retain_identity_after_request(
    identity: MemoryIdentity,
    outcome: str,
) -> None:
    """Test helper test_copied_background_context_cannot_retain_identity_a..."""
    async def scenario():
        """Test helper scenario."""
        resume = asyncio.Event()
        tasks = []

        async def child():
            """Test helper child."""
            await resume.wait()
            _assert_no_context()

        async def app(scope, receive, send):
            """Test helper app."""
            assert get_current_principal().principal_id == A
            tasks.append(asyncio.create_task(child()))
            if outcome == "exception":
                raise RuntimeError("test request failure")
            if outcome == "cancelled":
                raise asyncio.CancelledError()

        protected = _protected(app, identity)
        if outcome == "success":
            await protected(_scope(identity.token()), _receive, _send)
        else:
            expected = (
                asyncio.CancelledError if outcome == "cancelled" else RuntimeError
            )
            with pytest.raises(expected):
                await protected(_scope(identity.token()), _receive, _send)
        resume.set()
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=3)
        _assert_no_context()

    asyncio.run(scenario())


@pytest.mark.parametrize("outcome", ["success", "exception", "cancelled"])
def test_message_scope_binding_restores_outer_context_and_revokes_copies(
    identity: MemoryIdentity,
    outcome: str,
) -> None:
    """Test helper test_message_scope_binding_restores_outer_context_and_r..."""
    from app.research.identity_context import bind_mcp_principal_context

    async def scenario():
        """Test helper scenario."""
        access = await _adapter(identity).verify_token(identity.token(B))
        scope = _scope(identity.token(B))
        scope["user"] = AuthenticatedUser(access)
        scope["auth"] = AuthCredentials(access.scopes)
        resume, tasks = asyncio.Event(), []

        async def child():
            """Test helper child."""
            await resume.wait()
            _assert_no_context()

        async def app(outer_scope, receive, send):
            """Test helper app."""
            outer = get_current_principal()
            assert outer.principal_id == A
            try:
                with bind_mcp_principal_context(scope, clock=lambda: NOW) as principal:
                    assert principal.principal_id == B
                    assert get_current_principal() is principal
                    tasks.append(asyncio.create_task(child()))
                    if outcome == "exception":
                        raise RuntimeError("message failure")
                    if outcome == "cancelled":
                        raise asyncio.CancelledError()
            finally:
                assert get_current_principal() is outer

        if outcome == "success":
            await _protected(app, identity)(_scope(identity.token()), _receive, _send)
        else:
            expected = (
                asyncio.CancelledError if outcome == "cancelled" else RuntimeError
            )
            with pytest.raises(expected):
                await _protected(app, identity)(
                    _scope(identity.token()), _receive, _send
                )
        resume.set()
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=3)
        _assert_no_context()

    asyncio.run(scenario())


def test_adapter_does_not_swallow_real_cancellation() -> None:
    """Test helper test_adapter_does_not_swallow_real_cancellation."""
    verifier = AsyncMock()
    verifier.verify_bearer.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            ResearchTokenVerifier(verifier=verifier, clock=lambda: NOW).verify_token(
                "opaque"
            )
        )


def test_actual_stateful_sdk_reads_current_message_not_initialize_identity(
    identity: MemoryIdentity,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """No sockets: actual manager/session/JSON-RPC and authentication run in-process."""
    import httpx
    from app.research.identity_context import bind_mcp_principal_context
    from mcp import types
    from mcp.server.lowlevel import Server
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    from mcp.server.transport_security import TransportSecuritySettings

    async def scenario():
        """Test helper scenario."""
        server = Server("s03a-identity-bridge-test")
        observed = []

        @server.list_tools()
        async def list_tools():
            """Test helper list_tools."""
            _assert_no_context()  # the opening request's copied binding is revoked
            request = server.request_context.request
            with bind_mcp_principal_context(request.scope, clock=lambda: NOW):
                assert get_current_principal().principal_id == A
            _assert_no_context()
            return [
                types.Tool(
                    name="identity_probe",
                    inputSchema={"type": "object", "additionalProperties": False},
                )
            ]

        @server.call_tool(validate_input=False)
        async def call_tool(name, arguments):
            """Test helper call_tool."""
            assert name == "identity_probe" and arguments == {}
            _assert_no_context()
            request = server.request_context.request
            with bind_mcp_principal_context(
                request.scope, clock=lambda: NOW
            ) as principal:
                assert principal is get_current_principal()
                data = {
                    "subject": str(principal.principal_id),
                    "scopes": sorted(principal.scopes),
                }
                observed.append(data)
            _assert_no_context()
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=json.dumps(data))],
                structuredContent=data,
                isError=False,
            )

        manager = StreamableHTTPSessionManager(
            server,
            json_response=True,
            security_settings=TransportSecuritySettings(
                allowed_hosts=["research.example.test"],
                allowed_origins=["https://research.example.test"],
            ),
        )
        verifier = AsyncMock(wraps=_adapter(identity))
        app = AuthenticationMiddleware(
            PrincipalContextMiddleware(manager.handle_request, clock=lambda: NOW),
            backend=ResearchBearerAuthBackend(verifier),
        )
        token_a = identity.token()
        token_b = identity.token(B)
        token_read_only = identity.token(updates={"scope": "research:read"})
        headers = {
            "Authorization": f"Bearer {token_a}",
            "Accept": "application/json, text/event-stream",
            "Origin": "https://research.example.test",
        }
        async with (
            manager.run(),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="https://research.example.test",
            ) as client,
        ):
            response = await client.post(
                "/",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {"name": "in-memory-test", "version": "1"},
                    },
                },
            )
            assert response.status_code == 200, response.text
            assert "result" in response.json()
            session_id = response.headers["mcp-session-id"]
            headers.update(
                {"Mcp-Session-Id": session_id, "Mcp-Protocol-Version": "2025-11-25"}
            )
            initialized = await client.post(
                "/",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                },
            )
            assert initialized.status_code == 202
            listed = await client.post(
                "/",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/list",
                },
            )
            assert listed.status_code == 200
            assert listed.json()["result"]["tools"][0]["name"] == "identity_probe"
            call = {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "identity_probe", "arguments": {}},
            }
            first = await client.post("/", headers=headers, json=call)
            assert first.status_code == 200
            assert first.json()["result"]["structuredContent"] == {
                "subject": str(A),
                "scopes": ["research:create", "research:read"],
            }
            # A refreshed token in the SAME session loses create scope. If
            # initialize ContextVar leaked, the second result would be wrong.
            read_headers = {**headers, "Authorization": f"Bearer {token_read_only}"}
            second = await client.post(
                "/", headers=read_headers, json={**call, "id": 4}
            )
            assert second.status_code == 200
            assert second.json()["result"]["structuredContent"] == {
                "subject": str(A),
                "scopes": ["research:read"],
            }
            # The SDK's actual authorization_context includes iss/sub, so
            # the fixed nonsecret token marker does not collapse ownership.
            stolen = await client.post(
                "/",
                headers={**headers, "Authorization": f"Bearer {token_b}"},
                json={**call, "id": 5},
            )
            assert stolen.status_code == 404
            invalid = await client.post(
                "/",
                headers={**headers, "Authorization": "Bearer invalid"},
                json={**call, "id": 6},
            )
            assert invalid.status_code == 401
            repeated = await client.post(
                "/", headers=read_headers, json={**call, "id": 7}
            )
            assert repeated.status_code == 200
            assert repeated.json()["result"]["structuredContent"]["scopes"] == [
                "research:read"
            ]
            closed = await client.delete("/", headers=read_headers)
            assert closed.status_code == 200
            assert len(observed) == 3
            assert verifier.verify_token.await_count == 9
        _assert_no_context()
        for token in (token_a, token_b, token_read_only):
            assert token not in caplog.text
        assert IGNORED_SECRET not in caplog.text

    asyncio.run(asyncio.wait_for(scenario(), timeout=15))
