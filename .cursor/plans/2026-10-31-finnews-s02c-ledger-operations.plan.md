# S02-C1：研究账本事务、幂等与worker fencing

Planned-with: Manus 2.0
Implemented-with: Manus 2.0
Suggested-Impl-Model: 代码专精中档；并发事务/发布与lease边界须强推理审查
Author: Damon Li
Plan-Id: 2026-10-31-finnews-s02c-ledger-operations
Parent-Plan: .cursor/plans/2026-10-30-finnews-s02c-ledger.plan.md
Input-Base: f609412278def39d9b9f40f14f18b6282585d657
Input-A: 721aaaf7d49bf4f55354fd334cf2ec5b6d040c74; Alembic head 20261030_research_v11
Input-B: c635cd29bf654c8a05e7188be92fcd2f1e4187f8; merged locally at f609412278def39d9b9f40f14f18b6282585d657
Status: Local C1 implementation verified 2026-11-02: final four-file isolated PostgreSQL stage passed 23 tests; deterministic unique-key fallback tests cover same-hash reuse, different-hash conflict, fallback reauthorization denial, and existing-run retry while executor is down and quota is full. Independent source review PASS with no High/Medium findings. Ruff/format (88), py_compile, contract generator `--check`, and `git diff --check` passed. Changes remain uncommitted/unpushed; product/API/worker/Near integration remains out of scope for this node.

## Owned files

- `backend/app/research/ledger.py` — sole owner of `ResearchLedger` and run/quota/outbox/audit/event/brief transactions; methods in frozen `ResearchLedgerPort` other than SnapshotPort methods.
- `backend/tests/research/test_ledger_idempotency.py`
- `backend/tests/research/test_run_transactions.py`
- this plan and its handoff only.

Do not modify `snapshot.py`, `test_snapshot_freeze.py`, A/B code, Ports/errors/C1 DTO/manifest, config/composition, routes, Celery, dependencies, or docs. Parent will integrate C2 later.

## Frozen cross-module contract with C2

`ResearchLedger` accepts an injected `ResearchSnapshotService` implementing the frozen `SnapshotPort`. It delegates `materialize_snapshot`, `freeze_snapshot`, `read_snapshot` without opening its own separate transaction. For `claim_run`, the ledger alone owns the locked transaction and calls the C2 transaction-scoped method `_freeze_snapshot_in_transaction(session, run, now=now)` before committing the successful claim. C2 may not begin/commit/rollback its own transaction in that method. If atomic transaction-scoped freezing cannot meet frozen schema/semantics, stop and report rather than weaken the requirement.

Constructor must use explicit `ResearchDatabasePort`, `AuthorizationPort`, `ExecutorRegistryPort`, `ResearchSnapshotService`, bounded policy/config inputs; never read env or connect at import. Test-only key/material uses placeholders, never authenticating network or real credentials.

## Acceptance

Implement every non-Snapshot `ResearchLedgerPort` method on `ResearchLedger`: `create_or_reuse_run`, `search_articles`, `get_run`, `read_evidence`, `get_market_snapshot`, `read_events`, `claim_run`, `heartbeat_run`, `append_step_event`, `publish_brief`, `finish_run`, `reap_stale`. Required rows/events/audit/outbox/quota state listed in Master C §3 and S02-C plan commit/rollback atomically; database is sole counter/authority. Never serialize `ExecutionToken`/`RunLease` into public C1 DTO, event, audit, broker payload, log, or exceptions. Retain only token fingerprint. Existing same-hash requests remain readable when readiness/quota later change; no newly queued row if executor unavailable. Revoke licenses at read/publication time; redact revoked Brief but preserve completed status.

Tests must use real PostgreSQL via `.work/e2e/run_stage_tests.py` and A's `postgres_fixtures.py`, unique schema each test, no SQLite/fakes as proof for row-lock/transaction behavior. Satisfy AC-C1–C4 and AC-C7–C9 from parent plan. Test concurrent same idempotency key (10 callers), unique charge/outbox, hash conflict/principal isolation, readiness fail-before-write, injected rollback, claim duplication/token fencing, heartbeat expiry, event sequence, finish/publish/reaper race and failure atomicity.

Before merge: run exact C tests with fixed interpreter and runner; run Ruff `--line-length 88`, format check, `py_compile`, `git diff --check`, C1 generation check. Report exact test count, SQL sentinel unchanged, no credentials, and unimplemented integration boundaries. Do not commit/push until parent integration review.

## Blocker evidence (2026-10-31)

At initial inspection, C1 targets were absent; this execution created the ledger and two test files. C2 helper signature verified: `async def _freeze_snapshot_in_transaction(self, session: AsyncSession, run: ResearchRun, *, now: datetime) -> FrozenSnapshot`. Ruff (88 columns), Ruff format, py_compile, C1 generator check, and diff-check passed. Stage runner result: 1 failed, 5 passed; acceptance criteria remain incomplete and are not claimed green. See `.work/e2e/logs/s02c1-handoff.md` for limitations and next actions.

## C1 fixture follow-up (2026-11-02)

Corrected only `test_run_transactions.py` fixtures: completed-brief membership is inserted and flushed before freezing; excerpt text and policy cap are supplied at initial seed; denied policy/evidence rows are independently seeded with final immutable values; membership is populated before the shared test run is frozen; and the market-denial case uses market evidence paired to its exact payload. The current combined stage is **16 passed** across `test_ledger_idempotency.py`, `test_run_transactions.py`, `test_snapshot_freeze.py`, and `test_snapshot_schema_immutability.py`. See `.work/e2e/logs/s02c1-handoff.md` for the verified command/result. No ledger implementation, C2 implementation, migration, or C3 test was changed. This stage pass does not claim every broader AC or external SQL sentinel has been independently established.
