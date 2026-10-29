"""Typed composition hooks for the isolated research application mode.

Author: Damon Li
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import TYPE_CHECKING

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


async def _uninstalled_readiness() -> dict[str, ResearchReadinessCheck]:
    """Return deterministic S01 checks without probing any dependency."""
    return {
        "ledger_ready": ResearchReadinessCheck(False, "ledger_not_installed"),
        "identity_ready": ResearchReadinessCheck(False, "identity_not_installed"),
        "mcp_ready": ResearchReadinessCheck(False, "mcp_not_installed"),
        "executor_ready": ResearchReadinessCheck(False, "executor_not_installed"),
    }


def build_research_components(settings: Settings) -> ResearchComponents:
    """Build S01's disabled components without dynamic imports or side effects."""
    del settings
    return ResearchComponents(
        router=None,
        mcp_app=None,
        lifespan=None,
        readiness=_uninstalled_readiness,
        worker_modules=(),
    )
