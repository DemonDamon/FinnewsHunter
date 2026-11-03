# S03-D：单一应用装配、默认关闭与跨传输集成验收

Planned-with: Manus 2.0
Suggested-Impl-Model: 强推理代码模型；跨边界状态与生命周期的集成收口
Author: Damon Li
Plan-Id: 2026-11-02-finnews-s03d-app-integration
Parent-Plan: .cursor/plans/pending/2026-11-02-finnews-s03-research-surface.plan.md
Status: Pending; depends on S03-B and S03-C independent review.

## Owned files

- 修改`backend/app/core/config.py`：新增显式、无默认可用值的研究身份/transport安全配置；仅issuer、audience、public JWKS JSON、允许Host/Origin和execution feature flag；绝不增加private key或远端JWKS自动发现。默认research disabled。
- 修改`backend/app/research/composition.py`：只作为research组件composition root创建一次ResearchDatabase/ledger/auth/service/MCP实例；注入HTTP router/MCP ASGI及生命周期；readiness固定四项。
- 修改`backend/app/main.py`：沿用现有`ResearchComponents` hook和AsyncExitStack；只在APP_MODE=research且RESEARCH_ENABLED=true时mount router/MCP；同一服务对象经dependency injection供HTTP/MCP，绝不另起服务器。
- 修改`backend/tests/research/test_research_app_boot.py`；新增`backend/tests/research/test_research_surface_integration.py`。
- 本计划与`.work/e2e/logs/s03d-handoff.md`。
- 不修改C1 Port/DTO/DB、B/C各自路由/工具实现、Celery/worker、legacy服务实现、dependency lock。

## 配置与生命周期

`RESEARCH_IDENTITY_ISSUER`, `RESEARCH_IDENTITY_AUDIENCE`, `RESEARCH_TRUSTED_JWKS_JSON`, `RESEARCH_MCP_ALLOWED_HOSTS`, `RESEARCH_MCP_ALLOWED_ORIGINS`在research enabled时必须明确有效，否则诊断是identity/mcp not ready、请求fail closed；公钥配置解析异常不泄露正文。`RESEARCH_EXECUTION_ENABLED=true`还必须要求research mode、research enabled、DB/ledger和executor readiness全部真实通过；本批S04未完成前不得以fake ready初始化生产组件。

使用app现有生命周期AsyncExitStack进入MCP session manager lifecycle；测试计数证明单实例run/exit各一次，即使MCP子ASGI app不自行驱动lifespan。组件初始化失败时research仍liveness可读但readyz 503；legacy启动路径和Neo4j/Redis/数据库原初始化逻辑完全不动。

## AC

1. `APP_MODE=legacy`默认启动后四条研究HTTP路由及MCP均404；`APP_MODE=research, RESEARCH_ENABLED=false`同样不mount功能surface，固定diagnostics不暴露配置值。
2. `APP_MODE=research, RESEARCH_ENABLED=true`但issuer/JWKS/Host策略/DB缺失时仍不泄漏，identity/mcp/ledger readiness相应false；伪JWT、错误issuer、错误audience拒绝。
3. 注入同一Fake/real `ResearchApplicationService`实例，分别经HTTP run/read和MCP start/get调用后服务mock spy计数表明都调用同一对象；领域结果/授权拒绝一致。
4. 通过TestClient真实进出FastAPI lifespan，MCP manager只启动/关闭一次；原`/health`,`/readyz`,`/`和legacy route compatibility test保持。
5. 新路由精确只有4条，MCP精确只有5工具，主进程和监听端口不变；不启动服务、不需第二个Compose service。
6. 最终在任务专用PostgreSQL跑S02 A/B/C与S03相关集成测试全套；旧API regression和静态门禁全绿；独立审查无未关闭High/Medium。exec_enabled仍false、真实来源/模型/S04 worker未就绪时，不得宣称端到端闭环。

## Out of scope

不配置真实issuer、公网host、reverse proxy、Near连接、不提交部署密钥、不起S04 dispatcher/worker，不调用真实模型或外网Source Provider。所有test-only密钥和组件仅在测试内存；生产ready需由环境显式提供真实public JWKS和HTTPS origin策略。