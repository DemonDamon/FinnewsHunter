"""Core package public exports.

Author: Damon Li
"""
from __future__ import annotations

from typing import Any

__all__ = ["settings", "get_settings", "get_db", "init_database"]

_CONFIG_EXPORTS = frozenset({"settings", "get_settings"})
_DATABASE_EXPORTS = frozenset({"get_db", "init_database"})


def __getattr__(name: str) -> Any:
    """Load the original public export only when a caller requests it."""
    if name in _CONFIG_EXPORTS:
        from app.core.config import get_settings, settings

        exports = {"settings": settings, "get_settings": get_settings}
    elif name in _DATABASE_EXPORTS:
        from app.core.database import get_db, init_database

        exports = {"get_db": get_db, "init_database": init_database}
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    globals().update(exports)
    return exports[name]


def __dir__() -> list[str]:
    """Expose lazy public names to interactive and inspection tooling."""
    return sorted(set(globals()) | set(__all__))
