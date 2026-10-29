"""Legacy route assembly and settings validation tests.

Author: Damon Li
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from app.core.config import Settings
from pydantic import ValidationError

BACKEND_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("overrides", "field_name"),
    [
        ({"APP_MODE": "unsupported"}, "APP_MODE"),
        ({"RESEARCH_ENABLED": True}, "RESEARCH_ENABLED"),
        ({"RESEARCH_EXECUTION_ENABLED": True}, "RESEARCH_EXECUTION_ENABLED"),
        (
            {
                "APP_MODE": "research",
                "RESEARCH_ENABLED": True,
                "RESEARCH_SOURCE_ALLOWLIST": [""],
            },
            "RESEARCH_SOURCE_ALLOWLIST",
        ),
        (
            {
                "APP_MODE": "research",
                "RESEARCH_ENABLED": True,
                "RESEARCH_SOURCE_ALLOWLIST": ["Unsafe Source"],
            },
            "RESEARCH_SOURCE_ALLOWLIST",
        ),
        (
            {
                "APP_MODE": "research",
                "RESEARCH_ENABLED": True,
                "RESEARCH_SOURCE_ALLOWLIST": [f"source-{index}" for index in range(17)],
            },
            "RESEARCH_SOURCE_ALLOWLIST",
        ),
    ],
)
def test_research_settings_reject_invalid_combinations(
    overrides: dict[str, object], field_name: str
) -> None:
    """Invalid mode, flag, and source combinations must fail at validation time."""
    with pytest.raises(ValidationError) as error:
        Settings(**overrides)

    assert field_name in str(error.value)


def test_research_settings_keep_safe_legacy_defaults() -> None:
    """The existing default process must remain in fully disabled legacy mode."""
    defaults = Settings()
    enabled = Settings(
        APP_MODE="research",
        RESEARCH_ENABLED=True,
        RESEARCH_SOURCE_ALLOWLIST=["approved-source", "provider_2"],
    )

    assert defaults.APP_MODE == "legacy"
    assert defaults.RESEARCH_ENABLED is False
    assert defaults.RESEARCH_EXECUTION_ENABLED is False
    assert defaults.RESEARCH_SOURCE_ALLOWLIST == []
    assert enabled.RESEARCH_SOURCE_ALLOWLIST == ["approved-source", "provider_2"]


def test_legacy_router_factory_preserves_original_order_prefixes_and_tags() -> None:
    """Stub routers prove only assembly compatibility, not legacy business E2E behavior."""
    environment = os.environ.copy()
    environment.update(
        {
            "APP_MODE": "research",
            "RESEARCH_ENABLED": "false",
            "RESEARCH_EXECUTION_ENABLED": "false",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(BACKEND_ROOT),
        }
    )
    script = """
        import sys
        import types

        from fastapi import APIRouter

        import app.api.v1 as api_v1

        expected = [
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
        ]

        for module_name, _, _ in expected:
            module = types.ModuleType(f"app.api.v1.{module_name}")
            module.router = APIRouter()

            async def probe(name=module_name):
                return {"module": name}

            module.router.add_api_route("/_stub", probe, methods=["GET"])
            sys.modules[module.__name__] = module
            setattr(api_v1, module_name, module)

        research_router = api_v1.build_api_router("research")
        assert research_router.routes == []

        router = api_v1.build_api_router("legacy")
        actual = [
            (route_context.path_format, tuple(route_context.tags or ()))
            for included_router in router.routes
            for route_context in included_router.effective_route_contexts()
        ]
        expected_routes = [
            (f"{prefix}/_stub", tags)
            for _, prefix, tags in expected
        ]
        assert actual == expected_routes
    """
    completed = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        cwd=BACKEND_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, (
        f"legacy assembly subprocess failed\nstdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}"
    )


def test_core_public_exports_are_lazy_original_exports_not_database_stubs() -> None:
    """Settings exports stay import-safe and database exports remain their real module."""
    environment = os.environ.copy()
    environment.update(
        {
            "APP_MODE": "research",
            "RESEARCH_ENABLED": "false",
            "RESEARCH_EXECUTION_ENABLED": "false",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(BACKEND_ROOT),
        }
    )
    script = """
        import importlib
        import sys

        import app.core as core

        assert core.__all__ == ["settings", "get_settings", "get_db", "init_database"]
        assert set(core.__all__).issubset(dir(core))
        assert "app.core.config" not in sys.modules
        assert "app.core.database" not in sys.modules

        config = importlib.import_module("app.core.config")
        assert core.settings is config.settings
        assert core.get_settings is config.get_settings
        assert "app.core.database" not in sys.modules

        try:
            exported_get_db = core.get_db
        except ModuleNotFoundError as error:
            assert error.name == "psycopg"
            assert "get_db" not in core.__dict__
        else:
            database = importlib.import_module("app.core.database")
            assert exported_get_db is database.get_db
            assert core.init_database is database.init_database
    """
    completed = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        cwd=BACKEND_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, (
        f"core lazy export subprocess failed\nstdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}"
    )
