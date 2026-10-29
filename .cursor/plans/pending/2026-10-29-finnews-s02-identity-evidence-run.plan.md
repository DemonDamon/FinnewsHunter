# S02：身份、证据和权威研究账本

Planned-with: Manus 2.0
Suggested-Impl-Model: 代码专精中档；鉴权/SQL并发/许可由独立强推理Reviewer审查
Parent-Plan: .cursor/plans/pending/2026-10-29-finnewshunter-agent-first-master.plan.md
Plan-Id: 2026-10-29-finnews-s02-identity-evidence-run
Status: Blocked before implementation / 等待S01 Linux子门及上游合流；当前不派代码执行
Repo: FinnewsHunter
Base-FNH: 89c50de283d87de07c358b39e8d9e1e1b59eeb55；实施前更新为已审阅上游head
Input-C1: research-v1.1；digest=591d9cdbfc3dbc639cc0859639e11e910ff86a73fdb34c9697ba63af1534a59e
Input-SDK: agenticx[mcp]==0.6.5；官方MCP1.30.0；S00 hash lock
Author: Damon Li

## 1. 启动条件与完成定义

S00已通过本地独立复审。S01代码29项、两批合流60项测试通过，但Linux镜像尚被基础镜像网络阻塞。本计划先落pending，不标Ready，不绕过门禁或把宿主单测当Linux证据。S01整体通过并取得上游可消费基线后，重新登记base/head与artifact hash，才可移动到plans根目录执行。

本节点交付领域内部能力：受验证的金融Principal、Evidence准入/只读投影、独立PostgreSQL研究表、run幂等事务、快照冻结、事件/审计/outbox原子写入和fenced发布Port。不暴露HTTP/MCP，不创建dispatcher/worker或研究Flow，不接真实源/模型，不变更AGX/旧业务/前端。

完成不等于可创建真实queued run：S04未注册真实worker和新鲜心跳前，生产executor readiness仍false，创建必须明确execution_unavailable。已有run的授权查询不受executor下线或额度不足阻断。

## 2. 已核实输入和根因

C1 DTO当前位于 `backend/app/research/contracts.py`，其中结构检查不等于身份/许可/时点/事务检查。旧数据库模块不能成为新研究Base，也不能通过旧create_all或历史News批量回填制造合法Evidence。

S01真实composition接口：

```text
build_research_components(settings) -> ResearchComponents
ResearchComponents(router, mcp_app, lifespan, readiness, worker_modules=())
ResearchReadiness = Callable[[], Awaitable[dict[str, ResearchReadinessCheck]]]
ResearchReadinessCheck(ready: bool, reason: str)
```

当前components没有router/MCP/context/worker，四项check均false。S02只在owner登记后接入独立ledger/identity的lifespan/check；mcp_ready与executor_ready仍false，不提前注册领域端点。

## 3. 所有权和禁止范围

唯一写入白名单：
- 新 `backend/app/research/{auth.py,db.py,models.py,ports.py,evidence.py,ledger.py,errors.py}`。
- `backend/alembic.ini`、`backend/alembic/{env.py,script.py.mako,versions/*research*.py}`，专用研究Base和version table。
- `backend/tests/research/{test_identity.py,test_evidence_admission.py,test_ledger_idempotency.py,test_snapshot_freeze.py,test_run_transactions.py,test_research_migrations.py}` 及明确的临时库fixture文件。
- `docs/contracts/research-v1.1/ports.md`、`docs/operations/research-ledger.md`。
- 共享修改须先登记：`core/config.py`只增金融验证材料/独立研究DSN配置；`research/composition.py`只连接ledger/identity context与check。保留S01命名和cleanup，绝不让其余checks自动变true。

不得改C1现有DTO/manifest/schema（缺字段先回S00评审版本）；不得改requirements/lock（必要直接依赖回S00 owner处理）；不得改旧models/database/News/stock/analysis/graph/Alpha；不调用init_db/reset_all_data、不drop旧表、不更新gitlink，不写真实凭据或用户.env。

两个实现agent不能同时写同一工作树/共享迁移。细分S02-A（DB/迁移），S02-B（auth/准入），S02-C（ledger）时分别使用独立worktree；A/B可依据冻结Port定义并行，C必须在A/B明确合流后实施。若没有已合流源码，只消费冻结契约fixture，不复制活动目录当依赖。父agent负责最后composition接线。

## 4. FR-1：金融身份和统一资源授权

`auth.py`新增不可变Principal：`principal_id: UUID`、scopes与canonical实体范围、issuer/audience、expiry；由已验证token产生，不接受客户端self-reported principal。

首期选择显式部署公钥/可信JWKS签名材料、固定非对称算法白名单（至少RS256；不要同时猜测支持所有算法）。验证issuer、audience、exp、必要nbf、kid。alg=none/HS混用/缺签名/未知kid/过期/材料不可用一律fail closed。不新建身份签发服务，不把Near/Studio admin token当金融token。

公钥材料只从明确服务配置读；不能跟随token header的jku/x5u任意URL。远程JWKS如选用，固定HTTPS地址、timeout/cache寿命、禁止跨域redirect；缓存超过允许陈旧上界时拒绝，不能永久沿用旧key。不得在日志保存JWT或claims原文。

统一 `authorize_resource(principal, owner_id, entity_ids, required_scope)`：create需research:create；所有run/evidence/event读需research:read和实体范围。跨principal/不存在resource使用统一非枚举拒绝；不能因为搜索预览公开就放宽snapshot读取。

AC-1 / test_identity.py：临时测试密钥覆盖合法、错issuer/aud、过期、未来nbf、none/HS、未知kid、材料不可用、client principal注入、缺scope/实体范围；A/B同request_id隔离。测试密钥只在临时目录，不写生产配置。没有真实身份材料时只能验证机制，不宣称远程可用。

## 5. FR-2：独立Base和增量迁移

`db.py`只在研究context显式开启时创建独立async engine与session factory，不导入旧models或用户AGX配置，不在module import连库。URL缺失或材料不完整时check=false；不自动用旧开发数据库密码兜底。

新表为research命名域，至少包括：principal quota/concurrency row、source policy、evidence version、market payload、run、snapshot member、immutable brief、run event、audit、outbox；若内部heartbeat表预留供S04，只定义持久结构，不写fake worker ready。

数据库硬约束：
- run唯一 `(principal_id,request_id)`；source+version去重按经核实的业务键；snapshot成员 `(run_id,evidence_id)` 唯一且固定版本。
- event唯一 `(run_id,seq)` 和event_id；Brief唯一run_id；outbox唯一run_id/dispatch_id。
- status/check枚举受约束；timezone-aware UTC时间；JSONB只存通过bounded DTO的内容，正文权限不放宽。
- execution token不可猜测，持久化用安全hash或同等级防泄露方法；内部返回原token不进入public DTO/日志。

Alembic target_metadata仅研究Base，独立version table；upgrade只增研究对象，不比较/删除旧表。启动不自动create_all。失败迁移返回非零；生产不自动downgrade/drop。只在隔离测试DB验证空库与已有旧表场景。

AC-2 / test_research_migrations.py：真实PostgreSQL upgrade成功；旧表/数据哨兵不变；故意失败revision不会启动应用；module import无engine connect；唯一/check约束实际生效。SQLite不能替代PostgreSQL的行锁/并发gate。

## 6. FR-3：证据登记、许可投影和时点读取

`evidence.py`内部登记只接收已规范的Evidence/Market和来源policy，不暴露到MCP。policy包含license_id/terms_ref/批准时间/expiry/model use/storage/redisplay/allowed_excerpt_length；实际权利需人批准，测试policy不是生产许可。

生产准入要求origin=live、quality=verified_metadata、完整来源/时区/可得时点、当前有效许可及必要权利。fixture/incomplete/rejected隔离且不进入生产快照；market is_mock=true、缺币种/单位/复权/时间则拒绝。不能把历史News发布时间或created_at猜成available_at。

available_at是首次可信取得该版本的时点，不允许后来的查询/重复登记改早。新版本单独登记，已被快照引用的内容/hash/version不覆盖。09:00发布/10:02取得的版本不进10:00快照；新run10:05可用。

读Port只查已登记版本，不live fetch。每次读和最终发布重新验证当前许可；撤销后的completed run保留历史状态，但Brief=null、error_code=license_revoked，只返回安全元数据。不从result_ref跟随任意URL。正文/受限excerpt不进audit/event/error。

AC-3 / test_evidence_admission.py：合法元数据模拟仅在独立测试DB；unknown/过期/无model-use、fixture/incomplete/rejected、is_mock、缺market口径、迟取得证据、不可追溯旧News全部拒绝；重复version不改available_at/hash；受限正文sentinel不出现在日志/投影。测试不把合成样本称为真实数据或许可。

## 7. FR-4：幂等创建和额度事务

`ledger.py:create_run(principal, request)` 使用C1 StartResearchInput。规范化请求hash覆盖实体、seed、as_of、question、schema和pin住的策略版本，拒绝未来as_of/额外字段。空白规范化须明确且稳定，不悄悄改时间或证券。

```text
validate auth/scope/request
BEGIN
  lock principal+request_id key; lookup existing
  existing + different normalized request => conflict
  existing + same request => authorized safe view, audit retry; no quota/outbox
  new => validate seed/admission/current license/as_of
  verify trusted executor readiness, broker/registered heartbeat/deadline inputs
  lock principal quota/concurrency row; enforce budget
  insert one queued run + one outbox + audit; update quota once
COMMIT
```

并发唯一键异常不能泄漏SQL或误返回第二个run；需重新读取并比较hash。已存在run以它的策略pin计算幂等校验，不能因服务器默认策略变化把未改变的请求误判成新消费。当前失去read权限时返回统一拒绝；许可撤销按安全view规则处理。

new run readiness不得仅用模块可导入或客户端参数。S04未完成时生产为execution_unavailable且不写queued/outbox/额度；重试已存在run不受当前readiness或新额度不足影响。

AC-4 / test_ledger_idempotency.py：真实PostgreSQL并发10同键只1run/1outbox/1quota；不同hash冲突；A/B同request_id分别创建；事务注入失败回滚所有对象；已有run在worker下线/额度不足仍可安全读取；新run unavailable不留永久queued。测试readiness注入只在隔离测试，不接生产factory。

## 8. FR-5：快照、事件、fence和原子产物

`ports.py`先冻结内部Async Protocol及安全DomainError，至少包含create/get/read_evidence、materialize/freeze/read_snapshot、claim_run、append_step_event、publish_brief、finish_run、reap_stale。签名显式传Principal/run/token/固定时间，不能省略身份或把客户端字段当token。后续S03/S04/S05共用这些Port，不再复制金融逻辑。

materialize只读current run实体/截止时点/合法证据；freeze在写第一条Claim前事务标记。冻结后任何成员追加/替换/改版本拒绝；需要新资料只开新run/newrequest_id。

claim在行锁中要求queued、dispatch属于run，发execution token/lease，写running+started+audit。同一个dispatch重复不双claim。所有后续写验证running、token、lease未过期和预算，迟到worker无权发布。

publish只接通过确定性gate的Brief，但ledger仍检查run_id/as_of、snapshot/citation/currentlicense等关键不变量；在一个事务写唯一immutable Brief、completed、completed event与audit。数值语义的完整复算属于S05，ledger不能代模型宣称fact正确。

terminal状态completed/failed/cancelled/needs_review不得继续执行。stale收口在行锁内重新检查deadline/lease，撤销token、failed+event+audit同时提交。S04实现监督循环，S02这里只交付原子Port与验证。

事件seq由数据库在run锁内分配，不能用process全局计数。event_id唯一；Last-Event-ID校验与SSE传输留S03，但查询Port返回已提交、有界seq数据。audit只保存ID/安全码/阶段，不能保存raw prompt/token/body/受限证据。

AC-5 / test_snapshot_freeze.py、test_run_transactions.py：freeze后追加拒绝；跨run citation拒绝；相同/过期/撤销token、重复dispatch、并发terminal发布只一份；eventseq严格递增；任何artifact/event/audit失败整体回滚；许可撤销不返回Brief；stale与迟到publish竞争只能一个合法终态。

## 9. 测试环境与交接

实施前填入准确RESEARCH_TEST_DATABASE_URL，必须是专属临时PostgreSQL实例/库，不指向旧服务。测试需强制检测隔离资源标识，缺DSN时database gate=not_run，不skip后声称通过。不得用dropdb/reset脚本或docker compose down -v准备环境。

```bash
PYTHONPATH=backend "$LOCKED_PYTHON" -m pytest -p no:cacheprovider \
  backend/tests/research/test_identity.py \
  backend/tests/research/test_evidence_admission.py
RESEARCH_TEST_DATABASE_URL="$ISOLATED_TEST_DSN" \
  PYTHONPATH=backend "$LOCKED_PYTHON" -m pytest -p no:cacheprovider \
  backend/tests/research/test_ledger_idempotency.py \
  backend/tests/research/test_snapshot_freeze.py \
  backend/tests/research/test_run_transactions.py \
  backend/tests/research/test_research_migrations.py
```

上述测试文件和命令是待实施要求，不是已经通过的证据。正式执行还须联跑S00/S01已有60项与迁移隔离矩阵；独立Reviewer记录实际counts、事务/权限复现和所有未验证项。源码评论/docstrings英语、Author Damon Li；用户文档中文。

S02交付冻结Port定义、迁移head、身份配置契约、数据库约束与并发日志。之后才拆S03/S04并行；S03做公共读服务/MCP与session鉴权，S04做dispatcher/heartbeat/worker。默认执行开关继续关闭，只有真正闭环和批准输入后才逐步启用。
