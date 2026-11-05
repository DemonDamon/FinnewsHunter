"""Research application boot and lifecycle tests.

Author: Damon Li
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def run_research_script(
    script: str,
    *,
    research_enabled: bool = False,
    execution_enabled: bool = False,
    extra_env: dict[str, str] | None = None,
) -> str:
    """Run an isolated research-mode probe with the selected interpreter."""
    environment = os.environ.copy()
    environment.update(
        {
            "APP_MODE": "research",
            "RESEARCH_ENABLED": str(research_enabled).lower(),
            "RESEARCH_EXECUTION_ENABLED": str(execution_enabled).lower(),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(BACKEND_ROOT),
        }
    )
    if extra_env:
        environment.update(extra_env)
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
                    "/api/v1/research/runs",
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


def test_legacy_default_exposes_news_and_hides_research_surfaces() -> None:
    """Legacy mode must keep existing API routes and omit research HTTP/MCP mounts."""
    environment = os.environ.copy()
    environment.update(
        {
            "APP_MODE": "legacy",
            "RESEARCH_ENABLED": "false",
            "RESEARCH_EXECUTION_ENABLED": "false",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(BACKEND_ROOT),
        }
    )
    script = """
        from fastapi.testclient import TestClient

        from app.main import app

        paths = set(app.openapi()["paths"])
        assert any(path.startswith("/api/v1/news") for path in paths)
        assert not any(path.startswith("/api/v1/research/") for path in paths)
        assert all(getattr(route, "path", None) != "/api/v1/mcp" for route in app.routes)

        with TestClient(app, raise_server_exceptions=False) as client:
            assert client.get("/").status_code == 200
            assert client.get("/readyz").json()["mode"] == "legacy"
            for path in (
                "/api/v1/research/runs",
                "/api/v1/research/evidence/not-a-run",
                "/api/v1/mcp",
            ):
                assert client.get(path).status_code == 404, path
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
        f"legacy subprocess failed\nstdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}"
    )


def test_enabled_research_readiness_tracks_each_explicit_configuration_gap() -> None:
    """Each missing research credential or transport policy must map to a safe readiness reason."""
    valid_jwks = '{"keys":[{"kid":"memory","kty":"RSA","n":"abc","e":"AQAB","alg":"RS256","use":"sig"}]}'
    scenarios = {
        "missing_database": (
            {},
            lambda checks: (
                checks["ledger_ready"]["reason"] == "ledger_dsn_missing_or_invalid"
            ),
        ),
        "missing_issuer": (
            {
                "RESEARCH_IDENTITY_AUDIENCE": "research-test",
                "RESEARCH_TRUSTED_JWKS_JSON": valid_jwks,
            },
            lambda checks: checks["identity_ready"]["ready"] is False,
        ),
        "missing_audience": (
            {
                "RESEARCH_IDENTITY_ISSUER": "https://identity.test",
                "RESEARCH_TRUSTED_JWKS_JSON": valid_jwks,
            },
            lambda checks: checks["identity_ready"]["ready"] is False,
        ),
        "missing_jwks": (
            {
                "RESEARCH_IDENTITY_ISSUER": "https://identity.test",
                "RESEARCH_IDENTITY_AUDIENCE": "research-test",
            },
            lambda checks: checks["identity_ready"]["ready"] is False,
        ),
        "missing_allowed_host": (
            {
                "RESEARCH_IDENTITY_ISSUER": "https://identity.test",
                "RESEARCH_IDENTITY_AUDIENCE": "research-test",
                "RESEARCH_TRUSTED_JWKS_JSON": valid_jwks,
                "RESEARCH_MCP_ALLOWED_ORIGINS": '["https://research.test"]',
            },
            lambda checks: checks["mcp_ready"]["ready"] is False,
        ),
        "missing_allowed_origin": (
            {
                "RESEARCH_IDENTITY_ISSUER": "https://identity.test",
                "RESEARCH_IDENTITY_AUDIENCE": "research-test",
                "RESEARCH_TRUSTED_JWKS_JSON": valid_jwks,
                "RESEARCH_MCP_ALLOWED_HOSTS": '["research.test"]',
            },
            lambda checks: checks["mcp_ready"]["ready"] is False,
        ),
    }
    for name, (extra_env, assertion) in scenarios.items():
        output = run_research_script(
            """
            import asyncio
            import json
            import socket

            def refuse_network(*args, **kwargs):
                raise AssertionError("network access is not allowed during readiness probes")

            socket.create_connection = refuse_network

            from app.core.config import Settings
            from app.research.composition import build_research_components

            components = build_research_components(Settings())
            checks = asyncio.run(components.readiness())
            print(json.dumps({name: {"ready": check.ready, "reason": check.reason} for name, check in checks.items()}))
            """,
            research_enabled=True,
            extra_env=extra_env,
        )
        payload = json.loads(output.strip())
        assert assertion(payload), name


def test_malformed_jwks_keeps_liveness_without_leaking_configuration() -> None:
    """Invalid JWKS material must not break liveness or echo raw configuration."""
    output = run_research_script(
        """
        from fastapi.testclient import TestClient

        from app.main import app

        secret = "malformed-jwks-secret"
        with TestClient(app, raise_server_exceptions=False) as client:
            assert client.get("/health").status_code == 200
            readiness = client.get("/readyz")
            assert readiness.status_code == 503
            assert readiness.json()["checks"]["identity_ready"]["ready"] is False
            assert secret not in readiness.text
        """,
        research_enabled=True,
        extra_env={"RESEARCH_TRUSTED_JWKS_JSON": "malformed-jwks-secret"},
    )
    assert output == ""


def test_execution_switch_never_marks_executor_ready() -> None:
    """S04 is absent: execution may be toggled on but executor readiness stays false."""
    output = run_research_script(
        """
        import asyncio
        import json

        from app.core.config import Settings
        from app.research.composition import build_research_components

        settings = Settings()
        assert settings.RESEARCH_EXECUTION_ENABLED is True
        checks = asyncio.run(build_research_components(settings).readiness())
        executor = checks["executor_ready"]
        print(json.dumps({"ready": executor.ready, "reason": executor.reason}))
        """,
        research_enabled=True,
        execution_enabled=True,
    )
    payload = json.loads(output.strip())
    assert payload["ready"] is False
    assert payload["reason"] == "executor_not_installed"


def test_enabled_research_missing_security_material_stays_live_and_closed() -> None:
    """Missing explicit DB/identity/transport policy cannot enable requests."""
    output = run_research_script(
        """
        from fastapi.testclient import TestClient
        from app.main import app
        expected = {
            "/api/v1/research/runs",
            "/api/v1/research/runs/{id}",
            "/api/v1/research/runs/{id}/events",
            "/api/v1/research/evidence/{id}",
        }
        registered = set(app.openapi()["paths"])
        assert {path for path in registered if path.startswith("/api/v1/research/")} == expected
        assert all(getattr(route, "path", None) != "/api/v1/mcp" for route in app.routes)

        with TestClient(app, raise_server_exceptions=False) as client:
            assert client.get("/").status_code == 200
            health = client.get("/health").json()
            assert health["research"]["enabled"] is True
            ready = client.get("/readyz")
            assert ready.status_code == 503
            checks = ready.json()["checks"]
            assert all(check["ready"] is False for check in checks.values())
            assert checks["ledger_ready"]["reason"] != "ledger_ready"
            assert checks["identity_ready"]["reason"] == "identity_not_installed"
            assert checks["mcp_ready"]["reason"] == "mcp_not_installed"
            assert checks["executor_ready"]["reason"] == "executor_not_installed"
            assert client.get("/api/v1/research/runs/not-a-run").status_code == 401
        """,
        research_enabled=True,
    )
    assert output == ""
