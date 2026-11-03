# S03-A：统一研究应用服务与请求身份适配

Planned-with: Manus 2.0
Suggested-Impl-Model: 代码专精中档；身份安全分支交由强推理模型复审
Author: Damon Li
Plan-Id: 2026-11-02-finnews-s03a-domain-service
Parent-Plan: .cursor/plans/pending/2026-11-02-finnews-s03-research-surface.plan.md
Status: Pending; activate only after S02-C review/commit.

## 输入契约

唯一领域来源为 `backend/app/research/ports.py:IdentityVerifierPort, AuthorizationPort, ResearchLedgerPort`；DTO 只从 `backend/app/research/contracts.py` 导入。调用者不得自报 Principal、source URL、provider、model 或 scopes。

## Owned files

- 新增 `backend/app/research/service.py`：唯一共享 `ResearchApplicationService`；注入 ledger、authorization policy、UTC clock 和 `execution_enabled`；公开方法仅 `search_articles`, `get_evidence`, `get_market_snapshot`, `start_research`, `get_run`, `read_events`。
- 新增 `backend/app/research/identity_context.py`：bearer解析、安全MCP SDK TokenVerifier adapter及request-local Principal ContextVar middleware；不保存原始JWT，不读环境/文件/网络。
- 新增 `backend/tests/research/test_research_service.py` 与 `test_research_transport_auth.py`。
- 本计划与 `.work/e2e/logs/s03a-handoff.md`。
- 不得改 Port/DTO/ORM/migration、composition、main、HTTP router、MCP server、旧provider或依赖锁。

## 实施要求

`ResearchApplicationService` 方法只映射参数后调用注入的 `ResearchLedgerPort`，不重复授权规则、不直接访问ORM；`start_research` 在 `execution_enabled=False` 时用安全 `DomainError(code="execution_unavailable")` 在任何ledger写入之前拒绝。MCP五种读/写工具共用同一服务实例。Envelope每次从服务端生成request_id与clock as_of上下文；成功=`status=ok,error=null`；可重试基础设施拒绝=`unavailable`；其他安全业务拒绝=`error`；error带固定code/message/retryable，不含异常/凭据。Data为空与status必须符合`ResearchEnvelope` validator。

Bearer parser只接受一个合法 `Authorization: Bearer <opaque>` header，长度上限4096；不从query/cookie/body回退。MCP token adapter 调用`LocalRS256IdentityVerifier.verify_bearer(BearerCredential(...), now=clock())`，并构造SDK `AccessToken`：稳定 client_id/subject=principal UUID，scopes来自验证结果，expires_at为整数Unix秒，claims只含已验证iss/aud/entity_ids；`AccessToken.token`置固定非secret标记，禁止复制原bearer。任何token/JWKS/异常不得进入repr、日志或响应。

`PrincipalContextMiddleware` 每HTTP scope依据SDK认证用户的安全 claims构造不可变 `Principal`，在正常、异常及取消路径以token reset恢复原上下文；未认证、claims类型错误均 fail closed。并发ASGI task和A/B token隔离回归证明ContextVar不串用户。HTTP后续仍直接调用同一identity verifier，通过FastAPI dependency生成Principal，不读取MCP专用全局值。

## AC

1. 搜索/行情/run/evidence/事件服务对ledger调用参数和固定时间完全相同；无额外SQL/网络调用；重复run只由ledger幂等决定。
2. execution_enabled=false时start在fake ledger调用计数为0；true时仅透传冻结StartResearchInput与principal。
3. DomainError各状态映射到合法ResearchEnvelope；status/isError的最后绑定留给S03-C；错误中不出现输入文本、token、JWKS、SQL/堆栈。
4. bearer缺失、多值、畸形scheme、空值、>4096、RS256 invalid、过期、错误issuer/audience、jku/x5u注入均安全拒绝；raw token在日志、AccessToken.token、Context repr和异常中不存在。
5. 用异步并发两个不同principal请求后各自读取request-local Context；中途抛错/取消后context均reset，不发生principal串用。
6. Ruff/format/py_compile/diff-check与S03契约生成检查通过；不修改锁。

## 验证与交接

使用隔离测试clock和fake ledger做领域映射单元测试；身份测试可用临时RS256 key，仅在内存生成，禁止连接外部issuer。交接报告列实际测试数、命令与确切服务签名。实施前将此plan从pending移至`.cursor/plans/`根目录；父owner批准签名后才能启动S03-B/C。