"""FinnewsHunter application entry point.

Author: Damon Li
"""
import logging
import uuid
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import (
    get_redoc_html,
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
)
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.v1 import api_router
from app.core.config import settings
from app.research.composition import (
    RESEARCH_READINESS_NAMES,
    ResearchComponents,
    ResearchReadinessCheck,
    build_research_components,
)

# 配置日志
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

_SAFE_RESEARCH_REASONS = frozenset(
    {
        "component_not_ready",
        "executor_not_installed",
        "identity_not_installed",
        "ledger_not_installed",
        "mcp_not_installed",
        "readiness_unavailable",
    }
)


async def _research_readiness_payload(application: FastAPI) -> dict[str, dict[str, object]]:
    """Return fixed-name research checks without exposing component exceptions."""
    components: ResearchComponents | None = getattr(
        application.state, "research_components", None
    )
    if components is None:
        return {
            name: {"ready": False, "reason": "component_not_ready"}
            for name in RESEARCH_READINESS_NAMES
        }

    try:
        reported = await components.readiness()
    except Exception:  # noqa: BLE001
        # Extension failures must not leak through a public readiness response.
        return {
            name: {"ready": False, "reason": "readiness_unavailable"}
            for name in RESEARCH_READINESS_NAMES
        }

    checks: dict[str, dict[str, object]] = {}
    for name in RESEARCH_READINESS_NAMES:
        check = reported.get(name)
        if not isinstance(check, ResearchReadinessCheck):
            checks[name] = {"ready": False, "reason": "component_not_ready"}
            continue

        reason = (
            check.reason
            if check.reason in _SAFE_RESEARCH_REASONS
            else "component_not_ready"
        )
        checks[name] = {"ready": bool(check.ready), "reason": reason}
    return checks


def _research_is_ready(checks: dict[str, dict[str, object]]) -> bool:
    """Require every fixed readiness check before reporting research as ready."""
    return all(check["ready"] is True for check in checks.values())


def _research_internal_error_response() -> JSONResponse:
    """Create a correlation-only research failure response without exception data."""
    request_id = uuid.uuid4().hex
    logger.error("Research request failed request_id=%s", request_id)
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "request_id": request_id},
    )


class DocsCSPMiddleware(BaseHTTPMiddleware):
    """为文档页面设置 CSP 头，允许 unsafe-eval（Swagger UI 需要）"""
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
        except Exception:
            if settings.APP_MODE == "research":
                return _research_internal_error_response()
            raise

        # 只为文档页面设置 CSP
        if request.url.path in ["/docs", "/redoc", "/openapi.json"]:
            # 开发环境：完全禁用 CSP 限制（仅用于文档页面）
            # 生产环境应该使用更严格的策略
            if settings.DEBUG:
                # 开发环境：允许所有内容（Swagger UI 需要）
                response.headers["Content-Security-Policy"] = (
                    "default-src * 'unsafe-inline' 'unsafe-eval' data: blob:; "
                    "script-src * 'unsafe-inline' 'unsafe-eval'; "
                    "style-src * 'unsafe-inline'; "
                    "img-src * data: blob:; "
                    "font-src * data:; "
                    "connect-src *; "
                    "frame-src *; "
                    "object-src *; "
                    "media-src *; "
                    "worker-src * blob:; "
                    "manifest-src *; "
                    "form-action *; "
                    "base-uri *; "
                    "frame-ancestors *;"
                )
            else:
                # 生产环境：使用较宽松但仍有限制的策略
                response.headers["Content-Security-Policy"] = (
                    "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob: https:; "
                    "script-src 'self' 'unsafe-eval' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com; "
                    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com https://unpkg.com; "
                    "font-src 'self' data: https://fonts.gstatic.com https://cdn.jsdelivr.net; "
                    "img-src 'self' data: blob: https:; "
                    "connect-src 'self' https:; "
                    "frame-src 'self' https:; "
                    "object-src 'none'; "
                    "base-uri 'self'; "
                    "form-action 'self'"
                )
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    if settings.APP_MODE == "research":
        logger.info("=== FinnewsHunter Research Mode Starting ===")
        components: ResearchComponents = app.state.research_components
        try:
            async with AsyncExitStack() as exit_stack:
                if components.lifespan is not None:
                    await exit_stack.enter_async_context(components.lifespan(app))
                yield
        finally:
            logger.info("=== FinnewsHunter Research Mode Shutting Down ===")
        return

    # 启动时执行
    logger.info("=== FinnewsHunter Starting ===")
    logger.info(f"Environment: {'Development' if settings.DEBUG else 'Production'}")
    logger.info(f"LLM Provider: {settings.LLM_PROVIDER}/{settings.LLM_MODEL}")
    
    # 初始化 Neo4j 知识图谱（仅创建约束和索引，不构建具体图谱）
    try:
        from app.core.neo4j_client import get_neo4j_client
        from app.knowledge.graph_service import get_graph_service
        
        logger.info("🔍 初始化 Neo4j 知识图谱...")
        neo4j_client = get_neo4j_client()
        
        if neo4j_client.health_check():
            logger.info("✅ Neo4j 连接正常")
            # 初始化约束和索引（由 graph_service 自动完成）
            graph_service = get_graph_service()
            logger.info("✅ Neo4j 约束和索引已就绪")
            logger.info("💡 提示: 首次定向爬取时会自动为股票构建知识图谱")
        else:
            logger.warning("⚠️ Neo4j 连接失败，知识图谱功能将不可用（不影响其他功能）")
    except Exception as e:
        logger.warning(f"⚠️ Neo4j 初始化失败: {e}，知识图谱功能将不可用（不影响其他功能）")
    
    yield
    
    # 关闭时执行
    logger.info("=== FinnewsHunter Shutting Down ===")
    
    # 关闭 Neo4j 连接
    try:
        from app.core.neo4j_client import close_neo4j_client
        close_neo4j_client()
        logger.info("✅ Neo4j 连接已关闭")
    except:
        pass


# 创建 FastAPI 应用
# 禁用默认文档（我们将使用自定义 CDN）
app = FastAPI(
    title=settings.APP_NAME,
    description="Financial News Analysis Platform powered by AgenticX",
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan,
    docs_url=None,  # 禁用默认文档，使用自定义路由
    redoc_url=None,  # 禁用默认 ReDoc，使用自定义路由
)

research_components: ResearchComponents | None = None
if settings.APP_MODE == "research":
    research_components = build_research_components(settings)
app.state.research_components = research_components

# 添加文档页面的 CSP 中间件（必须在 CORS 之前）
app.add_middleware(DocsCSPMiddleware)

# 配置 CORS
# 开发环境允许所有来源（包括 file:// 协议）
if settings.DEBUG:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 开发环境允许所有来源
        allow_credentials=False,  # 允许所有来源时必须为 False
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    # 生产环境只允许配置的来源
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# 请求验证错误处理（422错误）
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """处理请求验证错误（422）"""
    if settings.APP_MODE == "research":
        request_id = uuid.uuid4().hex
        logger.warning("Research request rejected request_id=%s", request_id)
        return JSONResponse(
            status_code=422,
            content={"error": "invalid_request", "request_id": request_id},
        )

    # 尝试读取请求体
    body_str = ""
    try:
        body_bytes = await request.body()
        body_str = body_bytes.decode('utf-8')
    except Exception as e:
        logger.warning(f"Failed to read request body: {e}")
    
    logger.error(f"Validation error for {request.method} {request.url.path}")
    logger.error(f"Validation errors: {exc.errors()}")
    logger.error(f"Request body: {body_str}")
    
    return JSONResponse(
        status_code=422,
        content={
            "detail": exc.errors(),
            "body": body_str if settings.DEBUG else None
        }
    )


# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    if settings.APP_MODE == "research":
        return _research_internal_error_response()

    logger.error(f"Global exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Internal server error",
            "detail": str(exc) if settings.DEBUG else None
        }
    )


# 根路由
@app.get("/")
async def root():
    """根路由 - 系统信息"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "active",
        "message": "Welcome to FinnewsHunter API",
        "docs_url": "/docs",
        "api_prefix": settings.API_V1_PREFIX,
    }


# 健康检查
@app.get("/health")
async def health_check():
    """健康检查端点"""
    response = {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }
    if settings.APP_MODE == "research":
        checks = await _research_readiness_payload(app)
        response["mode"] = "research"
        response["research"] = {
            "enabled": settings.RESEARCH_ENABLED,
            "execution_enabled": settings.RESEARCH_EXECUTION_ENABLED,
            "ready": _research_is_ready(checks),
            "checks": checks,
        }
    return response


@app.get("/readyz")
async def readiness_check():
    """Report application readiness without promoting unavailable research hooks."""
    if settings.APP_MODE != "research":
        return {"status": "ready", "mode": "legacy"}

    checks = await _research_readiness_payload(app)
    ready = _research_is_ready(checks)
    return JSONResponse(
        status_code=200 if ready else 503,
        content={
            "status": "ready" if ready else "not_ready",
            "mode": "research",
            "checks": checks,
        },
    )


# 自定义 Swagger UI（使用 unpkg.com CDN，因为 jsdelivr.net 无法访问）
@app.get("/docs", include_in_schema=False)
@app.head("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    """自定义 Swagger UI，使用 unpkg.com CDN"""
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Swagger UI",
        oauth2_redirect_url="/docs/oauth2-redirect",
        swagger_js_url="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css",
        swagger_favicon_url="https://fastapi.tiangolo.com/img/favicon.png",
    )


# Swagger UI OAuth2 重定向
@app.get("/docs/oauth2-redirect", include_in_schema=False)
async def swagger_ui_redirect():
    """Swagger UI OAuth2 重定向"""
    return get_swagger_ui_oauth2_redirect_html()


# 自定义 ReDoc（使用 unpkg.com CDN）
@app.get("/redoc", include_in_schema=False)
@app.head("/redoc", include_in_schema=False)
async def redoc_html():
    """自定义 ReDoc，使用 unpkg.com CDN"""
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=app.title + " - ReDoc",
        redoc_js_url="https://unpkg.com/redoc@2/bundles/redoc.standalone.js",
        redoc_favicon_url="https://fastapi.tiangolo.com/img/favicon.png",
    )


# Chrome DevTools 配置文件（避免 404 日志）
@app.get("/.well-known/appspecific/com.chrome.devtools.json")
async def chrome_devtools_config():
    """Chrome DevTools 配置文件"""
    return {}


# 注册 API 路由
app.include_router(api_router, prefix=settings.API_V1_PREFIX)

if settings.APP_MODE == "research" and settings.RESEARCH_ENABLED:
    if research_components is not None and research_components.router is not None:
        app.include_router(research_components.router, prefix=settings.API_V1_PREFIX)
    if research_components is not None and research_components.mcp_app is not None:
        app.mount(f"{settings.API_V1_PREFIX}/mcp", research_components.mcp_app)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
