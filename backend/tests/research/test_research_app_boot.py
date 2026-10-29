"""Research application boot and lifecycle tests.

Author: Damon Li
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import os
import subprocess
import sys
import textwrap
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def run_research_script(script: str, *, research_enabled: bool = False) -> str:
    """Run an isolated research-mode probe with the selected interpreter."""
    environment = os.environ.copy()
    environment.update(
        {
            "APP_MODE": "research",
            "RESEARCH_ENABLED": str(research_enabled).lower(),
            "RESEARCH_EXECUTION_ENABLED": "false",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(BACKEND_ROOT),
        }
    )
    completed = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        cwd=BACKEND_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, (
        f"research subprocess failed\nstdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}"
    )
    return completed.stdout


def test_research_app_runs_real_lifespan_and_stays_not_ready() -> None:
    """Research mode must serve liveness without pretending dependencies are ready."""
    from app.research.composition import (
        RESEARCH_READINESS_NAMES,
        build_research_components,
    )

    source = inspect.getsource(build_research_components)
    assert not any(isinstance(node, ast.Delete) for node in ast.walk(ast.parse(source)))

    components = build_research_components(settings=object())
    checks = asyncio.run(components.readiness())
    assert tuple(checks) == RESEARCH_READINESS_NAMES
    assert all(check.ready is False for check in checks.values())

    output = run_research_script(
        """
        import io
        import logging
        import socket

        from fastapi import Body, FastAPI
        from fastapi.testclient import TestClient

        def refuse_network(*args, **kwargs):
            raise AssertionError("network access is not allowed during app boot")

        socket.create_connection = refuse_network

        from app.main import app

        sentinel = "sentinel-secret-must-not-leak"
        captured = io.StringIO()
        handler = logging.StreamHandler(captured)
        app_logger = logging.getLogger("app.main")
        original_propagate = app_logger.propagate
        app_logger.propagate = False
        app_logger.addHandler(handler)

        @app.post("/_test/validation")
        async def validation_probe(value: int = Body(embed=True)):
            return {"value": value}

        @app.get("/_test/error")
        async def error_probe():
            raise RuntimeError(sentinel)

        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                assert client.get("/").status_code == 200

                health = client.get("/health")
                assert health.status_code == 200
                assert health.json()["mode"] == "research"
                assert health.json()["research"]["ready"] is False

                readiness = client.get("/readyz")
                assert readiness.status_code == 503
                readiness_body = readiness.json()
                assert readiness_body["status"] == "not_ready"
                assert readiness_body["mode"] == "research"
                assert set(readiness_body["checks"]) == {
                    "ledger_ready",
                    "identity_ready",
                    "mcp_ready",
                    "executor_ready",
                }
                assert all(
                    check["ready"] is False
                    for check in readiness_body["checks"].values()
                )

                for path in (
                    "/api/v1/debug",
                    "/api/v1/llm",
                    "/api/v1/news",
                    "/api/v1/alpha",
                    "/api/v1/mcp",
                ):
                    assert client.get(path).status_code == 404, path

                validation = client.post(
                    "/_test/validation",
                    json={"value": sentinel},
                )
                assert validation.status_code == 422
                assert validation.json()["error"] == "invalid_request"
                assert sentinel not in validation.text
                assert "traceback" not in validation.text.lower()

                failure = client.get("/_test/error")
                assert failure.status_code == 500
                assert failure.json()["error"] == "internal_error"
                assert sentinel not in failure.text
                assert "traceback" not in failure.text.lower()
        finally:
            app_logger.removeHandler(handler)
            app_logger.propagate = original_propagate

        assert sentinel not in captured.getvalue()
        """
    )
    assert output == ""


def test_injected_components_compose_router_and_cleanup() -> None:
    """A test-only component fixture must compose and clean up in deterministic order."""
    output = run_research_script(
        """
        from contextlib import asynccontextmanager

        from fastapi import APIRouter
        from fastapi.testclient import TestClient

        import app.research.composition as composition
        from app.research.composition import ResearchComponents, ResearchReadinessCheck

        events = []
        router = APIRouter()

        @router.get("/_fixture")
        async def fixture_route():
            return {"fixture": True}

        @asynccontextmanager
        async def fixture_lifespan(application):
            events.append("enter")
            try:
                yield
            finally:
                events.append("exit")

        async def fixture_readiness():
            return {
                "ledger_ready": ResearchReadinessCheck(False, "fixture_not_ready"),
                "identity_ready": ResearchReadinessCheck(False, "fixture_not_ready"),
                "mcp_ready": ResearchReadinessCheck(False, "fixture_not_ready"),
                "executor_ready": ResearchReadinessCheck(False, "fixture_not_ready"),
            }

        def build_fixture_components(settings):
            return ResearchComponents(
                router=router,
                mcp_app=None,
                lifespan=fixture_lifespan,
                readiness=fixture_readiness,
                worker_modules=(),
            )

        composition.build_research_components = build_fixture_components

        from app.main import app

        with TestClient(app, raise_server_exceptions=False) as client:
            assert client.get("/health").status_code == 200
            assert client.get("/api/v1/_fixture").json() == {"fixture": True}
            assert client.get("/readyz").status_code == 503
            assert events == ["enter"]

        assert events == ["enter", "exit"]
        """,
        research_enabled=True,
    )
    assert output == ""


def test_component_lifespan_exit_errors_are_not_discarded() -> None:
    """A component teardown error must still execute cleanup and be surfaced."""
    output = run_research_script(
        """
        from contextlib import asynccontextmanager

        from fastapi.testclient import TestClient

        import app.research.composition as composition
        from app.research.composition import ResearchComponents, ResearchReadinessCheck

        events = []

        @asynccontextmanager
        async def failing_lifespan(application):
            events.append("enter")
            try:
                yield
            finally:
                events.append("exit")
                raise RuntimeError("fixture teardown failure")

        async def fixture_readiness():
            return {
                "ledger_ready": ResearchReadinessCheck(False, "fixture_not_ready"),
                "identity_ready": ResearchReadinessCheck(False, "fixture_not_ready"),
                "mcp_ready": ResearchReadinessCheck(False, "fixture_not_ready"),
                "executor_ready": ResearchReadinessCheck(False, "fixture_not_ready"),
            }

        def build_fixture_components(settings):
            return ResearchComponents(
                router=None,
                mcp_app=None,
                lifespan=failing_lifespan,
                readiness=fixture_readiness,
                worker_modules=(),
            )

        composition.build_research_components = build_fixture_components

        from app.main import app

        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                assert client.get("/health").status_code == 200
        except RuntimeError as error:
            assert str(error) == "fixture teardown failure"
        else:
            raise AssertionError("component teardown error was discarded")

        assert events == ["enter", "exit"]
        """,
        research_enabled=True,
    )
    assert output == ""
