# S02-C independent-review fixes: freeze-time license validity and materialized-only membership

Planned-with: Manus 2.0
Suggested-Impl-Model: 两个定向代码修复，分别由代码专精中档实施并由不同审查者复核
Author: Damon Li
Plan-Id: 2026-11-02-finnews-s02-review-fixes
Parent-Plan: .cursor/plans/2026-10-30-finnews-s02c-ledger.plan.md
Input-Base: current uncommitted S02-C worktree based on f609412278def39d9b9f40f14f18b6282585d657
Status: Local verified 2026-11-03; full research suite 112 passed; independent closure PASS (High=0, Medium=0); static and C1 contract checks PASS.

## Independent findings

- C2 medium (`snapshot.py:99-123,258-265`): freeze of already-materialized membership emits excerpt without rechecking exact policy `approved_at <= now < expires_at`; read path does check it.
- C3 medium (`20261031_snapshot_schema_immutability.py:29-34`): INSERT trigger rejects only `frozen`, so `none` can accept a membership; only `materialized` may accept inserts.
- C1 independent review: PASS. Combined PostgreSQL testing exposed one integration compatibility point: the C1 direct-market reader must pass request `now` into the C2 shared serializer; test-only direct-member fixtures also need a legal materialized parent state. Limit C1 changes to that call argument and those fixture transitions; do not alter other C1 behavior.

## Ownership and limits

Fix C2 only in `backend/app/research/snapshot.py`, `backend/tests/research/test_snapshot_freeze.py`, and the C2 plan/handoff. Pass explicit `now` to `_member` (or use an equally explicit shared policy-validity helper) and apply the same exact policy validity/window and live/quality checks when serializing a frozen snapshot. Add a real PostgreSQL case materialize before expiry, freeze at/after expiry while the worker lease is still valid, expect safe `license_revoked`, and assert transaction leaves snapshot unfrozen/no content result.

Fix C3 in `backend/alembic/versions/20261031_snapshot_schema_immutability.py`, its PostgreSQL behavior test, and C3 plan/handoff. INSERT trigger permits only parent state `materialized`; `none`, `frozen`, missing or unknown states fail with SQLSTATE `55000`. Test `none` rejection, `materialized` allowance, post-freeze rejection, and retain UPDATE/DELETE/hash-drift tests. C2 service paths must flush the parent transition to `materialized` before inserting members, within the same transaction.

The sole allowed C1 compatibility touch is passing the existing request `now` to the shared snapshot serializer; test-only direct-member fixtures may first move the test run to `materialized`, then freeze. No changes to Port/DTO, other migrations, S03 plans, main/composition/config, dependencies, or user services. No commit/push while a gate fails. Use only task-owned PostgreSQL fixture schemas.

## Required gates

Run C2 and C3 stage tests separately, then full C1/C2/C3 joint real-PostgreSQL runner; run ruff check/format, `py_compile`, contract generator `--check`, `git diff --check`; preserve 23+ current integration tests with added regression count. Obtain new independent read-only review on both finding closures. Until that review passes, do not start S03 implementation and do not mark S02-C complete.

## 2026-11-03 全套门禁收尾

全量research suite在隔离PostgreSQL运行后为110通过、1失败；唯一剩余根因为`db.py:RESEARCH_ALEMBIC_HEAD`仍为旧revision `20261030_research_v11`，而`upgrade head`已到`20261031_snapshot_immutability`。修正该常量，测试使用Alembic ScriptDirectory.get_current_head()独立核对迁移链，加入旧revision必定not-ready回归，不放宽ready判据。

同套件发现并已修正的测试适配纳入范围：`test_research_migrations.py`成员seed先materialized；`test_research_startup_script.py`缺文件负向测试用独立最小项目；`test_research_compose.py`在隔离HOME下使用可用独立Compose CLI，不接触用户Docker配置。Ruff仅排序/格式化新增research测试。禁止更改现有依赖、公开DTO和数据库约束。任务专属数据库的fixture schema只允许由stage runner在测试结束后精确清理本次创建的UUID schema，避免积累撑满临时盘；失败日志保留，禁止清理用户数据库。

验收：全量backend/tests/research使用已恢复的专属资源，实际测试数与结果记日志；Ruff check/format、编译、契约生成、diff-check全部通过；独立复核上述两项安全修复与revision readiness闭环后提交S02，S03由新工作树从该commit启动。
