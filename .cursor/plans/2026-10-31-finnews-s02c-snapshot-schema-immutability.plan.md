# S02-C3: PostgreSQL schema enforcement for frozen snapshot immutability

Planned-with: Manus 2.0
Implemented-with: Manus 2.0
Suggested-Impl-Model: 代码专精中档；独立审查触发器锁语义与并发顺序
Author: Damon Li
Plan-Id: 2026-10-31-finnews-s02c-snapshot-schema-immutability
Parent-Plan: `.cursor/plans/pending/2026-10-29-finnewshunter-agent-first-master.plan.md` §6; `.cursor/plans/2026-10-31-finnews-s02c-snapshot-freeze.plan.md`
Input-Base: `f609412278def39d9b9f40f14f18b6282585d657`; v11 `20261030_research_v11`; C1/C2 remain local integration changes
Status: Review remediation implemented locally; BLOCKED awaiting independent review. Static checks are to be recorded in the dedicated handoff. PostgreSQL tests and joint gates were intentionally not run for this remediation. Changes remain uncommitted/unpushed; does not imply full service or Near end-to-end readiness.

## Review finding and purpose

C2's service tests show frozen membership stays stable through the public service, but do not establish that raw SQL cannot add, rewrite, or delete membership. Master §6 requires snapshot membership to be frozen before the first Claim and remain unchanged across retries; new evidence requires a new run. This narrowly scoped C3 adds PostgreSQL enforcement rather than treating API-only checks as schema immutability.

## Owned files

- `backend/alembic/versions/20261031_snapshot_schema_immutability.py` — one new additive migration after `20261030_research_v11`.
- `backend/tests/research/test_snapshot_schema_immutability.py` — isolated PostgreSQL behavior test only.
- This plan and `/Users/damon/Documents/Manus/2026-10-29/tKG7Sl/.work/e2e/logs/s02c3-handoff.md`.

Do not modify C1/C2-owned code/tests/plans, the original v11 migration, generated contracts, or shared configuration. No commit/push, secret/network/model work, or destructive database action. Use only the stage runner's task-owned schema; never drop/reset a schema. Downgrade must remove only triggers/functions and preserve research data/tables.

## Database invariants

- A membership INSERT obtains `research_run` row lock (`FOR UPDATE`) before checking state. It is allowed only when the parent is exactly `materialized`; `none`, `frozen`, missing, and any unknown state raise SQLSTATE `55000`.
- Membership UPDATE and DELETE obtain the associated run row lock before state check and reject any mutation for frozen runs. A run-id rewrite locks both involved run rows in stable UUID order before checking either parent.
- A `research_run` UPDATE may transition to `frozen` normally; once frozen, it cannot change `snapshot_state` or `snapshot_frozen_at`.
- Trigger lock order remains run row → snapshot-member row, matching C1's claim/freeze transaction. v11 is unchanged.
- Direct SQL tests reject INSERT in `none`, exercise a legal transition to `materialized` and an allowed INSERT, then freeze through the service lifecycle and reject INSERT/UPDATE/DELETE, hash drift, and frozen timestamp rewrite by SQLSTATE, followed by successful read/count. Existing service-level C1/C2 behavior remains unaffected.

## Verification gates


## Implementation outcome (2026-10-31)

## Review remediation (2026-11-02)

The INSERT guard now permits only `snapshot_state='materialized'` and rejects all other states with SQLSTATE `55000`. The direct PostgreSQL regression rejects `none`, inserts only after an explicit `materialized` transition, and freezes through `ResearchSnapshotService`; it retains frozen INSERT/UPDATE/DELETE/hash-drift/state/timestamp rejection assertions. Static-only checks were requested; no PostgreSQL test was run. See `/Users/damon/Documents/Manus/2026-10-29/tKG7Sl/.work/e2e/logs/s02c3-review-fix-handoff.md`. BLOCKED pending independent review; do not mark this workstream complete.
