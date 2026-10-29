# Author: Damon Li
"""Tests for research Compose isolation and the verification worker image."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEPLOY_DIR = PROJECT_ROOT / "deploy"
DEV_COMPOSE = DEPLOY_DIR / "docker-compose.dev.yml"
RESEARCH_COMPOSE = DEPLOY_DIR / "docker-compose.research.yml"
DOCKERFILE = DEPLOY_DIR / "Dockerfile.celery"
ENTRYPOINT = DEPLOY_DIR / "celery-entrypoint.sh"
DOCKERIGNORE = PROJECT_ROOT / ".dockerignore"


def _research_compose_config(*profiles: str) -> dict[str, object]:
    """Parse the override with the local Compose implementation without starting it."""
    environment = os.environ.copy()
    environment.update(
        {
            "COMPOSE_PROJECT_NAME": "finnews_s01_config_only",
            "RESEARCH_ENABLED": "false",
            "RESEARCH_EXECUTION_ENABLED": "false",
        }
    )
    command = ["docker", "compose"]
    for profile in profiles:
        command.extend(["--profile", profile])
    command.extend(
        [
            "-f",
            str(DEV_COMPOSE),
            "-f",
            str(RESEARCH_COMPOSE),
            "config",
            "--format",
            "json",
        ]
    )
    result = subprocess.run(
        command,
        cwd=DEPLOY_DIR,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_research_override_exists_and_uses_supported_reset_and_override_tags() -> None:
    """The overlay must remove inherited env_file and Neo4j dependencies exactly."""
    assert RESEARCH_COMPOSE.is_file()
    content = RESEARCH_COMPOSE.read_text(encoding="utf-8")

    assert "env_file: !reset []" in content
    assert "depends_on: !override" in content
    assert "APP_MODE: research" in content
    assert "RESEARCH_ENABLED: ${RESEARCH_ENABLED:-false}" in content
    assert "RESEARCH_EXECUTION_ENABLED: ${RESEARCH_EXECUTION_ENABLED:-false}" in content
    assert "PYTHON_BASE: python:3.12" in content
    assert "FINNEWS_MODE: research" in content


def test_research_compose_config_has_only_postgres_and_redis_enabled_by_default() -> None:
    """A real Compose config parse must show all non-core services as opt-in profiles."""
    config = _research_compose_config()
    services = config["services"]
    assert isinstance(services, dict)

    assert set(services) == {"postgres", "redis"}

    profiled = _research_compose_config(
        "research-worker",
        "research-beat",
        "research-graph",
        "research-vector",
    )["services"]
    for name in (
        "celery-worker",
        "celery-beat",
        "neo4j",
        "milvus-etcd",
        "milvus-minio",
        "milvus-standalone",
    ):
        assert profiled[name]["profiles"], name


def test_research_worker_reuses_services_without_user_env_or_neo4j_dependency() -> None:
    """The worker is optional, targets the research queue, and cannot inherit Neo4j."""
    config = _research_compose_config("research-worker")
    worker = config["services"]["celery-worker"]

    assert worker["command"] == [
        "celery",
        "-A",
        "app.core.celery_app",
        "worker",
        "--loglevel=info",
        "--queues=research",
    ]
    assert "env_file" not in worker
    assert set(worker["depends_on"]) == {"postgres", "redis"}
    assert "neo4j" not in worker["depends_on"]
    assert worker["environment"]["APP_MODE"] == "research"
    assert worker["environment"]["RESEARCH_ENABLED"] == "false"
    assert worker["environment"]["RESEARCH_EXECUTION_ENABLED"] == "false"


def test_research_dockerfile_installs_only_the_hashed_lock_and_entrypoint_never_reinstalls() -> None:
    """Research images must use Python 3.12 and the reviewed hash lock at build time."""
    linux_lock = PROJECT_ROOT / "backend" / "requirements-research-linux.lock"
    assert linux_lock.is_file(), "Linux image lock must exist in the build context"
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    entrypoint = ENTRYPOINT.read_text(encoding="utf-8")

    assert "ARG PYTHON_BASE=python:3.11" in dockerfile
    assert "FROM ${PYTHON_BASE}" in dockerfile
    assert "ARG FINNEWS_MODE=legacy" in dockerfile
    assert (
        "COPY backend/requirements-research-linux.lock "
        "/opt/finnews-deps/requirements-research-linux.lock" in dockerfile
    )
    assert (
        "--require-hashes -r "
        "/opt/finnews-deps/requirements-research-linux.lock" in dockerfile
    )
    assert "-r /opt/finnews-deps/requirements-research.lock" not in dockerfile
    assert 'if [ "$FINNEWS_MODE" = "research" ]; then' in dockerfile
    assert "pip check" in entrypoint
    assert 'if [ "${APP_MODE:-legacy}" = "research" ]; then' in entrypoint
    research_branch = entrypoint.split('if [ "${APP_MODE:-legacy}" = "research" ]; then', 1)[1].split("fi", 1)[0]
    assert "pip install" not in research_branch


def test_dockerignore_excludes_sensitive_and_intermediate_context_without_excluding_lock() -> None:
    """The verification build context must not include local credentials or task artifacts."""
    content = DOCKERIGNORE.read_text(encoding="utf-8")

    for required in (".git", ".env", ".work", "node_modules"):
        assert required in content
    assert "requirements-research.lock" not in content
