# S01 研究模式应用生命周期

Author: Damon Li

S01 保留唯一应用入口 `app.main:app`。现有 FastAPI 可以用 `research` 模式启动，而不提前导入旧 API、数据库模型、图谱或采集任务。研究账本、身份授权、MCP 服务、执行器与研究任务尚未接入，因此研究 readiness 必须为 false。

## 配置与默认行为

`APP_MODE` 默认为 `legacy`，只接受 `legacy` 或 `research`。`RESEARCH_ENABLED` 与 `RESEARCH_EXECUTION_ENABLED` 均默认为 false。开启研究功能要求选择 research 模式；开启执行还要求研究功能已开启。未知模式和非法 flag 组合在 Settings 验证时直接拒绝。

`RESEARCH_SOURCE_ALLOWLIST` 默认为空列表，最多接受16个非空、小写安全来源 slug。这里只验证结构，不代表该来源已经获得许可；实际来源政策属于 S03。

## 导入和路由隔离

`app.core` 保留 `settings`、`get_settings`、`get_db`、`init_database` 四个公开导出及原 `__all__` 顺序。PEP 562 延迟加载让 Settings 导入不再触及旧数据库；只有显式访问数据库导出时才加载原 `app.core.database`，没有用假数据库替代原接口。

`app.api.v1.build_api_router(mode)` 在 research 模式返回空路由。只有选择 legacy 装配时才导入原业务模块，保留原十组路由的前缀、标签和顺序。研究模式不暴露旧 debug、LLM、新闻、分析、任务、图谱、股票、Agent 或 Alpha 路由。

## 组件接口与生命周期

`app.research.composition.build_research_components(settings)` 是单一组件工厂，返回以下真实类型：

```python
ResearchComponents(
    router: APIRouter | None,
    mcp_app: ASGIApp | None,
    lifespan: ResearchLifespan | None,
    readiness: ResearchReadiness,
    worker_modules: tuple[str, ...] = (),
)
```

`ResearchLifespan` 是 `Callable[[FastAPI], AbstractAsyncContextManager[None]]`；`ResearchReadiness` 是异步 callable，返回 `dict[str, ResearchReadinessCheck]`。每个 check 有 `ready: bool` 和安全 `reason: str`。

本节点返回空 router/MCP/lifespan/worker modules。四项 readiness 固定为 `ledger_not_installed`、`identity_not_installed`、`mcp_not_installed`、`executor_not_installed`，全部 false。后续模块通过这个工厂接线，不以 flag=true 冒充组件已就绪。

main 在研究模式只构建一次 components，放在 `app.state.research_components`。未来 router 仅在功能开关开启时注册到 `/api/v1`，MCP 固定挂载 `/api/v1/mcp`；当前没有假 MCP 或 run endpoint。

研究 lifespan 用 `AsyncExitStack` 管理组件 context，不执行旧 Neo4j 初始化或清理。退出异常完成必要清理后继续传播，不会被改写成研究完成。测试注入的 context 只证明装配机制，不属于生产组件。

## 健康检查与安全错误

`GET /health` 是进程存活检查，返回200；研究模式额外返回 mode、两项 flag 和四项 readiness check。`GET /readyz` 是运行就绪检查：当前 research 返回503与 `not_ready`，legacy 返回200且不改变原 `/health` 契约。

研究422只返回固定 `invalid_request` 与生成的请求关联ID；研究500只返回固定 `internal_error` 与关联ID。研究错误路径不读取或记录整个请求体，不回传 validation input、异常文本或 traceback。旧处理仍在 legacy 分支，未在本波重构。

## Celery

保留原 Celery 应用名、broker、backend和legacy限额。研究模式的 include 来自同一个组件工厂，当前为空；研究 beat schedule 为空。legacy 仍保留原 crawl include与十项定时配置。

Celery对象存在不代表 worker 就绪。默认空 modules 下，启动脚本在任何 Docker 探测前明确拒绝 `--with-worker`，不以 import error 或空 worker 冒称接线完成。

## 实际验证和剩余边界

2026-10-29，固定 S00 Python 3.12.12 环境下，S01 全量测试为 **29 passed**。其中应用侧15项覆盖真实 TestClient 的 lifespan、context清理、子进程模块隔离、敏感输入日志保护、legacy路由装配、公开导出和Celery分支；另外14项覆盖启动控制流、真实解释器空worker反例与Compose配置。

legacy路由测试使用明确的 router stubs，只证明装配等价，不等于旧业务端到端已通过。Compose只执行config，没有启动原服务。Linux镜像验证仍因镜像源EOF/官方地址超时受阻，不能用本机TestClient替代Linux容器证据。

操作命令和镜像验证步骤见 [研究模式启动说明](research-bootstrap.md)。S02–S05的账本、身份、MCP、可靠worker和真正的AGX研究Flow仍未实现；Near闭环和真实金融研究尚不可用。
