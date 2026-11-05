"""Typed composition hooks for the isolated research application mode.
Author: Damon Li
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, FastAPI
from starlette.types import ASGIApp

if TYPE_CHECKING:
    from app.core.config import Settings
RESEARCH_READINESS_NAMES = (
    "ledger_ready",
    "identity_ready",
    "mcp_ready",
    "executor_ready",
)


@dataclass(frozen=True, slots=True)
class ResearchReadinessCheck:
    """One safe and named research readiness result."""

    ready: bool
    reason: str


ResearchReadiness = Callable[[], Awaitable[dict[str, ResearchReadinessCheck]]]
ResearchLifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


@dataclass(frozen=True, slots=True)
class ResearchComponents:
    """The optional application hooks installed by later research milestones."""

    router: APIRouter | None
    mcp_app: ASGIApp | None
    lifespan: ResearchLifespan | None
    readiness: ResearchReadiness
    worker_modules: tuple[str, ...] = ()
    service: object | None = None
    identity_verifier: object | None = None


async def _uninstalled_readiness() -> dict[str, ResearchReadinessCheck]:
    """Return deterministic S01 checks without probing any dependency."""
    return {
        "ledger_ready": ResearchReadinessCheck(False, "ledger_not_installed"),
        "identity_ready": ResearchReadinessCheck(False, "identity_not_installed"),
        "mcp_ready": ResearchReadinessCheck(False, "mcp_not_installed"),
        "executor_ready": ResearchReadinessCheck(False, "executor_not_installed"),
    }


class _NoExecutor:
    """S04 is not installed: every run creation must fail closed."""

    @staticmethod
    async def get_readiness(*, now: datetime) -> Any:
        """Report executor readiness as permanently unavailable until S04."""
        from app.research.ports import ExecutorReadiness

        return ExecutorReadiness(
            False, "executor_not_installed", now, now + timedelta(seconds=1)
        )

    @staticmethod
    async def record_heartbeat(*, worker: Any, now: datetime) -> Any:
        """Ignore worker heartbeats while the executor registry is not installed."""
        return await _NoExecutor.get_readiness(now=now)


def _research_clock() -> datetime:
    """Return the current UTC instant for research composition wiring."""
    return datetime.now(UTC)


class _InstalledResearchReadiness:
    """Aggregate readiness probes for an installed research stack."""

    __slots__ = ("_database", "_clock", "_identity_ready", "_mcp")

    def __init__(
        self,
        database: object,
        clock: Callable[[], datetime],
        *,
        identity_ready: bool,
        mcp_component: object | None,
    ) -> None:
        self._database = database
        self._clock = clock
        self._identity_ready = identity_ready
        self._mcp = mcp_component

    async def __call__(self) -> dict[str, ResearchReadinessCheck]:
        """Aggregate ledger, identity, MCP, and executor readiness probes."""
        result = await self._database.check_ready(now=self._clock())
        db_reason = (
            result.reason
            if result.reason
            in {
                "ledger_ready",
                "ledger_not_configured",
                "ledger_dsn_missing_or_invalid",
                "ledger_migration_unavailable",
            }
            else "ledger_not_ready"
        )
        mcp_ready = bool(self._mcp and self._mcp.readiness.get("mcp"))
        return {
            "ledger_ready": ResearchReadinessCheck(result.ready, db_reason),
            "identity_ready": ResearchReadinessCheck(
                self._identity_ready,
                "identity_ready" if self._identity_ready else "identity_not_installed",
            ),
            "mcp_ready": ResearchReadinessCheck(
                mcp_ready, "mcp_ready" if mcp_ready else "mcp_not_installed"
            ),
            "executor_ready": ResearchReadinessCheck(False, "executor_not_installed"),
        }


class _InstalledResearchLifespan:
    """Dispose database resources after optional MCP lifespan."""

    __slots__ = ("_database", "_mcp")

    def __init__(self, database: object, mcp_component: object | None) -> None:
        self._database = database
        self._mcp = mcp_component

    @asynccontextmanager
    async def __call__(self, _application: FastAPI):
        """Enter MCP manager lifecycle and dispose database resources on exit."""
        try:
            async with AsyncExitStack() as stack:
                if self._mcp is not None:
                    await stack.enter_async_context(self._mcp.lifespan())
                yield
        finally:
            await self._database.dispose()


def build_research_components(settings: Settings) -> ResearchComponents:
    """Build research dependencies without connecting or discovering services."""
    if getattr(settings, "APP_MODE", None) != "research" or not getattr(
        settings, "RESEARCH_ENABLED", False
    ):
        return ResearchComponents(None, None, None, _uninstalled_readiness)
    from app.api.v1.research import router
    from app.mcp.finnews_server import create_finnews_mcp_app
    from app.research.auth import LocalRS256IdentityVerifier, ResearchAuthorizer
    from app.research.db import create_research_database
    from app.research.ledger import ResearchLedger
    from app.research.service import ResearchApplicationService
    from app.research.snapshot import ResearchSnapshotService

    now: Callable[[], datetime] = _research_clock
    dsn = settings.RESEARCH_DATABASE_URL
    database = create_research_database(dsn)
    ledger = ResearchLedger(
        database=database,
        authorizer=ResearchAuthorizer(),
        executor_registry=_NoExecutor(),
        snapshot_service=ResearchSnapshotService(database),
    )
    service = ResearchApplicationService(
        ledger=ledger,
        authorization=ResearchAuthorizer(),
        clock=now,
        execution_enabled=settings.RESEARCH_EXECUTION_ENABLED,
    )
    identity_ready = False
    jwks = None
    try:
        raw = settings.RESEARCH_TRUSTED_JWKS_JSON
        jwks = json.loads(raw) if raw else None
        keys = jwks.get("keys") if isinstance(jwks, dict) else None
        identity_ready = bool(
            settings.RESEARCH_IDENTITY_ISSUER
            and settings.RESEARCH_IDENTITY_AUDIENCE
            and isinstance(keys, list)
            and keys
            and all(
                isinstance(key, dict)
                and isinstance(key.get("kid"), str)
                and key.get("kty") == "RSA"
                and isinstance(key.get("n"), str)
                and isinstance(key.get("e"), str)
                and "d" not in key
                and "k" not in key
                and key.get("alg") in (None, "RS256")
                and key.get("use") in (None, "sig")
                for key in keys
            )
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        jwks = None
    verifier = LocalRS256IdentityVerifier(
        issuer=settings.RESEARCH_IDENTITY_ISSUER or "",
        audience=settings.RESEARCH_IDENTITY_AUDIENCE or "",
        trusted_jwks=jwks,
    )
    hosts = list(settings.RESEARCH_MCP_ALLOWED_HOSTS)
    origins = list(settings.RESEARCH_MCP_ALLOWED_ORIGINS)
    mcp_component = None
    if hosts and origins:
        mcp_component = create_finnews_mcp_app(
            service=service,
            token_verifier=verifier,
            clock=now,
            allowed_hosts=hosts,
            allowed_origins=origins,
        )

    readiness = _InstalledResearchReadiness(
        database,
        now,
        identity_ready=identity_ready,
        mcp_component=mcp_component,
    )
    lifespan = _InstalledResearchLifespan(database, mcp_component)

    return ResearchComponents(
        router=router,
        mcp_app=mcp_component.app if mcp_component else None,
        lifespan=lifespan,
        readiness=readiness,
        worker_modules=(),
        service=service,
        identity_verifier=verifier,
    )
