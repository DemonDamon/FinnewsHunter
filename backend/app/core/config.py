"""
FinnewsHunter 核心配置模块
使用 Pydantic Settings 管理环境变量和配置
"""
from typing import Optional, List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置类"""
    
    # 应用基础配置
    APP_NAME: str = "FinnewsHunter"
    APP_VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = Field(default=True)
    
    # 服务器配置
    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000)
    
    # CORS 配置
    BACKEND_CORS_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"]
    )
    
    # PostgreSQL 数据库配置
    POSTGRES_USER: str = Field(default="finnews")
    POSTGRES_PASSWORD: str = Field(default="finnews_dev_password")
    POSTGRES_HOST: str = Field(default="localhost")
    POSTGRES_PORT: int = Field(default=5432)
    POSTGRES_DB: str = Field(default="finnews_db")
    
    @property
    def DATABASE_URL(self) -> str:
        """异步数据库连接 URL"""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )
    
    @property
    def SYNC_DATABASE_URL(self) -> str:
        """同步数据库连接 URL（用于初始化）"""
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )
    
    # Redis 配置
    REDIS_HOST: str = Field(default="localhost")
    REDIS_PORT: int = Field(default=6379)
    REDIS_DB: int = Field(default=0)
    REDIS_PASSWORD: Optional[str] = Field(default=None)
    
    @property
    def REDIS_URL(self) -> str:
        """Redis 连接 URL"""
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
    
    # Milvus 配置
    MILVUS_HOST: str = Field(default="localhost")
    MILVUS_PORT: int = Field(default=19530)
    MILVUS_COLLECTION_NAME: str = Field(default="finnews_embeddings")
    MILVUS_DIM: int = Field(default=1536)  # OpenAI embedding dimension
    
    # Neo4j 知识图谱配置
    NEO4J_URI: str = Field(default="bolt://localhost:7687", description="Neo4j 连接URI")
    NEO4J_USER: str = Field(default="neo4j", description="Neo4j 用户名")
    NEO4J_PASSWORD: str = Field(default="finnews_neo4j_password", description="Neo4j 密码")
    
    # LLM 配置
    LLM_PROVIDER: str = Field(default="bailian")  # 默认提供商
    LLM_MODEL: str = Field(default="qwen-plus")
    LLM_TEMPERATURE: float = Field(default=0.7)
    LLM_MAX_TOKENS: int = Field(default=2000)
    LLM_TIMEOUT: int = Field(default=180)  # LLM 调用超时时间（秒），百炼建议180秒
    
    # 各厂商 API Key 配置
    DASHSCOPE_API_KEY: Optional[str] = Field(default=None, description="阿里云百炼 API Key")
    DASHSCOPE_BASE_URL: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        description="阿里云百炼 Base URL"
    )
    BAILIAN_API_KEY: Optional[str] = Field(default=None, description="百炼 API Key（与DASHSCOPE相同）")
    OPENAI_API_KEY: Optional[str] = Field(default=None, description="OpenAI API Key")
    DEEPSEEK_API_KEY: Optional[str] = Field(default=None, description="DeepSeek API Key")
    MOONSHOT_API_KEY: Optional[str] = Field(default=None, description="Moonshot (Kimi) API Key")
    ZHIPU_API_KEY: Optional[str] = Field(default=None, description="智谱 API Key")
    ANTHROPIC_API_KEY: Optional[str] = Field(default=None, description="Anthropic API Key")
    
    # 各厂商可用模型列表（逗号分隔）
    BAILIAN_MODELS: str = Field(
        default="qwen-plus,qwen-max,qwen-turbo,qwen-long",
        description="百炼可用模型（逗号分隔）"
    )
    OPENAI_MODELS: str = Field(
        default="gpt-4,gpt-4-turbo,gpt-3.5-turbo",
        description="OpenAI可用模型（逗号分隔）"
    )
    DEEPSEEK_MODELS: str = Field(
        default="deepseek-chat",
        description="DeepSeek可用模型（逗号分隔）"
    )
    MOONSHOT_MODELS: str = Field(
        default="moonshot-v1-8k,moonshot-v1-32k,moonshot-v1-128k",
        description="Moonshot可用模型（逗号分隔）"
    )
    ZHIPU_MODELS: str = Field(
        default="glm-4,glm-4-plus,glm-4-air,glm-3-turbo",
        description="智谱可用模型（逗号分隔）"
    )
    
    # Base URL 配置（用于第三方 API 转发）
    OPENAI_BASE_URL: Optional[str] = Field(default=None, description="OpenAI Base URL")
    DEEPSEEK_BASE_URL: Optional[str] = Field(default="https://api.deepseek.com/v1", description="DeepSeek Base URL")
    MOONSHOT_BASE_URL: Optional[str] = Field(default="https://api.moonshot.cn/v1", description="Moonshot Base URL")
    ZHIPU_BASE_URL: Optional[str] = Field(default="https://open.bigmodel.cn/api/paas/v4", description="智谱 Base URL")
    ANTHROPIC_BASE_URL: Optional[str] = Field(default=None, description="Anthropic Base URL")
    QWEN_BASE_URL: Optional[str] = Field(default=None, description="Qwen Base URL (deprecated)")
    BAILIAN_ACCESS_KEY_ID: Optional[str] = Field(default=None, description="百炼 Access Key ID")
    BAILIAN_ACCESS_KEY_SECRET: Optional[str] = Field(default=None, description="百炼 Access Key Secret")
    BAILIAN_AGENT_CODE: Optional[str] = Field(default=None, description="百炼 Agent Code")
    BAILIAN_REGION_ID: str = Field(default="cn-beijing", description="百炼 Region ID")
    
    # BochaAI 搜索 API 配置
    BOCHAAI_API_KEY: Optional[str] = Field(default=None, description="BochaAI Web Search API Key")
    BOCHAAI_ENDPOINT: str = Field(default="https://api.bochaai.com/v1/web-search", description="BochaAI API Endpoint")
    
    # Embedding 配置
    EMBEDDING_PROVIDER: str = Field(default="openai")  # openai, huggingface
    EMBEDDING_MODEL: str = Field(default="text-embedding-ada-002")
    EMBEDDING_BATCH_SIZE: int = Field(default=100)
    EMBEDDING_BASE_URL: Optional[str] = Field(default=None)  # 自定义 Embedding API 端点
    EMBEDDING_TIMEOUT: int = Field(default=30, description="Embedding API 超时时间（秒），建议设置为20-30秒")
    EMBEDDING_MAX_RETRIES: int = Field(default=2, description="Embedding API 最大重试次数，建议设置为1-2次以避免等待太久")
    
    # 爬虫配置
    CRAWLER_USER_AGENT: str = Field(
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    )
    CRAWLER_TIMEOUT: int = Field(default=30)
    CRAWLER_MAX_RETRIES: int = Field(default=3)
    CRAWLER_DELAY: float = Field(default=1.0)  # 请求间隔（秒）
    
    # Phase 2: 实时爬取与缓存配置（多源支持）
    CACHE_TTL: int = Field(default=1800, description="缓存过期时间（秒），默认30分钟")
    CRAWL_INTERVAL_SINA: int = Field(default=60, description="新浪财经爬取间隔（秒），默认60秒")
    CRAWL_INTERVAL_TENCENT: int = Field(default=60, description="腾讯财经爬取间隔（秒），默认60秒")
    CRAWL_INTERVAL_JWVIEW: int = Field(default=60, description="中新经纬爬取间隔（秒），默认60秒")
    CRAWL_INTERVAL_EEO: int = Field(default=60, description="经济观察网爬取间隔（秒），默认60秒")
    CRAWL_INTERVAL_CAIJING: int = Field(default=60, description="财经网爬取间隔（秒），默认60秒")
    CRAWL_INTERVAL_JINGJI21: int = Field(default=60, description="21经济网爬取间隔（秒），默认60秒")
    CRAWL_INTERVAL_JRJ: int = Field(default=600, description="金融界爬取间隔（秒），默认10分钟")
    NEWS_RETENTION_HOURS: int = Field(default=72000, description="新闻保留时间（小时），临时设置为72000小时（约8年）以包含所有爬取的新闻")
    FRONTEND_REFETCH_INTERVAL: int = Field(default=180, description="前端自动刷新间隔（秒），默认3分钟")
    
    # 日志配置
    LOG_LEVEL: str = Field(default="INFO")
    LOG_FILE: Optional[str] = Field(default="logs/finnews.log")
    
    # 安全配置
    SECRET_KEY: str = Field(default="your-secret-key-here-change-in-production")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60 * 24 * 7)  # 7 days
    
    # 业务配置
    MAX_NEWS_PER_REQUEST: int = Field(default=50)
    NEWS_CACHE_TTL: int = Field(default=3600)  # 1 hour
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        env_ignore_empty=True,
    )


# 全局配置实例
settings = Settings()


# 便捷访问函数
def get_settings() -> Settings:
    """获取配置实例（用于依赖注入）"""
    return settings

