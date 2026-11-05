# S03-D：单一应用装配、默认关闭与跨传输集成验收
Planned-with: Manus 2.0
Suggested-Impl-Model: 强推理代码模型；跨边界状态与生命周期的集成收口
Author: Damon Li
Plan-Id: 2026-11-02-finnews-s03d-app-integration
Parent-Plan: .cursor/plans/2026-11-02-finnews-s03-research-surface.plan.md
Status: Active; baseline HEAD 197d9848be73d78a57011abcb1aefaa9b976540d，S03-A/B/C在基线中。

## 根因与证据
当前 `backend/app/research/composition.py:build_research_components` 是 S01 空 hook（router/MCP/lifespan=None，readiness固定未安装）；`backend/app/main.py` 已有唯一 `app: FastAPI`、研究模式 `AsyncExitStack` lifespan、health/readyz 与条件 mount，但启用分支尚无可用组件。S01 `backend/tests/research/test_research_app_boot.py` 已验证固定未就绪组件可活性启动、legacy/research-disabled surface 不暴露及生命周期hook一次。本地接口已由 S02/S03-A/B/C提供：`LocalRS256IdentityVerifier`、`ResearchDatabase/create_research_database`、`ResearchLedger`、`ResearchApplicationService`、`api.v1.research.router` 的 `get_research_service/get_identity_verifier` 注入点，以及 `create_finnews_mcp_app()` 返回的 `FinnewsMCPApp(app, manager, lifespan, readiness)`。S03-D须将这些既有契约装配起来，而不复制实现。

## 精确范围与所有权
只可改：`backend/app/core/config.py`（`Settings`配置字段/校验）、`backend/app/research/composition.py`（`build_research_components`及仅本文件内私有辅助）、`backend/app/main.py`（ResearchComponents lifespan/mount/dependency overrides）、既有`backend/tests/research/test_research_app_boot.py`。只可新增：`backend/tests/research/test_research_surface_integration.py`、本计划、`.work/e2e/logs/s03d-handoff.md`。禁止改其它文件，包括legacy业务、contracts/Ports/ORM/迁移/worker/AGX与依赖锁；不commit/push。

## 变更意图
1. `Settings`默认 `APP_MODE=legacy`、`RESEARCH_ENABLED=false`、`RESEARCH_EXECUTION_ENABLED=false`；增加无隐式secret/default的 `RESEARCH_DATABASE_URL: str|None`、`RESEARCH_IDENTITY_ISSUER/AUDIENCE: str|None`、`RESEARCH_TRUSTED_JWKS_JSON: str|None`、`RESEARCH_MCP_ALLOWED_HOSTS/ORIGINS: list[str]`。不接受私钥/远端发现，不借用legacy DB默认DSN，不根据空值造host/JWKS。执行开关仅可在 research+enabled 模式打开；S04尚无executor，生产组件无论开关都不得谎报executor ready，生产start请求须由既有ledger安全返回execution unavailable且不得落queued。
2. `build_research_components(settings)`仅在 research且enabled时懒构造组件，不做连接/网络；安全解析本地JWKS JSON，构造唯一verifier/service/ledger/MCP。显式DB缺失/非法时给不可用database adapter/readiness，而非连接或fallback；Issuer/Audience/JWKS缺项对应identity false；allowed hosts/origins缺项对应MCP false且不能构造开放MCP app。readiness保留四个固定名称和safe reason。无真实 executor配置则 executor false。配置可用但DB连接/迁移head未知时仅 readiness probe按现有DB check尝试，异常只报固定reason。legacy与research-disabled完全不构造资源。
3. `main.py` research-enabled时将唯一router include到`/api/v1`，mount MCP ASGI于`/api/v1/mcp`；在同一个service/verifier上设置router dependency overrides。`ResearchComponents.lifespan(app)`通过父FastAPI已有AsyncExitStack enter一次；由composition生命周期组合service资源与MCP `manager.run()`，不假设mounted subapp lifespan自动执行。Research disabled/legacy不挂四路由及MCP；不更改legacy API启动路径、进程/端口。
4. 集成测试使用内存RS256密钥/JWKS、Fake service/ledger；通过FastAPI TestClient和MCP官方SDK transcript验证same app两个transport共用服务及一致的run/evidence/拒绝，不连接PG/网络，不宣称真实PG闭环。原bootstrap test扩展配置缺项、route精确集、依赖覆盖和生命周期exactly once断言。

## 验收标准与测试
- AC1：`test_research_app_boot.py` 用固定env子进程证明legacy默认、research-disabled四HTTP + `/api/v1/mcp`均404，legacy既有 `/api/v1/news*`仍可用；research enabled仍可`/`,`/health`，readyz 503并固定诊断，不泄露配置值。
- AC2：缺DB、issuer、audience、JWKS、Host、Origin分别导致ledger/identity/MCP相关readiness false；畸形JWKS不崩liveness、不外显JSON；认证拒绝闭合；不进行socket/DB连接。execution默认false，execution打开也不能把缺失S04 executor标ready。
- AC3：新增`test_research_surface_integration.py`生成仅测试内存RS256 key/token；提供Fake service记录principal+DTO，运行同一个FastAPI app lifespan，HTTP与MCP initialize/list/call都到达同一Fake对象，固定五工具与四HTTP集合，成功结果及deny/error语义一致，服务对象身份严格相同。
- AC4：通过生命周期计数器验证父app enter/exit各一次；mounted MCP app不自行驱动subapp lifespan；关闭/异常清理正确。
- AC5：既有legacy compatibility、S03-A/B/C及新增测试全通过；使用指定venv python执行ruff check/format --check、py_compile、contract generator `--check`、git diff --check；依赖锁无diff；不称真实PG闭环。

## Gates / rollback
实现前已确认工作树branch `feat/finnews-s03d-app-integration`、HEAD `197d9848be73d78a57011abcb1aefaa9b976540d`。完成按次序先测试再静态gate；任何非允许文件变化立即停止并还原该越界改动；不能通过时回退本计划范围代码至本分支HEAD（不回退其他基线文件），保留handoff记录失败证据，不提交。生产试用还依赖S04真实executor、显式PG迁移、部署方Issuer/Audience/公钥JWKS/可信Host与HTTPS Origin；本地fake测试不等于生产或PG闭环。
