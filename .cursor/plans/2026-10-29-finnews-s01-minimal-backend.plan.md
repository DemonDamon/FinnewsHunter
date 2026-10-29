# S01：现有后台的最小研究装配

Planned-with: Manus 2.0
Implemented-with: Manus 2.0
Suggested-Impl-Model: 代码专精中档；生命周期与部署由独立 Reviewer 核查
Parent-Plan: .cursor/plans/pending/2026-10-29-finnewshunter-agent-first-master.plan.md
Plan-Id: 2026-10-29-finnews-s01-minimal-backend
Status: Local code verified / 29 tests passed；Linux image gate blocked；overall未放行，S02不启动
Base-FNH: f236baf0ac2903374e77c43a6115d2817d6f019f
Implementation-Baseline: 89c50de283d87de07c358b39e8d9e1e1b59eeb55；PR在已提交S00上建立
Input-SDK: agenticx[mcp]==0.6.5；MCP 1.30.0；S00 reviewed immutable lock artifact
Input-C1-Digest: 591d9cdbfc3dbc639cc0859639e11e910ff86a73fdb34c9697ba63af1534a59e
Author: Damon Li

> 本节点只让同一个 FastAPI 应用能按研究模式安全启动，并交付后续模块的装配接口。研究身份/账本/MCP/worker 尚未实现时 readiness 必须为 false；不得通过 hardcoded healthy 或 test executor 冒称可研究。不新建生产应用入口、微服务或客户端。

### 2026-10-29 导入根因修订

独立子agent的红测确认 `app.core.__init__:5` 先于 `app.core.config` 执行，无条件导出database导致研究模式触旧模型并因缺psycopg失败。父agent将这一个包初始化文件纳入同一 FR-1 的精确导入隔离修复，不增加数据库业务、依赖或新入口。用延迟公开导出保留 `settings/get_settings/get_db/init_database` 名称；访问Settings不加载DB，显式访问DB公开符号才加载原模块，不删除legacy接口。

## 1. 前置与隔离输入

S00 已实测 31 tests、Ruff、pip check 并通过独立复审。S01 在新 worktree 从同一 origin/main 基线实施；只消费经校验的 S00 精确依赖文件和 manifest artifact，不依赖用户未提交源码、editable SDK 或浮动 branch。

父agent可把四个已审阅输入 artifact（requirements.txt、requirements-dev.txt、requirements-research.lock、C1 manifest）物化到测试/build context；S01不得修改其内容。它们的hash在任务 `.work/implementation/s00-handoff/artifact-hashes.json`。后续汇总先合 S00 再合 S01，真正远端合流仍按用户授权执行。

测试可用S00固定环境 Python，但不向其中安装/卸载新包；每个测试使用S01 cwd/PYTHONPATH隔离。Docker build只创建任务标签image；smoke container使用 `--rm --network none`，不挂现有用户数据，不开启Compose up或任何真实采集。未确认模型元数据前不commit/push/merge。

## 2. 根因与白名单

现 `backend/app/main.py:13–15` 在 import 阶段导入 core.database 和全路由聚合；聚合 `api/v1/__init__.py:5–8` 又导入分析、任务、图谱、Alpha。lifespan `main.py:69–106`每次尝试图谱。`celery_app.py:13`只include旧crawl tasks且 `:41–102`总注册beat。`start.sh:18–29`全量up、固定sleep、旧建表失败后继续。compose worker又依赖Neo4j。无图/向量的最小研究模式目前无法保证。

唯一代码白名单：
- `backend/app/core/config.py:Settings`：研究mode/flags及其校验。
- `backend/app/core/__init__.py`：只把原公开导出改为延迟加载，防止仅导入Settings就触旧DB；名称/显式DB访问行为保持。
- `backend/app/api/v1/__init__.py:api_router`：条件装配，legacy分支保留原路由名/前缀/tags。
- `backend/app/main.py`：精确 imports、lifespan、研究hooks装配、health/readiness、研究错误安全分支；不移动整个模块/大量格式化。
- `backend/app/core/celery_app.py`：研究include/beat分支，保留legacy配置。
- 新 `backend/app/research/composition.py` 与必要的空package init；不改S00 contracts。
- `backend/start.sh`、新 `deploy/docker-compose.research.yml`；尽量不改原compose，原默认行为保留。
- `deploy/Dockerfile.celery`、`deploy/celery-entrypoint.sh`：精确可选择锁定模式，legacy默认不变，不新生产service。
- 新tests `backend/tests/research/test_research_app_boot.py`、`test_legacy_route_compatibility.py`、`test_research_dependency_isolation.py`、`test_research_startup_script.py`、`test_research_compose.py`；必要test/package init。
- `docs/operations/research-bootstrap.md` 与S01 plan状态，日志写任务 `.work/implementation/logs/s01-*`。

禁止改：requirements/lock/DTO/schema、原News/stock/analysis/vector/graph/Alpha模块、供应商credentials、用户.env/数据库/全局设置、AGX源码/gitlink；不得重构正确的legacy业务逻辑。

## 3. FR-1：配置与legacy兼容

Settings新增：
- `APP_MODE: Literal["legacy","research"] = "legacy"`
- `RESEARCH_ENABLED: bool = False`
- `RESEARCH_EXECUTION_ENABLED: bool = False`
- `RESEARCH_SOURCE_ALLOWLIST: list[str] = []`，最多16个非空安全来源slug，来源是否合法仍由S03政策决定。

配置校验：execution_enabled要求mode=research且research_enabled=true；research_enabled要求mode=research。不接受未知APP_MODE，不把拼写错误静默变成legacy。默认不改原LLM默认值或数据连接配置。源码新注释/文档字符串英语、absolute imports、Author Damon Li。

api/v1聚合将旧 imports 与include放入 `build_api_router(mode)` 的legacy分支；export的 `api_router` 仍按settings选择，兼容旧 main import。research分支先返回空router，后续research router由FR-2组件装配，不能重注册同路由。

移除main中未使用的 `init_database` eager import；不再使research模式导入旧model engine。legacy路由会按原样导入其数据库依赖，行为不变。main import采用absolute paths，仅改所需行；不删除无关应用配置、middleware、Docs或原异常处理。

AC-1（test_legacy_route_compatibility / test_research_dependency_isolation）：
1. 用stub routers冻结原10个include的prefix/tags/order，比较legacy建router结果与原聚合意图；该单测只能证明装配保持，不冒称旧业务端到端通过。
2. 独立subprocess启动research app，sys.modules不得出现app.api.v1.analysis/tasks/news/news_v2/stocks/agents/debug/knowledge_graph/alpha_mining、旧app.models、vector/graph或crawl任务；无网络。
3. 默认APP_MODE为legacy且两flag关闭；非法组合在Settings验证阶段明确拒绝。

## 4. FR-2：单app composition hooks与真实未就绪

新增composition.py，小而可类型检查：

```text
ResearchComponents:
  router: APIRouter | None
  mcp_app: ASGI app | None
  lifespan: callable(FastAPI)->AsyncContextManager | None
  readiness: async callable()->named boolean checks
  worker_modules: tuple[str,...]（默认空，未来S04只登记固定内部module）

build_research_components(settings) -> disabled/uninstalled components
```

本节点默认checks为ledger_ready=false、identity_ready=false、mcp_ready=false、executor_ready=false，reason稳定，不包含host密码/exception/prompt。不能用RESEARCH_ENABLED=true把这些checks自动设true。后续S02/S03/S04通过单一factory与既有lifespan hook组合；不使用任意用户URL或客户端模块名作动态import。

main在research模式构造一次components并放app.state；如router存在且feature开启，注册到现有API前缀；如mcp_app存在，装配固定/api/v1/mcp（首期None所以不挂stub endpoint）。lifespan用AsyncExitStack合成组件context，安全收尾且不启动legacy Neo4j。S02–S04尚未接入时没有后台task、数据库connect或mock research。

`/health`仍是进程liveness 200；research模式额外输出mode、research readiness/disabled等安全字段。新增operational `/readyz`（不是第五条研究领域API）：research未就绪为503，且返回named checks/safe reasons；legacy可按原健康意图返回200。不把暂无modules冒称就绪。

AC-2（test_research_app_boot）：
- 在ASGI TestClient完成真实lifespan enter/exit；/与/health可访问，/readyz为503；research-enabled false/true都不伪造就绪。
- /api/v1旧debug/llm/news/alpha均404；/api/v1/mcp此时404而非mock成功；没有生产run API假结果。
- 用注入的测试components证明router/context可组合和顺序起停（这些仅test fixture，不公开为ready）。不得把模拟身份/ledger当生产组件。
- 组件context退出/异常不会遗漏cleanup；不能阻断liveness或丢弃异常当完成。

## 5. FR-3：研究请求错误不泄漏

原main validation handler会读取和logger.error打印整个body。对于research模式增加最前面的安全分支：不读取/返回/记录body，不打印exc.errors的input或任意stack；422返回固定安全错误 `invalid_request` 及安全request关联，500为 `internal_error`。legacy原处理块不更改。

如需validation细分，只返回固定类型码，不回传input字段或可能含secret的dict key；这是后续auth/provider接线前的必要保护，不改变合法成功响应。测试以sentinel-secret body/error触发422/500，caplog与response均不存在sentinel/stack。原Docs/CORS不在本波修改。

AC-3：test_research_app_boot中的敏感输入和unhandled异常case通过；legacy测试只验证原handler仍选择原分支，不测真实含secret的生产请求。

## 6. FR-4：Celery分支与非强制研究worker

celery_app继续原name/broker/backend。research时include使用components.worker_modules（本节点为空），beat_schedule为空；legacy时include仍只有app.tasks.crawl_tasks、原10项beat和原limits保留。不添加研究task、不改全局acks_late/worker lost。

S01可提供 `--with-worker`启动选项供以后S04使用，但当前modules未装载时必须明示不可用，不拉起无task却冒充ready的worker。readiness不通过Celery对象存在而变true。

AC-4（test_research_dependency_isolation）：subprocess import研究celery_app并检查include/beat空、没有旧crawl/Redis ping；legacy通过配置快照检查10项beat不变（不实际运行beat或crawl）。

## 7. FR-5：启动脚本和Compose复用

start.sh增加 `--mode legacy|research`（默认legacy）、`--check`（只检查配置，不up/迁移/启动）、`--no-services`（研究app纯启动诊断）、可选 `--with-worker`（仅组件已登记时）。CLI解析错误非零；未知flag不忽略。

legacy保持原既有服务集合/uvicorn app.main入口，不趁机删除data；用 `docker compose`优先、可兼容docker-compose，显式health等待代替sleep10。旧初始化的兼容处理不得用于研究迁移。

research使用两个compose文件、目标仅postgres/redis（worker仅明确选用）。迁移只有RESEARCH_ENABLED=true且Alembic文件实际存在时执行，缺文件提前非零退出；运行失败不能吞错。研究未启用可纯启动诊断且not_ready，不跑旧init_db或create_all。`--check`只compose config，不发送环境secret，不connect真实库。

新增compose.research override：
- 原vector/etcd/minio/Neo4j/beat置为显式optional profile；默认override `up`不带起它们。
- worker指定research队列，APP_MODE=research，两flag默认false；移除对Neo4j的硬depends_on。
- 研究overlay不自动读取用户.env；需要 `env_file: !reset []` 或经当前Compose支持的等效精确删除。depends_on用 `!override`覆盖为postgres/redis，确保不存在merge残留。
- 沿用同一个postgres/redis/worker service，不增加新MCP/appservice，不删volumes，不全局更改原compose。
- 文档记录所需Compose最低版本（tags实际支持）；通过当前本机2.39.2 config确认，不能假定PyYAML认识custom tags。

AC-5（startup_script/compose）：
1. `bash -n`、help、非法mode/flag明确。
2. PATH内fake Docker/uvicorn/python脚本记录--check无up/迁移/uvicorn；迁移失败非零且无后续uvicorn；research不存在init_db调用。
3. 真实 `docker compose ... config --format json`解析，研究服务默认集合只postgres/redis，worker/beat/graph/vector为optional；worker无Neo4jdepends。无原用户.env依赖。
4. 绝不在本节点真实Compose up/down -v或碰现有container。

## 8. FR-6：锁定镜像与Linux临时验证

精确调整同一个Dockerfile.celery：default legacy仍可用原依赖策略；research通过build args选择python:3.12和S00完整hash lock，安装失败不fallback浮动requirements。lock复制到不会被/app volume遮盖的/opt/finnews-deps。entrypoint APP_MODE=research执行pip check后直接exec，不启动时pip重新安装浮动requirements。legacy原entrypoint分支保留。

S00 lock包括dev依赖，当前生成镜像仅用于兼容和冒烟验证，不宣称已是最小/安全加固的正式生产镜像；S07最终发行需要经过运行时依赖与镜像安全review。S01不得悄悄重编不同平台lock，若mac-target lock在Linux不兼容，记录error并退回S00owner处理，而不是去hash/浮动安装绕过。

镜像标签仅 `finnews-s01-verify:20261029`。build上下文排除.node_modules/.git/.env/.work；若新`.dockerignore`必要，白名单仅排除敏感/中间产物，不改产品代码。smoke用`docker run --rm --network none --entrypoint python`，只挂S01测试app源码read-only，APP_MODE=research、flagsfalse、PYTHONDONTWRITEBYTECODE=1；不挂用户env/data，不传真实key。通过TestClient或短生命周期Uvicorn证明启动/health/readyz/oldroutes行为；运行结束容器删除，不启动长期服务。

AC-6：真实Linux arm64 Python3.12安装pip check、AGX Flow/ReAct或同一锁定版最小实际调用、研究app lifespans/health/404/503检查通过。日志保存实际image id、命令、结果与未验证项；不能把compose config通过当镜像已验证。Docker无法完成则标partial/blocked，不宣称Linux通过。

## 9. 审查和下一批交接

写docs/operations/research-bootstrap.md：本批已实现/未实现、准确启动/--check命令、not_ready原因、flags默认、实际Docker/test证据、不触原data的测试/回滚；先合S00产物再集成S01代码，维持同一app入口。

独立Reviewer只读审查imports/legacy路由/上下文cleanup/安全错误/profile/锁定entrypoint及真实日志，按具体path:line给finding。失败先修复复验，不扩张S02。

S02接收composition hook形态、真实C1 DTO/manifest、S01装配后的模式和健康契约。S01完成并不意味着数据库/identity/MCP已存在，不允许打开research create开关冒充ready。
