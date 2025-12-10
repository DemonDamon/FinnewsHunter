"""
LLM 配置 API 路由
返回可用的 LLM 厂商和模型列表
"""
import logging
from typing import List, Dict, Optional
from fastapi import APIRouter
from pydantic import BaseModel, Field

from ...core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


class ModelInfo(BaseModel):
    """模型信息"""
    value: str = Field(..., description="模型标识")
    label: str = Field(..., description="模型显示名称")
    description: str = Field(default="", description="模型描述")


class ProviderInfo(BaseModel):
    """厂商信息"""
    value: str = Field(..., description="厂商标识")
    label: str = Field(..., description="厂商显示名称")
    icon: str = Field(..., description="厂商图标")
    models: List[ModelInfo] = Field(..., description="可用模型列表")
    has_api_key: bool = Field(..., description="是否已配置API Key")


class LLMConfigResponse(BaseModel):
    """LLM 配置响应"""
    default_provider: str = Field(..., description="默认厂商")
    default_model: str = Field(..., description="默认模型")
    providers: List[ProviderInfo] = Field(..., description="可用厂商列表")


def parse_models(models_str: str, provider_label: str) -> List[ModelInfo]:
    """
    解析逗号分隔的模型字符串
    
    Args:
        models_str: 逗号分隔的模型字符串
        provider_label: 厂商显示名称
        
    Returns:
        模型信息列表
    """
    if not models_str:
        return []
    
    models = []
    for model in models_str.split(','):
        model = model.strip()
        if model:
            models.append(ModelInfo(
                value=model,
                label=model,
                description=f"{provider_label} 模型"
            ))
    return models


@router.get("/config", response_model=LLMConfigResponse)
async def get_llm_config():
    """
    获取 LLM 配置信息
    
    返回所有可用的厂商和模型列表，以及是否已配置 API Key
    """
    try:
        providers = []
        
        # 1. 百炼
        if settings.BAILIAN_MODELS:
            providers.append(ProviderInfo(
                value="bailian",
                label="百炼（阿里云）",
                icon="📦",
                models=parse_models(settings.BAILIAN_MODELS, "百炼"),
                has_api_key=bool(settings.DASHSCOPE_API_KEY or settings.BAILIAN_API_KEY)
            ))
        
        # 2. OpenAI
        if settings.OPENAI_MODELS:
            providers.append(ProviderInfo(
                value="openai",
                label="OpenAI",
                icon="🤖",
                models=parse_models(settings.OPENAI_MODELS, "OpenAI"),
                has_api_key=bool(settings.OPENAI_API_KEY)
            ))
        
        # 3. DeepSeek
        if settings.DEEPSEEK_MODELS:
            providers.append(ProviderInfo(
                value="deepseek",
                label="DeepSeek",
                icon="🧠",
                models=parse_models(settings.DEEPSEEK_MODELS, "DeepSeek"),
                has_api_key=bool(settings.DEEPSEEK_API_KEY)
            ))
        
        # 4. Kimi
        if settings.MOONSHOT_MODELS:
            providers.append(ProviderInfo(
                value="kimi",
                label="Kimi (Moonshot)",
                icon="🌙",
                models=parse_models(settings.MOONSHOT_MODELS, "Kimi"),
                has_api_key=bool(settings.MOONSHOT_API_KEY)
            ))
        
        # 5. 智谱
        if settings.ZHIPU_MODELS:
            providers.append(ProviderInfo(
                value="zhipu",
                label="智谱",
                icon="🔮",
                models=parse_models(settings.ZHIPU_MODELS, "智谱"),
                has_api_key=bool(settings.ZHIPU_API_KEY)
            ))
        
        return LLMConfigResponse(
            default_provider=settings.LLM_PROVIDER,
            default_model=settings.LLM_MODEL,
            providers=providers
        )
    
    except Exception as e:
        logger.error(f"Failed to get LLM config: {e}", exc_info=True)
        # 返回默认配置
        return LLMConfigResponse(
            default_provider="bailian",
            default_model="qwen-plus",
            providers=[]
        )

