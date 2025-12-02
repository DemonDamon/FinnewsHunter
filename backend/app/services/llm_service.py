"""
LLM 服务封装
"""
import logging
from typing import Optional, Dict, Any, Union
from agenticx import LiteLLMProvider, LLMResponse
from agenticx.llms.bailian_provider import BailianProvider

from ..core.config import settings

logger = logging.getLogger(__name__)


class LLMService:
    """
    LLM 服务封装类
    提供统一的 LLM 调用接口
    """
    
    def __init__(
        self,
        provider: str = None,
        model: str = None,
        temperature: float = None,
        max_tokens: int = None,
        api_key: str = None,
        base_url: str = None,
    ):
        """
        初始化 LLM 服务
        
        Args:
            provider: 提供商（openai, anthropic, ollama）
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大token数
            api_key: API密钥
            base_url: 自定义 API 端点（用于第三方转发）
        """
        self.provider_name = provider or settings.LLM_PROVIDER
        self.model = model or settings.LLM_MODEL
        self.temperature = temperature or settings.LLM_TEMPERATURE
        self.max_tokens = max_tokens or settings.LLM_MAX_TOKENS
        
        # 设置API密钥
        if api_key:
            self.api_key = api_key
        elif self.provider_name == "openai":
            self.api_key = settings.OPENAI_API_KEY
        elif self.provider_name == "anthropic":
            self.api_key = settings.ANTHROPIC_API_KEY
        else:
            self.api_key = None
        
        # 设置 Base URL（用于第三方 API 转发）
        if base_url:
            self.base_url = base_url
        elif self.provider_name == "openai":
            self.base_url = settings.OPENAI_BASE_URL
        elif self.provider_name == "anthropic":
            self.base_url = settings.ANTHROPIC_BASE_URL
        else:
            self.base_url = None
        
        # 创建 LLM 提供者
        self.llm_provider = self._create_provider()
    
    def _create_provider(self) -> Union[LiteLLMProvider, BailianProvider]:
        """创建 LLM 提供者"""
        try:
            # 检测是否使用 Dashscope/Bailian API
            is_dashscope = (
                self.base_url and "dashscope" in self.base_url.lower()
            ) or (
                self.model and self.model.startswith("qwen") and self.base_url
            )
            
            if is_dashscope:
                # 使用 BailianProvider（专门为百炼 API 设计）
                if not self.api_key:
                    raise ValueError("API key is required for Bailian provider")
                
                provider = BailianProvider(
                    model=self.model,
                    api_key=self.api_key,
                    base_url=self.base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1",
                    temperature=self.temperature,
                    timeout=float(settings.LLM_TIMEOUT),  # 从配置读取超时时间
                    max_retries=2   # 减少重试次数，避免总耗时过长
                )
                logger.info(f"Initialized BailianProvider: {self.model}")
                return provider
            else:
                # 使用 LiteLLMProvider（通用 provider）
                provider_kwargs = {
                    "model": self.model,
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens,
                    "api_key": self.api_key,
                }
                
                # 如果设置了自定义 base_url，添加到配置中
                if self.base_url:
                    provider_kwargs["base_url"] = self.base_url
                    logger.info(f"Using custom base URL: {self.base_url}")
                
                provider = LiteLLMProvider(**provider_kwargs)
                logger.info(f"Initialized LiteLLMProvider: {self.provider_name}/{self.model}")
                return provider
        except Exception as e:
            logger.error(f"Failed to initialize LLM provider: {e}")
            raise
    
    def generate(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        生成文本
        
        Args:
            prompt: 用户提示
            system_message: 系统消息
            **kwargs: 额外参数
            
        Returns:
            生成的文本
        """
        try:
            messages = []
            
            if system_message:
                messages.append({"role": "system", "content": system_message})
            
            messages.append({"role": "user", "content": prompt})
            
            # 确保传递 max_tokens（如果 kwargs 中没有）
            if "max_tokens" not in kwargs:
                kwargs["max_tokens"] = self.max_tokens
            
            response: LLMResponse = self.llm_provider.generate(
                messages=messages,
                **kwargs
            )
            
            return response.content
        
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            raise
    
    def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """
        分析文本情感
        
        Args:
            text: 待分析文本
            
        Returns:
            情感分析结果
        """
        system_message = """你是一个专业的金融新闻情感分析专家。
请分析给定新闻的情感倾向，判断其对相关股票的影响是利好、利空还是中性。

输出格式（JSON）：
{
    "sentiment": "positive/negative/neutral",
    "score": 0.0-1.0（情感强度）,
    "confidence": 0.0-1.0（置信度）,
    "reasoning": "分析理由"
}
"""
        
        prompt = f"""请分析以下新闻的情感倾向：

{text[:1000]}

请严格按照JSON格式输出结果。"""
        
        try:
            response_text = self.generate(prompt, system_message)
            
            # 尝试解析JSON
            import json
            import re
            
            # 提取JSON部分
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                return result
            else:
                # 如果无法解析，返回默认值
                return {
                    "sentiment": "neutral",
                    "score": 0.5,
                    "confidence": 0.5,
                    "reasoning": response_text
                }
        
        except Exception as e:
            logger.error(f"Sentiment analysis failed: {e}")
            return {
                "sentiment": "neutral",
                "score": 0.5,
                "confidence": 0.0,
                "reasoning": f"分析失败: {str(e)}"
            }
    
    def summarize(self, text: str, max_length: int = 200) -> str:
        """
        文本摘要
        
        Args:
            text: 原始文本
            max_length: 摘要最大长度
            
        Returns:
            摘要文本
        """
        system_message = f"""你是一个专业的金融新闻摘要专家。
请将给定的新闻内容总结为不超过{max_length}字的简洁摘要，保留关键信息。"""
        
        prompt = f"""请总结以下新闻：

{text}

摘要："""
        
        try:
            summary = self.generate(prompt, system_message, max_tokens=max_length)
            return summary.strip()
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            return text[:max_length] + "..."


# 全局实例
_llm_service: Optional[LLMService] = None


def get_llm_provider() -> Union[LiteLLMProvider, BailianProvider]:
    """
    获取 LLM 提供者实例（用于 AgenticX Agent）
    
    Returns:
        LiteLLMProvider 或 BailianProvider 实例
    """
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service.llm_provider


def get_llm_service() -> LLMService:
    """
    获取 LLM 服务实例
    
    Returns:
        LLMService 实例
    """
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service

