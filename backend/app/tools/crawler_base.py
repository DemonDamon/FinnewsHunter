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
    raw_html: Optional[str] = None  # 原始 HTML 内容
    
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
            "raw_html": self.raw_html,
        }


class BaseCrawler(BaseTool):
    """
    爬虫基类
    继承自 AgenticX BaseTool
    """
    
    # 股票相关URL关键词
    STOCK_URL_KEYWORDS = [
        '/stock/', '/gupiao/', '/securities/', '/zhengquan/', 
        '/a-shares/', '/ashares/', '/equity/', '/shares/',
        '/market/', '/listed/', '/ipo/'
    ]
    
    # 股票相关标题关键词
    STOCK_TITLE_KEYWORDS = [
        '股票', 'A股', 'a股', '上市', '个股', '涨停', '跌停', 
        'IPO', 'ipo', '新股', '配股', '增发', '重组', '并购',
        '股东', '董事', '证券', '港股', '科创板', '创业板',
        '主板', '中小板', '北交所', '沪市', '深市', '股价',
        '股份', '停牌', '复牌', '退市', '借壳'
    ]
    
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
    
    def _extract_article_content(self, soup: BeautifulSoup, selectors: List[dict] = None) -> str:
        """
        通用智能内容提取方法
        
        Args:
            soup: BeautifulSoup对象
            selectors: 可选的自定义选择器列表
            
        Returns:
            提取的正文内容
        """
        import re
        
        # 默认选择器（按优先级排序）
        default_selectors = [
            # 文章主体选择器
            {'class': re.compile(r'article[-_]?(body|content|text|main)', re.I)},
            {'class': re.compile(r'content[-_]?(article|body|text|main)', re.I)},
            {'class': re.compile(r'main[-_]?(content|body|text|article)', re.I)},
            {'class': re.compile(r'^(article|content|body|text|post)$', re.I)},
            {'itemprop': 'articleBody'},
            {'id': re.compile(r'(article|content|body|text)[-_]?(content|body|text)?', re.I)},
            # 通用选择器
            {'class': 'g-article-content'},
            {'class': 'article-content'},
            {'class': 'news-content'},
            {'id': 'contentText'},
        ]
        
        all_selectors = (selectors or []) + default_selectors
        
        for selector in all_selectors:
            content_div = soup.find(['div', 'article', 'section', 'main'], selector)
            if content_div:
                # 移除无关元素
                for tag in content_div.find_all(['script', 'style', 'iframe', 'ins', 'noscript', 'nav', 'footer', 'header']):
                    tag.decompose()
                for ad in content_div.find_all(class_=re.compile(r'(ad|advertisement|banner|recommend|related|share|comment)', re.I)):
                    ad.decompose()
                
                # 提取所有段落（不限制数量）
                paragraphs = content_div.find_all('p')
                if paragraphs:
                    content = '\n'.join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])
                    if content and len(content) > 50:
                        return self._clean_text(content)
                
                # 如果没有 p 标签，直接取文本
                text = content_div.get_text(separator='\n', strip=True)
                if text and len(text) > 50:
                    return self._clean_text(text)
        
        # 后备方案：取所有符合条件的段落（不限制数量）
        paragraphs = soup.find_all('p')
        if paragraphs:
            valid_paragraphs = [
                p.get_text(strip=True) for p in paragraphs 
                if p.get_text(strip=True) and len(p.get_text(strip=True)) > 15
                and not any(kw in p.get_text(strip=True).lower() for kw in ['copyright', '版权', '广告', 'advertisement'])
            ]
            content = '\n'.join(valid_paragraphs)
            if content:
                return self._clean_text(content)
        
        return ""
    
    def _is_stock_related_by_url(self, url: str) -> bool:
        """
        根据URL路径判断是否为股票相关新闻
        
        Args:
            url: 新闻URL
            
        Returns:
            是否为股票相关
        """
        url_lower = url.lower()
        return any(keyword in url_lower for keyword in self.STOCK_URL_KEYWORDS)
    
    def _is_stock_related_by_title(self, title: str) -> bool:
        """
        根据标题关键词判断是否为股票相关新闻
        
        Args:
            title: 新闻标题
            
        Returns:
            是否为股票相关
        """
        return any(keyword in title for keyword in self.STOCK_TITLE_KEYWORDS)
    
    def _filter_stock_news(self, news_list: List[NewsItem]) -> List[NewsItem]:
        """
        筛选股票相关新闻
        组合URL路径和标题关键词两种策略
        
        Args:
            news_list: 原始新闻列表
            
        Returns:
            股票相关新闻列表
        """
        filtered_news = []
        for news in news_list:
            # URL匹配 或 标题匹配
            if self._is_stock_related_by_url(news.url) or self._is_stock_related_by_title(news.title):
                filtered_news.append(news)
                logger.debug(f"Stock news matched: {news.title[:50]}...")
            else:
                logger.debug(f"Filtered out: {news.title[:50]}...")
        
        logger.info(f"Stock filter: {len(news_list)} -> {len(filtered_news)} items")
        return filtered_news
    
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

