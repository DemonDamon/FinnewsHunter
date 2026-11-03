# S02-C2：研究快照的时点物化、冻结与授权读取

Planned-with: Manus 2.0
Implemented-with: Manus 2.0
Suggested-Impl-Model: 代码专精中档；snapshot跨run引用/撤权/冻结时点由独立强推理review
Author: Damon Li
Plan-Id: 2026-10-31-finnews-s02c-snapshot-freeze
Parent-Plan: .cursor/plans/2026-10-30-finnews-s02c-ledger.plan.md
Input-Base: f609412278def39d9b9f40f14f18b6282585d657
Input-A: 721aaaf7d49bf4f55354fd334cf2ec5b6d040c74; Alembic head 20261030_research_v11
Input-B: c635cd29bf654c8a05e7188be92fcd2f1e4187f8; merged locally at f609412278def39d9b9f40f14f18b6282585d657
Status: BLOCKED等待独立review。本轮修复已让freeze/read序列化共同校验`storage_allowed`、`model_use_allowed`、`approved_at <= now < expires_at`及live/verified_metadata，并新增许可在物化后到期的真实PostgreSQL回归；依用户限制未启动PostgreSQL，故该回归及联合门禁尚未执行，不能标记PASS。静态检查结果与未执行项记录在C2专属handoff。Uncommitted/unpushed；no product API/worker/Near end-to-end claim.

## Owned files

- `backend/app/research/snapshot.py` — sole owner of `ResearchSnapshotService`, snapshot selection and serialization.
- `backend/tests/research/test_snapshot_freeze.py`
- this plan and its handoff only.

Do not modify `ledger.py`, other C tests, A/B code, Ports/errors/C1 DTO/manifest, configuration/composition, routes, Celery, dependencies, or docs. Parent integrates C1/C2 after both code reviews.

## Frozen cross-module contract with C1

`ResearchSnapshotService` accepts the injected `ResearchDatabasePort`, `AuthorizationPort`, and current source-policy resolver/data; no module import side effects. It implements all frozen SnapshotPort methods. Public `materialize_snapshot`, `freeze_snapshot`, and `read_snapshot` own their transaction boundary, validate the `RunLease` against the current DB token hash/status/deadline, and use only registered rows. For C1 atomic claim, implement `_freeze_snapshot_in_transaction(session, run, *, now)` as a transaction-scoped helper: it MUST NOT begin/commit/rollback/close the supplied session; it locks/rechecks state and returns frozen membership to caller. Caller C1 owns the outer transaction. Share any function signature in handoff; C1's subplan defines the required call.

## Acceptance

- Select only evidence registered in A's `research_evidence`, for exactly the run's canonical entity and seed evidence, with `available_at <= run.as_of`, live origin/verified policy, current unexpired `storage_allowed` and `model_use_allowed`; never query any provider or old News table.
- Deterministic selection sort by `(available_at, evidence_id)` and enforce C1 per-run bound. Verify only same-run membership and DB composite evidence version/hash identity. Freeze inserts the exact immutable IDs/version/hash in one transaction; no later insert/update/delete/replace/re-version is possible through API or schema. Duplicate materialization/freeze is idempotent only if the exact set/content matches; else stable conflict.
- Read returns bounded DTOs from the stored member set and current license/source policy. For revoked/expired policy fail closed/redact according to frozen Port; do not include cross-run member, arbitrary request URL/body, raw ORM data, token, SQL detail or excerpt outside policy.
- C1's claim transaction calls `_freeze_snapshot_in_transaction` before commit and started event; no separate commit or early worker execution.

## Acceptance tests

Use real PostgreSQL fixture/runner only. Verified in the final joint gate: 10:02 availability excluded at 10:00 and eligible at 10:05, no expansion of an already materialized set after a newly eligible insert, cross-run/out-of-entity member read rejected, altered stored version rejected by composite FK, hash-only member update rejected by C3 trigger, excerpt bounds, duplicate freeze, expiry fail-closed, token/deadline fencing, transaction rollback, `model_use_allowed=false` denial, and direct market payload linkage/mock/malformed behavior. Expiry-based completed-run Brief redaction is covered; the current schema has no mutable policy-revocation field/state, so explicit revocation semantics remain outside this node. Never rely on SQLite/mock for constraints.

Run `python3 <root>/.work/e2e/run_stage_tests.py <integration-tree> --stage s02c2-acceptance --database backend/tests/research/test_snapshot_freeze.py` with isolated task PostgreSQL only; no DATABASE URL logging or schema cleanup. Ruff `--line-length 88`, format, `py_compile`, C1 generator `--check`, `git diff --check` passed. Record exact base SHA, tests and remaining S03/S04/S05 work in handoff. Do not commit/push until parent integration review.
