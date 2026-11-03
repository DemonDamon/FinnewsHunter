# S02-A：研究账本 PostgreSQL Base、模型与增量迁移

Planned-with: Manus 2.0
Implemented-with: Manus 2.0
Suggested-Impl-Model: 代码专精中档；SQL 约束、迁移隔离与并发结果须由强推理 Reviewer 复核
Author: Damon Li
Plan-Id: 2026-10-30-finnews-s02a-database
Status: Review fixes implemented / 2026-10-31；review-fix 阶段真实 PostgreSQL 11 passed，等待独立复审；未提交
Parent-Plan: .cursor/plans/pending/2026-10-29-finnewshunter-agent-first-master.plan.md
Parent-S02-Plan: .cursor/plans/2026-10-29-finnews-s02-identity-evidence-run.plan.md
Repo: FinnewsHunter
Input-C1: research-v1.1; digest=591d9cdbfc3dbc639cc0859639e11e910ff86a73fdb34c9697ba63af1534a59e
Input-Port-Freeze: backend/app/research/ports.py and docs/contracts/research-v1.1/ports.md
Execution-Input: use the frozen `ResearchAsyncSessionFactory`, `ResearchDatabasePort`, `EvidenceRegistrationPort`, immutable `SourcePolicy`, and DTOs exactly as defined by the Port freeze.

## 1. Goal, ownership, and non-negotiable boundaries

Implement the independent PostgreSQL persistence foundation for the S02 research namespace: SQLAlchemy async engine/session factory, a research-only declarative Base, ORM schema, Alembic environment/version table, one additive migration, and migration-only fixtures/tests. This is a storage substrate, not a second ledger, auth system, read service, dispatcher, worker, or Flow.

Create an independent worktree from the reviewed S01/S02-freeze base, for example `feat/finnews-s02a-database`. Do not share a worktree, an Alembic revision, or an uncommitted directory with S02-B. C may start only after the reviewed A and B heads are merged to a single integration base.

### Exact write allowlist

- `backend/app/research/db.py`
- `backend/app/research/models.py`
- `backend/app/research/repositories.py` (only persistence adapters for frozen Ports; no ledger policy)
- `backend/alembic.ini`
- `backend/alembic/env.py`
- `backend/alembic/script.py.mako`
- `backend/alembic/versions/<new_revision>_research_v11.py`
- `backend/tests/research/postgres_fixtures.py`
- `backend/tests/research/test_research_migrations.py`
- `docs/operations/research-ledger.md` (A-owned migration/setup section only)

The parent integration owner alone changes `backend/app/core/config.py` and `backend/app/research/composition.py`. Do not modify `contracts.py`, C1 schemas/manifest/fixtures, requirements or locks, legacy database/models, `News`, financial providers, Celery, MCP, AGX, deploy compose, or any user credential file. Do not commit/push/deploy, start Docker, run a provider, inspect secrets, call a model, or use a network source.

## 2. Verified evidence and root cause

S01 has only disabled composition hooks. There is no `ports.py`, research database Base, research model, or Alembic migration. The existing database is legacy-owned, so reusing its Base or `create_all` would silently mix metadata and can autogenerate destructive old-table DDL. Master §6.6–7.3 and S02 FR-2 require an authoritative PostgreSQL ledger with actual unique constraints, row locking and all-or-nothing transactions. SQLite cannot verify these semantics.

The frozen Port module exposes the exact async session-factory type but creates no engine or connection at import time. A must construct `async_sessionmaker[AsyncSession]` only when research context is explicitly enabled by the parent composition root, and expose it through `ResearchDatabasePort`; it must not create a connection merely on import.

## 3. Required design and exact changes

### FR-A1 — Independent async PostgreSQL context

In `backend/app/research/db.py`, implement `create_research_database(...)` (exact argument types from the frozen Port / configuration adapter) and a `ResearchDatabase` adapter implementing `ResearchDatabasePort`. It receives an explicit research DSN and constructs `create_async_engine` plus `async_sessionmaker[AsyncSession]` only in this factory. Module import must not construct an engine, open a session, call legacy initializers, or read environment variables.

A missing DSN, an unsupported non-PostgreSQL URL, or unavailable database check maps to a safe not-ready result for the parent owner; it must never fall back to an old default DB/password. Session transactions use `async with session_factory() as session` and `async with session.begin()`; no global session and no sync ORM session may cross async boundaries.

### FR-A2 — Research-only metadata and additive migration

In `backend/app/research/models.py`, declare a dedicated `ResearchBase(DeclarativeBase)` and only `research_` table names. Define the minimum persistence structures required by frozen Ports and Master §6/7: principal quota/concurrency, source policy, evidence version, market payload, research run, snapshot member, immutable brief, run event, audit, outbox, and the S04-reserved worker/heartbeat state. Store UTC-aware timestamps; database-level enums/checks limit statuses/check types; JSONB fields hold bounded C1 DTO projections only.

Required database constraints include:

- `(principal_id, request_id)` unique for runs;
- source/version business-key deduplication and immutable evidence hash/version behavior;
- `(run_id, evidence_id)` unique snapshot membership with pinned version/hash;
- `(run_id, seq)` and global event ID uniqueness;
- one Brief per run and one outbox `(run_id, dispatch_id)`;
- non-null foreign keys needed to prevent cross-run citation/snapshot links;
- execution token storage as a one-way secure hash only—never a raw token column, DTO, event payload, audit payload, or log field.

In `backend/alembic/env.py`, set `target_metadata` to the research Base only and configure a distinct research Alembic version table. The revision `<new_revision>_research_v11.py` is hand-reviewed additive DDL: no `drop_*`, no old table comparison/deletion, no `create_all`, no production downgrade/drop automation. `backend/alembic.ini` must point only at this research environment; it must not replace legacy migration configuration.

### FR-A3 — Frozen persistence handoff to B and C

In `repositories.py`, provide only adapters implementing the frozen `EvidenceRegistrationPort` and `ResearchDatabasePort` interfaces. The evidence-registration adapter persists a B-created `AdmittedEvidence` and its immutable policy projection in one transaction, returning the registered C1 `EvidenceV1`/internal registration record as prescribed by the Port. It does not validate bearer tokens, derive policy, create runs, charge quota, publish Briefs, or expose public HTTP/MCP methods.

Document the explicit handoff in code comments and `docs/operations/research-ledger.md`: B calls the frozen registry interface; it never imports an ORM model. C receives A's session factory/repository implementations only after merge and owns all ledger transactional state-machine use.

## 4. Before/after transaction intent

Before: importing research code has no database objects, and existing legacy initialization owns unrelated metadata.

After:

```text
parent composition (later, owner only) -> create_research_database(research_dsn)
  -> async_sessionmaker[AsyncSession]
A repository adapter -> session.begin()
  -> INSERT research_source_policy/evidence/market projection
  -> enforce PostgreSQL constraints
  -> COMMIT or complete rollback
```

Alembic upgrade has this scope:

```text
empty isolated PostgreSQL -> upgrade research head -> only research_* + research_alembic_version
existing isolated legacy sentinel table/data -> upgrade research head -> sentinel unchanged; only research_* added
forced failed revision -> non-zero process result; application composition is not started
```

## 5. Acceptance criteria and exact tests

All database tests must require `RESEARCH_TEST_DATABASE_URL` for a dedicated disposable PostgreSQL database whose isolation marker is asserted by `postgres_fixtures.py`. If absent, report `database_gate=not_run`; never skip and claim success. Tests must not use SQLite, `dropdb`, `reset_all_data`, `init_db`, `create_all`, or Docker commands.

| AC | Test file and fixture | Required assertion |
|---|---|---|
| AC-A1 | `test_research_migrations.py::test_module_import_does_not_connect` | Import db/models/repositories with a patched connection path; no engine connect/session/legacy import is triggered. |
| AC-A2 | `test_research_migrations.py::test_upgrade_empty_isolated_postgresql` | `alembic upgrade head` succeeds; exactly research metadata/version table is created; expected unique/check/FK constraints exist. |
| AC-A3 | `test_research_migrations.py::test_upgrade_preserves_legacy_sentinel` | Pre-created non-research sentinel table and row remain byte-for-byte/query-equivalent after upgrade. |
| AC-A4 | `test_research_migrations.py::test_bad_revision_fails_without_application_start` | Injected invalid revision returns non-zero and does not mark research ready. |
| AC-A5 | `test_research_migrations.py::test_constraints_are_enforced_by_postgresql` | Duplicate run/event/snapshot/outbox and invalid status/check insertions fail at PostgreSQL, not only Python validation. |
| AC-A6 | `test_research_migrations.py::test_registration_rolls_back_policy_and_evidence` | A forced second-write failure leaves neither partial policy/evidence/market row nor changed sentinel. |

Use only the fixed interpreter:

```bash
PYTHONPATH=backend RESEARCH_TEST_DATABASE_URL="$ISOLATED_TEST_DSN" \
  /Users/damon/Documents/Manus/2026-10-29/tKG7Sl/.work/implementation/FinnewsHunter/.work/implementation/sdk-clean-065/venv/bin/python \
  -m pytest -p no:cacheprovider backend/tests/research/test_research_migrations.py
```

Record the actual isolated DB resource name, exact command, result count, Alembic revision, base/head SHA, and unverified items in the handoff. Do not put the DSN/password in the plan, code, logs, or commit.

## 6. Failure, rollback, and completion

A migration/import/readiness failure is a hard database gate: return safe not-ready and stop; do not fall back to legacy DB or SQLite. A migration transaction failure rolls back only the failed migration transaction; no automatic downgrade/drop is permitted. Operational rollback means leave research tables intact and let the parent disable research execution, not delete evidence/audit records.

Complete only when the reviewed A head provides a research-only async factory, additive PostgreSQL migration head, and evidence-registration adapter that matches the frozen Port, and every AC above has real PostgreSQL evidence. It is not complete merely because models import, an SQLite test is green, or a migration file exists.

## 7. 实测记录（2026-10-30）

- 基线与当前 HEAD：`d4a53f332414bb095ad225f1084319f0e6128892`；未提交。
- 研究 Alembic head：`20261030_research_v11`。
- 专属 runner：`python3 .../.work/e2e/run_stage_tests.py .../FinnewsHunter-s02a --stage s02a --database backend/tests/research/test_research_migrations.py`，最终 `6 passed`；全部使用 runner 校验的专属 PostgreSQL `finnews_e2e_test`，未使用 SQLite。
- AC-A1 至 AC-A6 已覆盖模块导入无连接、空 schema 增量 upgrade、legacy sentinel 保留、坏 revision fail-closed、实际 PostgreSQL 唯一/检查约束、登记第二写失败的整体回滚。
- 固定解释器 Ruff（88 列）和 `PYTHONPATH=backend .../generate_research_contracts.py --check` 均通过。完整交接与限制见 `.work/e2e/logs/s02a-handoff.md`（父工作目录）。


## 8. 独立审查修复验证（2026-10-31）

- 真实专属 PostgreSQL runner：`python3 .../.work/e2e/run_stage_tests.py <FinnewsHunter-s02a> --stage s02a-review-fix --database backend/tests/research/test_research_migrations.py`：**11 passed**。包括快照复合证据身份错版/错哈希拒绝、`Asia/Shanghai` session 下 `now()` 默认值 instant、不同 `admitted_at` 的成功幂等重试并保留首次值，以及 market/payload 双向非法拒绝与 registry 同事务合法写入。
- 迁移仍仅为 additive：在原研究DDL中新增 Evidence 三列唯一键及 snapshot member 对应复合 FK；替换四个 timezone-sensitive 默认表达式为 `now()`；新增 DEFERRABLE INITIALLY DEFERRED 成对约束触发器/校验函数。没有删除/重建现有数据库对象或表；downgrade 继续拒绝自动清理。
- Ruff check/format（88列）、C1 contract generator `--check`、目标文件 `py_compile` 和 `git diff --check` 全部通过。未改动B/C/config/C1文件，未commit/push。
