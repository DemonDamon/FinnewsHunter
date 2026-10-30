# research-v1.1 内部 Port 冻结

- Contract version: `research-v1.1`
- C1 manifest digest: `591d9cdbfc3dbc639cc0859639e11e910ff86a73fdb34c9697ba63af1534a59e`
- Status: S02 接口冻结；本文件不是已实现账本、身份、worker、Flow 或 Near E2E 的声明
- Planned-with: Manus 2.0
- Implemented-with: Manus 2.0
- Author: Damon Li

本文定义 `backend/app/research/ports.py` 与 `errors.py` 的唯一内部契约。它们只声明 Python 值对象和 `Protocol`；导入不创建 SQLAlchemy engine/session、ORM、网络连接、provider、worker、任务、环境变量读取或业务写入。`contracts.py`、schema、fixture 与 manifest 均未修改。

## 1. 全局规则与分层

### 1.1 C1 公开 DTO 与内部对象严格分离

公开 HTTP/MCP 使用既有 C1 DTO：`StartResearchInput`、`GetRunInput`、`GetEvidenceInput`、`GetMarketSnapshotInput`、`SearchArticlesInput`、`EvidenceV1`、`MarketPayloadV1`、`ResearchRunViewV1`、`ResearchBriefV1` 与 `RunEventV1`。本冻结不新增或改写它们。

`Principal`、`BearerCredential`、`SourcePolicy`、`AdmittedEvidence`、`DispatchTask`、`DispatchLease`、`RunLease`、`ExecutionToken`、snapshot 值对象、`ApprovedBrief` 和 `RunFinishRequest` 是内部类型，不可加入 C1 public DTO、MCP envelope、HTTP query/body、audit/event JSON、Celery payload 或日志。

`ExecutionToken` 尤其是 worker fence 秘密：只存在于进程内 `RunLease.token`，其 `repr()`/`str()` 固定脱敏；数据库只能保存 `fingerprint()` 的单向 SHA-256 比较值。绝不能返回或记录原 token、原 bearer、JWT、claims、原始 prompt、受限正文或 SQL 错误。

### 1.2 固定时间与身份来源

所有跨 Port 行为均显式带有 timezone-aware `now: datetime`；测试传固定时钟，生产 composition 注入当前 UTC 时间。`ValueError` 表示实现方构造了 naive 时间、空内部 ID 或不一致值对象，属于编程错误，不能翻译成成功响应。

公开读/创建方法显式带 `Principal`。它仅能由 S02-B 的 `IdentityVerifierPort.verify_bearer()` 在本地可信 JWKS、RS256、issuer/audience、签名、`kid`、`exp` 与必需 `nbf` 全部验证后产生。API 字段、MCP session、Near/Studio admin token 或客户端 `principal_id` 永远不能构造/替代 Principal。

worker 操作不用客户端 Principal：任务只带 `DispatchTask(run_id, dispatch_id, contract_version)`；账本在行锁下从已存 run 恢复 owner。所有 worker 写均显式带同 run 的 `RunLease`，由 secret fence 和 expiry 验证。任何不匹配、过期、撤销、重复或终态写均拒绝。

### 1.3 稳定错误

运行时可预期失败只抛 `DomainError(code, safe_message, retryable)`。稳定 `code` 集合为：

`identity_invalid`、`identity_material_unavailable`、`resource_not_found_or_denied`、`request_conflict`、`evidence_ineligible`、`market_data_unverifiable`、`license_revoked`、`execution_unavailable`、`quota_exceeded`、`invalid_run_state`、`dispatch_mismatch`、`snapshot_frozen`、`lease_expired`、`execution_fenced`、`terminal_state`、`citation_invalid`、`brief_gate_rejected`、`event_cursor_invalid`、`persistence_failed`。

`resource_not_found_or_denied` 是唯一跨主体/不存在资源的非枚举拒绝投影。`DomainError.__str__()` 只输出 code；传输层只能通过 `as_contract_error()` 写 C1 `ContractError`，不可附 stack、token、SQL、URL body 或 provider 原文。

## 2. 不可变内部值对象

| 类型 | 创建者 | 要点 |
|---|---|---|
| `Principal(principal_id, scopes, entity_ids, issuer, audience, expires_at)` | S02-B auth | 只接受经验证的身份；scopes/entity_ids 非空；不可变。 |
| `BearerCredential(_serialized)` | 传输适配器，立即交 S02-B | 仅 `for_verification()` 向 verifier 给出原文；字符串表示脱敏。 |
| `SourcePolicy(source_id, policy_version, license_id, terms_ref, approved_at, expires_at, redisplay_allowed, model_use_allowed, storage_allowed, allowed_excerpt_length)` | 父 owner 由审批记录映射 | 不等于代码 allowlist 或许可本身；B 要求 source/version 对齐、有效期、storage/model-use 等完整。 |
| `AdmittedEvidence(evidence, policy, admitted_at)` | S02-B evidence | 纯准入成功的精确版本绑定；未持久化。 |
| `DispatchTask(run_id, dispatch_id, contract_version)` | S02 ledger/outbox | 固定 Celery 消息内容；不得带 bearer、正文、token 或用户代码。 |
| `DispatchLease(task, dispatcher_id, lease_id, lease_expires_at)` | S02 ledger | S04 ack/release 必须携带，避免其他 dispatcher 确认。 |
| `ExecutionToken(_secret)` | S02 ledger claim | 不可打印秘密；仅 fingerprint 允许持久化。 |
| `RunLease(run_id, token, lease_expires_at, deadline_at)` | S02 ledger claim/heartbeat | worker 所有写都要携带；lease 不得晚于 deadline。 |
| `SnapshotMember(evidence, version, content_hash)` | S02 ledger | 明确钉住 C1 evidence 的版本和 hash。 |
| `SnapshotMaterialization` / `FrozenSnapshot` | S02 snapshot | 前者是选择结果；后者只向 fenced S05 worker 给不可变、有界投影。 |
| `StepEvent(type, payload)` | S05 Flow | 仅 `step_started`、`evidence_added`、`claim_checked`，payload 类型与 type 对齐。 |
| `ApprovedBrief(brief, model_profile_id, policy_version, evaluation_digest, approved_at)` | S05 gate | 表示已通过结构/引用/数值/模型 policy gate；S02 仍会重验 run/snapshot/license。 |
| `RunFinishRequest(status, code, cancellation_reason)` | S04/S05 | 仅 failed/needs_review/cancelled；cancelled 必须有理由。 |

`LedgerReadiness` 不暴露 DSN；`ExecutorReadiness` 必须带 `checked_at/expires_at`，不能把“模块可 import”当 worker 就绪；`WorkerIdentity` 只能标识已注册 worker。

## 3. SQLAlchemy 与持久化边界（S02-A）

```python
ResearchAsyncSessionFactory = async_sessionmaker[AsyncSession]

class ResearchDatabasePort(Protocol):
    @property
    def session_factory(self) -> ResearchAsyncSessionFactory: ...

    async def check_ready(*, now: datetime) -> LedgerReadiness: ...
```

A 在显式研究 context 的 factory 内创建独立 PostgreSQL engine 与这个 factory；module import 和 `session_factory` property 访问不得连接数据库。每个 repository/ledger transaction 只能经该 factory 使用 `async with session.begin()`。

A 拥有独立 research Base、`research_` tables、Alembic target metadata/version table 与迁移。B 永不 import ORM/model/session；C 不创建第二套 Base/factory。共享 config/composition 由父 owner 顺序接线，不能被 A/B/C 并行修改。

`check_ready` 的返回是安全状态，不能暴露 DSN/driver detail。缺 DSN、非 PostgreSQL 或不可用连接为 not-ready；绝不兜底旧数据库、`create_all`、SQLite 或 legacy initializer。

## 4. 身份、授权、准入与登记（S02-B）

```python
class IdentityVerifierPort(Protocol):
    async def verify_bearer(
        *, credential: BearerCredential, now: datetime
    ) -> Principal: ...

class AuthorizationPort(Protocol):
    def authorize_resource(
        *, principal: Principal, owner_id: UUID,
        entity_ids: frozenset[str], required_scope: ResearchScope,
        now: datetime
    ) -> None: ...

class EvidenceAdmissionPort(Protocol):
    def admit_evidence(
        *, evidence: EvidenceV1, policy: SourcePolicy,
        now: datetime
    ) -> AdmittedEvidence: ...

class EvidenceRegistrationPort(Protocol):
    async def register_evidence(
        *, admission: AdmittedEvidence, now: datetime
    ) -> EvidenceV1: ...
```

### 4.1 `verify_bearer`

B 只接受父 owner 映射的本地可信 JWKS 材料，并仅允许 RS256。它验证 issuer、audience、签名、存在且可信的 `kid`、`exp` 与必需 `nbf`，之后才创建 Principal。`alg=none`、HS/算法混用、无签名、未知 kid、过期、未来 nbf、错误 issuer/audience、解析失败或材料不可用均抛 `identity_invalid` 或 `identity_material_unavailable`，fail closed。

外部部署材料只是未来配置形态：目前材料不完整即 `identity_material_unavailable`，不能远程取 key、跟随 token `jku`/`x5u`、跟随 redirect 或新增签发服务。验证方法无数据库事务；不保存 raw JWT/claims。

### 4.2 `authorize_resource`

create 使用 `required_scope="research:create"`，owner 固定为 `principal.principal_id`；run/evidence/event/read 使用 `research:read`，owner 和 entity IDs 从已存资源查询。验证 Principal 未过期、scope、实体范围和 owner；失败一律 `resource_not_found_or_denied`，不区分资源不存在、别的主体、过期 read scope 或无 entity range。该方法无 I/O/事务，不可把搜索 preview 当授权。

### 4.3 `admit_evidence` 与 `register_evidence`

`admit_evidence` 必须是纯逻辑，不 import ORM/SQLAlchemy session/provider/HTTP。它只允许生产 `origin=live`、`quality_status=verified_metadata`、匹配 source/policy version、可信 metadata/时区/available_at、当前许可（非未知/过期）、storage/model-use 允许的 C1 version。市场 evidence 额外要求 payload linkage、`is_mock=false`、currency/unit/adjustment/observed/fetched/available time 完整。fixture、incomplete/rejected、mock、不可核实 market 或没有许可的记录在持久化前抛 `evidence_ineligible` / `market_data_unverifiable`。

成功后 B 把 `AdmittedEvidence` 交给 A 的 `register_evidence`。后者在一个数据库事务内登记 policy/evidence/market 投影，并返回已登记的 `EvidenceV1`。相同业务 key/version/hash 必须幂等，不能把 `available_at` 提早、改 hash/version；新版本另建记录。registry 写失败抛 `persistence_failed` 并完整回滚，B 不自行开 session/补偿写。受限 excerpt/body sentinel 不得进入 DomainError、日志、audit 或 event。

## 5. S04 readiness、outbox 与 dispatcher

```python
class ExecutorRegistryPort(Protocol):
    async def record_heartbeat(
        *, worker: WorkerIdentity, now: datetime
    ) -> ExecutorReadiness: ...

    async def get_readiness(*, now: datetime) -> ExecutorReadiness: ...

class OutboxPort(Protocol):
    async def claim_pending_dispatches(
        *, dispatcher_id: str, now: datetime, lease_duration: timedelta,
        limit: int
    ) -> tuple[DispatchLease, ...]: ...

    async def acknowledge_dispatch(*, lease: DispatchLease, now: datetime) -> None: ...

    async def release_dispatch(
        *, lease: DispatchLease, retry_at: datetime, now: datetime
    ) -> None: ...
```

S04 实现 broker/Celery 和监督循环，S02 提供 PostgreSQL row-lock-backed Port。`get_readiness` 由 create path 内部调用，必须同时考虑执行开关、broker 可达、已注册 worker heartbeat 及 `expires_at`；不能由 API client 传值或以 Python import 替代。新 run 不 ready 时为 `execution_unavailable`，且没有 run/outbox/quota 写；已存在 run 的授权读取/retry 不重做 readiness 或再消费配额。

`claim_pending_dispatches` 只租用 pending durable rows，返回的每个 task payload 恰为 `run_id/dispatch_id/contract_version`。S04 发送 broker 后以同一 `DispatchLease` acknowledge；发送失败才按明确 `retry_at` release，不删除 task。该方法的 DB transaction 只变更 outbox lease/delivery state；它不调用 broker，也不运行 worker。

## 6. S03 公共读取 Port

```python
class ResearchReadPort(Protocol):
    async def search_articles(
        *, principal: Principal, request: SearchArticlesInput,
        now: datetime
    ) -> ArticlesSearchResult: ...

    async def get_run(
        *, principal: Principal, request: GetRunInput,
        now: datetime
    ) -> ResearchRunViewV1: ...

    async def read_evidence(
        *, principal: Principal, request: GetEvidenceInput,
        now: datetime
    ) -> EvidenceV1: ...

    async def get_market_snapshot(
        *, principal: Principal, request: GetMarketSnapshotInput,
        now: datetime
    ) -> MarketPayloadV1 | None: ...

    async def read_events(
        *, principal: Principal, run_id: UUID,
        after_event_id: UUID | None, limit: int, now: datetime
    ) -> RunEventPage: ...
```

S03 HTTP/MCP adapters authenticate each request with B first and only call these methods; they do not query ORM. `search_articles` 只读已登记资料 preview，不 live fetch；`read_evidence` 要求 request 的 evidence 是该 Principal 所有 run 的快照成员；`get_market_snapshot` 只读已登记 market，`None` 由传输层投影为 C1 unavailable 而非 mock fallback。全部重新校验当前许可。

`get_run` 对 completed+license revoked 返回安全 run view：`status="completed"`、`error_code="license_revoked"`、`brief=None`。不得沿 `result_ref` 请求 URL。`read_events` 要验证 Last-Event-ID 属于同一已授权 run，返回已提交且有界、seq 单调递增的 `RunEventPage`；未知/跨 run cursor 为 `event_cursor_invalid` 或非枚举拒绝。

每个 public read 自己是只读 DB transaction（或同等 repeatable safe query）边界；绝不发 provider 请求、修改 snapshot、写 audit 原文或依赖前端授权。

## 7. S05 snapshot、claim/fence 与 publication Port

```python
class SnapshotPort(Protocol):
    async def materialize_snapshot(
        *, run_id: UUID, lease: RunLease, now: datetime
    ) -> SnapshotMaterialization: ...

    async def freeze_snapshot(
        *, run_id: UUID, lease: RunLease, now: datetime
    ) -> FrozenSnapshot: ...

    async def read_snapshot(
        *, run_id: UUID, lease: RunLease, now: datetime
    ) -> FrozenSnapshot: ...

class ResearchLedgerPort(ResearchReadPort, SnapshotPort, Protocol):
    async def create_or_reuse_run(
        *, principal: Principal, request: StartResearchInput,
        now: datetime
    ) -> ResearchRunViewV1: ...

    async def claim_run(
        *, task: DispatchTask, worker: WorkerIdentity,
        now: datetime
    ) -> RunLease | None: ...

    async def heartbeat_run(
        *, run_id: UUID, lease: RunLease, worker: WorkerIdentity,
        now: datetime
    ) -> RunLease: ...

    async def append_step_event(
        *, run_id: UUID, lease: RunLease, event: StepEvent,
        now: datetime
    ) -> RunEventV1: ...

    async def publish_brief(
        *, run_id: UUID, lease: RunLease,
        approved_brief: ApprovedBrief, now: datetime
    ) -> RunTransition: ...

    async def finish_run(
        *, run_id: UUID, lease: RunLease, finish: RunFinishRequest,
        now: datetime
    ) -> RunTransition: ...

    async def reap_stale(
        *, now: datetime, limit: int
    ) -> tuple[ReapedRun, ...]: ...
```

### 7.1 `create_or_reuse_run`

这是一个事务边界。账本先在 `(principal_id, request_id)` 锁/唯一键下定位既有 run，并以固定规范 hash（canonical entity、seed evidence、exact as_of、nullable question、schema、policy version）比较：同 hash 返回已授权 safe view 并写 retry audit，绝不重复 quota/outbox；不同 hash 抛 `request_conflict`。仅新 run 才在同一 transaction 内验证 scope、seed/admission/current license/as_of、S04 readiness、锁 quota/concurrency、写 queued run + one outbox + audit + quota mutation。唯一冲突 race 必须 rollback 后重新读取权威行，不能泄漏 SQL 或生成第二 run。

### 7.2 `claim_run`、`heartbeat_run`、`append_step_event`

`claim_run` 在 run 行锁内验证 dispatch 与 run 对应、registered worker/contract、queued 状态；第一次成功时生成不可猜 execution token、持久化 hash、设 running/lease/deadline、写 started event/audit 并提交。重复同 dispatch 返回 `None`，不得双 claim。任务没有 Principal/bearer/token 输入可替代该验证。

`heartbeat_run` 在一个事务内锁 run，验证 `run_id`、token fingerprint、worker、running 状态、lease/deadline，续租不得超过 total deadline；失败为 `execution_fenced`、`lease_expired`、`terminal_state` 或 `invalid_run_state`。`append_step_event` 做相同 fence 检查，在同一 run 锁内由数据库分配唯一严格递增 `seq`，只写有界 type/payload；不得用进程全局计数。

### 7.3 snapshot

`materialize_snapshot` 只从已登记且对 run entity、as_of、当前许可都合格的 exact evidence version 选择成员；不 live refresh、不接任意 URL、不能通过稍后取得的证据回填早期 as_of。`freeze_snapshot` 在 fenced DB transaction 内钉住 member evidence/version/hash，并拒绝以后追加、替换或重版本。第一次 worker step event/publication 前必须已有 frozen snapshot。`read_snapshot` 只向同一有效 lease 的 Flow 提供有界 C1 投影；S05 ReAct 同步工具仅可读它的内存 snapshot，不持有 async session 或网络。

### 7.4 `publish_brief`、`finish_run`、`reap_stale`

`publish_brief` 仅接收 S05 生成的 `ApprovedBrief`，但账本仍在同一 transaction/row lock 中重验：lease、running、run_id、as_of、frozen snapshot citation、current license、one Brief constraint。通过时原子写 immutable Brief、completed、completed event 与 audit，返回 `RunTransition`；不替代 S05 做数值/事实正确性宣称。并发终态/过期 token 不能写第二 Brief。

`finish_run` 只允许 failed/needs_review/cancelled，连同对应 event/audit 一次提交；completed/failed/cancelled/needs_review 均不再执行。`reap_stale` 由 S04 supervisor 调用，在每行锁下重新检查 queue deadline/lease，撤销 token fence 后原子写 failed + `worker_lost`/`dispatch_timeout` event + audit。S02 不实现循环、Celery 或重跑；迟到 worker 之后 publish 必须失败。

## 8. 实现责任与真实 PostgreSQL验收

| 节点 | 只能实现 | 不能实现 |
|---|---|---|
| S02-A | async factory、research Base/ORM/Alembic、registry/repository | auth、准入规则、ledger/worker/Flow/public route |
| S02-B | RS256 local-JWKS verifier、authorization、纯 evidence admission | ORM/migration、远程 JWKS、issuer、provider、ledger |
| S02-C | ledger/snapshot 事务与所有上述 Port 实现 | 新 Base/auth/worker transport/Flow/public route |
| S03 | HTTP/MCP 传输与 read service | 直查 research ORM、第二套金融逻辑 |
| S04 | broker/Celery/dispatcher supervisor | 第二状态机、token/lease 规则重写 |
| S05 | Flow、确定性 citation/numeric/model gate | 绕过 snapshot 或直接 ORM 发布 |
| 父 owner | config/composition 接线 | 并行让多个 agent 改共享文件 |

迁移、约束、10 并发同键 idempotency、rollback、old-table sentinel、quota/outbox、freeze、claim/lease/fence、event seq、terminal race 都必须使用显式隔离的 PostgreSQL `RESEARCH_TEST_DATABASE_URL`。SQLite/mock lock 不能替代。DSN 缺失记录为 `database_gate=not_run`，不得将 skip 当通过；禁止 `dropdb`、`init_db`、`reset_all_data`、`create_all`、`docker compose down -v`。

基础冻结检查使用：

```bash
PYTHONPATH=backend \
  /Users/damon/Documents/Manus/2026-10-29/tKG7Sl/.work/implementation/FinnewsHunter/.work/implementation/sdk-clean-065/venv/bin/python \
  -m pytest -p no:cacheprovider \
  backend/tests/research/test_research_ports.py \
  backend/tests/research/test_contract_schema.py

/Users/damon/Documents/Manus/2026-10-29/tKG7Sl/.work/implementation/FinnewsHunter/.work/implementation/sdk-clean-065/venv/bin/python \
  -m ruff check --line-length 88 \
  backend/app/research/ports.py \
  backend/app/research/errors.py \
  backend/tests/research/test_research_ports.py
```

以上仅验证接口冻结与 C1 未漂移。它不构成 PostgreSQL、身份材料、许可、Celery、AGX Flow、模型或 Near E2E 已就绪的证据。
