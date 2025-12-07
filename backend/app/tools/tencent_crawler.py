"""
腾讯财经爬虫工具
目标URL: https://news.qq.com/ch/finance/
"""
import re
import logging
from typing import List, Optional
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import json

from .crawler_base import BaseCrawler, NewsItem

logger = logging.getLogger(__name__)


class TencentCrawlerTool(BaseCrawler):
    """
    腾讯财经新闻爬虫
    爬取腾讯财经频道最新新闻
    """
    
    BASE_URL = "https://news.qq.com/ch/finance/"
    # 腾讯新闻API（如果页面动态加载，可能需要调用API）
    API_URL = "https://pacaio.match.qq.com/irs/rcd"
    SOURCE_NAME = "tencent"
    
    def __init__(self):
        super().__init__(
            name="tencent_finance_crawler",
            description="Crawl financial news from Tencent Finance (news.qq.com)"
        )
    
    def crawl(self, start_page: int = 1, end_page: int = 1) -> List[NewsItem]:
        """
        爬取腾讯财经新闻
        
        Args:
            start_page: 起始页码
            end_page: 结束页码
            
        Returns:
            新闻列表
        """
        news_list = []
        
        try:
            # 腾讯财经页面只爬取首页
            page_news = self._crawl_page(1)
            news_list.extend(page_news)
            logger.info(f"Crawled Tencent Finance, got {len(page_news)} news items")
        except Exception as e:
            logger.error(f"Error crawling Tencent Finance: {e}")
        
        # 应用股票筛选
        filtered_news = self._filter_stock_news(news_list)
        return filtered_news
    
    def _crawl_page(self, page: int) -> List[NewsItem]:
        """
        爬取单页新闻
        
        Args:
            page: 页码
            
        Returns:
            新闻列表
        """
        news_items = []
        
        try:
            response = self._fetch_page(self.BASE_URL)
            soup = self._parse_html(response.text)
            
            # 提取新闻列表
            # 腾讯的新闻可能在各种容器中，尝试提取所有新闻链接
            news_links = self._extract_news_links(soup)
            
            logger.info(f"Found {len(news_links)} potential news links")
            
            # 限制爬取数量，避免过多请求
            max_news = 20
            for i, link_info in enumerate(news_links[:max_news]):
                try:
                    news_item = self._extract_news_item(link_info)
                    if news_item:
                        news_items.append(news_item)
                except Exception as e:
                    logger.warning(f"Failed to extract news item {i+1}: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Error crawling page {page}: {e}")
        
        return news_items
    
    def _extract_news_links(self, soup: BeautifulSoup) -> List[dict]:
        """
        从页面中提取新闻链接
        
        Args:
            soup: BeautifulSoup对象
            
        Returns:
            新闻链接信息列表
        """
        news_links = []
        
        # 查找所有包含 /rain/a/ 或 /omn/article/ 的链接（腾讯新闻的URL模式）
        all_links = soup.find_all('a', href=True)
        
        for link in all_links:
            href = link.get('href', '')
            
            # 腾讯新闻URL模式
            if '/rain/a/' in href or '/omn/' in href:
                # 确保是完整URL
                if not href.startswith('http'):
                    href = 'https:' + href if href.startswith('//') else 'https://news.qq.com' + href
                
                # 提取标题（可能在链接文本或内部元素中）
                title = link.get_text(strip=True)
                
                if title and href not in [n['url'] for n in news_links]:
                    news_links.append({
                        'url': href,
                        'title': title
                    })
        
        return news_links
    
    def _extract_news_item(self, link_info: dict) -> Optional[NewsItem]:
        """
        提取单条新闻详情
        
        Args:
            link_info: 新闻链接信息
            
        Returns:
            NewsItem或None
        """
        url = link_info['url']
        title = link_info['title']
        
        try:
            # 获取新闻详情页
            response = self._fetch_page(url)
            soup = self._parse_html(response.text)
            
            # 提取正文内容
            content = self._extract_content(soup)
            if not content:
                logger.debug(f"No content found for: {title}")
                return None
            
            # 提取发布时间
            publish_time = self._extract_publish_time(soup)
            
            # 提取作者
            author = self._extract_author(soup)
            
            return NewsItem(
                title=title,
                content=content,
                url=url,
                source=self.SOURCE_NAME,
                publish_time=publish_time,
                author=author
            )
            
        except Exception as e:
            logger.warning(f"Failed to extract news from {url}: {e}")
            return None
    
    def _extract_content(self, soup: BeautifulSoup) -> str:
        """
        提取新闻正文
        
        Args:
            soup: BeautifulSoup对象
            
        Returns:
            新闻正文
        """
        # 尝试多种选择器
        content_selectors = [
            {'class': 'content-article'},
            {'class': 'LEFT'},
            {'id': 'Cnt-Main-Article-QQ'},
            {'class': 'article'},
        ]
        
        for selector in content_selectors:
            content_div = soup.find('div', selector)
            if content_div:
                # 获取所有段落
                paragraphs = content_div.find_all('p')
                if paragraphs:
                    content = '\n'.join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])
                    if content:
                        return self._clean_text(content)
        
        # 如果没找到，尝试提取所有段落
        paragraphs = soup.find_all('p')
        if paragraphs:
            content = '\n'.join([p.get_text(strip=True) for p in paragraphs[:10] if p.get_text(strip=True)])
            return self._clean_text(content) if content else ""
        
        return ""
    
    def _extract_publish_time(self, soup: BeautifulSoup) -> Optional[datetime]:
        """
        提取发布时间
        
        Args:
            soup: BeautifulSoup对象
            
        Returns:
            发布时间
        """
        try:
            # 尝试多种时间选择器
            time_selectors = [
                {'class': 'a-time'},
                {'class': 'article-time'},
                {'class': 'time'},
            ]
            
            for selector in time_selectors:
                time_elem = soup.find('span', selector)
                if time_elem:
                    time_str = time_elem.get_text(strip=True)
                    return self._parse_time_string(time_str)
            
            # 尝试从meta标签获取
            meta_time = soup.find('meta', {'property': 'article:published_time'})
            if meta_time and meta_time.get('content'):
                return datetime.fromisoformat(meta_time['content'].replace('Z', '+00:00'))
            
        except Exception as e:
            logger.debug(f"Failed to parse publish time: {e}")
        
        # 默认返回当前时间
        return datetime.now()
    
    def _parse_time_string(self, time_str: str) -> datetime:
        """
        解析时间字符串（如"1小时前"、"昨天"、"2024-12-06 10:00"）
        
        Args:
            time_str: 时间字符串
            
        Returns:
            datetime对象
        """
        now = datetime.now()
        
        # 处理相对时间
        if '分钟前' in time_str:
            minutes = int(re.search(r'(\d+)', time_str).group(1))
            return now - timedelta(minutes=minutes)
        elif '小时前' in time_str:
            hours = int(re.search(r'(\d+)', time_str).group(1))
            return now - timedelta(hours=hours)
        elif '昨天' in time_str:
            return now - timedelta(days=1)
        elif '前天' in time_str:
            return now - timedelta(days=2)
        
        # 尝试解析绝对时间
        try:
            # 尝试多种格式
            formats = [
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d %H:%M',
                '%Y-%m-%d',
                '%Y年%m月%d日 %H:%M',
                '%Y年%m月%d日',
            ]
            for fmt in formats:
                try:
                    return datetime.strptime(time_str, fmt)
                except ValueError:
                    continue
        except Exception:
            pass
        
        # 默认返回当前时间
        return now
    
    def _extract_author(self, soup: BeautifulSoup) -> Optional[str]:
        """
        提取作者
        
        Args:
            soup: BeautifulSoup对象
            
        Returns:
            作者名称
        """
        try:
            # 尝试多种作者选择器
            author_selectors = [
                {'class': 'author'},
                {'class': 'article-author'},
                {'class': 'source'},
            ]
            
            for selector in author_selectors:
                author_elem = soup.find('span', selector) or soup.find('a', selector)
                if author_elem:
                    author = author_elem.get_text(strip=True)
                    if author:
                        return author
        except Exception as e:
            logger.debug(f"Failed to extract author: {e}")
        
        return None

