"""Verify the isolated research-v1.1 PostgreSQL migration substrate.

These tests intentionally exercise real PostgreSQL DDL and constraints through
the stage runner's dedicated disposable database.  They do not use SQLite,
``create_all``, destructive reset helpers, or container commands.

Author: Damon Li
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from app.research.contracts import EvidenceV1
from app.research.db import RESEARCH_ALEMBIC_HEAD, create_research_database
from app.research.errors import DomainError
from app.research.models import (
    ResearchEvidence,
    ResearchMarketPayload,
    ResearchSourcePolicy,
)
from app.research.ports import AdmittedEvidence, SourcePolicy
from app.research.repositories import EvidenceRegistrationRepository
from sqlalchemy import event, func, inspect, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

from backend.tests.research.postgres_fixtures import (
    ALEMBIC_DIR,
    IsolatedPostgres,
    alembic_config,
    create_postgres_context,
    set_search_path,
    upgrade_head,
)

NOW = datetime(2026, 10, 30, 2, 0, tzinfo=UTC)
_HASH_A = "a" * 64
_HASH_B = "b" * 64


@pytest.fixture
def postgres_context() -> IsolatedPostgres:
    """Allocate one runner-validated, non-destructive PostgreSQL test schema."""
    return create_postgres_context()


async def _run_in_schema(
    context: IsolatedPostgres,
    operation,
):
    """Run one async operation in the fresh schema and release its test engine."""
    engine = create_async_engine(context.url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await set_search_path(connection, context)
            return await operation(connection)
    finally:
        await engine.dispose()


async def _table_names(context: IsolatedPostgres) -> set[str]:
    """Inspect the schema-local tables using PostgreSQL's actual catalog."""

    async def inspect_tables(connection: AsyncConnection) -> set[str]:
        return await connection.run_sync(
            lambda sync_connection: set(
                inspect(sync_connection).get_table_names(schema=context.schema)
            )
        )

    return await _run_in_schema(context, inspect_tables)


async def _constraint_catalog(context: IsolatedPostgres) -> dict[str, object]:
    """Read migration-created unique/check/foreign-key metadata from PostgreSQL."""

    def inspect_constraints(sync_connection):
        inspector = inspect(sync_connection)
        return {
            "run_unique": inspector.get_unique_constraints(
                "research_run", schema=context.schema
            ),
            "run_check": inspector.get_check_constraints(
                "research_run", schema=context.schema
            ),
            "snapshot_unique": inspector.get_unique_constraints(
                "research_snapshot_member", schema=context.schema
            ),
            "event_unique": inspector.get_unique_constraints(
                "research_run_event", schema=context.schema
            ),
            "outbox_unique": inspector.get_unique_constraints(
                "research_outbox", schema=context.schema
            ),
            "citation_fks": inspector.get_foreign_keys(
                "research_brief_citation", schema=context.schema
            ),
        }

    async def inspect_all(connection: AsyncConnection) -> dict[str, object]:
        return await connection.run_sync(inspect_constraints)

    return await _run_in_schema(context, inspect_all)


async def _seed_policy_evidence_run(context: IsolatedPostgres) -> dict[str, UUID]:
    """Insert the minimal valid rows needed to exercise database-only constraints."""
    identifiers = {
        "evidence_id": uuid4(),
        "run_id": uuid4(),
        "principal_id": uuid4(),
        "request_id": uuid4(),
        "outbox_id": uuid4(),
        "snapshot_id": uuid4(),
    }

    async def seed(connection: AsyncConnection) -> None:
        await connection.execute(
            text(
                """
                INSERT INTO research_source_policy (
                    source_id, policy_version, license_id, terms_ref, approved_at,
                    expires_at, redisplay_allowed, model_use_allowed, storage_allowed,
                    allowed_excerpt_length
                ) VALUES (
                    'source_one', 'v1', 'license-one', 'terms-one', :now,
                    :expires_at, true, true, true, 4000
                )
                """
            ),
            {"now": NOW, "expires_at": datetime(2026, 11, 1, tzinfo=UTC)},
        )
        await connection.execute(
            text(
                """
                INSERT INTO research_evidence (
                    evidence_id, source_id, source_url, content_hash, published_at,
                    fetched_at, available_at, timezone, license_scope, entity_id,
                    excerpt, quality_status, evidence_kind, version,
                    source_policy_version, origin, admitted_at
                ) VALUES (
                    :evidence_id, 'source_one', 'https://source.example.test/item',
                    :content_hash, :now, :now, :now, 'UTC', 'redisplay',
                    'CN.SH.600519', 'bounded evidence', 'verified_metadata', 'event',
                    'ev-v1', 'v1', 'live', :now
                )
                """
            ),
            {
                "evidence_id": identifiers["evidence_id"],
                "content_hash": _HASH_A,
                "now": NOW,
            },
        )
        await connection.execute(
            text(
                """
                INSERT INTO research_run (
                    run_id, request_id, principal_id, entity_id, seed_evidence_id,
                    request_hash, as_of, status, snapshot_state, policy_version,
                    prompt_version, created_at, updated_at
                ) VALUES (
                    :run_id, :request_id, :principal_id, 'CN.SH.600519', :evidence_id,
                    :request_hash, :now, 'queued', 'none', 'v1', 'prompt-v1', :now, :now
                )
                """
            ),
            {
                "run_id": identifiers["run_id"],
                "request_id": identifiers["request_id"],
                "principal_id": identifiers["principal_id"],
                "evidence_id": identifiers["evidence_id"],
                "request_hash": _HASH_B,
                "now": NOW,
            },
        )
        await connection.execute(
            text(
                """
                INSERT INTO research_snapshot_member (
                    snapshot_member_id, run_id, evidence_id, evidence_version,
                    content_hash, selected_at
                ) VALUES (:snapshot_id, :run_id, :evidence_id, 'ev-v1', :content_hash, :now)
                """
            ),
            {
                "snapshot_id": identifiers["snapshot_id"],
                "run_id": identifiers["run_id"],
                "evidence_id": identifiers["evidence_id"],
                "content_hash": _HASH_A,
                "now": NOW,
            },
        )
        await connection.execute(
            text(
                """
                INSERT INTO research_outbox (
                    outbox_id, run_id, dispatch_id, contract_version, delivery_status,
                    available_at, created_at
                ) VALUES (:outbox_id, :run_id, 'dispatch-one', 'research-v1.1',
                    'pending', :now, :now)
                """
            ),
            {
                "outbox_id": identifiers["outbox_id"],
                "run_id": identifiers["run_id"],
                "now": NOW,
            },
        )

    await _run_in_schema(context, seed)
    return identifiers


def test_module_import_does_not_connect(postgres_context: IsolatedPostgres) -> None:
    """AC-A1: importing persistence modules cannot construct an engine or load legacy DB."""
    _ = postgres_context
    backend_root = Path(__file__).resolve().parents[2]
    script = """
import sys
from unittest.mock import patch

with patch('sqlalchemy.ext.asyncio.create_async_engine', side_effect=AssertionError('engine')):
    import app.research.db
    import app.research.models
    import app.research.repositories
assert 'app.core.database' not in sys.modules
assert 'app.models' not in sys.modules
"""
    environment = {
        "HOME": os.environ.get("HOME", ""),
        "PATH": os.environ["PATH"],
        "PYTHONPATH": str(backend_root),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=backend_root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_upgrade_empty_isolated_postgresql(postgres_context: IsolatedPostgres) -> None:
    """AC-A2: the empty isolated schema gains only research tables and version state."""
    upgrade_head(postgres_context)
    expected = {
        "research_alembic_version",
        "research_principal_quota",
        "research_source_policy",
        "research_evidence",
        "research_market_payload",
        "research_run",
        "research_snapshot_member",
        "research_brief",
        "research_brief_citation",
        "research_run_event",
        "research_audit",
        "research_outbox",
        "research_worker_heartbeat",
    }
    assert asyncio.run(_table_names(postgres_context)) == expected
    catalog = asyncio.run(_constraint_catalog(postgres_context))
    assert {item["name"] for item in catalog["run_unique"]} >= {
        "research_run_principal_request_key"
    }
    assert {item["name"] for item in catalog["snapshot_unique"]} >= {
        "research_snapshot_run_evidence_key"
    }
    assert {item["name"] for item in catalog["event_unique"]} >= {
        "research_event_run_seq_key"
    }
    assert {item["name"] for item in catalog["outbox_unique"]} >= {
        "research_outbox_run_dispatch_key"
    }
    assert {item["name"] for item in catalog["run_check"]} >= {
        "research_run_status_check",
        "research_run_snapshot_state_check",
    }
    assert any(
        fk["name"] == "research_citation_snapshot_member_fk"
        for fk in catalog["citation_fks"]
    )
    database = create_research_database(
        postgres_context.url,
        connect_args={"server_settings": {"search_path": postgres_context.schema}},
    )
    readiness = asyncio.run(database.check_ready(now=NOW))
    asyncio.run(database.dispose())
    assert readiness.ready is True
    assert readiness.reason == "ledger_ready"
    assert RESEARCH_ALEMBIC_HEAD == "20261030_research_v11"


def test_upgrade_preserves_legacy_sentinel(postgres_context: IsolatedPostgres) -> None:
    """AC-A3: upgrade ignores a pre-existing non-research table and its row."""
    sentinel = b"legacy-sentinel-byte-equivalent"

    async def create_sentinel(connection: AsyncConnection) -> None:
        await connection.execute(
            text(
                "CREATE TABLE legacy_sentinel (id integer primary key, payload bytea not null)"
            )
        )
        await connection.execute(
            text("INSERT INTO legacy_sentinel (id, payload) VALUES (1, :payload)"),
            {"payload": sentinel},
        )

    asyncio.run(_run_in_schema(postgres_context, create_sentinel))
    upgrade_head(postgres_context)

    async def read_sentinel(connection: AsyncConnection) -> tuple[bytes, set[str]]:
        payload = (
            await connection.execute(
                text("SELECT payload FROM legacy_sentinel WHERE id = 1")
            )
        ).scalar_one()
        names = await connection.run_sync(
            lambda sync_connection: set(
                inspect(sync_connection).get_table_names(schema=postgres_context.schema)
            )
        )
        return payload, names

    payload, names = asyncio.run(_run_in_schema(postgres_context, read_sentinel))
    assert payload == sentinel
    assert "legacy_sentinel" in names
    assert "research_evidence" in names


def test_bad_revision_fails_without_application_start(
    postgres_context: IsolatedPostgres,
    tmp_path: Path,
) -> None:
    """AC-A4: a migration error stays non-ready and cannot start application composition."""
    migration_root = tmp_path / "research_bad_migrations"
    versions = migration_root / "versions"
    versions.mkdir(parents=True)
    shutil.copy2(ALEMBIC_DIR / "env.py", migration_root / "env.py")
    (versions / "bad_revision.py").write_text(
        """
from __future__ import annotations
revision = 'bad_revision'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    raise RuntimeError('forced migration failure')

def downgrade():
    raise RuntimeError('not available')
""",
        encoding="utf-8",
    )
    config = alembic_config(postgres_context, script_location=migration_root)
    with pytest.raises(RuntimeError, match="forced migration failure"):
        command.upgrade(config, "head")
    assert "app.main" not in sys.modules
    database = create_research_database(
        postgres_context.url,
        connect_args={"server_settings": {"search_path": postgres_context.schema}},
    )
    readiness = asyncio.run(database.check_ready(now=NOW))
    asyncio.run(database.dispose())
    assert readiness.ready is False
    assert readiness.reason == "ledger_migration_unavailable"


def test_constraints_are_enforced_by_postgresql(
    postgres_context: IsolatedPostgres,
) -> None:
    """AC-A5: uniqueness and status/check failures come from PostgreSQL constraints."""
    upgrade_head(postgres_context)
    identifiers = asyncio.run(_seed_policy_evidence_run(postgres_context))

    async def duplicate_run(connection: AsyncConnection) -> None:
        await connection.execute(
            text(
                """
                INSERT INTO research_run (
                    run_id, request_id, principal_id, entity_id, seed_evidence_id,
                    request_hash, as_of, status, snapshot_state, policy_version,
                    prompt_version, created_at, updated_at
                ) VALUES (
                    :new_run, :request_id, :principal_id, 'CN.SH.600519', :evidence_id,
                    :request_hash, :now, 'queued', 'none', 'v1', 'prompt-v1', :now, :now
                )
                """
            ),
            {**identifiers, "new_run": uuid4(), "request_hash": _HASH_B, "now": NOW},
        )

    with pytest.raises(IntegrityError):
        asyncio.run(_run_in_schema(postgres_context, duplicate_run))

    async def add_event_then_duplicate(connection: AsyncConnection) -> None:
        for event_id in (uuid4(), uuid4()):
            await connection.execute(
                text(
                    """
                    INSERT INTO research_run_event (
                        event_id, run_id, seq, event_type, occurred_at, payload_projection
                    ) VALUES (:event_id, :run_id, 1, 'started', :now, '{}'::jsonb)
                    """
                ),
                {"event_id": event_id, "run_id": identifiers["run_id"], "now": NOW},
            )

    with pytest.raises(IntegrityError):
        asyncio.run(_run_in_schema(postgres_context, add_event_then_duplicate))

    async def duplicate_snapshot(connection: AsyncConnection) -> None:
        await connection.execute(
            text(
                """
                INSERT INTO research_snapshot_member (
                    snapshot_member_id, run_id, evidence_id, evidence_version,
                    content_hash, selected_at
                ) VALUES (:snapshot_id, :run_id, :evidence_id, 'ev-v1', :content_hash, :now)
                """
            ),
            {
                "snapshot_id": uuid4(),
                "run_id": identifiers["run_id"],
                "evidence_id": identifiers["evidence_id"],
                "content_hash": _HASH_A,
                "now": NOW,
            },
        )

    with pytest.raises(IntegrityError):
        asyncio.run(_run_in_schema(postgres_context, duplicate_snapshot))

    async def duplicate_outbox(connection: AsyncConnection) -> None:
        await connection.execute(
            text(
                """
                INSERT INTO research_outbox (
                    outbox_id, run_id, dispatch_id, contract_version, delivery_status,
                    available_at, created_at
                ) VALUES (:outbox_id, :run_id, 'dispatch-one', 'research-v1.1',
                    'pending', :now, :now)
                """
            ),
            {"outbox_id": uuid4(), "run_id": identifiers["run_id"], "now": NOW},
        )

    with pytest.raises(IntegrityError):
        asyncio.run(_run_in_schema(postgres_context, duplicate_outbox))

    async def invalid_run_status(connection: AsyncConnection) -> None:
        await connection.execute(
            text(
                """
                INSERT INTO research_run (
                    run_id, request_id, principal_id, entity_id, seed_evidence_id,
                    request_hash, as_of, status, snapshot_state, policy_version,
                    prompt_version, created_at, updated_at
                ) VALUES (
                    :run_id, :request_id, :principal_id, 'CN.SH.600519', :evidence_id,
                    :request_hash, :now, 'not-a-status', 'none', 'v1', 'prompt-v1', :now, :now
                )
                """
            ),
            {
                "run_id": uuid4(),
                "request_id": uuid4(),
                "principal_id": uuid4(),
                "evidence_id": identifiers["evidence_id"],
                "request_hash": _HASH_B,
                "now": NOW,
            },
        )

    with pytest.raises(IntegrityError):
        asyncio.run(_run_in_schema(postgres_context, invalid_run_status))

    async def invalid_event_type(connection: AsyncConnection) -> None:
        await connection.execute(
            text(
                """
                INSERT INTO research_run_event (
                    event_id, run_id, seq, event_type, occurred_at, payload_projection
                ) VALUES (:event_id, :run_id, 2, 'not-an-event', :now, '{}'::jsonb)
                """
            ),
            {"event_id": uuid4(), "run_id": identifiers["run_id"], "now": NOW},
        )

    with pytest.raises(IntegrityError):
        asyncio.run(_run_in_schema(postgres_context, invalid_event_type))


def test_registration_rolls_back_policy_and_evidence(
    postgres_context: IsolatedPostgres,
) -> None:
    """AC-A6: a forced second write leaves policy/evidence/market and sentinel unchanged."""
    upgrade_head(postgres_context)
    sentinel = b"registration-sentinel"

    async def create_sentinel(connection: AsyncConnection) -> None:
        await connection.execute(
            text(
                "CREATE TABLE legacy_sentinel (id integer primary key, payload bytea not null)"
            )
        )
        await connection.execute(
            text("INSERT INTO legacy_sentinel (id, payload) VALUES (1, :payload)"),
            {"payload": sentinel},
        )

    asyncio.run(_run_in_schema(postgres_context, create_sentinel))
    evidence = EvidenceV1.model_validate(
        {
            "evidence_id": str(uuid4()),
            "source_id": "rollback_source",
            "source_url": "https://source.example.test/rollback",
            "content_hash": _HASH_A,
            "published_at": NOW.isoformat(),
            "fetched_at": NOW.isoformat(),
            "available_at": NOW.isoformat(),
            "timezone": "UTC",
            "license_scope": "redisplay",
            "entity_ids": ["CN.SH.600519"],
            "excerpt": "bounded rollback evidence",
            "quality_status": "verified_metadata",
            "evidence_kind": "event",
            "version": "rollback-v1",
            "source_policy_version": "v1",
            "origin": "live",
            "market_payload": None,
        }
    )
    admission = AdmittedEvidence(
        evidence=evidence,
        policy=SourcePolicy(
            source_id="rollback_source",
            policy_version="v1",
            license_id="license-rollback",
            terms_ref="terms-rollback",
            approved_at=NOW,
            expires_at=datetime(2026, 11, 1, tzinfo=UTC),
            redisplay_allowed=True,
            model_use_allowed=True,
            storage_allowed=True,
            allowed_excerpt_length=4000,
        ),
        admitted_at=NOW,
    )
    database = create_research_database(
        postgres_context.url,
        connect_args={"server_settings": {"search_path": postgres_context.schema}},
    )
    repository = EvidenceRegistrationRepository(database)
    engine = database._engine
    assert engine is not None

    def force_evidence_write_failure(*_args, **_kwargs) -> None:
        raise SQLAlchemyError("forced second write failure")

    event.listen(
        engine.sync_engine,
        "before_cursor_execute",
        force_evidence_write_failure,
        retval=False,
    )
    try:
        with pytest.raises(DomainError) as raised:
            asyncio.run(repository.register_evidence(admission=admission, now=NOW))
    finally:
        event.remove(
            engine.sync_engine, "before_cursor_execute", force_evidence_write_failure
        )
        asyncio.run(database.dispose())
    assert raised.value.code == "persistence_failed"

    async def count_rows(connection: AsyncConnection) -> tuple[int, int, int, bytes]:
        policy_count = (
            await connection.execute(
                select(func.count()).select_from(ResearchSourcePolicy)
            )
        ).scalar_one()
        evidence_count = (
            await connection.execute(select(func.count()).select_from(ResearchEvidence))
        ).scalar_one()
        market_count = (
            await connection.execute(
                select(func.count()).select_from(ResearchMarketPayload)
            )
        ).scalar_one()
        payload = (
            await connection.execute(
                text("SELECT payload FROM legacy_sentinel WHERE id = 1")
            )
        ).scalar_one()
        return policy_count, evidence_count, market_count, payload

    assert asyncio.run(_run_in_schema(postgres_context, count_rows)) == (
        0,
        0,
        0,
        sentinel,
    )


@pytest.mark.parametrize(
    ("wrong_version", "wrong_hash"),
    [("wrong-v", _HASH_A), ("ev-v1", _HASH_B)],
)
def test_snapshot_member_binds_exact_evidence_identity(
    postgres_context: IsolatedPostgres, wrong_version: str, wrong_hash: str
) -> None:
    """A snapshot cannot pin an existing evidence ID to another version/hash."""
    upgrade_head(postgres_context)
    ids = asyncio.run(_seed_policy_evidence_run(postgres_context))

    async def insert_mismatched_member(connection: AsyncConnection) -> None:
        await connection.execute(
            text("""
                INSERT INTO research_snapshot_member (
                    snapshot_member_id, run_id, evidence_id, evidence_version,
                    content_hash, selected_at
                ) VALUES (:member, :run, :evidence, :version, :hash, :now)
            """),
            {
                "member": uuid4(),
                "run": ids["run_id"],
                "evidence": ids["evidence_id"],
                "version": wrong_version,
                "hash": wrong_hash,
                "now": NOW,
            },
        )

    with pytest.raises(IntegrityError):
        asyncio.run(_run_in_schema(postgres_context, insert_mismatched_member))


def test_server_timestamp_default_is_timezone_independent(
    postgres_context: IsolatedPostgres,
) -> None:
    """TIMESTAMPTZ now() records the same instant under a non-UTC session TZ."""
    upgrade_head(postgres_context)

    async def insert_and_compare(connection: AsyncConnection) -> None:
        await connection.execute(text("SET LOCAL TIME ZONE 'Asia/Shanghai'"))
        await connection.execute(
            text("""
            INSERT INTO research_source_policy (
                source_id, policy_version, license_id, terms_ref, approved_at,
                expires_at, redisplay_allowed, model_use_allowed, storage_allowed,
                allowed_excerpt_length
            ) VALUES ('tz-check', 'v1', 'license', 'terms', :now, :expires,
                      true, true, true, 20)
        """),
            {"now": NOW, "expires": datetime(2026, 11, 1, tzinfo=UTC)},
        )
        row = (
            await connection.execute(
                text("""
            SELECT EXTRACT(EPOCH FROM registered_at), EXTRACT(EPOCH FROM transaction_timestamp())
            FROM research_source_policy WHERE source_id = 'tz-check'
        """)
            )
        ).one()
        assert row[0] == row[1]
        assert (
            await connection.execute(text("SHOW TIME ZONE"))
        ).scalar_one() == "Asia/Shanghai"

    asyncio.run(_run_in_schema(postgres_context, insert_and_compare))


def _registration_admission(*, market: bool, admitted_at: datetime) -> AdmittedEvidence:
    evidence_id = uuid4()
    payload = None
    if market:
        payload = {
            "evidence_id": str(evidence_id),
            "symbol": "CN.SH.600519",
            "observed_at": NOW.isoformat(),
            "available_at": NOW.isoformat(),
            "fetched_at": NOW.isoformat(),
            "timezone": "UTC",
            "currency": "CNY",
            "adjustment": "none",
            "fields": [{"name": "close", "value": "1.0", "unit": "CNY"}],
            "provider": "fixture-provider",
            "version": "market-v1",
            "is_mock": True,
        }
    evidence = EvidenceV1.model_validate(
        {
            "evidence_id": str(evidence_id),
            "source_id": "retry-market" if market else "retry-event",
            "source_url": "https://source.example.test/item",
            "content_hash": _HASH_A,
            "published_at": NOW.isoformat(),
            "fetched_at": NOW.isoformat(),
            "available_at": NOW.isoformat(),
            "timezone": "UTC",
            "license_scope": "redisplay",
            "entity_ids": ["CN.SH.600519"],
            "excerpt": "bounded evidence",
            "quality_status": "verified_metadata",
            "evidence_kind": "market" if market else "event",
            "version": "ev-v1",
            "source_policy_version": "v1",
            "origin": "fixture",
            "market_payload": payload,
        }
    )
    return AdmittedEvidence(
        evidence=evidence,
        policy=SourcePolicy(
            source_id=evidence.source_id,
            policy_version="v1",
            license_id="license-one",
            terms_ref="terms-one",
            approved_at=NOW,
            expires_at=datetime(2026, 11, 1, tzinfo=UTC),
            redisplay_allowed=True,
            model_use_allowed=True,
            storage_allowed=True,
            allowed_excerpt_length=4000,
        ),
        admitted_at=admitted_at,
    )


def test_registration_retry_ignores_later_admitted_at(
    postgres_context: IsolatedPostgres,
) -> None:
    """An exact retry returns the existing evidence and preserves first admission time."""
    upgrade_head(postgres_context)
    first_time = NOW
    second_time = datetime(2026, 10, 30, 3, 0, tzinfo=UTC)
    first = _registration_admission(market=False, admitted_at=first_time)
    retry = replace(first, admitted_at=second_time)
    database = create_research_database(
        postgres_context.url,
        connect_args={"server_settings": {"search_path": postgres_context.schema}},
    )
    repository = EvidenceRegistrationRepository(database)

    async def register_twice() -> None:
        try:
            assert (
                await repository.register_evidence(admission=first, now=NOW)
                == first.evidence
            )
            assert (
                await repository.register_evidence(admission=retry, now=second_time)
                == first.evidence
            )
        finally:
            await database.dispose()

    asyncio.run(register_twice())

    async def read_saved(connection: AsyncConnection):
        return await connection.execute(
            text("""
            SELECT admitted_at, count(*) OVER () FROM research_evidence
            WHERE source_id = 'retry-event' AND version = 'ev-v1'
        """)
        )

    row = asyncio.run(_run_in_schema(postgres_context, lambda c: read_saved(c))).one()
    assert row[0] == first_time
    assert row[1] == 1


def test_deferred_market_evidence_pair_constraint_and_registration(
    postgres_context: IsolatedPostgres,
) -> None:
    """Both illegal pair directions fail at commit; registry writes valid market atomically."""
    upgrade_head(postgres_context)

    async def seed_policy(connection: AsyncConnection) -> None:
        await connection.execute(
            text("""
            INSERT INTO research_source_policy (
                source_id, policy_version, license_id, terms_ref, approved_at,
                expires_at, redisplay_allowed, model_use_allowed, storage_allowed,
                allowed_excerpt_length
            ) VALUES ('pair-source', 'v1', 'license', 'terms', :now, :expires,
                      true, true, true, 20)
        """),
            {"now": NOW, "expires": datetime(2026, 11, 1, tzinfo=UTC)},
        )

    asyncio.run(_run_in_schema(postgres_context, seed_policy))

    async def insert_evidence(
        connection: AsyncConnection, *, kind: str, eid: UUID
    ) -> None:
        await connection.execute(
            text("""
            INSERT INTO research_evidence (
                evidence_id, source_id, source_url, content_hash, published_at,
                fetched_at, available_at, timezone, license_scope, entity_id, excerpt,
                quality_status, evidence_kind, version, source_policy_version, origin, admitted_at
            ) VALUES (:id, 'pair-source', 'https://source.example.test/item', :hash,
                :now, :now, :now, 'UTC', 'redisplay', 'CN.SH.600519', 'evidence',
                'verified_metadata', :kind, :version, 'v1', 'fixture', :now)
        """),
            {
                "id": eid,
                "hash": _HASH_A if kind == "event" else _HASH_B,
                "now": NOW,
                "kind": kind,
                "version": str(eid),
            },
        )

    market_without_payload = uuid4()
    with pytest.raises(IntegrityError):
        asyncio.run(
            _run_in_schema(
                postgres_context,
                lambda c: insert_evidence(c, kind="market", eid=market_without_payload),
            )
        )

    async def event_with_payload(connection: AsyncConnection) -> None:
        eid = uuid4()
        await insert_evidence(connection, kind="event", eid=eid)
        await connection.execute(
            text("""
            INSERT INTO research_market_payload (
                evidence_id, symbol, observed_at, available_at, fetched_at, timezone,
                currency, adjustment, fields_projection, provider, version, is_mock
            ) VALUES (:id, 'CN.SH.600519', :now, :now, :now, 'UTC', 'CNY', 'none',
                      '[]'::jsonb, 'fixture-provider', 'v1', true)
        """),
            {"id": eid, "now": NOW},
        )

    with pytest.raises(IntegrityError):
        asyncio.run(_run_in_schema(postgres_context, event_with_payload))

    admission = _registration_admission(market=True, admitted_at=NOW)
    database = create_research_database(
        postgres_context.url,
        connect_args={"server_settings": {"search_path": postgres_context.schema}},
    )
    try:
        registered = asyncio.run(
            EvidenceRegistrationRepository(database).register_evidence(
                admission=admission, now=NOW
            )
        )
        assert registered == admission.evidence
    finally:
        asyncio.run(database.dispose())

    async def confirm_valid_pair(connection: AsyncConnection) -> tuple[int, int]:
        evidence_count = (
            await connection.execute(
                text("SELECT count(*) FROM research_evidence WHERE evidence_id = :id"),
                {"id": admission.evidence.evidence_id},
            )
        ).scalar_one()
        payload_count = (
            await connection.execute(
                text(
                    "SELECT count(*) FROM research_market_payload WHERE evidence_id = :id"
                ),
                {"id": admission.evidence.evidence_id},
            )
        ).scalar_one()
        return evidence_count, payload_count

    assert asyncio.run(_run_in_schema(postgres_context, confirm_valid_pair)) == (1, 1)
