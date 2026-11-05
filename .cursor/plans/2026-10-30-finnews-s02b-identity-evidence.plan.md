# S02-B：金融身份验证与证据准入

Planned-with: Manus 2.0
Implemented-with: Manus 2.0
Suggested-Impl-Model: 代码专精中档；JWT fail-closed、许可及时点逻辑须由强推理安全 Reviewer 复核
Author: Damon Li
Plan-Id: 2026-10-30-finnews-s02b-identity-evidence
Status: Implemented / S02-B 独立复审完成，待父 owner 整合与API边界门禁
Parent-Plan: .cursor/plans/pending/2026-10-29-finnewshunter-agent-first-master.plan.md
Parent-S02-Plan: .cursor/plans/2026-10-29-finnews-s02-identity-evidence-run.plan.md
Repo: FinnewsHunter
Input-C1: research-v1.1; digest=591d9cdbfc3dbc639cc0859639e11e910ff86a73fdb34c9697ba63af1534a59e
Input-Port-Freeze: backend/app/research/ports.py, backend/app/research/errors.py, and docs/contracts/research-v1.1/ports.md
Database-Handoff: consume only A's frozen `ResearchDatabasePort` / `EvidenceRegistrationPort` adapter. B must not declare SQLAlchemy model/Base/table/migration or create a private ORM.

## 1. Goal, ownership, and non-negotiable boundaries

Implement the verified financial Principal producer and deterministic evidence/market admission logic. The output is an immutable internal `Principal`, admissible evidence bundle, and a call to A's registry Port; it is not a public endpoint, an identity issuer, a provider adapter, a ledger, a snapshot, a worker, or a database schema.

Use a second independent worktree from the same reviewed S01/S02-freeze base, for example `feat/finnews-s02b-identity-evidence`. Do not share A's worktree or create a migration. C begins only from an integration worktree whose A and B changes were reviewed and merged by the parent owner.

### Exact write allowlist

- `backend/app/research/auth.py`
- `backend/app/research/evidence.py`
- `backend/tests/research/test_identity.py`
- `backend/tests/research/test_evidence_admission.py`
- `docs/operations/research-ledger.md` (B-owned identity/evidence operational section only)

The parent integration owner alone maps Settings into B factories in `backend/app/core/config.py` and connects them in `backend/app/research/composition.py`. B must not modify ports/errors/C1 contracts, config, composition, requirements/locks, Alembic, legacy models/News, providers, MCP, HTTP routes, worker/Celery, AGX, or user `.env`/credentials. Do not inspect real JWKS/JWT material, issue a token, call remote JWKS, follow `jku`/`x5u`, call providers/models/network sources, commit/push/deploy, or run Docker.

## 2. Verified evidence and root cause

C1 only validates DTO shape. It deliberately has no trusted requester identity, license decision, reliable available-at provenance, or persistence policy. Master §6.2, §6.8 and S02 FR-1/FR-3 require these decisions before a run can consume evidence. A client-provided `principal_id`, scopes or entity list cannot be trusted. Neither an old `News.created_at` nor published time is an acceptable substitute for evidence `available_at`.

The frozen Port defines `Principal` as a non-public immutable value object; only `auth.py` may construct it after signature/claim validation. It defines a pure `EvidenceAdmissionPort` and an A-provided async `EvidenceRegistrationPort`. This prevents B from inventing a second ORM and lets A/B work in separate worktrees.

## 3. Required design and exact changes

### FR-B1 — Verified Principal, RS256 local trusted material only

In `backend/app/research/auth.py`, implement an `IdentityVerifierPort` adapter and unified `AuthorizationPort.authorize_resource(...)` behavior against the exact frozen types. Its only initial acceptable verification profile is:

- algorithm allowlist exactly `RS256`;
- explicit issuer and audience match;
- signed JWT required; validate `exp`, require/validate `nbf`, and use `kid` only to select a configured trusted local JWKS key;
- public key/JWKS material is supplied by the parent-owned Settings mapping, never read at import and never logged;
- missing material, unknown `kid`, invalid signature, wrong issuer/audience, expired/future-nbf claim, `alg=none`, HMAC algorithm, absent signature, malformed token, or parse failure all fail closed with stable safe `DomainError` codes.

Do not add an issuer, login page, token minting service, token persistence, token cache, remote JWK discovery, or support for token header `jku`/`x5u`. The Port reserves an external-deployment material mode only as unavailable/fail-closed until a separately reviewed implementation supplies a fixed HTTPS endpoint, timeout, redirect prohibition and bounded staleness policy. It must not silently enable remote access.

Build `Principal` only after all checks pass. Never deserialize one from API JSON, query values, session ID, Near/Studio admin token, or a `principal_id` request field. Raw bearer input is represented only by the redacted internal credential type; do not log/repr it or retain original JWT/claims blobs.

`authorize_resource` must require `research:create` for creation and `research:read` for run/evidence/event reads, verify entity scope and owner ID, and return the frozen non-enumerating denial for cross-principal/nonexistent resources. It must not grant a snapshot/evidence read because a search preview was visible.

### FR-B2 — Pure evidence/market admission

In `backend/app/research/evidence.py`, implement a pure `EvidenceAdmissionPort` adapter. It consumes only C1 `EvidenceV1`, frozen `SourcePolicy`, explicit `now`, and the immutable registration input. It has no database imports and no provider/HTTP calls.

A production-admissible record requires all of: `origin=live`; `quality_status=verified_metadata`; approved and unexpired source policy; `storage_allowed`; `model_use_allowed`; source/policy/version match; HTTPS approved-source identity; a complete timezone-aware `published_at`, `fetched_at`, `available_at`; `available_at <= fetched_at`; a nonempty canonical entity list; and a market payload, where applicable, with `is_mock=false`, currency, unit, adjustment, observed/fetched/available time and matching evidence ID. Fixture, incomplete, rejected, mock, unknown/expired/no-model-use/no-storage policy and incomplete market semantics are rejected with a stable DomainError, never normalized into admissible data.

Preserve the supplied earliest trusted `available_at`. Re-registration of the same evidence business key must go through A's registry adapter and produce idempotent same-version behavior; it must never overwrite content hash/version or move `available_at` earlier. A new version is a separate registration. B must not infer availability from legacy News `published_at`/`created_at` or current registration time.

### FR-B3 — Explicit A registry handoff

Provide a small service/factory in `evidence.py` that first calls the pure admission method and then awaits only injected `EvidenceRegistrationPort.register_evidence(admission=..., now=...)`. It must never import `models.py`, open a SQLAlchemy session, or reimplement constraints. The parent owner wires the real A adapter only after the merged integration base exists; B's standalone unit tests use an in-memory Protocol-shaped recorder, not SQLite or a private ORM.

The service must prevent restricted body/excerpt sentinel text from entering DomainError message, audit/event input, logging or public projection. It may return only the registered bounded `EvidenceV1` value prescribed by the Port.

## 4. Before/after intent

Before: a DTO can be structurally valid without a trusted bearer, license, usable available-at value, or database registration path.

After:

```text
Authorization header -> redacted internal credential
  -> local configured JWKS + RS256 signature/issuer/audience/exp/nbf/kid checks
  -> immutable Principal
  -> authorize_resource(principal, stored_owner, entity_ids, required_scope, now)

EvidenceV1 + SourcePolicy -> pure admission decision
  -> injected A EvidenceRegistrationPort transaction
  -> immutable registered version; no legacy News mutation
```

## 5. Acceptance criteria and exact tests

Tests use temporary test key material created only under the test temp directory; no production config/key/JWT is read or written. Do not claim that a remote identity provider is available. All DB-facing evidence tests use a Protocol recorder; full persistence semantics belong to A/C real PostgreSQL suites.

| AC | Test file and fixture | Required assertion |
|---|---|---|
| AC-B1 | `test_identity.py::test_valid_rs256_local_jwks_produces_immutable_principal` | Correct issuer/audience/kid/RS256/exp/nbf yields `Principal`; its representation contains no bearer/raw claim text. |
| AC-B2 | `test_identity.py::test_invalid_identity_inputs_fail_closed` | Wrong issuer/audience, expired, future `nbf`, none/HS, unsigned/malformed, unknown `kid`, unavailable material and client-principal injection yield a safe DomainError; no fallback verifier is used. |
| AC-B3 | `test_identity.py::test_authorize_resource_has_scope_entity_and_owner_isolation` | Same `request_id` does not make principals A/B interchangeable; missing scope/entity range and cross-owner read use non-enumerating denial. |
| AC-B4 | `test_evidence_admission.py::test_live_verified_policy_admits_and_calls_registry_once` | Valid live event and valid non-mock market payload pass pure admission then call injected registry once with unchanged available_at/hash/version. |
| AC-B5 | `test_evidence_admission.py::test_ineligible_evidence_never_calls_registry` | fixture, incomplete/rejected, unknown/expired/no-model-use/no-storage policy, bad timestamps, mock/missing currency/unit/adjustment and non-traceable legacy candidate reject before registry. |
| AC-B6 | `test_evidence_admission.py::test_same_version_never_moves_available_at_or_leaks_excerpt` | Recorder sees preserved initial availability/hash/version; an excerpt sentinel is absent from exception/message/returned safe diagnostic. |
| AC-B7 | `test_evidence_admission.py::test_admission_has_no_orm_or_provider_dependency` | Import and pure admission run without engine/session/provider/network use; static import guard rejects `models`, SQLAlchemy session and HTTP client imports in `evidence.py`. |

Run with the fixed interpreter:

```bash
PYTHONPATH=backend \
  /Users/damon/Documents/Manus/2026-10-29/tKG7Sl/.work/implementation/FinnewsHunter/.work/implementation/sdk-clean-065/venv/bin/python \
  -m pytest -p no:cacheprovider \
  backend/tests/research/test_identity.py \
  backend/tests/research/test_evidence_admission.py
```

Also run Ruff with explicit 88-character width on the exact files. Record command, count, base/head SHA, temporary-fixture-only statement, and any not-run PostgreSQL gate in the handoff without logging material values.

## 6. Failure, rollback, and completion

Any identity material/configuration error is unavailable/denied, not an anonymous or default principal. Any policy/evidence ambiguity rejects registration; no silent time shift, mock fallback, raw-body diagnostics or legacy backfill. A registry failure is propagated as its safe stable DomainError and has no B-side compensating ORM write.

Complete only when B produces trusted immutable Principals solely from local RS256 trusted material, enforces owner/scope/entity authorization, performs pure fail-closed evidence/market admission, and hands registrations exclusively to the frozen A interface with every AC recorded. This is not completion of external identity deployment, source approval, public routes, ledger, worker, or model use.

## 7. 实测记录

- 基线与实施 HEAD：`d4a53f332414bb095ad225f1084319f0e6128892`；未提交。
- 固定 Python 的两个 S02-B 测试模块共 10 项通过（身份4项、证据6项）；覆盖 excerpt 策略/长度、显式冻结 source-host mapping 与攻击 host、market provider/version/时间顺序、JWKS 深冻结及恶意 RS256 key 注入、畸形 authorizer entity_ids、单尾点和 punycode A-label规范化及IDNA 2003碰撞拒绝。
- Ruff check 与 format check（四个 B 文件、88 列）通过；`PYTHONPATH=backend <固定解释器> backend/scripts/generate_research_contracts.py --check` 通过，未改变 C1 工件；四个 B 文件 `py_compile` 通过，`git diff --check` 通过。
- 来源信任映射现在由 `DeterministicEvidenceAdmission(approved_source_hosts=...)` 显式注入；空/缺映射拒绝，嵌套集合于构造时复制冻结。父 owner 需仅从审核后的官方源配置提供映射；本节点未改 composition/config。
- 测试密钥仅在 pytest 临时目录生成；未读取真实 JWT、生产密钥、远端 JWKS、源、模型或数据库。PostgreSQL 集成门禁不属于本节点，未运行。
- host信任策略只接受 ASCII DNS/A-label配置及ASCII host，使用完全相等匹配；不接受Unicode U-label，不执行Python IDNA 2003转换，不做子域/后缀匹配。配置方必须提供经人工审核的官方精确主机名。ASCII `xn--` label只按其DNS字符形状作为精确allowlist标识；本组件不把其视为对IDNA语义有效性的认证。
- 独立复核：旧H1/M1/M2/M3全部关闭；`faß`/`fass`潜在折叠通过ASCII-only拒绝关闭；Principal只能由server verifier/composition产生仍为Low内部边界，需在后续真实API集成门禁中证明请求字段不能构造principal。独立复审报告在任务工作目录 `.work/e2e/logs/rereview-s02b-ascii.md`。
