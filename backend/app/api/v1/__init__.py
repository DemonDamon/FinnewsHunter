"""Version-one API router assembly.

Author: Damon Li
"""
from __future__ import annotations

from importlib import import_module
from typing import Literal

from fastapi import APIRouter

from app.core.config import settings

LegacyRouterSpec = tuple[str, str, tuple[str, ...]]

_LEGACY_ROUTER_SPECS: tuple[LegacyRouterSpec, ...] = (
    ("news", "/news", ("news",)),
    ("news_v2", "/news/v2", ("news-v2",)),
    ("analysis", "/analysis", ("analysis",)),
    ("tasks", "/tasks", ("tasks",)),
    ("llm_config", "/llm", ("llm",)),
    ("stocks", "/stocks", ("stocks",)),
    ("agents", "/agents", ("agents",)),
    ("debug", "/debug", ("debug",)),
    ("knowledge_graph", "/knowledge-graph", ("knowledge-graph",)),
    ("alpha_mining", "", ()),
)


def _legacy_router_module(module_name: str):
    """Load one legacy route module only while assembling legacy mode."""
    module = globals().get(module_name)
    if module is None:
        module = import_module(f"app.api.v1.{module_name}")
        globals()[module_name] = module
    return module


def build_api_router(mode: Literal["legacy", "research"]) -> APIRouter:
    """Build the route set permitted for the selected application mode."""
    router = APIRouter()
    if mode == "research":
        return router
    if mode != "legacy":
        raise ValueError(f"Unsupported application mode: {mode}")

    for module_name, prefix, tags in _LEGACY_ROUTER_SPECS:
        module = _legacy_router_module(module_name)
        router.include_router(module.router, prefix=prefix, tags=list(tags))
    return router


api_router = build_api_router(settings.APP_MODE)

__all__ = ["api_router"]
