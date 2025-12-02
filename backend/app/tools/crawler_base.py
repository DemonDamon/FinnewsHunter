"""
爬虫基类
符合 AgenticX BaseTool 协议
"""
import time
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from agenticx import BaseTool
from agenticx.core import ToolMetadata, ToolCategory
from ..core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class NewsItem:
    """新闻数据项"""
    title: str
    content: str
    url: str
    source: str
    publish_time: Optional[datetime] = None
    author: Optional[str] = None
    keywords: Optional[List[str]] = None
    stock_codes: Optional[List[str]] = None
    summary: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "title": self.title,
            "content": self.content,
            "url": self.url,
            "source": self.source,
            "publish_time": self.publish_time.isoformat() if self.publish_time else None,
            "author": self.author,
            "keywords": self.keywords,
            "stock_codes": self.stock_codes,
            "summary": self.summary,
        }


class BaseCrawler(BaseTool):
    """
    爬虫基类
    继承自 AgenticX BaseTool
    """
    
    def __init__(self, name: str = "base_crawler", description: str = "Base crawler for financial news"):
        # 创建 ToolMetadata
        metadata = ToolMetadata(
            name=name,
            description=description,
            category=ToolCategory.DATA_ACCESS,
            version="1.0.0"
        )
        super().__init__(metadata=metadata)
        
        # 爬虫特定配置
        self.user_agent = settings.CRAWLER_USER_AGENT
        self.timeout = settings.CRAWLER_TIMEOUT
        self.max_retries = settings.CRAWLER_MAX_RETRIES
        self.delay = settings.CRAWLER_DELAY
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': self.user_agent})
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def _fetch_page(self, url: str) -> requests.Response:
        """
        获取网页内容（带重试机制）
        
        Args:
            url: 目标URL
            
        Returns:
            响应对象
        """
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            time.sleep(self.delay)  # 请求间隔
            return response
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            raise
    
    def _parse_html(self, html: str) -> BeautifulSoup:
        """
        解析HTML
        
        Args:
            html: HTML字符串
            
        Returns:
            BeautifulSoup对象
        """
        return BeautifulSoup(html, 'lxml')
    
    def _extract_chinese_ratio(self, text: str) -> float:
        """
        计算中文字符比例
        
        Args:
            text: 文本
            
        Returns:
            中文字符比例（0-1）
        """
        import re
        pattern = re.compile(r'[\u4e00-\u9fa5]+')
        chinese_chars = pattern.findall(text)
        chinese_count = sum(len(chars) for chars in chinese_chars)
        total_count = len(text)
        return chinese_count / total_count if total_count > 0 else 0
    
    def _clean_text(self, text: str) -> str:
        """
        清理文本
        
        Args:
            text: 原始文本
            
        Returns:
            清理后的文本
        """
        import re
        # 移除HTML标签
        text = re.sub(r'<[^>]+>', '', text)
        # 移除特殊空格
        text = text.replace('\u3000', ' ')
        # 移除多余空格和换行
        text = ' '.join(text.split())
        return text.strip()
    
    def crawl(self, start_page: int = 1, end_page: int = 1) -> List[NewsItem]:
        """
        爬取新闻
        
        Args:
            start_page: 起始页
            end_page: 结束页
            
        Returns:
            新闻列表
        """
        raise NotImplementedError("Subclass must implement crawl method")
    
    def _setup_parameters(self):
        """设置工具参数（AgenticX 要求）"""
        pass  # 爬虫不需要特殊参数设置
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        """
        同步执行方法（AgenticX Tool 协议要求）
        
        Args:
            **kwargs: 参数字典
                - start_page: 起始页
                - end_page: 结束页
                
        Returns:
            执行结果
        """
        start_page = kwargs.get('start_page', 1)
        end_page = kwargs.get('end_page', 1)
        
        logger.info(f"Crawling from page {start_page} to {end_page}")
        news_list = self.crawl(start_page, end_page)
        
        return {
            "success": True,
            "count": len(news_list),
            "news_list": [news.to_dict() for news in news_list],
        }
    
    async def aexecute(self, **kwargs) -> Dict[str, Any]:
        """
        异步执行方法（AgenticX Tool 协议要求）
        当前实现为同步执行的包装
        
        Args:
            **kwargs: 参数字典
                
        Returns:
            执行结果
        """
        return self.execute(**kwargs)

