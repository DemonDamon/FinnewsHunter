"""
财经网爬虫工具
目标URL: https://www.caijing.com.cn/ (股市栏目)
"""
import re
import logging
from typing import List, Optional
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

from .crawler_base import BaseCrawler, NewsItem

logger = logging.getLogger(__name__)


class CaijingCrawlerTool(BaseCrawler):
    """
    财经网爬虫
    主要爬取股市相关新闻
    """
    
    BASE_URL = "https://finance.caijing.com.cn/"
    # 股市栏目URL
    STOCK_URL = "https://finance.caijing.com.cn/"
    SOURCE_NAME = "caijing"
    
    def __init__(self):
        super().__init__(
            name="caijing_crawler",
            description="Crawl financial news from Caijing (caijing.com.cn)"
        )
    
    def crawl(self, start_page: int = 1, end_page: int = 1) -> List[NewsItem]:
        """
        爬取财经网新闻
        
        Args:
            start_page: 起始页码
            end_page: 结束页码
            
        Returns:
            新闻列表
        """
        news_list = []
        
        try:
            page_news = self._crawl_page(1)
            news_list.extend(page_news)
            logger.info(f"Crawled Caijing, got {len(page_news)} news items")
        except Exception as e:
            logger.error(f"Error crawling Caijing: {e}")
        
        # 应用股票筛选
        filtered_news = self._filter_stock_news(news_list)
        return filtered_news
    
    def _crawl_page(self, page: int) -> List[NewsItem]:
        """爬取单页新闻"""
        news_items = []
        
        try:
            # 尝试爬取股市栏目或主页
            try:
                response = self._fetch_page(self.STOCK_URL)
            except:
                response = self._fetch_page(self.BASE_URL)
            
            soup = self._parse_html(response.text)
            
            # 提取新闻列表
            news_links = self._extract_news_links(soup)
            logger.info(f"Found {len(news_links)} potential news links")
            
            # 限制爬取数量
            max_news = 20
            for link_info in news_links[:max_news]:
                try:
                    news_item = self._extract_news_item(link_info)
                    if news_item:
                        news_items.append(news_item)
                except Exception as e:
                    logger.warning(f"Failed to extract news item: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Error crawling page: {e}")
        
        return news_items
    
    def _extract_news_links(self, soup: BeautifulSoup) -> List[dict]:
        """从页面中提取新闻链接"""
        news_links = []
        
        # 查找新闻链接
        all_links = soup.find_all('a', href=True)
        
        for link in all_links:
            href = link.get('href', '')
            title = link.get_text(strip=True)
            
            # 财经网新闻URL模式
            if ('/\d{4}/' in href or '/article/' in href or '.shtml' in href) and title:
                # 规范化 URL，优先 https，避免重复前缀
                if href.startswith('//'):
                    href = 'https:' + href
                elif href.startswith('/'):
                    href = 'https://www.caijing.com.cn' + href
                elif href.startswith('http://'):
                    href = href.replace('http://', 'https://', 1)
                elif not href.startswith('http'):
                    href = 'https://www.caijing.com.cn/' + href.lstrip('/')
                
                if href not in [n['url'] for n in news_links]:
                    news_links.append({'url': href, 'title': title})
        
        return news_links
    
    def _extract_news_item(self, link_info: dict) -> Optional[NewsItem]:
        """提取单条新闻详情"""
        url = link_info['url']
        title = link_info['title']
        
        try:
            response = self._fetch_page(url)
            raw_html = response.text  # 保存原始 HTML
            soup = self._parse_html(raw_html)
            
            # 提取正文
            content = self._extract_content(soup)
            if not content:
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
                author=author,
                raw_html=raw_html,  # 保存原始 HTML
            )
            
        except Exception as e:
            logger.warning(f"Failed to extract news from {url}: {e}")
            return None
    
    def _extract_content(self, soup: BeautifulSoup) -> str:
        """提取新闻正文"""
        content_selectors = [
            {'class': 'article-content'},
            {'class': 'main_txt'},
            {'class': 'content'},
            {'id': 'the_content'},
        ]
        
        for selector in content_selectors:
            content_div = soup.find('div', selector)
            if content_div:
                paragraphs = content_div.find_all('p')
                if paragraphs:
                    content = '\n'.join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])
                    if content:
                        return self._clean_text(content)
        
        # 后备方案：使用基类的智能提取方法
        return self._extract_article_content(soup)
        
        return ""
    
    def _extract_publish_time(self, soup: BeautifulSoup) -> Optional[datetime]:
        """提取发布时间"""
        try:
            time_elem = soup.find('span', {'class': re.compile(r'time|date')})
            if time_elem:
                time_str = time_elem.get_text(strip=True)
                return self._parse_time_string(time_str)
        except Exception as e:
            logger.debug(f"Failed to parse publish time: {e}")
        
        return datetime.now()
    
    def _parse_time_string(self, time_str: str) -> datetime:
        """解析时间字符串"""
        now = datetime.now()
        
        # 尝试解析绝对时间
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
        
        return now
    
    def _extract_author(self, soup: BeautifulSoup) -> Optional[str]:
        """提取作者"""
        try:
            author_elem = soup.find('span', {'class': re.compile(r'author|source')})
            if author_elem:
                return author_elem.get_text(strip=True)
        except Exception as e:
            logger.debug(f"Failed to extract author: {e}")
        
        return None

