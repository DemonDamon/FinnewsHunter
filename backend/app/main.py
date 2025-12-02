"""
FinnewsHunter 主应用入口
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .core.config import settings
from .core.database import init_database
from .api.v1 import api_router

# 配置日志
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    logger.info("=== FinnewsHunter Starting ===")
    logger.info(f"Environment: {'Development' if settings.DEBUG else 'Production'}")
    logger.info(f"LLM Provider: {settings.LLM_PROVIDER}/{settings.LLM_MODEL}")
    
    # 这里可以添加初始化逻辑，如连接数据库、初始化服务等
    # 注意：数据库表的创建应该通过独立脚本完成，不应在启动时自动执行
    
    yield
    
    # 关闭时执行
    logger.info("=== FinnewsHunter Shutting Down ===")


# 创建 FastAPI 应用
app = FastAPI(
    title=settings.APP_NAME,
    description="Financial News Analysis Platform powered by AgenticX",
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

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


# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
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
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


# 注册 API 路由
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
