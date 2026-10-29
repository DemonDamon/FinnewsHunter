# Author: Damon Li
"""Tests for the isolated research startup script behavior."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
START_SCRIPT = PROJECT_ROOT / "backend" / "start.sh"


def _write_executable(path: Path, content: str) -> None:
    """Write one isolated command fake with executable permissions."""
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _fake_tools(tmp_path: Path) -> dict[str, Path]:
    """Create command fakes that record invocations without starting services."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True)
    docker_log = "${CALL_LOG:?CALL_LOG must be set}"

    _write_executable(
        bin_dir / "docker",
        f"""#!/usr/bin/env bash
set -eu
printf 'docker|APP_MODE=%s|RESEARCH_ENABLED=%s|ARGS=%s\\n' "${{APP_MODE:-}}" "${{RESEARCH_ENABLED:-}}" "$*" >> {docker_log}
if [[ "${{1:-}}" == "compose" && "${{2:-}}" == "version" ]]; then
  printf '%s\\n' 'Docker Compose version v2.39.2-desktop.1'
fi
""",
    )
    _write_executable(
        bin_dir / "docker-compose",
        f"""#!/usr/bin/env bash
set -eu
printf 'docker-compose|ARGS=%s\\n' "$*" >> {docker_log}
if [[ "${{1:-}}" == "version" ]]; then
  printf '%s\\n' 'docker-compose version 1.29.2'
fi
""",
    )
    _write_executable(
        bin_dir / "python",
        f"""#!/usr/bin/env bash
set -eu
printf 'python|APP_MODE=%s|RESEARCH_ENABLED=%s|ARGS=%s\\n' "${{APP_MODE:-}}" "${{RESEARCH_ENABLED:-}}" "$*" >> {docker_log}
if [[ "${{1:-}}" == "-m" && "${{2:-}}" == "alembic" ]]; then
  exit "${{FAKE_ALEMBIC_EXIT:-0}}"
fi
if [[ "${{1:-}}" == "-c" ]]; then
  printf '%s' "${{FAKE_WORKER_MODULES:-}}"
fi
""",
    )
    _write_executable(
        bin_dir / "uvicorn",
        f"""#!/usr/bin/env bash
set -eu
printf 'uvicorn|APP_MODE=%s|RESEARCH_ENABLED=%s|ARGS=%s\\n' "${{APP_MODE:-}}" "${{RESEARCH_ENABLED:-}}" "$*" >> {docker_log}
""",
    )
    _write_executable(
        bin_dir / "sleep",
        f"""#!/usr/bin/env bash
set -eu
printf 'sleep|ARGS=%s\\n' "$*" >> {docker_log}
""",
    )
    return {"bin": bin_dir, "python": bin_dir / "python", "uvicorn": bin_dir / "uvicorn"}


def _run_start(
    tmp_path: Path,
    arguments: list[str],
    *,
    project_root: Path = PROJECT_ROOT,
    extra_env: dict[str, str] | None = None,
    direct: bool = False,
) -> tuple[subprocess.CompletedProcess[str], str]:
    """Run a copied or repository script with controlled infrastructure commands."""
    tools = _fake_tools(tmp_path)
    call_log = tmp_path / "calls.log"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{tools['bin']}{os.pathsep}{env.get('PATH', '')}",
            "CALL_LOG": str(call_log),
            "PYTHON_BIN": str(tools["python"]),
            "UVICORN_BIN": str(tools["uvicorn"]),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    if extra_env:
        env.update(extra_env)

    script = project_root / "backend" / "start.sh"
    command = [str(script), *arguments] if direct else ["bash", str(script), *arguments]
    result = subprocess.run(
        command,
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return result, call_log.read_text(encoding="utf-8") if call_log.exists() else ""


def _copy_minimal_project(tmp_path: Path) -> Path:
    """Copy only files the startup script owns into an isolated test project."""
    project = tmp_path / "project"
    (project / "backend").mkdir(parents=True)
    (project / "deploy").mkdir()
    for source in (
        PROJECT_ROOT / "backend" / "start.sh",
        PROJECT_ROOT / "deploy" / "docker-compose.dev.yml",
        PROJECT_ROOT / "deploy" / "docker-compose.research.yml",
    ):
        destination = project / source.relative_to(PROJECT_ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return project


def test_bash_syntax_help_and_invalid_options_are_explicit(tmp_path: Path) -> None:
    """The CLI must reject unknown modes and flags instead of ignoring them."""
    syntax = subprocess.run(["bash", "-n", str(START_SCRIPT)], text=True, capture_output=True, check=False)
    assert syntax.returncode == 0, syntax.stderr
    assert START_SCRIPT.stat().st_mode & stat.S_IXUSR

    help_result, help_calls = _run_start(tmp_path / "help", ["--help"], direct=True)
    assert help_result.returncode == 0
    assert "Usage:" in help_result.stdout
    assert help_calls == ""

    invalid_mode, _ = _run_start(tmp_path / "invalid-mode", ["--mode", "unsupported"])
    assert invalid_mode.returncode != 0
    assert "Unsupported mode" in invalid_mode.stderr

    unknown_flag, _ = _run_start(tmp_path / "unknown-flag", ["--not-a-real-flag"])
    assert unknown_flag.returncode != 0
    assert "Unknown option" in unknown_flag.stderr


def test_research_check_only_runs_compose_config_without_side_effects(tmp_path: Path) -> None:
    """Research --check must not start services, migrations, or Uvicorn."""
    result, calls = _run_start(tmp_path, ["--mode", "research", "--check"], direct=True)

    assert result.returncode == 0, result.stderr
    assert "docker|" in calls
    assert "docker-compose|" not in calls
    assert "-f " in calls and "docker-compose.research.yml" in calls
    assert " config --format json" in calls
    assert " up " not in calls
    assert "python|" not in calls
    assert "uvicorn|" not in calls
    assert "init_db.py" not in calls


def test_research_no_services_is_a_pure_app_diagnostic(tmp_path: Path) -> None:
    """--no-services starts only the research app with disabled defaults."""
    result, calls = _run_start(tmp_path, ["--mode", "research", "--no-services"])

    assert result.returncode == 0, result.stderr
    assert "docker|" not in calls
    assert "python|" not in calls
    assert "init_db.py" not in calls
    assert "uvicorn|APP_MODE=research|RESEARCH_ENABLED=false" in calls
    assert "app.main:app" in calls


def test_research_enabled_no_services_is_rejected_before_application_start(tmp_path: Path) -> None:
    """Enabled research must not bypass migration safety through a diagnostic command."""
    result, calls = _run_start(
        tmp_path,
        ["--mode", "research", "--no-services"],
        extra_env={"RESEARCH_ENABLED": "true"},
    )

    assert result.returncode != 0
    assert "--no-services is a pure diagnostic" in result.stderr
    assert "docker|" not in calls
    assert "python|" not in calls
    assert "uvicorn|" not in calls
    assert "init_db.py" not in calls


def test_research_enabled_requires_real_alembic_files_before_services(tmp_path: Path) -> None:
    """An enabled research migration cannot fall back to the legacy initializer."""
    result, calls = _run_start(
        tmp_path,
        ["--mode", "research"],
        extra_env={"RESEARCH_ENABLED": "true"},
    )

    assert result.returncode != 0
    assert "Alembic migration files are required" in result.stderr
    assert " up " not in calls
    assert "python|" not in calls
    assert "uvicorn|" not in calls
    assert "init_db.py" not in calls


def test_failed_research_migration_prevents_uvicorn(tmp_path: Path) -> None:
    """A migration failure exits nonzero and never continues to Uvicorn."""
    project = _copy_minimal_project(tmp_path)
    (project / "backend" / "alembic").mkdir()
    (project / "backend" / "alembic.ini").write_text("[alembic]\nscript_location = alembic\n", encoding="utf-8")

    result, calls = _run_start(
        tmp_path / "run",
        ["--mode", "research"],
        project_root=project,
        extra_env={"RESEARCH_ENABLED": "true", "FAKE_ALEMBIC_EXIT": "12"},
    )

    assert result.returncode == 12
    assert "python|APP_MODE=research|RESEARCH_ENABLED=true|ARGS=-m alembic" in calls
    assert "uvicorn|" not in calls
    assert "init_db.py" not in calls


def test_legacy_remains_the_default_and_uses_legacy_initializer(tmp_path: Path) -> None:
    """The no-argument path preserves the legacy Compose and init behavior."""
    result, calls = _run_start(tmp_path, [])

    assert result.returncode == 0, result.stderr
    assert "docker|APP_MODE=|RESEARCH_ENABLED=|ARGS=compose version" in calls
    assert "ARGS=compose -f " in calls
    assert "docker-compose.dev.yml" in calls
    assert " up -d --wait" in calls
    assert "python|APP_MODE=legacy" in calls
    assert "init_db.py" in calls
    assert "uvicorn|APP_MODE=legacy" in calls


def test_with_worker_fake_control_flow_rejects_unregistered_research_modules(tmp_path: Path) -> None:
    """The fake interpreter covers only the no-worker control-flow branch."""
    result, calls = _run_start(tmp_path, ["--mode", "research", "--with-worker"])

    assert result.returncode != 0
    assert "no worker modules are registered" in result.stderr
    assert "celery-worker" not in calls
    assert "uvicorn|" not in calls


@pytest.mark.skipif(
    not (PROJECT_ROOT / "backend" / "app" / "research" / "composition.py").is_file(),
    reason="Requires the S01 application composition implementation from the application owner.",
)
def test_with_worker_real_interpreter_reports_empty_components_without_compose(tmp_path: Path) -> None:
    """A real interpreter must distinguish an empty registry from an import failure."""
    tool_dir = tmp_path / "bin"
    tool_dir.mkdir()
    call_log = tmp_path / "calls.log"
    docker = tool_dir / "docker"
    uvicorn = tool_dir / "uvicorn"
    _write_executable(docker, f"#!/usr/bin/env bash\nprintf 'docker|ARGS=%s\\n' \"$*\" >> {call_log}\n")
    _write_executable(uvicorn, f"#!/usr/bin/env bash\nprintf 'uvicorn|ARGS=%s\\n' \"$*\" >> {call_log}\n")

    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{tool_dir}{os.pathsep}{environment.get('PATH', '')}",
            "PYTHON_BIN": sys.executable,
            "UVICORN_BIN": str(uvicorn),
            "RESEARCH_ENABLED": "false",
            "RESEARCH_EXECUTION_ENABLED": "false",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    result = subprocess.run(
        [str(START_SCRIPT), "--mode", "research", "--with-worker"],
        cwd=PROJECT_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    calls = call_log.read_text(encoding="utf-8") if call_log.exists() else ""
    assert result.returncode != 0
    assert "no worker modules are registered" in result.stderr
    assert "component registry could not be loaded" not in result.stderr
    assert "docker|" not in calls
    assert "uvicorn|" not in calls
