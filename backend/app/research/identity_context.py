"""Bridge verified research identity to MCP 1.30.0 without retaining JWTs.

ASGI scope authentication is trusted only after the official SDK backend has
called ResearchTokenVerifier. HTTP dependencies instead call verify_http_principal
and never consult the MCP request context. No identity is cached by session.

Author: Damon Li
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from mcp.server.auth.middleware.bearer_auth import (
    AuthenticatedUser,
    BearerAuthBackend,
)
from mcp.server.auth.provider import AccessToken, TokenVerifier
from starlette.authentication import AuthCredentials
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.research.errors import DomainError
from app.research.ports import (
    BearerCredential,
    IdentityVerifierPort,
    Principal,
    ResearchScope,
)

Clock = Callable[[], datetime]
MAX_AUTHORIZATION_LENGTH = 4096
VERIFIED_TOKEN_MARKER = "verified-research-identity"
_BEARER = re.compile(rb"(?i:Bearer) ([A-Za-z0-9._~+/-]+=*)")
_OPAQUE = re.compile(r"[A-Za-z0-9._~+/-]+=*")
_ENTITY = re.compile(r"CN\.(?:SH|SZ|BJ)\.[0-9]{6}")
_ALLOWED_SCOPES = frozenset({"research:create", "research:read"})


@dataclass(slots=True, repr=False)
class _RequestIdentity:
    """Revoke identity in copied background-task contexts when a request ends."""

    principal: Principal | None = field(repr=False)


_principal_context: ContextVar[_RequestIdentity | None] = ContextVar(
    "research_verified_principal", default=None
)


def _invalid_identity() -> DomainError:
    """Keep every untrusted transport identity error secret-safe and identical."""
    return DomainError(
        code="identity_invalid",
        safe_message="identity verification failed",
        retryable=False,
    )


def _utc_now(clock: Clock) -> datetime:
    """Reject invalid injected clocks without interpolating their values."""
    now = clock()
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise _invalid_identity()
    return now.astimezone(UTC)


def parse_bearer_headers(
    headers: Sequence[tuple[bytes, bytes]],
) -> BearerCredential:
    """Accept exactly one ASCII Bearer field, at most 4096 bytes in total.

    Scheme matching is case-insensitive, but whitespace, comma-folded values,
    duplicate fields (including mixed casing), and credential fallback are not
    accepted. The 4096-byte bound includes the seven-byte ``Bearer `` prefix.
    """
    values = [value for name, value in headers if name.lower() == b"authorization"]
    if len(values) != 1:
        raise _invalid_identity()
    value = values[0]
    if not isinstance(value, bytes) or len(value) > MAX_AUTHORIZATION_LENGTH:
        raise _invalid_identity()
    match = _BEARER.fullmatch(value)
    if match is None:
        raise _invalid_identity()
    return BearerCredential(match.group(1).decode("ascii"))


async def verify_http_principal(
    *,
    headers: Sequence[tuple[bytes, bytes]],
    verifier: IdentityVerifierPort,
    clock: Clock,
) -> Principal:
    """Build HTTP identity only by parsing raw headers and invoking the verifier."""
    credential = parse_bearer_headers(headers)
    return await verifier.verify_bearer(credential=credential, now=_utc_now(clock))


class ResearchTokenVerifier(TokenVerifier):
    """Implement the installed SDK protocol with a local, injected verifier.

    The only token retained by the returned AccessToken is a constant marker.
    ``None`` is the SDK's invalid-token outcome; no diagnostic is logged or
    reflected, including when the underlying identity adapter is unavailable.
    """

    __slots__ = ("_clock", "_verifier")

    def __init__(self, *, verifier: IdentityVerifierPort, clock: Clock) -> None:
        """Keep only injected dependencies, never bearer material."""
        self._verifier = verifier
        self._clock = clock

    async def verify_token(self, token: str) -> AccessToken | None:
        """Reverify on every SDK request, returning verified safe identity fields."""
        if (
            not isinstance(token, str)
            or not token
            or len(token) + len("Bearer ") > MAX_AUTHORIZATION_LENGTH
            or _OPAQUE.fullmatch(token) is None
        ):
            return None
        try:
            principal = await self._verifier.verify_bearer(
                credential=BearerCredential(token), now=_utc_now(self._clock)
            )
        except Exception:  # noqa: BLE001 -- fail closed without logging identity secrets
            # Cancellation is BaseException and deliberately propagates.
            # The SDK treats None as fail closed and returns its fixed 401.
            return None
        return AccessToken(
            token=VERIFIED_TOKEN_MARKER,
            client_id=str(principal.principal_id),
            subject=str(principal.principal_id),
            scopes=sorted(principal.scopes),
            expires_at=int(principal.expires_at.timestamp()),
            resource=principal.audience,
            claims={
                "iss": principal.issuer,
                "aud": principal.audience,
                "entity_ids": sorted(principal.entity_ids),
            },
        )


class ResearchBearerAuthBackend(BearerAuthBackend):
    """Preflight strict raw headers before the SDK's otherwise permissive parser.

    Install this in Starlette AuthenticationMiddleware, outside
    PrincipalContextMiddleware. The official backend still owns authentication
    and constructs AuthenticatedUser; this bridge never supplies a Principal.
    """

    async def authenticate(self, conn: HTTPConnection):
        """Reject duplicates/oversize/folded credentials before calling the SDK."""
        try:
            parse_bearer_headers(conn.scope.get("headers", []))
        except DomainError:
            return None
        return await super().authenticate(conn)


def get_current_principal() -> Principal:
    """Return only this MCP request's identity, failing closed outside its scope."""
    binding = _principal_context.get()
    if binding is None or binding.principal is None:
        raise _invalid_identity()
    return binding.principal


def _principal_from_scope(scope: Scope, *, now: datetime) -> Principal:
    """Validate the SDK's authenticated safe projection, not raw JWT claims."""
    user = scope.get("user")
    auth = scope.get("auth")
    if not isinstance(user, AuthenticatedUser) or not isinstance(auth, AuthCredentials):
        raise _invalid_identity()
    info = user.access_token
    if not isinstance(info, AccessToken) or info.token != VERIFIED_TOKEN_MARKER:
        raise _invalid_identity()
    claims = info.claims
    if not isinstance(claims, dict) or set(claims) != {"iss", "aud", "entity_ids"}:
        raise _invalid_identity()
    issuer, audience, entities = claims["iss"], claims["aud"], claims["entity_ids"]
    if (
        not isinstance(issuer, str)
        or not issuer
        or not isinstance(audience, str)
        or not audience
        or info.resource != audience
        or not isinstance(info.subject, str)
        or info.client_id != info.subject
        or type(info.expires_at) is not int
        or not isinstance(info.scopes, list)
        or not info.scopes
        or any(type(item) is not str for item in info.scopes)
        or not set(info.scopes).issubset(_ALLOWED_SCOPES)
        or len(set(info.scopes)) != len(info.scopes)
        or set(auth.scopes) != set(info.scopes)
        or not isinstance(entities, list)
        or not entities
        or any(
            type(item) is not str or _ENTITY.fullmatch(item) is None
            for item in entities
        )
        or len(set(entities)) != len(entities)
    ):
        raise _invalid_identity()
    try:
        principal_id = UUID(info.subject)
        expires_at = datetime.fromtimestamp(info.expires_at, tz=UTC)
    except (ValueError, OverflowError, OSError):
        raise _invalid_identity() from None
    if now >= expires_at:
        raise _invalid_identity()
    return Principal(
        principal_id=principal_id,
        scopes=cast(frozenset[ResearchScope], frozenset(info.scopes)),
        entity_ids=frozenset(entities),
        issuer=issuer,
        audience=audience,
        expires_at=expires_at,
    )


@contextmanager
def bind_mcp_principal_context(scope: Scope, *, clock: Clock) -> Iterator[Principal]:
    """Bind the current SDK message's authenticated Request.scope in a handler.

    Stateful SDK handlers run in session tasks, not necessarily the current HTTP
    task. Call this with ``server.request_context.request.scope`` for EACH tool
    or list handler, never with a cached initialize scope. This validates only
    the safe SDK projection; the outer backend already reverified this request.
    Copied ContextVar bindings are revoked at exit, including on cancellation.
    """
    if scope.get("type") != "http":
        raise _invalid_identity()
    parse_bearer_headers(scope.get("headers", []))
    principal = _principal_from_scope(scope, now=_utc_now(clock))
    binding = _RequestIdentity(principal)
    context_token = _principal_context.set(binding)
    try:
        yield principal
    finally:
        binding.principal = None
        _principal_context.reset(context_token)


class PrincipalContextMiddleware:
    """Bind immutable SDK-verified identity only for the duration of one HTTP call.

    Required order: AuthenticationMiddleware(ResearchBearerAuthBackend) -> this
    middleware -> protected MCP ASGI app. Never place identity in app.state or
    MCP session data. Non-HTTP lifecycle scopes simply pass through unchanged.
    """

    __slots__ = ("_clock", "app")

    def __init__(self, app: ASGIApp, *, clock: Clock) -> None:
        """Retain the downstream app and the explicit UTC-aware clock only."""
        self.app = app
        self._clock = clock

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Reset the prior context on completion, exceptions, and cancellation."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        context_token = _principal_context.set(None)
        binding = None
        try:
            try:
                parse_bearer_headers(scope.get("headers", []))
                principal = _principal_from_scope(scope, now=_utc_now(self._clock))
            except DomainError:
                response = JSONResponse(
                    {"error": "identity_invalid"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
                await response(scope, receive, send)
                return
            binding = _RequestIdentity(principal)
            _principal_context.set(binding)
            await self.app(scope, receive, send)
        finally:
            if binding is not None:
                binding.principal = None
            _principal_context.reset(context_token)
