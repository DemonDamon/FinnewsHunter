"""Verify the legacy synchronous DSN uses its declared installed driver.

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


def test_sync_database_driver_constructs_without_network(tmp_path: Path) -> None:
    """Use real settings and engines without credentials or database calls."""
    script = textwrap.dedent(
        """
        import json
        import socket

        attempts = []

        def reject_network(*args, **kwargs):
            attempts.append("blocked")
            raise AssertionError("network connection is forbidden")

        socket.create_connection = reject_network
        socket.socket.connect = reject_network

        from app.core.config import Settings
        from sqlalchemy import create_engine

        settings = Settings(
            _env_file=None,
            POSTGRES_USER="test",
            POSTGRES_PASSWORD="test",
            POSTGRES_HOST="127.0.0.1",
            POSTGRES_PORT=1,
            POSTGRES_DB="isolated_probe",
        )
        assert settings.DATABASE_URL.startswith("postgresql+asyncpg://")
        assert settings.SYNC_DATABASE_URL.startswith("postgresql+psycopg2://")
        engine = create_engine(settings.SYNC_DATABASE_URL)
        assert engine.dialect.driver == "psycopg2"
        engine.dispose()
        assert attempts == []
        print(json.dumps({"driver": "psycopg2", "network_attempts": 0}))
        """
    )
    environment = {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path),
        "PYTHONPATH": str(BACKEND_ROOT),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"driver": "psycopg2", "network_attempts": 0}
