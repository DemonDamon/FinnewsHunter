"""Research-mode dependency isolation and Celery split tests.

Author: Damon Li
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def run_mode_script(mode: str, script: str) -> str:
    """Execute a clean subprocess with one explicit application mode."""
    environment = os.environ.copy()
    environment.update(
        {
            "APP_MODE": mode,
            "RESEARCH_ENABLED": "false",
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
        f"{mode} subprocess failed\nstdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}"
    )
    return completed.stdout


def test_research_main_import_does_not_load_legacy_dependency_tree() -> None:
    """Research app import must be offline and absent all legacy application dependencies."""
    output = run_mode_script(
        "research",
        """
        import json
        import socket
        import sys

        def refuse_network(*args, **kwargs):
            raise AssertionError("network access is not allowed during import")

        socket.create_connection = refuse_network

        import app.main

        forbidden_exact = {
            "app.api.v1.analysis",
            "app.api.v1.tasks",
            "app.api.v1.news",
            "app.api.v1.news_v2",
            "app.api.v1.stocks",
            "app.api.v1.agents",
            "app.api.v1.debug",
            "app.api.v1.knowledge_graph",
            "app.api.v1.alpha_mining",
            "app.tasks.crawl_tasks",
        }
        forbidden_prefixes = (
            "app.models",
            "app.storage.vector",
            "app.knowledge.graph",
        )
        loaded = set(sys.modules)
        assert not (forbidden_exact & loaded)
        assert not any(
            name.startswith(forbidden_prefixes)
            for name in loaded
        )
        print(json.dumps({"module_count": len(loaded)}))
        """,
    )
    assert json.loads(output)["module_count"] > 0


def test_research_celery_configuration_has_no_tasks_or_beat_schedule() -> None:
    """Research Celery must not load crawl modules or register scheduled crawl work."""
    output = run_mode_script(
        "research",
        """
        import json
        import socket
        import sys

        def refuse_network(*args, **kwargs):
            raise AssertionError("network access is not allowed during Celery import")

        socket.create_connection = refuse_network

        from app.core.celery_app import celery_app

        assert tuple(celery_app.conf.include) == ()
        assert dict(celery_app.conf.beat_schedule) == {}
        assert "app.tasks.crawl_tasks" not in sys.modules
        print(json.dumps({"include": list(celery_app.conf.include)}))
        """,
    )
    assert json.loads(output) == {"include": []}


def test_legacy_celery_configuration_keeps_the_ten_existing_beats() -> None:
    """Legacy mode must retain its single crawl include and ten named beat entries."""
    output = run_mode_script(
        "legacy",
        """
        import json

        from app.core.celery_app import celery_app

        expected = [
            "crawl-sina-every-1min",
            "crawl-tencent-every-1min",
            "crawl-jwview-every-1min",
            "crawl-eeo-every-1min",
            "crawl-caijing-every-1min",
            "crawl-jingji21-every-1min",
            "crawl-nbd-every-1min",
            "crawl-yicai-every-1min",
            "crawl-163-every-1min",
            "crawl-eastmoney-every-1min",
        ]
        assert tuple(celery_app.conf.include) == ("app.tasks.crawl_tasks",)
        assert list(celery_app.conf.beat_schedule) == expected
        assert len(celery_app.conf.beat_schedule) == 10
        print(json.dumps({"beat_count": len(celery_app.conf.beat_schedule)}))
        """,
    )
    assert json.loads(output) == {"beat_count": 10}
