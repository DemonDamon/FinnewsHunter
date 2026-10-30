# S02-C：权威研究账本、快照与事务状态机

Planned-with: Manus 2.0
Implemented-with: Manus 2.0
Suggested-Impl-Model: 代码专精中档；幂等、并发、事务、lease/fence 与发布原子性须由强推理 Reviewer 复核
Author: Damon Li
Plan-Id: 2026-10-30-finnews-s02c-ledger
Status: Blocked pending reviewed merge of S02-A and S02-B; do not start implementation early
Parent-Plan: .cursor/plans/pending/2026-10-29-finnewshunter-agent-first-master.plan.md
Parent-S02-Plan: .cursor/plans/2026-10-29-finnews-s02-identity-evidence-run.plan.md
Repo: FinnewsHunter
Input-C1: research-v1.1; digest=591d9cdbfc3dbc639cc0859639e11e910ff86a73fdb34c9697ba63af1534a59e
Input-Port-Freeze: backend/app/research/ports.py, backend/app/research/errors.py, docs/contracts/research-v1.1/ports.md
Required-Merged-Inputs: reviewed S02-A PostgreSQL migration/head and repository adapters; reviewed S02-B `Principal`, authorization, evidence admission/registration behavior; explicit integration base SHA recorded before work begins.

## 1. Goal, dependencies, and non-negotiable boundaries

Implement the one authoritative S02 ledger state machine through the frozen async Ports: idempotent create/reuse, quota and outbox atomic write, authorized read projection, snapshot materialize/freeze/read, dispatcher claim, execution token fence/heartbeat, bounded event sequencing, terminal finish/reap, and immutable Brief publication. C owns ledger behavior only; it does not create HTTP/MCP handlers, Celery task transport, a dispatcher loop, provider, AGX Flow/model call, independent auth, schema or migration.

C must use a new integration worktree, for example `feat/finnews-s02c-ledger`, created only after A+B reviewed heads are merged and their actual SHA/revision are recorded in this file before coding. C must not copy either unmerged worktree. It consumes their public implementations through frozen ports/repositories; it does not amend their schema/auth logic.

### Exact write allowlist

- `backend/app/research/ledger.py`
- `backend/app/research/snapshot.py`
- `backend/tests/research/test_ledger_idempotency.py`
- `backend/tests/research/test_snapshot_freeze.py`
- `backend/tests/research/test_run_transactions.py`
- `docs/operations/research-ledger.md` (C-owned transaction/recovery section only)

Do not modify ports/errors/C1 contracts/manifest, A's db/models/alembic/repositories, B's auth/evidence, config/composition, requirements/locks, legacy models/routes/providers, MCP, Celery dispatch/worker, AGX, or user config/credentials. The parent owner exclusively wires shared config/composition after C review. No Docker, remote source, model, token/key inspection, commit/push/deploy, or synthetic completion claims.

## 2. Verified evidence and root cause

Master §6.6–7.3 requires PostgreSQL—not client/session/queue state—to be the single authority. `(principal_id, request_id)` is idempotent only when the normalized request hash is also identical. Outbox, quota and audit must commit atomically, because retries and Celery delivery are at least once. A queue task only carries `(run_id, dispatch_id, contract_version)` and cannot be trusted as a bearer or fence.

Master requires snapshot members to be fixed before Flow generation and frozen on the first successful Claim. A late/duplicate/expired worker must not publish. A completed run may remain historically completed while revoked license reads redact Brief content. Existing worker availability or quota changes cannot break authorized reads/retries of a pre-existing run.

A supplies actual PostgreSQL row-lock/constraint facilities; B supplies verified Principal and admissible registered Evidence. The frozen Port separately identifies public C1 values and internal secret-bearing `ExecutionToken`/`RunLease`, which must never cross a C1 DTO, event/audit JSON, task payload, log or exception message.

## 3. Required design and exact changes

### FR-C1 — Create/reuse and quota/outbox transaction

In `backend/app/research/ledger.py`, implement `ResearchLedgerPort.create_or_reuse_run(principal, request, now)` exactly as frozen. It validates authorization, C1 request constraints and stable normalized hash over canonical entity, seed evidence, exact as_of, normalized nullable question, schema version and policy version. It rejects a future as_of and any additional/unrecognized material before writing.

Use one PostgreSQL transaction with row/key locking and this exact order:

```text
lock/retrieve principal + request_id
existing different normalized hash -> conflict
existing same hash -> re-authorize safe view; append retry audit; no quota/outbox write
new -> verify registered seed/admission/current license/as_of
    -> query injected executor readiness (not client input/module import)
    -> lock principal quota/concurrency row and enforce budget
    -> insert queued run + exactly one outbox + audit + quota mutation
COMMIT
```

For a uniqueness race, catch the database integrity conflict, rollback the transaction, reread the authoritative row, compare hash, and return the existing safe result or stable conflict. Never expose SQL error text or create a second run. If executor readiness is false/expired, reject a new run as `execution_unavailable` before persistent queued/outbox/quota state. Existing authorized run read/retry must remain available even when readiness is now false or quota is exhausted.

### FR-C2 — Snapshot and read boundaries

In `backend/app/research/snapshot.py` (and delegated ledger methods), implement the frozen `SnapshotPort`: materialize from only registered current run entity/seed/cutoff data where `available_at <= as_of` and current policy permits use; then freeze atomically before the first successful claim. Materialization and freeze require a valid `RunLease`/fence token and fixed `now`; callers cannot supply arbitrary evidence URLs/body/versions.

After frozen, reject append/replacement/re-versioning. `read_snapshot` returns only bounded C1 evidence projections whose members belong to that run, after auth/license policy as required by the Port. A cross-run citation/evidence ID must fail. The S05 Flow uses this immutable snapshot; it cannot query live data or mutate snapshot membership.

### FR-C3 — Claim, fence, heartbeat and terminal transitions

Implement the frozen worker-facing Ports strictly under a locked run row:

- `claim_run`: require matching outbox dispatch, registered live worker/heartbeat and `queued`; issue a cryptographically unpredictable `ExecutionToken`, persist only its secure hash, set running/started/lease/deadline, freeze snapshot boundary, append started event/audit in the same transaction. Duplicate dispatch must not create a second token or execute a second claim.
- `heartbeat_run`: require the matching running run, token hash and unexpired lease/deadline; extend only within run budget; return a renewed internal lease. It must not accept a string from a task/API client as a token.
- `append_step_event`: under the same fence, allocate database sequence (not in-process counter) and write only bounded safe DTO payloads.
- `finish_run`: write safe `failed`, `needs_review`, or `cancelled` terminal state/event/audit atomically; terminal runs never execute again.
- `reap_stale`: lock/recheck queue deadline or lease expiry, revoke token/fence, transition to failed with `worker_lost` or `dispatch_timeout`, and commit state/event/audit together. S04 supplies the loop; C implements only atomic data operation.

### FR-C4 — Model-gated immutable publication and authorized reads

Implement `publish_brief` only for an S05-generated frozen `ApprovedBrief`/model-gate value and valid lease. The ledger rechecks run ID/as_of, frozen snapshot membership, citations, active licenses, one-Brief constraint and terminal race under its transaction. It writes immutable Brief, completed state, completed event and audit together, returning no raw prompt/token/body. Do not use the ledger to claim semantic/numeric correctness; S05 deterministic/model gates own that decision.

`get_run`, `get_evidence`, `search_articles`, `get_market_snapshot` and `read_events` implement the frozen public read Ports. Each takes `Principal` and fixed `now`, performs B authorization and current license revalidation, returns only C1 bounded DTOs, and applies a non-enumerating denial. A revoked completed run remains completed but produces `brief=None, error_code=license_revoked`; no unrestricted `result_ref` fetch. Event query validates Last-Event-ID ownership and returns committed, bounded strictly ordered events only.

## 4. Transaction pseudocode and ownership boundary

```text
S04 dispatcher -> OutboxPort.claim_pending_dispatches/mark_dispatched
S04 worker task(run_id, dispatch_id, contract_version)
  -> ResearchLedgerPort.claim_run(task, worker, now) -> internal RunLease
S05 Flow -> materialize_snapshot / freeze_snapshot / read_snapshot
  -> append_step_event / deterministic+model gate
  -> publish_brief(run_id, lease, approved_brief, now)
S04 supervisor -> reap_stale(now, limit)
S03 public handler -> B verified Principal -> read Port only
```

C never opens a second ORM or bypasses A's async session factory. It owns transaction scopes: the listed state/event/audit/outbox/quota groups are each one database transaction, never a sequence of best-effort commits. B owns identity/evidence admission; S04 owns broker/Celery transport and looping; S05 owns model/claim/numeric evaluation; parent owns configuration/composition.

## 5. Acceptance criteria and exact tests

Every persistence test requires an isolated PostgreSQL `RESEARCH_TEST_DATABASE_URL` marked by A's fixture. SQLite, an in-memory fake, mock row locks and Docker lifecycle commands are prohibited substitutes. Test DSN/resource identifiers must not be logged in artifacts; missing DSN is reported as `database_gate=not_run`, never a success/skip claim.

| AC | Test file and fixture | Required assertion |
|---|---|---|
| AC-C1 | `test_ledger_idempotency.py::test_ten_concurrent_same_principal_requests_write_one_run` | Ten real PostgreSQL async callers with same `(principal, request_id, normalized hash)` produce one run/outbox/quota charge; all obtain authorized same run. |
| AC-C2 | `test_ledger_idempotency.py::test_hash_conflict_and_principal_isolation` | Same principal/request ID with changed as_of/question/seed/policy gives stable conflict; A/B same request ID each create separate runs. |
| AC-C3 | `test_ledger_idempotency.py::test_unavailable_new_run_writes_nothing_and_existing_retry_is_readable` | False/stale executor readiness yields execution_unavailable without queued/outbox/quota; same-hash existing authorized retry still reads during worker-down/quota-exhausted state. |
| AC-C4 | `test_run_transactions.py::test_create_failure_rolls_back_all_ledger_rows` | Inject failure at run/outbox/audit/quota insertion points and assert no partial rows/charges; SQL detail is not returned. |
| AC-C5 | `test_snapshot_freeze.py::test_freeze_rejects_append_replace_and_cross_run_citation` | After freeze, append/reversion fails; an evidence ID from another run cannot be cited/read/published. |
| AC-C6 | `test_snapshot_freeze.py::test_point_in_time_and_license_revocation_projection` | 10:02 availability is absent from 10:00 snapshot and eligible at 10:05 only; revoked completed run retains status but has null Brief/license_revoked. |
| AC-C7 | `test_run_transactions.py::test_dispatch_claim_lease_heartbeat_and_fence` | Same dispatch cannot double claim; wrong/expired/revoked token and expired lease reject heartbeat/event/publish; token representation never leaks to DTO/event/audit/log capture. |
| AC-C8 | `test_run_transactions.py::test_terminal_publish_and_reap_race_is_atomic` | Concurrent stale reaper/late publisher yields exactly one legal terminal state; publication has one immutable Brief/completed event/audit or failure has one failure event/audit. |
| AC-C9 | `test_run_transactions.py::test_event_sequence_and_full_transaction_rollback` | Concurrent events get strictly increasing unique database seq; injected artifact/event/audit failure rolls back all associated state changes. |

Run only after A+B merge using the fixed interpreter:

```bash
PYTHONPATH=backend RESEARCH_TEST_DATABASE_URL="$ISOLATED_TEST_DSN" \
  /Users/damon/Documents/Manus/2026-10-29/tKG7Sl/.work/implementation/FinnewsHunter/.work/implementation/sdk-clean-065/venv/bin/python \
  -m pytest -p no:cacheprovider \
  backend/tests/research/test_ledger_idempotency.py \
  backend/tests/research/test_snapshot_freeze.py \
  backend/tests/research/test_run_transactions.py
```

Then run Ruff with explicit `--line-length 88` on the C-owned Python files. Handoff must record merged A/B SHA, migration revision, actual Postgres command/result counts, transaction/fence reproduction evidence, remaining blocked S03/S04/S05 work, and no secret values.

## 6. Failure, rollback, and completion

Any authorization, policy, token, lease, dispatch, snapshot, quota, executor-readiness or database ambiguity rejects/rolls back safely. Do not requeue or silently extend an old run, weaken current-license checks, return a Brief after revocation, or use a transient worker process as authority. Operational rollback disables new execution via the parent-owned feature switch and safely reaps/retains ledger history; it never drops research tables or deletes audit/evidence.

Complete only when the frozen Port is implemented over A's actual PostgreSQL schema with B identity/evidence integration, all real PostgreSQL ACs are documented, and S03/S04/S05 can consume the ledger without direct ORM access. It does not complete public routes, outbox broker delivery, a worker loop, model approval, source integration, or Near end-to-end operation.
